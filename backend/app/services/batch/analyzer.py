import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.database import supabase
from app.services.batch.doc_service import find_relevant_docs

PARALLEL_WORKERS = 5           # 동시 Gemini API 호출 수 (10에서 축소 — Windows httpx 동시연결 폭주 시 WinError 10035 완화)
SUPABASE_PAGE_SIZE = 1000      # Supabase 페이지당 조회 건수
PROGRESS_INTERVAL = 50         # 진행률 업데이트 주기
AI_REQUEST_TIMEOUT_MS = 30000  # Gemini 호출 1건 타임아웃 (30초)
AI_MAX_RETRY = 3               # 호출 재시도 횟수
DB_MAX_RETRY = 3               # Supabase 호출 재시도 횟수 (일시적 네트워크 오류 대응)

# 호출 1건당 타임아웃 지정 — 먹통 응답이 워커 스레드를 무한 점유하는 것을 방지
client = genai.Client(
    api_key=settings.GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=AI_REQUEST_TIMEOUT_MS),
)

SYSTEM_PROMPT = """당신은 병무청 불건전정보 모니터링 전문 분석관입니다.
「병무청 불건전정보 가이드라인」에 따라 주어진 텍스트를 분석하고 반드시 JSON만 반환하세요.

[대상정보 정의]
- 병역면탈 조장정보: 병역법 제86조(도망·신체손상)·제87조제1항(대리수검)을 조장하는 정보(구체적 실행방법·연락수단 포함)
- 허위·조작정보: 내용의 전부/일부가 허위이거나 사실로 오인하도록 변형된 정보
- 불건전정보: 위에 해당하지 않으나 성실한 병역이행을 저해·왜곡하여 병무행정의 공정성·신뢰도를 훼손할 우려가 있는 정보

반환 형식:
{
  "false_score": 0~100 정수 (0=완전한 사실, 100=완전한 허위/조작),
  "false_level": "낮음" | "중간" | "높음",
  "category": 아래 [분류 구분] 중 하나,
  "action_type": "삭제대상" | "비대상" | "종합판단",
  "false_reason": 판단 이유 한 줄 (40자 이내),
  "intent_type": 아래 [의도 유형] 중 하나,
  "content_type": 아래 [내용 유형] 중 하나,
  "department_names": 아래 부서 목록 중 관련 있는 부서명을 관련도가 높은 순서로 최대 2개까지 배열로 (관련 부서가 없으면 [], 1개면 1개만)
}

[분류 구분 - category] (가이드라인 삭제기준)
- "편법·속임수·공정성 훼손": 규정을 회피한 편법 안내, 거짓·속임수 신청 조장, 성실 병역이행 저해·병무행정 신뢰도 훼손 → 원칙적 삭제대상
- "허위·조작": 내용 전부/일부가 허위(허위정보)이거나, 사실로 오인하도록 조작(조작정보, AI 생성 이미지·영상 포함)된 정보 → 원칙적 삭제대상
- "단순문의·불평": 고의성 없는 단순 문의, 병역에 대한 단순 불평·불만 → 비대상
- "정책비판": 병무정책 비판·패러디·풍자(허위 없음) → 원칙적 비대상, 악의성·허위가 크면 종합판단
- "정상정보": 사실에 근거한 언론·시사 보도, 학술·연구, 법률 상담, 단순 의견 등 삭제 제외 대상 → 비대상
- "해당없음": 병역·병무와 무관한 내용 → 비대상

[의도 유형 - intent_type] : "악의적 유포" | "단순 오해" | "풍자/비판" | "사실 보도" | "불명확"
[내용 유형 - content_type] : "사실관계 오류" | "과장/왜곡" | "출처 불명" | "맥락 누락" | "문제없음"
[거짓점수 기준] : 0~33 "낮음" / 34~66 "중간" / 67~100 "높음"

[판단 사례] (원문 요지 → category / action_type)
- 병무청이 장애인에게 3급 줘 현역 보냄, 전담의사는 공무원 아니라 무책임·역고소 → 허위·조작 / 삭제대상 (전담의사는 임기제 공무원, 역고소 등은 사실무근)
- 학점은행제로 사유를 만들어 입영을 최대 2년 연기하는 법 → 편법·속임수·공정성 훼손 / 삭제대상 (사유 없는 자의 편법 연기 조장)
- 꾀병가 꿀팁: 비대면 진료앱으로 처방전 받아 병가 신청 → 편법·속임수·공정성 훼손 / 삭제대상 (거짓·속임수 병가 조장)
- 정신과 6개월 다니면 장기대기 면제 쉬움, 3년만 버티면 됨 → 편법·속임수·공정성 훼손 / 삭제대상 (병무행정 공정성·신뢰도 저해)
- 제3국 임시영주권 취득 후 실제 거주 않고 국외여행허가로 병역연기 → 편법·속임수·공정성 훼손 / 삭제대상 (편법 국외여행허가 조장)
- 예비군·동원훈련 때 일부러 쓰러지는 연기를 해도 되냐 → 편법·속임수·공정성 훼손 / 삭제대상 (거짓·속임수로 훈련 회피 조장)
- 사회복무 복무기관 재지정 위해 일을 망쳐놓고 자살·사고 가능성을 어필하라 → 편법·속임수·공정성 훼손 / 삭제대상 (악의적 편법 조장)
- 사회복무요원이 이용자를 학대하는 AI 생성 사진을 사실처럼 지속 게시 → 허위·조작 / 삭제대상 (조작정보)
- 군대 가야 하는 이유가 뭐임 / 군대 가기 싫다 → 단순문의·불평 / 비대상 (단순 불평)
- 생계감면 되려면 어떤 조건이 맞아야 하나요? → 단순문의·불평 / 비대상 (고의성 없는 단순 문의)
- 병무행정 비판 목적의 명백한 패러디·풍자(허위 없음) → 정책비판 / 비대상
- 민원 부결에 앙심을 품고 근거 없이 병무청을 부패 집단이라 반복 비방 → 정책비판 / 종합판단 (악의적 비판, 의도·맥락 종합 필요)
- 병무청의 제도 변경을 사실에 근거해 전달하는 언론 기사 → 정상정보 / 비대상 (삭제 제외 대상인 언론보도)

[중요 규칙]
- 병역·병무 업무와 무관한 내용이면 category="해당없음", action_type="비대상", false_score=0, false_level="낮음", intent_type="불명확", content_type="문제없음"으로 반환하고 false_reason에 "병무청 무관 내용"이라고 명시하세요.
- 표현의 자유·건전한 정책비판·단순 불평은 비대상으로 판단하세요.
- 사실에 근거한 언론·시사 보도, 학술·연구, 법률 상담, 단순 의견 표현은 삭제 제외 대상(category="정상정보", action_type="비대상")입니다. 명백한 편법·허위가 없는 한 삭제대상으로 분류하지 마세요."""

