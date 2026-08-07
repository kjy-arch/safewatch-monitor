"""2단계 검증 API — 삭제대상 판정을 본문으로 재확인 (2026-08-07).

판정을 **덮어쓰지 않는다.** 2차 결과는 verify_* 컬럼에만 쌓이고, 최종 판단은 담당자가
검수 화면에서 기존 재분류 기능으로 한다.
"""
from fastapi import APIRouter, BackgroundTasks, Body

from app.core.database import supabase
from app.services import verify

router = APIRouter(tags=["verify"])


@router.post("/verify/run")
def run_verify(background_tasks: BackgroundTasks, body: dict = Body(default=None)):
    """미확인 삭제대상·종합판단을 본문으로 재판정. 백그라운드 실행."""
    # status() 검사만 하면 run()이 응답 뒤에 실행되는 사이에 두 번째 요청이 통과한다.
    # 검사·설정을 원자적으로 하는 try_begin()으로 잡는다(중복 실행 실측 2026-08-07).
    if not verify.try_begin():
        return {"message": "이미 검증이 진행 중입니다."}
    limit = int((body or {}).get("limit") or 200)
    background_tasks.add_task(verify.run, limit)
    return {"message": "2단계 검증 시작됨. 잠시 후 결과를 확인하세요."}


@router.get("/verify/status")
def verify_status():
    """진행 상태 (화면 폴링용)."""
    return verify.status()


@router.get("/verify/pending")
def verify_pending():
    """아직 2차 확인을 안 한 건수 — 버튼 노출 판단용."""
    rows = verify.pending(limit=1000)
    fetchable = sum(1 for r in rows if r["source_type"] in verify.FETCHABLE)
    return {"total": len(rows), "fetchable": fetchable,
            "skip": len(rows) - fetchable}


@router.get("/verify/results")
def verify_results(only_mismatch: bool = False, limit: int = 100):
    """2차 확인 결과 — 1차와 2차를 나란히 본다.

    only_mismatch=true면 판정이 갈린 건만. 검수 우선순위가 그쪽에 있다.
    """
    q = (
        supabase.table("crawled_articles")
        .select("id, source_type, url, title, content, content_full, false_score, "
                "label_l2, category, action_type, false_reason, "
                "verify_status, verify_action, verify_reason, verified_at")
        .not_.is_("verify_status", "null")
        .order("verified_at", desc=True)
        .limit(limit)
    )
    rows = q.execute().data
    for r in rows:
        r["mismatch"] = bool(r.get("verify_action")
                             and r["verify_action"] != r.get("action_type"))
    if only_mismatch:
        rows = [r for r in rows if r["mismatch"]]
    return rows
