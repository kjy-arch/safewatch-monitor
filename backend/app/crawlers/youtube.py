import httpx
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.core.database import supabase


def _get_cutoff() -> datetime:
    """어제 00:00 KST 기준 UTC."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    yesterday_kst = (now_kst - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_kst.astimezone(timezone.utc)


def _parse_iso(date_str: str) -> datetime:
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def crawl_youtube(source_id: str, keywords: list[str]) -> int:
    """유튜브 동영상(어제 이후) + 댓글 수집 후 DB 저장."""
    saved = 0
    key = settings.YOUTUBE_API_KEY
    cutoff = _get_cutoff()
    # YouTube API publishedAfter 파라미터 (RFC 3339)
    published_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    for keyword in keywords:
        try:
            res = httpx.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part":              "snippet",
                    "q":                 keyword,
                    "type":              "video",
                    "maxResults":        10,
                    "order":             "date",
                    "regionCode":        "KR",
                    "relevanceLanguage": "ko",
                    "publishedAfter":    published_after,  # ★ 어제 이후만
                    "key":               key,
                },
                timeout=10,
            )
            if res.status_code != 200:
                continue

            for item in res.json().get("items", []):
                video_id = item["id"].get("videoId")
                if not video_id:
                    continue

                snippet      = item["snippet"]
                video_title  = snippet.get("title", "")
                channel_name = snippet.get("channelTitle", "")
                pub_str      = snippet.get("publishedAt", "")
                description  = snippet.get("description", "")
                video_url    = f"https://www.youtube.com/watch?v={video_id}"

                saved += _save(source_id, video_title,
                                description or video_title,
                                video_url, channel_name, pub_str)

                # 댓글 수집
                try:
                    c_res = httpx.get(
                        "https://www.googleapis.com/youtube/v3/commentThreads",
                        params={
                            "part": "snippet", "videoId": video_id,
                            "maxResults": 20, "order": "time", "key": key,
                        },
                        timeout=10,
                    )
                    if c_res.status_code != 200:
                        continue

                    for c in c_res.json().get("items", []):
                        top = c["snippet"]["topLevelComment"]["snippet"]
                        comment_text   = top.get("textDisplay", "")
                        comment_author = top.get("authorDisplayName", "")
                        comment_date   = top.get("publishedAt", "")
                        comment_url    = f"{video_url}&lc={c['id']}"

                        # ★ 어제 이후 댓글만
                        if _parse_iso(comment_date) < cutoff:
                            continue
                        if len(comment_text) < 10:
                            continue

                        saved += _save(source_id, f"[댓글] {video_title}",
                                       comment_text, comment_url,
                                       comment_author, comment_date)
                except Exception:
                    pass

        except Exception:
            continue

    return saved


def _save(source_id, title, content, url, author, published_at) -> int:
    try:
        if supabase.table("crawled_articles").select("id").eq("url", url).execute().data:
            return 0
        supabase.table("crawled_articles").insert({
            "source_id":    source_id,
            "source_type":  "유튜브",
            "title":        title[:200],
            "content":      content[:2000],
            "url":          url,
            "author":       author,
            "published_at": published_at,
        }).execute()
        return 1
    except Exception:
        return 0