# 가이드라인 삭제기준 → 조치유형 결정적 매핑 (정책비판만 AI 판단 존중)
CATEGORY_TO_ACTION = {
    "편법·속임수·공정성 훼손": "삭제대상",
    "허위·조작": "삭제대상",
    "단순문의·불평": "비대상",
    "정상정보": "비대상",
    "해당없음": "비대상",
}
VALID_CATEGORIES = set(CATEGORY_TO_ACTION) | {"정책비판"}
VALID_ACTIONS = {"삭제대상", "비대상", "종합판단"}


HANGUL_RE = re.compile(r"[가-힣]")


def prefilter(text: str) -> dict | None:
    """Gemini 호출 없이 확정 가능한 '비대상'을 로컬에서 판정. 판정 불가면 None.

    한글이 한 글자도 없는 내용(번호·날짜·기호·자모만 등)은 병역 관련 정보가 될 수 없어
    AI가 항상 '병무청 무관'으로 답한다. 이런 행은 API 호출을 낭비하므로 즉시 확정한다.
    한글이 있으면 짧더라도 AI에 보낸다("군대 빼는법 없나" 같은 짧은 조장정보 보호).
    """
    t = (text or "").strip()
    if t and HANGUL_RE.search(t):
        return None
    return {
        "false_score":      0,
        "false_level":      "낮음",
        "category":         "해당없음",
        "action_type":      "비대상",
        "false_reason":     "병무청 무관 내용(자동판정)",
        "intent_type":      "불명확",
        "content_type":     "문제없음",
        "department_names": [],
    }


