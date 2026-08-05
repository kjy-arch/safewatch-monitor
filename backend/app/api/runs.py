"""실행 이력·담당자 API (Phase 3).

담당자 정보는 인증이 아니라 **기록**이다 — app/core/operator.py 주석 참조.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import operator
from app.services import run_log

router = APIRouter(tags=["runs"])


class OperatorUpdate(BaseModel):
    name: str


@router.get("/operator")
def read_operator():
    """현재 PC의 담당자 정보. name이 null이면 최초 입력이 필요하다."""
    s = operator.snapshot()
    return {**s, "display": operator.describe(), "configured": bool(s["operator_name"])}


@router.put("/operator")
def update_operator(body: OperatorUpdate):
    try:
        name = operator.set_name(body.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"operator_name": name, "display": operator.describe()}


@router.get("/runs")
def list_runs(limit: int = 50):
    """최근 실행 이력 — 다른 PC에서 돌린 것도 함께 보인다."""
    return run_log.recent(limit)


@router.get("/runs/active")
def active_runs():
    """지금 실행 중인 작업. 다른 PC에서 돌리는 중이면 중복 실행을 피할 수 있다."""
    rows = run_log.active()
    return {"count": len(rows), "runs": rows}
