import httpx, re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from app.core.database import supabase

# 병무청 관련 갤러리
GALLERIES = [
    ("군대", "arm"),
    ("국방부", "ministry_of_national_defense"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.dcinside.com",
}


def crawl_dcinside(source_id: str, keywords: list[str]) -> int:
    """디시인사이드 갤러리 검색글 수집."""
    saved = 0

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
                    continue

                soup = BeautifulSoup(res.text, "html.parser")
                posts = soup.select(".sch_result_list li") or soup.select(".gall_list tr.ub-content")

                for post in posts[:10]:
                    try:
                        title_tag = post.select_one("a.tit, a.title, .gall_tit a")
                        if not title_tag:
                            continue

                        title = title_tag.get_text(strip=True)
                        href  = title_tag.get("href", "")
                        url   = href if href.startswith("http") else f"https://www.dcinside.com{href}"

                        # 본문 가져오기
                        content = _get_post_content(url) or title

                        exists = supabase.table("crawled_articles").select("id").eq("url", url).execute().data
                        if exists:
                            continue

                        supabase.table("crawled_articles").insert({
                            "source_id":    source_id,
                            "source_type":  "커뮤니티",
                            "title":        title,
                            "content":      content[:2000],
                            "url":          url,
                            "author":       f"디시 {gallery_name}갤",
                            "published_at": datetime.now(timezone.utc).isoformat(),
                        }).execute()
                        saved += 1

                    except Exception:
                        continue

            except Exception:
                continue

    return saved


def _get_post_content(url: str) -> str:
    try:
        res = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        soup = BeautifulSoup(res.text, "html.parser")
        content_div = soup.select_one(".write_div, .post-content, #viewContent")
        if content_div:
            return re.sub(r"\s+", " ", content_div.get_text()).strip()
    except Exception:
        pass
    return ""
