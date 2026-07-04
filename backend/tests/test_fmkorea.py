"""fmkorea 크롤러 파싱 단위 테스트 (네트워크·DB 없음).

실행: .venv\\Scripts\\python.exe tests\\test_fmkorea.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from datetime import datetime, timezone
from app.crawlers.fmkorea import parse_search_results, _parse_time

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


HTML = """
<ul class="searchResult">
  <li><dl>
    <dt><a href="/10036642493">[야구] 최신 글</a><span class="time">2026-07-03 13:34</span></dt>
    <dd>본문 요약입니다</dd>
  </dl></li>
  <li><dl>
    <dt><a href="/10012345678">[자유] 오래된 글</a><span class="time">2020-01-01 10:00</span></dt>
    <dd>옛날 내용</dd>
  </dl></li>
  <li><dl>
    <dt><a href="https://www.fmkorea.com/999">절대경로 글</a><span class="time">2026-07-03 09:00</span></dt>
  </dl></li>
  <li><dl><dt>링크 없는 항목</dt></dl></li>
</ul>
"""

cutoff = datetime(2026, 7, 1, tzinfo=timezone.utc)
rows = parse_search_results(HTML, cutoff)

check("컷오프 이후 2건만 수집 (오래된 글·링크없는 항목 제외)", len(rows) == 2, f"got {len(rows)}")
check("상대경로 → 절대 URL", rows[0]["url"] == "https://www.fmkorea.com/10036642493", f"got {rows[0]['url']}")
check("절대경로 유지", rows[1]["url"] == "https://www.fmkorea.com/999")
check("dd 없으면 제목을 내용으로", rows[1]["content"] == "절대경로 글")
check("제목 추출", rows[0]["title"] == "[야구] 최신 글")
check("KST→UTC 변환", _parse_time("2026-07-03 13:34").isoformat() == "2026-07-03T04:34:00+00:00")
check("잘못된 시각 → None", _parse_time("어제") is None)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
