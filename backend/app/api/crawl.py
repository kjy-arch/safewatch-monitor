from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, BackgroundTasks, UploadFile, File
from fastapi.responses import Response
from app.core.scheduler import run_crawl_and_analyze
from app.services.analyzer import analyze_unclassified
from app.services.notifier import _build_excel
from app.services import excel_classifier
from app.core.database import supabase
from app.core import progress

router = APIRouter(tags=["crawl"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/crawl/run")
def manual_crawl(background_tasks: BackgroundTasks):
    """수동으로 전체 크롤링 + 분류 실행 (주말·공휴일에도 강제 실행)."""
    if progress.is_running():
        return {"message": "이미 수집이 진행 중입니다."}
    background_tasks.add_task(run_crawl_and_analyze, True)
    return {"message": "크롤링 시작됨. 잠시 후 결과를 확인하세요."}


@router.get("/crawl/status")
def crawl_status():
    """현재 수집·분류 진행 상태 (대시보드 폴링용)."""
    return progress.snapshot()


@router.get("/articles/export")
def export_articles(scope: str = "today", false_level: str = None):
    """수집 결과를 엑셀(.xlsx)로 다운로드. scope=today(오늘) | all(전체)."""
    query = supabase.table("crawled_articles").select("*, departments(name)")

    if scope == "today":
        now_kst = datetime.now(timezone(timedelta(hours=9)))
        today_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        query = query.gte("created_at", today_start.isoformat())
    if false_level:
        query = query.eq("false_level", false_level)

    articles = query.order("false_score", desc=True).limit(5000).execute().data
    xlsx = _build_excel(articles)

    stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
    filename = f"safewatch_{scope}_{stamp}.xlsx"
    return Response(
        content=xlsx,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/classify/excel")
async def classify_excel(background_tasks: BackgroundTasks,
                         file: UploadFile = File(...), limit: int = 200):
    """업로드된 엑셀의 원문을 Monitor 분류기로 분류 (백그라운드). 진행은 /classify/result로 폴링."""
    if excel_classifier.snapshot()["status"] == "running":
        return {"message": "이미 분류가 진행 중입니다.", "total": 0}

    data = await file.read()
    try:
        rows = excel_classifier.parse_excel(data)
    except Exception as e:
        return {"message": f"엑셀을 읽지 못했습니다: {type(e).__name__}", "total": 0}
    if not rows:
        return {"message": "원문(내용) 열을 찾지 못했습니다. '원문' 또는 '내용' 열을 확인하세요.", "total": 0}

    background_tasks.add_task(excel_classifier.run, rows, limit)
    return {"message": "분류를 시작했습니다.", "total": min(len(rows), limit)}


@router.get("/classify/result")
def classify_result():
    """엑셀 분류 진행 상태 + 결과 (대시보드 폴링용)."""
    return excel_classifier.snapshot()


@router.get("/classify/export")
def classify_export():
    """엑셀 분류 결과를 xlsx로 다운로드 (수집 엑셀과 동일 서식 재사용)."""
    results = excel_classifier.snapshot()["results"]
    articles = [{
        "source_type":     r.get("source") or "",
        "published_at":    "",
        "false_score":     r.get("false_score"),
        "false_level":     r.get("false_level"),
        "label_l2":        r.get("label_l2"),
        "subject":         r.get("subject"),
        "false_reason":    r.get("false_reason"),
        "departments":     {"name": r.get("department_name") or ""},
        "content":         r.get("text") or "",
        "title":           "",
        "url":             r.get("url") or "",
        "response_status": "미확인",
    } for r in results]

    xlsx = _build_excel(articles)
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d_%H%M")
    return Response(
        content=xlsx,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="classified_{stamp}.xlsx"'},
    )


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