def analyze_text(text: str, source_type: str, departments: list) -> tuple[dict, list]:
    """분석 단일 진입점 — 프리필터 통과 시에만 Gemini 호출.

    (결과, 키워드 매칭 후보) 반환. 평가 하네스도 이 함수를 써 운영과 동일 경로를 검증한다.
    """
    result = prefilter(text)
    if result is not None:
        return result, []
    route_hits = route_departments(text, departments)
    return _analyze_single(text, source_type, departments, route_hits), route_hits


def _retry_db(fn):
    """일시적 네트워크 오류(WinError 10035, HTTP/2 종료 등)에 대비한 Supabase 호출 재시도."""
    for attempt in range(DB_MAX_RETRY):
        try:
            return fn()
        except Exception:
            if attempt == DB_MAX_RETRY - 1:
                raise
            time.sleep(2 * (attempt + 1))


def analyze_batch(batch_id: str):
    departments = _retry_db(
        lambda: supabase.table("departments").select("id, name, keywords").execute()
    ).data

    # 미완료(pending/failed) 행만 페이지네이션 조회 — 재실행 시 실패분만 다시 분석됨
    articles = []
    offset = 0
    while True:
        page = _retry_db(
            lambda: supabase.table("articles")
            .select("id, original_text, source_type")
            .eq("batch_id", batch_id)
            .neq("status", "done")
            .range(offset, offset + SUPABASE_PAGE_SIZE - 1)
            .execute()
        ).data
        articles.extend(page)
        if len(page) < SUPABASE_PAGE_SIZE:
            break
        offset += SUPABASE_PAGE_SIZE

    _retry_db(lambda: supabase.table("batches").update({"status": "analyzing"}).eq("id", batch_id).execute())

    # 동일 (원문, 출처) 조합은 분석 결과가 같으므로 한 번만 호출하고 결과를 공유 (중복 과금 방지)
    groups: dict[tuple, list[str]] = {}
    for a in articles:
        groups.setdefault((a["original_text"], a["source_type"]), []).append(a["id"])

    analyzed = 0
    completed = 0

    def process_group(item):
        (text, source_type), ids = item
        try:
            # 1) 프리필터로 확정되면 Gemini 미호출. 아니면 키워드 후보와 함께 AI 판단
            result, route_hits = analyze_text(text, source_type, departments)
            # 2) AI가 관련도 높은 순으로 반환한 부서명을 ID로 매핑 (최대 2개, 중복 제거)
            dept_ids = []
            for name in (result.get("department_names") or []):
                did = _find_dept_id(name, departments)
                if did and did not in dept_ids:
                    dept_ids.append(did)
                if len(dept_ids) == 2:
                    break
            # 3) AI가 못 정했으면 키워드 단일 매칭으로 폴백
            if dept_ids:
                dept_method = "ai"
            elif len(route_hits) == 1:
                dept_ids = [route_hits[0]["id"]]
                dept_method = "rule"
            else:
                dept_method = None
            dept_id = dept_ids[0] if dept_ids else None          # 1순위 (관련도 높음)
            dept_id_2 = dept_ids[1] if len(dept_ids) > 1 else None  # 2순위
            _retry_db(lambda: supabase.table("articles").update({
                "false_score":  result["false_score"],
                "false_level":  result["false_level"],
                "category":     result["category"],
                "action_type":  result["action_type"],
                "false_reason": result["false_reason"],
                "intent_type":  result["intent_type"],
                "content_type": result["content_type"],
                "department_id": dept_id,
                "department_id_2": dept_id_2,
                "dept_method": dept_method,
                "status": "done",
                "error_reason": None,
            }).in_("id", ids).execute())
            return len(ids)
        except Exception as e:
            # 실패 사유를 남겨 조용한 유실을 방지 (사유 저장 실패는 무시)
            try:
                _retry_db(lambda: supabase.table("articles").update({
                    "status": "failed",
                    "error_reason": str(e)[:500],
                }).in_("id", ids).execute())
            except Exception:
                pass
            return 0

    prev_bucket = 0
    try:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(process_group, item): item for item in groups.items()}
            for future in as_completed(futures):
                analyzed += future.result()
                completed += len(futures[future][1])
                # 50건 경계를 넘을 때마다 진행률 저장 — 실패해도 배치 진행에는 영향 없음
                if completed // PROGRESS_INTERVAL != prev_bucket:
                    prev_bucket = completed // PROGRESS_INTERVAL
                    try:
                        supabase.table("batches").update({"analyzed_rows": completed}).eq("id", batch_id).execute()
                    except Exception:
                        pass
    finally:
        # 정산: 카운터 누적값이 아닌 articles 실측 집계로 배치를 확정.
        # 어떤 예외가 나도 status가 'analyzing'에 영원히 남지 않음 (600 멈춤 재발 방지)
        try:
            done_cnt = _retry_db(lambda: supabase.table("articles").select(
                "id", count="exact").eq("batch_id", batch_id).eq("status", "done").execute()).count
            failed_cnt = _retry_db(lambda: supabase.table("articles").select(
                "id", count="exact").eq("batch_id", batch_id).eq("status", "failed").execute()).count
            _retry_db(lambda: supabase.table("batches").update({
                "analyzed_rows": done_cnt + failed_cnt,
                "failed_rows": failed_cnt,
                "status": "done",
            }).eq("id", batch_id).execute())
        except Exception:
            pass

    failed = len(articles) - analyzed
    return {"analyzed": analyzed, "failed": failed, "total": len(articles)}


