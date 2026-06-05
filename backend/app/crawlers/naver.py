import httpx, re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from app.core.config import settings
from app.core.database import supabase

NAVER_HEADERS = {
    "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
}

TYPE_MAP = {
    "naver_news":  ("news",         "언론"),
    "naver_blog":  ("blog",         "SNS"),
    "naver_cafe":  ("cafearticle",  "커뮤니티"),
}


def _get_cutoff() -> datetime:
    """어제 00:00 KST (UTC+9) 기준 — 이 시각 이후 게시물만 수집."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def _parse_date(date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>|&[a-z]+;", "", text).strip()


def crawl_naver(source_id: str, source_type: str, keywords: list[str]) -> int:
    """네이버 뉴스/블로그/카페 크롤링 — 어제 이후 게시물만 저장."""
    if source_type not in TYPE_MAP:
        return 0

    api_type, article_source_type = TYPE_MAP[source_type]
    cutoff = _get_cutoff()
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

            for item in res.json().get("items", []):
                pub_at = _parse_date(item.get("pubDate", ""))

                # ★ 어제 00:00 이전 게시물은 건너뜀
                # 최신순 정렬이므로 cutoff보다 오래되면 이후 항목도 모두 오래된 것
                if pub_at < cutoff:
                    break

                title   = _clean(item.get("title", ""))
                content = _clean(item.get("description", ""))
                url     = item.get("originallink") or item.get("link", "")
                author  = item.get("bloggername") or item.get("cafename") or ""

                if not content:
                    continue

                # URL 중복 방지 (2차 안전망)
                if supabase.table("crawled_articles").select("id").eq("url", url).execute().data:
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
