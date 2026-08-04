from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from datetime import datetime, timedelta, timezone
from app.core.database import supabase
from app.services.batch.excel import build_quarterly_excel

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/quarterly/download")
def quarterly_report(
    from_date: str | None = Query(None, alias="from", description="시작일 YYYY-MM-DD"),
    to_date: str | None = Query(None, alias="to", description="종료일 YYYY-MM-DD"),
):
    """분기(기본 최근 3개월) 집계 보고서 엑셀 다운로드."""
    now = datetime.now(timezone.utc)
    to_dt = datetime.fromisoformat(to_date) if to_date else now
    from_dt = datetime.fromisoformat(from_date) if from_date else (to_dt - timedelta(days=90))

    # 기간 내 분석완료 건 조회 (페이지네이션)
    articles = []
    offset = 0
    while True:
        page = (
            supabase.table("articles")
            .select("created_at, category, action_type, false_level, intent_type, source_type, department_id, department_id_2")
            .eq("status", "done")
            .gte("created_at", from_dt.isoformat())
            .lte("created_at", to_dt.isoformat())
            .range(offset, offset + 999)
            .execute()
            .data
        )
        articles.extend(page)
        if len(page) < 1000:
            break
        offset += 1000

    depts = supabase.table("departments").select("id, name").execute().data
    dept_map = {d["id"]: d["name"] for d in depts}
    period = f"{from_dt.date()} ~ {to_dt.date()}"
    excel_bytes = build_quarterly_excel(articles, dept_map, period)

    filename = f"quarterly_report_{from_dt.date()}_{to_dt.date()}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
