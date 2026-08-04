from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.batch.app_settings import get_settings, set_risk_threshold

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    risk_threshold: int = Field(..., ge=0, le=100)


@router.get("")
def read_settings():
    return get_settings()


@router.put("")
def update_settings(body: SettingsUpdate):
    try:
        rt = set_risk_threshold(body.risk_threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 저장 실패: {e}")
    return {"risk_threshold": rt}
