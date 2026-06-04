import httpx
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from app.core.config import settings
from app.core.database import supabase

NAVER_HEADERS = {
    "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
}

TYPE_MAP = {
    "naver_news": ("news", "언론"),
    "naver_blog": ("blog", "SNS"),
    "naver_cafe": ("cafearticle", "커뮤니티"),
}


def _parse_date(date_str: str):
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _clean(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>|&[a-z]+;", "", text).strip()


def crawl_naver(source_id: str, source_type: str, keywords: list[str]) -> int:
    """네이버 뉴스/블로그/카페 크롤링 후 DB 저장. 저장된 건수 반환."""
    if source_type not in TYPE_MAP:
        return 0

    api_type, article_source_type = TYPE_MAP[source_type]
    saved = 0

    for keyword in keywords:
        try:
            res = httpx.get(
                f"https://openapi.naver.com/v1/search/{api_type}.json",
                params={"query": keyword, "display": 20, "sort": "date"},
                headers=NAVER_HEADERS,
                timeout=10,
            )
            if res.status_code != 200:
                continue

            items = res.json().get("items", [])
            for item in items:
                title   = _clean(item.get("title", ""))
                content = _clean(item.get("description", ""))
                url     = item.get("originallink") or item.get("link", "")
                author  = item.get("bloggername") or item.get("cafename") or ""
                pub_at  = _parse_date(item.get("pubDate", ""))

                if not content:
                    continue

                # URL 중복 방지
                exists = supabase.table("crawled_articles").select("id").eq("url", url).execute().data
                if exists:
                    continue

                supabase.table("crawled_articles").insert({
                    "source_id":    source_id,
                    "source_type":  article_source_type,
                    "title":        title,
                    "content":      content,
                    "url":          url,
                    "author":       author,
                    "published_at": pub_at.isoformat(),
                }).execute()
                saved += 1

        except Exception:
            continue

    return saved
