"""배치 엑셀 파싱 테스트 — 원문 열 선택 우선순위 (네트워크·DB 불필요).

실행: .venv\\Scripts\\python.exe tests\\test_batch_excel.py
"""
import os, sys
from io import BytesIO

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

import openpyxl
from app.services.batch.excel import parse_excel

failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


def build(rows: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


BODY = "지금 172에 53kg인데 5kg만 빼면 공익 가능하냐?"

print("[원문 열 선택 우선순위]")
# 제목·내용이 함께 있으면 반드시 '내용'을 원문으로 — 제목만 분류되면 본문이 통째로 누락된다
rows = parse_excel(build([["제목", "내용", "출처", "링크"],
                          ["공익 문의", BODY, "커뮤니티", "http://x.test/1"]]))
check("제목보다 내용 우선", rows and rows[0]["text"] == BODY, f"got {rows[0]['text'] if rows else None!r}")
check("출처 인식", rows and rows[0]["source_type"] == "커뮤니티")
check("링크 인식", rows and rows[0]["source_url"] == "http://x.test/1")

# '원문'은 '내용'보다도 앞선다 (Monitor 산출 엑셀 형식)
rows = parse_excel(build([["내용", "원문"], ["짧은 요약", BODY]]))
check("내용보다 원문 우선", rows and rows[0]["text"] == BODY, f"got {rows[0]['text'] if rows else None!r}")

# 본문 계열이 없으면 제목이라도 쓴다
rows = parse_excel(build([["제목", "출처"], ["군면제 방법 문의", "커뮤니티"]]))
check("본문 없으면 제목 사용", rows and rows[0]["text"] == "군면제 방법 문의",
      f"got {rows[0]['text'] if rows else None!r}")

print("\n[헤더 탐지]")
# Monitor 산출 엑셀은 1행이 제목 행(병합) — 그 아래 진짜 헤더를 찾아야 한다
rows = parse_excel(build([["SafeWatch Monitor 수집 결과 — 2026년", None, None],
                          ["원문", "출처", "링크"],
                          [BODY, "커뮤니티", "http://x.test/9"]]))
check("상단 제목행 건너뛰기", rows and rows[0]["text"] == BODY, f"got {rows[0]['text'] if rows else None!r}")

print("\n[기타]")
rows = parse_excel(build([["원문"], [BODY], [""], ["   "]]))
check("빈 행 제외", len(rows) == 1, f"got {len(rows)}")

rows = parse_excel(build([["원문", "출처"], [BODY, "이상한출처"]]))
check("알 수 없는 출처는 '언론'으로", rows and rows[0]["source_type"] == "언론",
      f"got {rows[0]['source_type'] if rows else None!r}")

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
