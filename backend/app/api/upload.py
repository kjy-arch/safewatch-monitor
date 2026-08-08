from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from io import BytesIO
from datetime import datetime, timedelta, timezone
from app.core.database import supabase
from app.services.batch.excel import (
    MAX_UPLOAD_BYTES,
    parse_excel,
    build_result_excel,
)
from app.services.batch.analyzer import analyze_batch
from app.services.batch.stats import summarize
from app.services.batch.app_settings import get_risk_threshold
from app.services import run_log

router = APIRouter(prefix="/batches", tags=["upload"])


def _analyze_batch_logged(batch_id: str):
    """분석 + 실행 이력 기록 — 누가 어떤 배치를 돌렸는지 남긴다 (Phase 3)."""
    run_id = run_log.start("batch", batch_id=batch_id)
    try:
        result = analyze_batch(batch_id)
        run_log.finish(run_id, analyzed=result.get("analyzed", 0),
                       message=f"{result.get('total', 0)}건 중 {result.get('analyzed', 0)}건 분류"
                               + (f" (실패 {result['failed']}건)" if result.get("failed") else ""))
    except Exception as e:
        run_log.fail(run_id, f"{type(e).__name__}: {e}")
        raise


def _ordered_articles(batch_id: str, columns: str = "*") -> list[dict]:
    """배치의 행을 엑셀 원본 순서대로 반환.

    1순위 row_index(migration 008). 미적용 환경에서도 순서가 보장되도록, 업로드 시 행마다
    1µs씩 증가시켜 저장한 created_at을 2순위 키로 쓴다.
    (기존에는 일괄 insert로 created_at이 전 행 동일 → tie-break가 없어 순서가 뒤섞였다.)
    """
    articles = (
        supabase.table("articles").select(columns)
        .eq("batch_id", batch_id).order("created_at").execute().data
    )
    LAST = 10 ** 9  # row_index 없는 과거 데이터는 뒤로 보내고 created_at으로 정렬
    articles.sort(key=lambda a: (
        a["row_index"] if a.get("row_index") is not None else LAST,
        a.get("created_at") or "",
    ))
    return articles


@router.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx)만 업로드 가능합니다.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기는 10MB 이하여야 합니다.")

    try:
        rows = parse_excel(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not rows:
        raise HTTPException(status_code=422, detail="분석할 행이 없습니다. 'text' 컬럼을 확인해주세요.")

    # batches 테이블에 배치 생성
    batch = supabase.table("batches").insert({
        "file_name": filename,
        "total_rows": len(rows),
        "analyzed_rows": 0,
    }).execute().data[0]

    # articles 테이블에 원문 저장 (500건씩 나눠서 insert — 대용량 안정성)
    # row_index: 엑셀 원본 순서(1부터). 결과를 항상 1번부터 순서대로 보여주기 위한 정렬 키.
    # created_at: 행마다 1µs씩 증가 — migration 008 미적용 환경에서도 순서가 보존된다.
    base_ts = datetime.now(timezone.utc)
    articles_to_insert = [
        {
            "batch_id": batch["id"],
            "original_text": row["text"],
            "source_type": row["source_type"],
            "source_url": row["source_url"] or None,
            "row_index": idx,
            "created_at": (base_ts + timedelta(microseconds=idx)).isoformat(),
        }
        for idx, row in enumerate(rows, 1)
    ]
    chunk_size = 500
    for i in range(0, len(articles_to_insert), chunk_size):
        chunk = articles_to_insert[i:i + chunk_size]
        try:
            supabase.table("articles").insert(chunk).execute()
        except Exception as e:
            # migration 008(row_index) 미적용 환경 호환 — 순서 보장만 포기하고 업로드는 진행
            if "row_index" not in str(e):
                raise
            supabase.table("articles").insert(
                [{k: v for k, v in a.items() if k != "row_index"} for a in chunk]
            ).execute()

    return {
        "batch_id": batch["id"],
        "file_name": filename,
        "total_rows": len(rows),
        "message": f"{len(rows)}행 업로드 완료. /api/batches/{batch['id']}/analyze 로 분석을 시작하세요.",
    }


@router.post("/{batch_id}/analyze")
def start_analyze(batch_id: str, background_tasks: BackgroundTasks):
    batch = supabase.table("batches").select("id").eq("id", batch_id).execute().data
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")
    background_tasks.add_task(_analyze_batch_logged, batch_id)
    return {"message": "분석 시작됨. 잠시 후 결과를 확인하세요. (미완료·실패 행만 분석되므로 실패분 재분석에도 사용 가능)", "batch_id": batch_id}


@router.get("")
def list_batches():
    result = supabase.table("batches").select("*").order("created_at", desc=True).execute()
    return result.data


@router.get("/{batch_id}")
def get_batch(batch_id: str):
    batch = supabase.table("batches").select("*").eq("id", batch_id).execute().data
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")

    articles = _ordered_articles(batch_id)

    return {"batch": batch[0], "articles": articles}


@router.get("/{batch_id}/stats")
def get_batch_stats(batch_id: str):
    batch = supabase.table("batches").select("id").eq("id", batch_id).execute().data
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")
    articles = supabase.table("articles").select(
        "false_score, false_level, action_type, category, intent_type, content_type, source_type, department_id, department_id_2"
    ).eq("batch_id", batch_id).eq("status", "done").execute().data
    depts = supabase.table("departments").select("id, name").execute().data
    dept_map = {d["id"]: d["name"] for d in depts}
    return summarize(articles, dept_map, get_risk_threshold())


@router.get("/{batch_id}/download")
def download_result(batch_id: str):
    batch = supabase.table("batches").select("*").eq("id", batch_id).execute().data
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")

    articles = _ordered_articles(batch_id)
    depts = supabase.table("departments").select("id, name").execute().data
    dept_map = {d["id"]: d["name"] for d in depts}

    original_rows = [{"text": a["original_text"], "source_type": a["source_type"], "source_url": a.get("source_url", "")} for a in articles]
    analysis_results = [
        {
            "false_score":  a.get("false_score"),
            "false_level":  a.get("false_level"),
            "category":     a.get("category", ""),
            "action_type":  a.get("action_type", ""),
            "false_reason": a.get("false_reason"),
            "intent_type":  a.get("intent_type", ""),
            "content_type": a.get("content_type", ""),
            "department":   dept_map.get(a.get("department_id"), ""),
            "department_2": dept_map.get(a.get("department_id_2"), ""),
        }
        for a in articles
    ]

    excel_bytes = build_result_excel(original_rows, analysis_results)
    filename = f"result_{batch[0]['file_name']}"

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
