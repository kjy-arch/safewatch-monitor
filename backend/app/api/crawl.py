from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, BackgroundTasks, Body
from fastapi.responses import Response
from app.core.scheduler import run_crawl_and_analyze, run_analyze_only, tier_of
from app.services.analyzer import analyze_unclassified
from app.services.notifier import _build_excel
from app.services import exporter
from app.core.database import supabase
from app.core import progress

router = APIRouter(tags=["crawl"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/crawl/sources")
def crawl_sources_list():
    """수집 소스 목록 + 위험 분류(safe/gray) — 대시보드 소스 선택용."""
    rows = (
        supabase.table("crawl_sources")
        .select("id, name, source_type, is_active")
        .order("source_type")
        .execute()
        .data
    )
    for r in rows:
        r["tier"] = tier_of(r["source_type"])
    return rows


@router.post("/crawl/run")
def manual_crawl(background_tasks: BackgroundTasks, body: dict = Body(default=None)):
    """수동 크롤링 + 분류 실행.

    body.source_ids가 주어지면 그 소스만, 없으면 안전 소스만 수집(회색은 명시 선택 필요).
    """
    if progress.is_running():
        return {"message": "이미 수집이 진행 중입니다."}
    source_ids = (body or {}).get("source_ids")
    background_tasks.add_task(run_crawl_and_analyze, True, source_ids)
    return {"message": "크롤링 시작됨. 잠시 후 결과를 확인하세요."}


@router.get("/crawl/status")
def crawl_status():
    """현재 수집·분류 진행 상태 (대시보드 폴링용)."""
    return progress.snapshot()


@router.get("/articles/export")
def export_articles(scope: str = "today", false_level: str = None):
    """수집 결과를 엑셀(.xlsx)로 다운로드. scope=today(오늘) | all(전체)."""
    articles = exporter.fetch_articles(scope, false_level)
    xlsx = _build_excel(articles)

    stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
    filename = f"safewatch_{scope}_{stamp}.xlsx"
    return Response(
        content=xlsx,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/crawl/backlog")
def crawl_backlog():
    """미분류(백로그) 건수 — 대시보드 표시용."""
    n = (
        supabase.table("crawled_articles")
        .select("id", count="exact")
        .is_("false_score", "null")
        .execute()
        .count
    )
    return {"unclassified": n}


@router.post("/crawl/analyze")
def manual_analyze(background_tasks: BackgroundTasks, body: dict = Body(default=None)):
    """미분류 백로그를 AI 분류. body.limit로 이번 배치 건수 지정(기본 100)."""
    if progress.is_running():
        return {"message": "이미 실행 중입니다."}
    try:
        limit = max(1, int((body or {}).get("limit") or 100))
    except (TypeError, ValueError):
        limit = 100
    background_tasks.add_task(run_analyze_only, limit)
    return {"message": f"미분류 분류 시작 (최대 {limit}건)"}


@router.get("/articles")
def list_articles(
    false_level: str = None,
    source_type: str = None,
    response_status: str = None,
    limit: int = 50,
):
    query = supabase.table("crawled_articles").select(
        "id, title, content, url, source_type, false_score, false_level, "
        "false_reason, label_l2, subject, response_status, "
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
        "false_level, source_type, label_l2, response_status"
    ).execute().data

    total = len(articles)
    by_level   = {}
    by_source  = {}
    by_label   = {}
    by_status  = {}

    for a in articles:
        by_level[a["false_level"] or "미분류"]     = by_level.get(a["false_level"] or "미분류", 0) + 1
        by_source[a["source_type"] or "-"]         = by_source.get(a["source_type"] or "-", 0) + 1
        by_label[a["label_l2"] or "미분류"]        = by_label.get(a["label_l2"] or "미분류", 0) + 1
        by_status[a["response_status"] or "미확인"] = by_status.get(a["response_status"] or "미확인", 0) + 1

    return {
        "total": total,
        "by_level":  by_level,
        "by_source": by_source,
        "by_label":  by_label,
        "by_status": by_status,
    }
