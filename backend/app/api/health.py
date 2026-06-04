from fastapi import APIRouter
from app.core.database import supabase

router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    sources = supabase.table("crawl_sources").select("name").execute().data
    return {
        "status": "ok",
        "message": "SafeWatch Monitor API is running",
        "crawl_sources": len(sources),
    }
