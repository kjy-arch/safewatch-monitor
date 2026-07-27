"""instagram 크롤러 파싱 단위 테스트 (네트워크·DB 없음).

실행: .venv\\Scripts\\python.exe tests\\test_instagram.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from datetime import datetime, timezone
from app.crawlers.instagram import parse_hashtag_media, _to_hashtag, _parse_ts, crawl_instagram

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


ITEMS = [
    {"id": "1", "caption": "병역면탈 방법 공유\n두번째줄",
     "permalink": "https://www.instagram.com/p/AAA/", "timestamp": "2026-07-04T11:03:10+0000"},
    {"id": "2", "caption": "오래된 글",
     "permalink": "https://www.instagram.com/p/BBB/", "timestamp": "2020-01-01T10:00:00+0000"},
    {"id": "3", "caption": "",  # 캡션 없는 이미지-only → 제외
     "permalink": "https://www.instagram.com/p/CCC/", "timestamp": "2026-07-04T12:00:00+0000"},
    {"id": "4", "caption": "permalink 없는 글",  # url 없음 → 제외
     "permalink": "", "timestamp": "2026-07-04T12:00:00+0000"},
]

cutoff = datetime(2026, 7, 3, tzinfo=timezone.utc)
rows = parse_hashtag_media(ITEMS, "병역면탈", cutoff)

check("유효 1건만 (옛글·캡션없음·permalink없음 제외)", len(rows) == 1, f"got {len(rows)}")
check("source_type=SNS", rows[0]["source_type"] == "SNS")
check("title은 캡션 첫 줄", rows[0]["title"] == "병역면탈 방법 공유", f"got {rows[0]['title']}")
check("content는 전체 캡션", rows[0]["content"] == "병역면탈 방법 공유\n두번째줄")
check("permalink → url", rows[0]["url"] == "https://www.instagram.com/p/AAA/")
check("author에 해시태그", rows[0]["author"] == "인스타그램 #병역면탈")
check("timestamp KST무관 UTC 변환", rows[0]["published_at"] == "2026-07-04T11:03:10+00:00",
      f"got {rows[0]['published_at']}")

check("해시태그 정규화: # 제거", _to_hashtag("#병무청") == "병무청")
check("해시태그 정규화: 공백 제거", _to_hashtag("신검 4급") == "신검4급")
check("잘못된 timestamp → None", _parse_ts("어제") is None)

# no-op: 자격증명 미설정 시 예외 없이 0 반환
check("자격증명 없으면 no-op(0)", crawl_instagram("sid", ["병무청"]) == 0)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
