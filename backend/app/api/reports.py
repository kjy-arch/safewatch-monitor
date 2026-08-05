from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from datetime import datetime, timedelta, timezone
from app.core.database import supabase
from app.services.batch.excel import build_quarterly_excel
from app.services import unified_query

router = APIRouter(prefix="/reports", tags=["reports"])


def _period(from_date: str | None, to_date: str | None):
    now = datetime.now(timezone.utc)
    to_dt = datetime.fromisoformat(to_date) if to_date else now
    from_dt = datetime.fromisoformat(from_date) if from_date else (to_dt - timedelta(days=90))
    return from_dt, to_dt


@router.get("/quarterly/summary")
def quarterly_summary(
    from_date: str | None = Query(None, alias="from", description="시작일 YYYY-MM-DD"),
    to_date: str | None = Query(None, alias="to", description="종료일 YYYY-MM-DD"),
):
    """보고서에 들어갈 집계를 미리 확인 (엑셀 없이). 중복 제거 내역도 함께 반환."""
    from_dt, to_dt = _period(from_date, to_date)
    data = unified_query.fetch(from_dt, to_dt)
    rows = data["rows"]

    def dist(field):
        out = {}
        for r in rows:
            out[r.get(field) or "(미분류)"] = out.get(r.get(field) or "(미분류)", 0) + 1
        return dict(sorted(out.items(), key=lambda x: -x[1]))

    return {
        "period": f"{from_dt.date()} ~ {to_dt.date()}",
        "total": len(rows),
        "sources": {"수집분": data["crawled"], "업로드분": data["uploaded"],
                    "중복제거": data["deduped"]},
        "by_origin":      dist("origin"),
        "by_action_type": dist("action_type"),
        "by_category":    dist("category"),
        "by_false_level": dist("false_level"),
        "by_intent_type": dist("intent_type"),
        "by_source_type": dist("source_type"),
    }


@router.get("/quarterly/download")
def quarterly_report(
    from_date: str | None = Query(None, alias="from", description="시작일 YYYY-MM-DD"),
    to_date: str | None = Query(None, alias="to", description="종료일 YYYY-MM-DD"),
):
    """분기(기본 최근 3개월) 집계 보고서 엑셀 — 수집분 + 업로드분 통합.

    같은 글이 양쪽에 있으면(수집 엑셀을 다시 올려 재분류한 경우) 중복을 제거한다.
    자세한 규칙은 app/services/unified_query.py 참조.
    """
    from_dt, to_dt = _period(from_date, to_date)
    data = unified_query.fetch(from_dt, to_dt)

    depts = supabase.table("departments").select("id, name").execute().data
    dept_map = {d["id"]: d["name"] for d in depts}
    period = (f"{from_dt.date()} ~ {to_dt.date()}"
              f"  (수집 {data['crawled']} + 업로드 {data['uploaded']}"
              f" − 중복 {data['deduped']} = {len(data['rows'])}건)")
    excel_bytes = build_quarterly_excel(data["rows"], dept_map, period)

    filename = f"quarterly_report_{from_dt.date()}_{to_dt.date()}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
