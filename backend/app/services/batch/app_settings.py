"""애플리케이션 설정 저장소 (app_settings 테이블). 위험 임계값 등."""
from app.core.database import supabase

DEFAULT_RISK_THRESHOLD = 70


def get_settings() -> dict:
    try:
        rows = supabase.table("app_settings").select("key, value").execute().data
    except Exception:
        rows = []
    d = {r["key"]: r["value"] for r in rows}
    try:
        rt = int(d.get("risk_threshold", DEFAULT_RISK_THRESHOLD))
    except (TypeError, ValueError):
        rt = DEFAULT_RISK_THRESHOLD
    return {"risk_threshold": max(0, min(100, rt))}


def get_risk_threshold() -> int:
    return get_settings()["risk_threshold"]


def set_risk_threshold(value: int) -> int:
    value = max(0, min(100, int(value)))
    supabase.table("app_settings").upsert({"key": "risk_threshold", "value": str(value)}).execute()
    return value
