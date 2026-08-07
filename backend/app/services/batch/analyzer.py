import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.database import supabase
from app.services.batch.doc_service import find_relevant_docs
# Phase 2 — 수집분/업로드분이 같은 프롬프트·파서를 쓰도록 통합
from app.services.unified_prompt import SYSTEM_PROMPT, parse_unified
from app.services.keyword_scorer import has_military_context
from app.services.pii_masking import mask_pii

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

HANGUL_RE = re.compile(r"[가-힣]")


def prefilter(text: str) -> dict | None:
    """Gemini 호출 없이 확정 가능한 '비대상'을 로컬에서 판정. 판정 불가면 None.

    두 가지를 로컬에서 확정한다.
      ① 한글이 한 글자도 없는 내용(번호·날짜·기호·자모만 등)
      ② 병역 관련 단어가 하나도 없는 내용 — 수집분과 같은 게이트
         (실측 676건에서 무관 글이 32%였고 그만큼 호출이 낭비됐다)
    한글·병역어가 있으면 짧더라도 AI에 보낸다("군대 빼는법 없나" 같은 짧은 조장정보 보호).
    """
    t = (text or "").strip()
    if t and HANGUL_RE.search(t) and has_military_context(t):
        return None
    return {
        "false_score":      0,
        "false_level":      "낮음",
        "label_l2":         "단순내용",
        "subject":          "기타",
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
                "label_l2":     result["label_l2"],
                "subject":      result["subject"],
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
    prompt = mask_pii(prompt)

    for attempt in range(AI_MAX_RETRY):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                # JSON 강제 — 통합 프롬프트가 길어지면서 산문 응답으로 파싱 실패하는
                # 건이 생겼다(골든셋 2건 유실). 수집분 경로는 원래 이 옵션을 쓰고 있었다.
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
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

    # 두 축 정규화·보정은 unified_prompt.parse_unified가 전담 (수집분과 동일 규칙)
    return parse_unified(json.loads(raw))
