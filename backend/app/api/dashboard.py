"""화면 서빙 — React 통합본(우선) / 기존 단일 HTML(폴백).

Phase 5에서 화면을 React로 통일했다. `frontend/dist`가 빌드돼 있으면 그것을 서빙하고,
빌드 전이거나 Node가 없는 환경에서는 기존 dashboard.html로 자동 폴백한다.
(설치 직후 빌드를 못 한 PC에서도 최소한 수집은 돌릴 수 있어야 하기 때문.)

빌드: frontend 폴더에서 `npm install && npm run build`
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["dashboard"])

_BACKEND_ROOT = Path(__file__).resolve().parent.parent      # backend/app
_HTML_PATH = _BACKEND_ROOT / "dashboard.html"
_DIST = _BACKEND_ROOT.parent.parent / "frontend" / "dist"   # <repo>/frontend/dist


def dist_ready() -> bool:
    return (_DIST / "index.html").is_file()


@router.get("/assets/{path:path}")
def spa_assets(path: str):
    """React 빌드 산출물(js/css/이미지). dist 밖 경로 요청은 거부한다."""
    target = (_DIST / "assets" / path).resolve()
    if not str(target).startswith(str(_DIST.resolve())) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


@router.get("/favicon.svg")
@router.get("/icons.svg")
def spa_icon_root():
    # index.html이 참조하는 public 자산 (빌드 시 dist 루트로 복사됨)
    for name in ("favicon.svg", "icons.svg"):
        f = _DIST / name
        if f.is_file():
            return FileResponse(f)
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/", response_class=HTMLResponse)
def dashboard():
    """통합 화면. React 빌드가 있으면 그것을, 없으면 기존 단일 HTML을 서빙."""
    if dist_ready():
        return FileResponse(_DIST / "index.html")
    return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))
