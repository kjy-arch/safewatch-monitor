from fastapi import APIRouter, BackgroundTasks
from app.core.scheduler import run_crawl_and_analyze
from app.services.analyzer import analyze_unclassified
from app.core.database import supabase

router = APIRouter(tags=["crawl"])


@router.post("/crawl/run")
def manual_crawl(background_tasks: BackgroundTasks):
    """수동으로 전체 크롤링 + 분류 실행."""
    background_tasks.add_task(run_crawl_and_analyze)
    return {"message": "크롤링 시작됨. 잠시 후 결과를 확인하세요."}


@router.post("/crawl/analyze")
def manual_analyze(background_tasks: BackgroundTasks):
    """미분류 기사만 AI 분류 실행."""
    background_tasks.add_task(analyze_unclassified, 30)
    return {"message": "AI 분류 시작됨."}


@router.get("/articles")
def list_articles(
    false_level: str = None,
    source_type: str = None,
    response_status: str = None,
    limit: int = 50,
):
    query = supabase.table("crawled_articles").select(
        "id, title, content, url, source_type, false_score, false_level, "
        "false_reason, intent_type, content_type, response_status, "
        "published_at, created_at, departments(name)"
    ).order("created_at", desc=True).limit(limit)

    if false_level:
        query = query.eq("false_level", false_level)
    if source_type:
        query = query.eq("source_type", source_type)
    if response_status:
        query = query.eq("response_status", response_status)

    return query.execute().data


@router.patch("/articles/{article_id}/status")
def update_status(article_id: str, body: dict):
    status = body.get("response_status")
    memo   = body.get("response_memo", "")
    supabase.table("crawled_articles").update({
        "response_status": status,
        "response_memo":   memo,
    }).eq("id", article_id).execute()
    return {"message": "상태 업데이트 완료"}


@router.get("/stats")
def get_stats():
    articles = supabase.table("crawled_articles").select(
        "false_level, source_type, intent_type, response_status"
    ).execute().data

    total = len(articles)
    by_level   = {}
    by_source  = {}
    by_intent  = {}
    by_status  = {}

    for a in articles:
        by_level[a["false_level"] or "미분류"]     = by_level.get(a["false_level"] or "미분류", 0) + 1
        by_source[a["source_type"] or "-"]         = by_source.get(a["source_type"] or "-", 0) + 1
        by_intent[a["intent_type"] or "미분류"]    = by_intent.get(a["intent_type"] or "미분류", 0) + 1
        by_status[a["response_status"] or "미확인"] = by_status.get(a["response_status"] or "미확인", 0) + 1

    return {
        "total": total,
        "by_level":  by_level,
        "by_source": by_source,
        "by_intent": by_intent,
        "by_status": by_status,
    }
