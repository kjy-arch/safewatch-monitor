"""실행 이력 기록 — run_logs 테이블 (migration 007).

DB에 남기므로 다른 PC에서도 "지난주에 누가 돌렸나"를 볼 수 있다. 이력 기록이
실패해도 수집·분류 자체는 진행되어야 하므로 모든 함수는 예외를 삼킨다.
"""
from datetime import datetime, timezone

from app.core.database import supabase
from app.core import operator

# 이 시간(분)을 넘긴 running 건은 죽은 실행으로 본다 — 서버 강제 종료 등으로
# finish가 호출되지 못한 경우 '실행 중'이 영원히 남는 것을 방지.
STALE_MINUTES = 180


def start(run_type: str, batch_id: str | None = None) -> str | None:
    """실행 시작 기록. run_logs.id 반환(실패 시 None)."""
    try:
        row = {"run_type": run_type, "status": "running", **operator.snapshot()}
        if batch_id:
            row["batch_id"] = batch_id
        res = supabase.table("run_logs").insert(row).execute().data
        print(f"[이력] {run_type} 시작 — {operator.describe()}", flush=True)
        return res[0]["id"] if res else None
    except Exception as e:
        print(f"[이력] 시작 기록 실패(무시): {type(e).__name__}: {e}", flush=True)
        return None


def finish(run_id: str | None, collected: int = 0, analyzed: int = 0,
           message: str = "", status: str = "done") -> None:
    """실행 종료 기록."""
    if not run_id:
        return
    try:
        supabase.table("run_logs").update({
            "status":      status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "collected":   collected,
            "analyzed":    analyzed,
            "message":     (message or "")[:500],
        }).eq("id", run_id).execute()
    except Exception as e:
        print(f"[이력] 종료 기록 실패(무시): {type(e).__name__}: {e}", flush=True)


def fail(run_id: str | None, message: str) -> None:
    finish(run_id, message=message, status="failed")


def active() -> list[dict]:
    """지금 실행 중인 기록 — 다른 PC에서 돌리고 있는지 확인용.

    STALE_MINUTES를 넘긴 건은 죽은 실행으로 보고 제외한다.
    """
    try:
        rows = (supabase.table("run_logs")
                .select("id, run_type, operator_name, os_account, host_name, started_at")
                .eq("status", "running")
                .order("started_at", desc=True).limit(20).execute().data)
    except Exception:
        return []

    now = datetime.now(timezone.utc)
    fresh = []
    for r in rows:
        started = r.get("started_at")
        if not started:
            continue
        try:
            ts = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - ts).total_seconds() / 60 <= STALE_MINUTES:
            fresh.append(r)
    return fresh


def recent(limit: int = 50) -> list[dict]:
    """최근 실행 이력."""
    try:
        return (supabase.table("run_logs").select("*")
                .order("started_at", desc=True).limit(limit).execute().data)
    except Exception as e:
        print(f"[이력] 조회 실패: {type(e).__name__}: {e}", flush=True)
        return []
