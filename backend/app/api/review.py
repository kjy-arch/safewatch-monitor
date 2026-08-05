"""검수·재분류 API (Phase 6, 요구 Q3)."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import review

router = APIRouter(prefix="/review", tags=["review"])


class ReclassifyBody(BaseModel):
    changes: dict = Field(..., description="바꿀 항목 {필드: 값}")
    reason: str = Field("", description="재분류 사유 (이력에 남음)")


@router.get("/queue")
def review_queue(
    action_type: str | None = Query(None, description="예: 삭제대상"),
    response_status: str | None = Query(None, description="예: 미확인"),
    limit: int = 100,
):
    """검수 대상 — 수집분·업로드분 통합, 위험도 순."""
    return review.queue(action_type, response_status, limit)


@router.get("/fields")
def editable_fields():
    """재분류 가능한 항목과 허용값 (화면 드롭다운 구성용)."""
    return {f: (sorted(v) if v else None) for f, v in review.EDITABLE.items()}


@router.patch("/{table}/{target_id}")
def reclassify(table: str, target_id: str, body: ReclassifyBody):
    """AI 판정을 담당자 판정으로 교체하고 이력을 남긴다."""
    try:
        return review.reclassify(table, target_id, body.changes, body.reason)
    except review.ReviewError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/history")
def all_history(limit: int = 100):
    return review.history(limit=limit)


@router.get("/{table}/{target_id}/history")
def item_history(table: str, target_id: str):
    return review.history(table, target_id)
