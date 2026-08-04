from fastapi import APIRouter
from app.core.database import supabase
from app.services import keyword_scorer

router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    sources = supabase.table("crawl_sources").select("name").execute().data
    # 사전 필터는 keyword_scores.json이 없으면 조용히 꺼진다(전건 Gemini 호출 → 비용 급증).
    # 설치 누락을 로그가 아니라 화면에서 바로 알 수 있게 상태로 노출한다.
    prefilter_on = keyword_scorer.is_enabled()
    return {
        "status": "ok",
        "message": "SafeWatch Monitor API is running",
        "crawl_sources": len(sources),
        "prefilter": {
            "enabled": prefilter_on,
            "warning": None if prefilter_on else (
                "키워드 사전 필터 비활성 — 모든 글이 Gemini로 분류되어 API 비용이 크게 늘어납니다. "
                "backend에서 build_keyword_scores.py를 실행하세요."
            ),
        },
    }
