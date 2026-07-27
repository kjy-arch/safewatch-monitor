import re
import httpx
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.crawlers.storage import save_articles

# Meta Graph API — 인스타그램은 일반 키워드 검색이 없고 해시태그 검색만 제공.
# ig_hashtag_search로 해시태그 id를 얻은 뒤 recent_media로 최근 공개 게시물을 조회.
# 제약: IG 비즈니스/크리에이터 계정 1개당 고유 해시태그 30개 / 7일 (고정셋 반복은 1개로 카운트).
GRAPH_VERSION = "v21.0"
BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _get_cutoff() -> datetime:
    """어제 00:00 KST 기준 UTC."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def _to_hashtag(keyword: str) -> str:
    """키워드 → 해시태그 질의어. '#'·공백 제거 (해시태그는 공백 불가)."""
    return re.sub(r"\s+", "", keyword.lstrip("#"))


def _parse_ts(ts: str) -> datetime | None:
    """Graph API timestamp: '2026-07-04T11:03:10+0000'."""
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def parse_hashtag_media(items: list, tag: str, cutoff: datetime) -> list[dict]:
    """recent_media 응답의 data 항목 → row 목록. 컷오프 이전·캡션 없는 글 제외.

    캡션이 없는 이미지-only 게시물은 텍스트 분류 대상이 아니므로 건너뛴다.
    """
    out = []
    for item in items:
        caption = (item.get("caption") or "").strip()
        if not caption:
            continue

        post_dt = _parse_ts(item.get("timestamp", ""))
        if post_dt and post_dt < cutoff:
            continue

        permalink = item.get("permalink", "")
        if not permalink:
            continue

        title = caption.splitlines()[0][:100] if caption else ""
        out.append({
            "source_type":  "SNS",
            "title":        title,
            "content":      caption[:2000],
            "url":          permalink,
            "author":       f"인스타그램 #{tag}",
            "published_at": (post_dt or datetime.now(timezone.utc)).isoformat(),
        })
    return out


def crawl_instagram(source_id: str, keywords: list[str]) -> int:
    """인스타그램 해시태그 최근 게시물 수집 — 어제 이후만.

    INSTAGRAM_ACCESS_TOKEN·INSTAGRAM_BUSINESS_ACCOUNT_ID 미설정 시 no-op.
    """
    token = settings.INSTAGRAM_ACCESS_TOKEN
    ig_id = settings.INSTAGRAM_BUSINESS_ACCOUNT_ID
    if not token or not ig_id:
        print("[instagram] 자격증명(INSTAGRAM_ACCESS_TOKEN / _BUSINESS_ACCOUNT_ID) 미설정 — 건너뜀")
        return 0

    saved = 0
    failed = 0
    cutoff = _get_cutoff()

    for keyword in keywords:
        tag = _to_hashtag(keyword)
        if not tag:
            continue
        try:
            # ① 해시태그 문자열 → 해시태그 id
            r = httpx.get(
                f"{BASE}/ig_hashtag_search",
                params={"user_id": ig_id, "q": tag, "access_token": token},
                timeout=10,
            )
            if r.status_code != 200:
                print(f"[instagram] '#{tag}' 해시태그 조회 HTTP {r.status_code}")
                failed += 1
                continue
            data = r.json().get("data", [])
            if not data:
                continue
            hashtag_id = data[0].get("id")

            # ② 해시태그 id → 최근 공개 게시물
            m = httpx.get(
                f"{BASE}/{hashtag_id}/recent_media",
                params={
                    "user_id":      ig_id,
                    "fields":       "id,caption,permalink,timestamp",
                    "access_token": token,
                },
                timeout=10,
            )
            if m.status_code != 200:
                print(f"[instagram] '#{tag}' recent_media HTTP {m.status_code}")
                failed += 1
                continue

            rows = parse_hashtag_media(m.json().get("data", []), tag, cutoff)
            for row in rows:
                row["source_id"] = source_id
            saved += save_articles(rows)

        except Exception as e:
            print(f"[instagram] '#{tag}' 수집 실패: {type(e).__name__}: {e}")
            failed += 1
            continue

    if failed:
        print(f"[instagram] 키워드 {len(keywords)}개 중 {failed}개 실패")
    return saved