def route_departments(text: str, departments: list) -> list:
    """키워드 규칙으로 매칭되는 부서 목록 반환 (참고용 후보 + 폴백).
    관련도 순위는 AI가 판단하므로 여기서는 매칭 여부만 본다."""
    return [
        d for d in departments
        if any(kw and kw in text for kw in (d.get("keywords") or []))
    ]


def _find_dept_id(dept_name: str | None, departments: list) -> str | None:
    if not dept_name:
        return None
    for d in departments:
        if d["name"] == dept_name:
            return d["id"]
    for d in departments:
        if dept_name in d["name"] or d["name"] in dept_name:
            return d["id"]
    return None


def _analyze_single(text: str, source_type: str, departments: list,
                    route_hits: list | None = None) -> dict:
    source_label = {
        "언론": "언론 기사",
        "SNS": "SNS 게시물",
        "커뮤니티": "커뮤니티 게시물",
        "유튜브": "유튜브 댓글",
    }.get(source_type, "텍스트")

    dept_list = "\n".join(
        f"- {d['name']}: {', '.join(d['keywords'])}" if d.get('keywords') else f"- {d['name']}"
        for d in departments
    )
    dept_section = f"[분류 가능한 부서 목록]\n{dept_list}"
    if route_hits:  # 키워드 매칭 후보를 참고 힌트로 제공 (최종 순위는 AI가 판단)
        dept_section += "\n[키워드 매칭 후보(참고)] " + ", ".join(d["name"] for d in route_hits)

    relevant_docs = _retry_db(lambda: find_relevant_docs(text))
    doc_section = ""
    if relevant_docs:
        doc_section = "\n\n[병무청 공식 자료 참고]\n" + "\n---\n".join(relevant_docs)

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{dept_section}"
        f"{doc_section}\n\n"
        f"출처: {source_label}\n"
        f"텍스트: {text}"
    )

    for attempt in range(AI_MAX_RETRY):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )
            break
        except Exception as e:
            if attempt < AI_MAX_RETRY - 1:
                time.sleep(5 * (attempt + 1))
            else:
                raise e

    raw = response.text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)
    score = max(0, min(100, int(data.get("false_score", 50))))

    if score <= 33:
        level = "낮음"
    elif score <= 66:
        level = "중간"
    else:
        level = "높음"

    # 가이드라인 분류 구분 정규화 + 조치유형 결정 (정책비판만 AI 판단 존중)
    category = data.get("category")
    if category not in VALID_CATEGORIES:
        category = "해당없음"
    if category in CATEGORY_TO_ACTION:
        action_type = CATEGORY_TO_ACTION[category]
    else:  # 정책비판
        action_type = data.get("action_type") if data.get("action_type") in VALID_ACTIONS else "비대상"

    # 부서명: 배열(관련도 순) 우선, 구버전 단일 필드도 허용
    names = data.get("department_names")
    if isinstance(names, str):
        names = [names]
    elif not isinstance(names, list):
        names = []
    if not names and data.get("department_name"):
        names = [data.get("department_name")]
    names = [str(n) for n in names if n][:2]

    return {
        "false_score":      score,
        "false_level":      level,
        "category":         category,
        "action_type":      action_type,
        "false_reason":     str(data.get("false_reason", ""))[:100],
        "intent_type":      str(data.get("intent_type", "불명확")),
        "content_type":     str(data.get("content_type", "불명확")),
        "department_names": names,
    }
