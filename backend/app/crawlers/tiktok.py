import httpx
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.crawlers.storage import save_articles

# TikTok Research API — 공개 영상을 키워드로 질의. 무료지만 학술·비영리·정부 심사 승인 필요.
# OAuth2 client_credentials로 access_token을 발급받은 뒤 video/query를 호출한다.
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
QUERY_URL = "https://open.tiktokapis.com/v2/research/video/query/"
VIDEO_FIELDS = "id,video_description,create_time,username,region_code"
MAX_COUNT = 20


def _get_cutoff() -> datetime:
    """어제 00:00 KST 기준 UTC."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def _get_access_token(client_key: str, client_secret: str) -> str | None:
    """client_credentials 그랜트로 access_token 발급."""
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "client_key":    client_key,
                "client_secret": client_secret,
                "grant_type":    "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"[tiktok] 토큰 발급 HTTP {r.status_code}")
            return None
        return r.json().get("access_token")
    except Exception as e:
        print(f"[tiktok] 토큰 발급 실패: {type(e).__name__}: {e}")
        return None


def parse_research_videos(payload: dict, cutoff: datetime) -> list[dict]:
    """video/query 응답 → row 목록. 컷오프 이전·설명 없는 영상 제외."""
    out = []
    for v in payload.get("data", {}).get("videos", []):
        desc = (v.get("video_description") or "").strip()
        if not desc:
            continue

        create_time = v.get("create_time")
        post_dt = (
            datetime.fromtimestamp(create_time, tz=timezone.utc)
            if isinstance(create_time, (int, float)) else None
        )
        if post_dt and post_dt < cutoff:
            continue

        vid = v.get("id", "")
        username = v.get("username", "")
        out.append({
            "source_type":  "SNS",
            "title":        desc.splitlines()[0][:100],
            "content":      desc[:2000],
            "url":          f"https://www.tiktok.com/@{username}/video/{vid}",
            "author":       f"@{username}" if username else "틱톡",
            "published_at": (post_dt or datetime.now(timezone.utc)).isoformat(),
        })
    return out


def crawl_tiktok(source_id: str, keywords: list[str]) -> int:
    """틱톡 Research API 영상 수집 — 어제 이후만.

    TIKTOK_CLIENT_KEY·TIKTOK_CLIENT_SECRET 미설정 시 no-op.
    """
    client_key = settings.TIKTOK_CLIENT_KEY
    client_secret = settings.TIKTOK_CLIENT_SECRET
    if not client_key or not client_secret:
        print("[tiktok] 자격증명(TIKTOK_CLIENT_KEY / _CLIENT_SECRET) 미설정 — 건너뜀")
        return 0

    token = _get_access_token(client_key, client_secret)
    if not token:
        return 0

    saved = 0
    failed = 0
    cutoff = _get_cutoff()
    # Research API는 start_date/end_date(YYYYMMDD, UTC)로 기간을 제한
    now_utc = datetime.now(timezone.utc)
    start_date = cutoff.strftime("%Y%m%d")
    end_date = now_utc.strftime("%Y%m%d")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    for keyword in keywords:
        try:
            r = httpx.post(
                QUERY_URL,
                params={"fields": VIDEO_FIELDS},
                json={
                    "query": {"and": [
                        {"operation": "IN", "field_name": "keyword",
                         "field_values": [keyword]},
                    ]},
                    "start_date": start_date,
                    "end_date":   end_date,
                    "max_count":  MAX_COUNT,
                },
                headers=headers,
                timeout=15,
            )
            if r.status_code != 200:
                print(f"[tiktok] '{keyword}' video/query HTTP {r.status_code}")
                failed += 1
                continue

            rows = parse_research_videos(r.json(), cutoff)
            for row in rows:
                row["source_id"] = source_id
            saved += save_articles(rows)

        except Exception as e:
            print(f"[tiktok] '{keyword}' 수집 실패: {type(e).__name__}: {e}")
            failed += 1
            continue

    if failed:
        print(f"[tiktok] 키워드 {len(keywords)}개 중 {failed}개 실패")
    return saved
