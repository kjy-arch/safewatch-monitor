import httpx
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from app.crawlers.storage import save_articles

BASE = "https://www.fmkorea.com"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": BASE,
}


def _get_cutoff() -> datetime:
    """어제 00:00 KST 기준 UTC."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def _parse_time(text: str) -> datetime | None:
    """에펨 검색결과 시각: '2026-07-02 21:06'."""
    try:
        dt = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)
    except Exception:
        return None


def parse_search_results(html: str, cutoff: datetime) -> list[dict]:
    """검색 결과 HTML → (제목/내용/url/게시일) 목록. 컷오프 이전 글 제외."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select(".searchResult li")[:15]:
        try:
            a = li.select_one("dt a")
            if not a:
                continue
            time_tag = li.select_one(".time")
            post_dt = _parse_time(time_tag.get_text(strip=True)) if time_tag else None
            # 정렬이 보장되지 않으므로 break 대신 건별 skip
            if post_dt and post_dt < cutoff:
                continue

            title = a.get_text(strip=True)
            href = a.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"
            dd = li.select_one("dd")
            content = dd.get_text(" ", strip=True) if dd else title

            out.append({
                "title":        title,
                "content":      content[:2000],
                "url":          url,
                "published_at": (post_dt or datetime.now(timezone.utc)).isoformat(),
            })
        except Exception as e:
            print(f"[fmkorea] 게시글 파싱 실패: {type(e).__name__}: {e}")
            continue
    return out


def crawl_fmkorea(source_id: str, keywords: list[str]) -> int:
    """에펨코리아 통합검색 수집 — 어제 이후 게시물만."""
    saved = 0
    failed = 0
    cutoff = _get_cutoff()

    for keyword in keywords:
        try:
            res = httpx.get(
                f"{BASE}/search.php",
                params={"mid": "home", "act": "IS", "is_keyword": keyword,
                        "where": "document"},
                headers=HEADERS,
                timeout=15,
                follow_redirects=True,
            )
            if res.status_code != 200:
                print(f"[fmkorea] '{keyword}' HTTP {res.status_code}")
                failed += 1
                continue

            rows = [{
                "source_id":   source_id,
                "source_type": "커뮤니티",
                "author":      "에펨코리아",
                **item,
            } for item in parse_search_results(res.text, cutoff)]

            saved += save_articles(rows)

        except Exception as e:
            print(f"[fmkorea] '{keyword}' 수집 실패: {type(e).__name__}: {e}")
            failed += 1
            continue

    if failed:
        print(f"[fmkorea] 키워드 {len(keywords)}개 중 {failed}개 실패")
    return saved
