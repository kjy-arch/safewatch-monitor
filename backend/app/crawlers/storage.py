from app.core.database import supabase


def existing_urls(urls: list[str]) -> set[str]:
    """이미 저장된 URL 집합을 한 번의 쿼리로 조회."""
    if not urls:
        return set()
    rows = (
        supabase.table("crawled_articles")
        .select("url")
        .in_("url", urls)
        .execute()
        .data
    )
    return {r["url"] for r in rows}


def save_articles(rows: list[dict]) -> int:
    """URL 중복을 제거하고 일괄 저장. 실제 저장된 건수 반환.

    crawled_articles.url의 UNIQUE 제약을 이용해 ON CONFLICT DO NOTHING으로
    저장하므로, 동시 실행(스케줄 + 수동 크롤링)에도 중복·유실이 없다.
    """
    unique: dict[str, dict] = {}
    for r in rows:
        unique.setdefault(r["url"], r)
    if not unique:
        return 0

    res = (
        supabase.table("crawled_articles")
        .upsert(list(unique.values()), on_conflict="url", ignore_duplicates=True)
        .execute()
    )
    return len(res.data or [])
