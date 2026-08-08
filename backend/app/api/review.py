"""검수·재분류 API (Phase 6, 요구 Q3)."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import exclusions, review

router = APIRouter(prefix="/review", tags=["review"])


class ReclassifyBody(BaseModel):
    changes: dict = Field(..., description="바꿀 항목 {필드: 값}")
    reason: str = Field("", description="재분류 사유 (이력에 남음)")


class ExclusionBody(BaseModel):
    table: Literal["crawled_articles", "articles"]
    target_id: str
    rule_type: Literal["url", "content_hash"]
    reason: str = Field(..., min_length=1, max_length=500)


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


@router.get("/exclusions")
def exclusion_rules(active_only: bool = True, limit: int = 200):
    """담당자가 등록한 URL·동일 내용 제외 규칙."""
    try:
        return exclusions.list_rules(active_only, limit)
    except Exception:
        raise HTTPException(status_code=503,
                            detail="제외 규칙을 조회할 수 없습니다. 마이그레이션 011 적용 여부를 확인하세요.")


@router.post("/exclusions")
def create_exclusion(body: ExclusionBody):
    """현재 글에서 제외 규칙을 만들고 그 글도 비대상·무관으로 바꾼다."""
    try:
        row = review.fetch_one(body.table, body.target_id)
        raw_value = (row.get("url") if body.table == "crawled_articles"
                     else row.get("source_url")) if body.rule_type == "url" else (
                         row.get("content") if body.table == "crawled_articles"
                         else row.get("original_text")
                     )
        rule = exclusions.register(body.rule_type, raw_value or "", body.reason)
        result = review.reclassify(body.table, body.target_id, {
            "action_type": "비대상",
            "response_status": "무관",
            "response_memo": f"제외 규칙: {body.reason[:500]}",
        }, body.reason)
        exclusions.record_match(rule["id"], body.table, body.target_id)
        return {"rule": rule, "review": result}
    except (review.ReviewError, exclusions.ExclusionError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=503,
                            detail="제외 규칙을 저장할 수 없습니다. 마이그레이션 011 적용 여부를 확인하세요.")


@router.delete("/exclusions/{rule_id}")
def deactivate_exclusion(rule_id: str):
    try:
        return exclusions.deactivate(rule_id)
    except exclusions.ExclusionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=503,
                            detail="제외 규칙을 해제할 수 없습니다. 마이그레이션 011 적용 여부를 확인하세요.")


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
