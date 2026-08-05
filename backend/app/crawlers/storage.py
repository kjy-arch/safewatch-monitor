from app.core.database import supabase

# 같은 글이 다른 URL로 올라온 것을 잡기 위한 본문 비교 길이.
# 분기 보고서의 중복 제거(services/unified_query.py)와 같은 기준을 쓴다.
DEDUP_PREFIX = 60
# 본문이 이보다 짧으면 앞부분이 우연히 겹치기 쉬워 원문 대조를 하지 않는다.
DEDUP_MIN_LEN = 30
RECENT_LIMIT = 3000   # 본문 비교 대상 — 최근 저장분


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


def _key(text: str | None) -> str:
    """중복 판정 키 — 공백을 접어 서식 차이를 흡수."""
    return " ".join((text or "").split())[:DEDUP_PREFIX]


def _recent_content_keys() -> set[str]:
    """최근 저장분의 본문 키. 조회 실패 시 빈 집합(중복 차단만 건너뛴다)."""
    try:
        rows = (
            supabase.table("crawled_articles")
            .select("content")
            .order("created_at", desc=True)
            .limit(RECENT_LIMIT)
            .execute()
            .data
        )
    except Exception as e:
        print(f"[storage] 본문 중복 조회 실패(무시): {type(e).__name__}: {e}", flush=True)
        return set()
    return {_key(r.get("content")) for r in rows
            if len((r.get("content") or "").strip()) >= DEDUP_MIN_LEN}


def save_articles(rows: list[dict]) -> int:
    """URL·본문 중복을 제거하고 일괄 저장. 실제 저장된 건수 반환.

    URL 중복은 crawled_articles.url의 UNIQUE 제약으로 DB가 막는다(ON CONFLICT DO NOTHING).
    다만 **같은 글이 다른 URL로 올라오는 경우**는 그것으로 걸러지지 않는다. 실측에서
    예비군 훈령·업무보고 영상 등이 하루에 3~6회씩 중복 수집됐고, 그만큼 Gemini 호출이
    낭비됐다. 그래서 본문 앞부분으로도 한 번 더 거른다.
    """
    unique: dict[str, dict] = {}
    for r in rows:
        unique.setdefault(r["url"], r)
    if not unique:
        return 0

    seen = _recent_content_keys()
    deduped, skipped = [], 0
    for r in unique.values():
        body = (r.get("content") or "").strip()
        if len(body) >= DEDUP_MIN_LEN:
            k = _key(body)
            if k in seen:
                skipped += 1
                continue
            seen.add(k)
        deduped.append(r)

    if skipped:
        print(f"[storage] 본문 중복 {skipped}건 제외 (다른 URL·같은 내용)", flush=True)
    if not deduped:
        return 0

    res = (
        supabase.table("crawled_articles")
        .upsert(deduped, on_conflict="url", ignore_duplicates=True)
        .execute()
    )
    return len(res.data or [])
