"""수집 결과 엑셀 조회·생성·저장.

엑셀 서식 생성은 notifier._build_excel(이메일 첨부와 동일 서식)을 재사용한다.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.core.config import settings
from app.core.database import supabase
from app.services.notifier import _build_excel

KST = timezone(timedelta(hours=9))


def fetch_articles(scope: str = "today", false_level: str | None = None) -> list:
    """저장된 기사 조회. scope=today(오늘 수집분) | all(전체)."""
    query = supabase.table("crawled_articles").select("*, departments(name)")

    if scope == "today":
        today_start = (
            datetime.now(KST)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
        )
        query = query.gte("created_at", today_start.isoformat())
    if false_level:
        query = query.eq("false_level", false_level)

    return query.order("false_score", desc=True).limit(5000).execute().data


def export_dir() -> Path:
    """저장 폴더 — EXPORT_DIR 미설정 시 사용자 다운로드 폴더."""
    return Path(settings.EXPORT_DIR) if settings.EXPORT_DIR else Path.home() / "Downloads"


def save_export(scope: str = "today") -> str | None:
    """조회 → 엑셀 생성 → 파일로 저장. 저장 경로 반환(기사 없으면 None).

    같은 날 여러 번 실행해도 덮어쓰지 않도록 파일명에 시각(HHMM)을 넣는다.
    """
    articles = fetch_articles(scope)
    if not articles:
        return None

    out_dir = export_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"safewatch_{datetime.now(KST).strftime('%Y%m%d_%H%M')}.xlsx"
    path = out_dir / filename
    path.write_bytes(_build_excel(articles))
    return str(path)
