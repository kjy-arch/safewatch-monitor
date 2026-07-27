import httpx
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.crawlers.storage import save_articles

# X API v2 recent search (최근 7일). 무료 티어 폐지 — Bearer 토큰(유료/pay-per-use) 필요.
# 읽기 과금(~$0.005/read)이므로 키워드당 max_results를 작게 유지.
SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
MAX_RESULTS = 10
RATE_LIMIT_ABORT = 2  # 연속 429(속도/크레딧) 이 횟수면 남은 키워드 중단


def _get_cutoff() -> datetime:
    """어제 00:00 KST 기준 UTC."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def _parse_iso(ts: str) -> datetime | None:
    """X created_at: '2026-07-04T11:03:10.000Z'."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def parse_tweets(payload: dict, cutoff: datetime) -> list[dict]:
    """recent search 응답 → row 목록. includes.users로 author_id→@username 매핑."""
    users = {
        u["id"]: u.get("username", "")
        for u in payload.get("includes", {}).get("users", [])
    }
    out = []
    for t in payload.get("data", []):
        post_dt = _parse_iso(t.get("created_at", ""))
        if post_dt and post_dt < cutoff:
            continue

        text = (t.get("text") or "").strip()
        if not text:
            continue

        tid = t.get("id", "")
        username = users.get(t.get("author_id"), "")
        out.append({
            "source_type":  "SNS",
            "title":        text.splitlines()[0][:100],
            "content":      text[:2000],
            "url":          f"https://x.com/i/status/{tid}",
            "author":       f"@{username}" if username else "X",
            "published_at": (post_dt or datetime.now(timezone.utc)).isoformat(),
        })
    return out


def crawl_x(source_id: str, keywords: list[str]) -> int:
    """X 최근 게시물(한국어) 수집 — 어제 이후만. X_BEARER_TOKEN 미설정 시 no-op."""
    token = settings.X_BEARER_TOKEN
    if not token:
        print("[x] 자격증명(X_BEARER_TOKEN) 미설정 — 건너뜀")
        return 0

    saved = 0
    failed = 0
    rate_limited = 0
    cutoff = _get_cutoff()
    start_time = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")  # RFC 3339
    headers = {"Authorization": f"Bearer {token}"}

    for keyword in keywords:
        try:
            r = httpx.get(
                SEARCH_URL,
                params={
                    "query":        f"{keyword} lang:ko -is:retweet",
                    "max_results":  MAX_RESULTS,
                    "start_time":   start_time,
                    "tweet.fields": "created_at,author_id",
                    "expansions":   "author_id",
                    "user.fields":  "username",
                },
                headers=headers,
                timeout=10,
            )
            if r.status_code == 429:
                rate_limited += 1
                failed += 1
                print(f"[x] '{keyword}' HTTP 429 (속도/크레딧 제한 {rate_limited}회)")
                if rate_limited >= RATE_LIMIT_ABORT:
                    print("[x] 연속 429 — 이번 실행 중단 (다음 실행에서 재시도)")
                    break
                continue
            if r.status_code != 200:
                print(f"[x] '{keyword}' HTTP {r.status_code}")
                failed += 1
                continue
            rate_limited = 0

            rows = parse_tweets(r.json(), cutoff)
            for row in rows:
                row["source_id"] = source_id
            saved += save_articles(rows)

        except Exception as e:
            print(f"[x] '{keyword}' 수집 실패: {type(e).__name__}: {e}")
            failed += 1
            continue

    if failed:
        print(f"[x] 키워드 {len(keywords)}개 중 {failed}개 실패")
    return saved
