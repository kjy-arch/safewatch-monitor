import json, time
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.database import supabase
from app.services.classifier_prompt import (
    SYSTEM_PROMPT, LABEL_SCORE_RANGES, PROMOTION_LABELS, ALL_LABELS, SUBJECTS,
)
from app.services.keyword_scorer import score_text, is_enabled as prefilter_enabled, PREFILTER_THRESHOLD

client = genai.Client(api_key=settings.GEMINI_API_KEY)

# 이번 프로세스에서 분류에 실패한 기사 ID — 같은 실행 안에서 같은 기사를
# 반복 재시도해 배치를 점유하는 것을 방지. 재시작하면 초기화되어 자연 재시도.
_failed_ids: set = set()
_FAILED_IDS_MAX = 500


def analyze_unclassified(limit: int = 20) -> int:
    """분석 안 된 수집 기사를 Gemini로 분류 (병무청 공식 분류체계)."""
    query = (
        supabase.table("crawled_articles")
        .select("id, title, content, source_type")
        .is_("false_score", "null")
    )
    if _failed_ids:
        query = query.not_.in_("id", list(_failed_ids)[:_FAILED_IDS_MAX])
    articles = query.limit(limit).execute().data
    departments = supabase.table("departments").select("id, name, keywords").execute().data

    # 키워드 점수 사전 필터: 고점수 우선 분류, 임계치 미만은 Gemini 없이 단순정보 처리
    if prefilter_enabled():
        articles.sort(key=lambda a: score_text(f"{a.get('title') or ''} {a['content']}"),
                      reverse=True)

    analyzed = 0
    prefiltered = 0
    for article in articles:
        try:
            text = f"{article.get('title') or ''} {article['content']}"
            kw_score = score_text(text) if prefilter_enabled() else -1
            if 0 <= kw_score < PREFILTER_THRESHOLD:
                supabase.table("crawled_articles").update({
                    "false_score":  5,
                    "false_level":  "낮음",
                    "false_reason": f"키워드 사전필터 자동분류 (점수 {kw_score})",
                    "label_l2":     "단순내용",
                    "subject":      "기타",
                }).eq("id", article["id"]).execute()
                prefiltered += 1
                analyzed += 1
                continue

            result = _analyze(article.get("title") or "", article["content"],
                              article["source_type"], departments)
            dept_id = _find_dept(result.get("department_name"), departments)

            update_fields = {
                "false_score":  result["false_score"],
                "false_level":  result["false_level"],
                "false_reason": result["false_reason"],
                "label_l2":     result["label_l2"],
                "subject":      result["subject"],
                "department_id": dept_id,
            }
            try:
                supabase.table("crawled_articles").update(update_fields).eq("id", article["id"]).execute()
            except Exception:
                # label_l2/subject 컬럼 미적용(002 마이그레이션 전)이어도 분류 자체는 저장
                update_fields.pop("label_l2", None)
                update_fields.pop("subject", None)
                supabase.table("crawled_articles").update(update_fields).eq("id", article["id"]).execute()

            analyzed += 1
        except Exception as e:
            print(f"[analyzer] 기사 {article['id']} 분류 실패: {type(e).__name__}: {e}")
            if len(_failed_ids) < _FAILED_IDS_MAX:
                _failed_ids.add(article["id"])
            continue

    if prefiltered:
        print(f"[analyzer] 사전필터로 {prefiltered}건 자동분류 (Gemini 호출 생략)")
    if analyzed < len(articles):
        print(f"[analyzer] {len(articles)}건 중 {len(articles) - analyzed}건 실패")
    return analyzed


def _find_dept(name, departments):
    if not name:
        return None
    for d in departments:
        if d["name"] == name or name in d["name"]:
            return d["id"]
    return None


def _analyze(title: str, text: str, source_type: str, departments: list) -> dict:
    source_label = {"언론": "언론 기사", "SNS": "SNS 게시물",
                    "커뮤니티": "커뮤니티 게시물", "유튜브": "유튜브 댓글",
                    "지식인": "지식인 질문글"}.get(source_type, "텍스트")
    dept_list = "\n".join(f"- {d['name']}" for d in departments)

    system = f"{SYSTEM_PROMPT}\n\n[부서 목록]\n{dept_list}"
    prompt = f"출처: {source_label}\n제목: {title[:150]}\n내용: {text[:800]}"

    # Gemini 호출 — 실패 시 최대 3회 재시도
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))  # 5초, 10초 대기 후 재시도
            else:
                raise e

    return _parse_response(response.text)


def _parse_response(raw: str) -> dict:
    """Gemini 응답 JSON을 검증·보정해 저장용 dict로 변환."""
    raw = raw.strip()
    if raw.startswith("```"):  # JSON 모드 실패 대비 안전망
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw.strip())

    label = str(data.get("label_l2", "")).strip()
    if label not in ALL_LABELS:
        label = "단순내용"

    # 점수: 라벨별 허용 구간으로 보정 (모델이 구간 밖 점수를 주면 구간에 클램프)
    lo, hi = LABEL_SCORE_RANGES[label]
    try:
        score = int(data.get("false_score", lo))
    except (TypeError, ValueError):
        score = lo
    score = max(lo, min(hi, score))
    level = "낮음" if score <= 33 else ("중간" if score <= 66 else "높음")

    subject = str(data.get("subject", "")).strip()
    if subject not in SUBJECTS:
        subject = "기타"

    return {
        "label_l1":        "조장정보" if label in PROMOTION_LABELS else "단순병역정보",
        "label_l2":        label,
        "subject":         subject,
        "false_score":     score,
        "false_level":     level,
        "false_reason":    str(data.get("reason", data.get("false_reason", "")))[:100],
        "department_name": data.get("department_name"),
    }
