import sys

# Windows 콘솔(cp949)에서 로그의 em대시(—) 등 유니코드 출력 시 UnicodeEncodeError로
# 크롤/분류가 중단되는 것을 방지 — 모든 print를 UTF-8로 고정 (tests/*와 동일 패턴).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.health import router as health_router
from app.api.crawl import router as crawl_router
from app.api.dashboard import router as dashboard_router
from app.core.config import settings
from app.core.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="SafeWatch Monitor API",
    description="병무청 언론·SNS 자동 수집 및 허위정보 모니터링",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(crawl_router, prefix="/api")
app.include_router(dashboard_router)  # 대시보드는 루트(/)에 서빙
