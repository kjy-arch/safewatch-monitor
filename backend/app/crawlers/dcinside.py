import httpx, re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from app.crawlers.storage import existing_urls, save_articles

GALLERIES = [
    ("군대", "arm"),
    ("국방부", "ministry_of_national_defense"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.dcinside.com",
}


def _get_cutoff() -> datetime:
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def _parse_dc_date(text: str) -> datetime | None:
    """디시 날짜 형식 파싱: '26.06.04 13:22' 또는 '13:22' (오늘)."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    try:
        if re.match(r"^\d{2}\.\d{2}\.\d{2}", text):
            dt = datetime.strptime(text.strip(), "%y.%m.%d %H:%M")
            dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
        elif re.match(r"^\d{2}:\d{2}", text):
            # 오늘 날짜
            t = datetime.strptime(text.strip(), "%H:%M")
            dt = now_kst.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        else:
            return None
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def crawl_dcinside(source_id: str, keywords: list[str]) -> int:
    """디시인사이드 갤러리 검색글 수집 — 어제 이후 게시물만."""
    saved = 0
    failed = 0
    cutoff = _get_cutoff()

    for keyword in keywords:
        for gallery_name, gallery_id in GALLERIES:
            try:
                res = httpx.get(
                    "https://search.dcinside.com/post/p/1/sort/latest",
                    params={"q": keyword, "gid": gallery_id},
                    headers=HEADERS,
                    timeout=10,
                    follow_redirects=True,
                )
                if res.status_code != 200:
                    print(f"[dcinside:{gallery_name}] '{keyword}' HTTP {res.status_code}")
                    failed += 1
                    continue

                soup = BeautifulSoup(res.text, "html.parser")
                posts = soup.select(".sch_result_list li") or soup.select(".gall_list tr.ub-content")

                candidates = []
                for post in posts[:15]:
                    try:
                        title_tag = post.select_one("a.tit, a.title, .gall_tit a")
                        if not title_tag:
                            continue

                        # ★ 게시일 추출 및 필터
                        date_tag = post.select_one(".date, .gall_date, td.gall_date")
                        post_dt  = _parse_dc_date(date_tag.get_text(strip=True)) if date_tag else None

                        if post_dt and post_dt < cutoff:
                            break  # 최신순이므로 이후는 모두 오래된 글

                        title = title_tag.get_text(strip=True)
                        href  = title_tag.get("href", "")
                        url   = href if href.startswith("http") else f"https://www.dcinside.com{href}"
                        candidates.append((title, url, post_dt))

                    except Exception as e:
                        print(f"[dcinside:{gallery_name}] 게시글 파싱 실패: {type(e).__name__}: {e}")
                        continue

                if not candidates:
                    continue

                # 이미 저장된 글은 본문 fetch 전에 걸러냄 (일괄 조회 1회)
                dup = existing_urls([url for _, url, _ in candidates])

                rows = []
                for title, url, post_dt in candidates:
                    if url in dup:
                        continue
                    content = _get_post_content(url) or title
                    rows.append({
                        "source_id":    source_id,
                        "source_type":  "커뮤니티",
                        "title":        title,
                        "content":      content[:2000],
                        "url":          url,
                        "author":       f"디시 {gallery_name}갤",
                        "published_at": (post_dt or datetime.now(timezone.utc)).isoformat(),
                    })

                saved += save_articles(rows)

            except Exception as e:
                print(f"[dcinside:{gallery_name}] '{keyword}' 수집 실패: {type(e).__name__}: {e}")
                failed += 1
                continue

    if failed:
        print(f"[dcinside] 키워드×갤러리 {len(keywords) * len(GALLERIES)}건 중 {failed}건 실패")
    return saved


def _get_post_content(url: str) -> str:
    try:
        res = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        soup = BeautifulSoup(res.text, "html.parser")
        div = soup.select_one(".write_div, .post-content, #viewContent")
        if div:
            return re.sub(r"\s+", " ", div.get_text()).strip()
    except Exception as e:
        print(f"[dcinside] 본문 조회 실패: {type(e).__name__}: {e}")
    return ""
