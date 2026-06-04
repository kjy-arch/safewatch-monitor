import json
from google import genai
from app.core.config import settings
from app.core.database import supabase

client = genai.Client(api_key=settings.GEMINI_API_KEY)

SYSTEM_PROMPT = """당신은 병무청 언론 모니터링 전문 분석관입니다.
주어진 텍스트를 분석하여 반드시 JSON만 반환하세요.

반환 형식:
{
  "false_score": 0~100 정수,
  "false_level": "낮음" | "중간" | "높음",
  "false_reason": 판단 이유 한 줄 (40자 이내),
  "intent_type": "악의적 유포" | "단순 오해" | "풍자/비판" | "사실 보도" | "불명확",
  "content_type": "사실관계 오류" | "과장/왜곡" | "출처 불명" | "맥락 누락" | "문제없음",
  "department_name": 아래 부서 목록 중 하나 또는 null
}

기준: 0~33=낮음, 34~66=중간, 67~100=높음
병무청에 불리하거나 허위일수록 점수 높게."""


def analyze_unclassified(limit: int = 20) -> int:
    """분석 안 된 수집 기사를 Gemini로 분류."""
    articles = (
        supabase.table("crawled_articles")
        .select("id, content, source_type")
        .is_("false_score", "null")
        .limit(limit)
        .execute()
        .data
    )
    departments = supabase.table("departments").select("id, name, keywords").execute().data

    analyzed = 0
    for article in articles:
        try:
            result = _analyze(article["content"], article["source_type"], departments)
            dept_id = _find_dept(result.get("department_name"), departments)

            supabase.table("crawled_articles").update({
                "false_score":  result["false_score"],
                "false_level":  result["false_level"],
                "false_reason": result["false_reason"],
                "intent_type":  result["intent_type"],
                "content_type": result["content_type"],
                "department_id": dept_id,
            }).eq("id", article["id"]).execute()

            analyzed += 1
        except Exception:
            continue

    return analyzed


def _find_dept(name, departments):
    if not name:
        return None
    for d in departments:
        if d["name"] == name or name in d["name"]:
            return d["id"]
    return None


def _analyze(text: str, source_type: str, departments: list) -> dict:
    source_label = {"언론": "언론 기사", "SNS": "SNS 게시물",
                    "커뮤니티": "커뮤니티 게시물", "유튜브": "유튜브 댓글"}.get(source_type, "텍스트")
    dept_list = "\n".join(f"- {d['name']}" for d in departments)

    prompt = f"{SYSTEM_PROMPT}\n\n[부서 목록]\n{dept_list}\n\n출처: {source_label}\n텍스트: {text[:800]}"

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw.strip())
    score = max(0, min(100, int(data.get("false_score", 50))))
    level = "낮음" if score <= 33 else ("중간" if score <= 66 else "높음")

    return {
        "false_score":     score,
        "false_level":     level,
        "false_reason":    str(data.get("false_reason", ""))[:100],
        "intent_type":     str(data.get("intent_type", "불명확")),
        "content_type":    str(data.get("content_type", "불명확")),
        "department_name": data.get("department_name"),
    }
