from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

_HTML_PATH = Path(__file__).resolve().parent.parent / "dashboard.html"


@router.get("/", response_class=HTMLResponse)
def dashboard():
    """운영자용 대시보드 (단일 HTML). 매 요청 시 파일을 읽어 수정 즉시 반영."""
    return _HTML_PATH.read_text(encoding="utf-8")
