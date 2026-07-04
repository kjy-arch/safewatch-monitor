"""dcinside 갤러리 검색 파싱 단위 테스트 (네트워크·DB 없음).

실행: .venv\\Scripts\\python.exe tests\\test_dcinside.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from datetime import datetime, timezone
from app.crawlers.dcinside import parse_gallery_rows

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


HTML = """
<table class="gall_list"><tbody>
  <tr class="ub-content">
    <td class="gall_num">설문</td>
    <td class="gall_tit"><a href="/board/view/?id=x&no=1">공지 글</a></td>
    <td class="gall_date">26/06/29</td>
  </tr>
  <tr class="ub-content">
    <td class="gall_num">3217959</td>
    <td class="gall_tit"><a href="/board/view/?id=gongik_new&no=3217959">경계선지능 공익 흔하냐</a></td>
    <td class="gall_date" title="2026-07-04 11:03:10">11:03</td>
  </tr>
  <tr class="ub-content">
    <td class="gall_num">100</td>
    <td class="gall_tit"><a href="/board/view/?id=gongik_new&no=100">아주 옛날 글</a></td>
    <td class="gall_date" title="2020-01-01 10:00:00">20.01.01</td>
  </tr>
  <tr class="ub-content">
    <td class="gall_num">200</td>
    <td class="gall_tit"><a href="/board/view/?id=gongik_new&no=200">날짜 title 없는 글</a></td>
    <td class="gall_date">07.04</td>
  </tr>
</tbody></table>
"""

cutoff = datetime(2026, 7, 3, tzinfo=timezone.utc)
rows = parse_gallery_rows(HTML, cutoff)

check("공지·옛글 제외하고 2건", len(rows) == 2, f"got {len(rows)}: {[r[0] for r in rows]}")
check("제목 추출", rows[0][0] == "경계선지능 공익 흔하냐")
check("상대경로 → 절대 URL", rows[0][1] == "https://gall.dcinside.com/board/view/?id=gongik_new&no=3217959")
check("title 속성 KST→UTC", rows[0][2].isoformat() == "2026-07-04T02:03:10+00:00",
      f"got {rows[0][2]}")
check("날짜 없는 글은 post_dt=None으로 포함", rows[1][0] == "날짜 title 없는 글" and rows[1][2] is None)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
