import re, time
import httpx
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from app.crawlers.storage import existing_urls, save_articles

BASE = "https://gall.dcinside.com"

# 학습자료(21~24년) URL 분석 기반 — 조장정보 실발생 상위 갤러리
# (이름, 갤러리 id, URL prefix: 정식='' / 마이너='mgallery/' / 미니='mini/')
GALLERIES = [
    ("공익", "gongik_new", ""),          # 3,546건 — 압도적 1위
    ("면제", "myunjae",    "mgallery/"),  # 222건
    ("군대", "army",       ""),           # 162건
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gall.dcinside.com",
}


def _get_cutoff() -> datetime:
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def parse_gallery_rows(html: str, cutoff: datetime) -> list[tuple]:
    """갤러리 검색 결과 HTML → (제목, url, 게시일) 목록.

    공지·설문 행(gall_num이 숫자가 아님)은 제외, 게시일은 td.gall_date의
    title 속성("2026-07-04 11:03:10", KST)에서 파싱. 컷오프 이전 글 제외.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.select(".gall_list tr.ub-content")[:20]:
        try:
            num = tr.select_one("td.gall_num")
            if not num or not num.get_text(strip=True).isdigit():
                continue  # 공지/설문

            title_tag = tr.select_one(".gall_tit a")
            if not title_tag:
                continue

            date_tag = tr.select_one("td.gall_date")
            post_dt = None
            if date_tag and date_tag.get("title"):
                try:
                    post_dt = datetime.strptime(
                        date_tag["title"].strip(), "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)
                except ValueError:
                    pass

            # 검색 결과가 최신순이지만 확신할 수 없어 break 대신 건별 skip
            if post_dt and post_dt < cutoff:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"
            out.append((title, url, post_dt))

        except Exception as e:
            print(f"[dcinside] 게시글 파싱 실패: {type(e).__name__}: {e}")
            continue
    return out


def crawl_dcinside(source_id: str, keywords: list[str]) -> int:
    """디시 갤러리 내부 검색(제목+내용) 수집 — 어제 이후 게시물만."""
    saved = 0
    failed = 0
    cutoff = _get_cutoff()

    for keyword in keywords:
        for gallery_name, gallery_id, prefix in GALLERIES:
            try:
                res = httpx.get(
                    f"{BASE}/{prefix}board/lists/",
                    params={"id": gallery_id, "s_type": "search_subject_memo",
                            "s_keyword": keyword},
                    headers=HEADERS,
                    timeout=10,
                    follow_redirects=True,
                )
                if res.status_code != 200:
                    print(f"[dcinside:{gallery_name}] '{keyword}' HTTP {res.status_code}")
                    failed += 1
                    continue

                candidates = parse_gallery_rows(res.text, cutoff)
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
                time.sleep(0.5)  # 갤러리 검색 간 소폭 대기 (요청 속도 완화)

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
