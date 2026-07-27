"""x 크롤러 파싱 단위 테스트 (네트워크·DB 없음).

실행: .venv\\Scripts\\python.exe tests\\test_x.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from datetime import datetime, timezone
from app.crawlers.x import parse_tweets, _parse_iso, crawl_x

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


PAYLOAD = {
    "data": [
        {"id": "111", "text": "군면제 방법 정리\n둘째 줄", "author_id": "u1",
         "created_at": "2026-07-04T11:03:10.000Z"},
        {"id": "222", "text": "오래된 트윗", "author_id": "u2",
         "created_at": "2020-01-01T10:00:00.000Z"},
        {"id": "333", "text": "   ", "author_id": "u1",  # 빈 텍스트 → 제외
         "created_at": "2026-07-04T12:00:00.000Z"},
    ],
    "includes": {"users": [
        {"id": "u1", "username": "someuser"},
        {"id": "u2", "username": "olduser"},
    ]},
}

cutoff = datetime(2026, 7, 3, tzinfo=timezone.utc)
rows = parse_tweets(PAYLOAD, cutoff)

check("유효 1건만 (옛글·빈텍스트 제외)", len(rows) == 1, f"got {len(rows)}")
check("source_type=SNS", rows[0]["source_type"] == "SNS")
check("title은 첫 줄", rows[0]["title"] == "군면제 방법 정리", f"got {rows[0]['title']}")
check("content는 전체 텍스트", rows[0]["content"] == "군면제 방법 정리\n둘째 줄")
check("url은 상태 링크", rows[0]["url"] == "https://x.com/i/status/111")
check("author는 @username 매핑", rows[0]["author"] == "@someuser")
check("created_at → UTC", rows[0]["published_at"] == "2026-07-04T11:03:10+00:00",
      f"got {rows[0]['published_at']}")

# username 없는 author_id → "X"
NO_USER = {"data": [{"id": "444", "text": "익명", "author_id": "zzz",
                     "created_at": "2026-07-04T11:00:00.000Z"}], "includes": {}}
check("username 못 찾으면 author=X", parse_tweets(NO_USER, cutoff)[0]["author"] == "X")
check("잘못된 created_at → None", _parse_iso("어제") is None)

# no-op: 자격증명 미설정 시 예외 없이 0 반환
check("자격증명 없으면 no-op(0)", crawl_x("sid", ["병무청"]) == 0)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
