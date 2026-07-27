"""tiktok 크롤러 파싱 단위 테스트 (네트워크·DB 없음).

실행: .venv\\Scripts\\python.exe tests\\test_tiktok.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from datetime import datetime, timezone
from app.crawlers.tiktok import parse_research_videos, crawl_tiktok

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


# create_time은 epoch(UTC). 2026-07-04 11:03:10 UTC = 1783163... 계산 대신 알려진 값 사용.
T_NEW = int(datetime(2026, 7, 4, 11, 3, 10, tzinfo=timezone.utc).timestamp())
T_OLD = int(datetime(2020, 1, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp())

PAYLOAD = {"data": {"videos": [
    {"id": "9001", "video_description": "군면제 꿀팁\n둘째 줄", "username": "creator1",
     "create_time": T_NEW, "region_code": "KR"},
    {"id": "9002", "video_description": "옛날 영상", "username": "creator2",
     "create_time": T_OLD, "region_code": "KR"},
    {"id": "9003", "video_description": "", "username": "creator3",  # 설명 없음 → 제외
     "create_time": T_NEW, "region_code": "KR"},
]}}

cutoff = datetime(2026, 7, 3, tzinfo=timezone.utc)
rows = parse_research_videos(PAYLOAD, cutoff)

check("유효 1건만 (옛글·설명없음 제외)", len(rows) == 1, f"got {len(rows)}")
check("source_type=SNS", rows[0]["source_type"] == "SNS")
check("title은 설명 첫 줄", rows[0]["title"] == "군면제 꿀팁", f"got {rows[0]['title']}")
check("content는 전체 설명", rows[0]["content"] == "군면제 꿀팁\n둘째 줄")
check("url은 영상 링크",
      rows[0]["url"] == "https://www.tiktok.com/@creator1/video/9001", f"got {rows[0]['url']}")
check("author는 @username", rows[0]["author"] == "@creator1")
check("create_time epoch → UTC ISO", rows[0]["published_at"] == "2026-07-04T11:03:10+00:00",
      f"got {rows[0]['published_at']}")

# videos 키 없어도 예외 없이 빈 목록
check("빈 응답 → []", parse_research_videos({"data": {}}, cutoff) == [])

# no-op: 자격증명 미설정 시 예외 없이 0 반환
check("자격증명 없으면 no-op(0)", crawl_tiktok("sid", ["병무청"]) == 0)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
