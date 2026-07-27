"""excel_classifier.parse_excel 단위 테스트 (네트워크·DB 없음).

실행: .venv\\Scripts\\python.exe tests\\test_excel_classifier.py
"""
import os, sys
from io import BytesIO
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

import openpyxl
from app.services.excel_classifier import parse_excel

failures = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


def _xlsx(rows):
    wb = openpyxl.Workbook(); ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO(); wb.save(buf); return buf.getvalue()


# 1) Monitor 내보내기 형태: 1행 병합타이틀 + 2행 헤더 + 데이터
data = _xlsx([
    ["SafeWatch Monitor 수집 결과 — 2026년"],                       # 타이틀 행
    ["번호", "출처", "게시일", "원문", "링크"],                      # 헤더 행
    [1, "언론", "2026-07-27", "군면제 방법 공유합니다", "http://a"],
    [2, "커뮤니티", "2026-07-27", "정신과 4급 후기", "http://b"],
    [3, "SNS", "2026-07-27", "", "http://c"],                        # 원문 빈 값 → 제외
])
rows = parse_excel(data)
check("타이틀 행 건너뛰고 원문 2건", len(rows) == 2, f"got {len(rows)}")
check("원문 추출", rows[0]["text"] == "군면제 방법 공유합니다")
check("링크 매핑", rows[0]["url"] == "http://a")
check("출처 매핑", rows[1]["source"] == "커뮤니티")

# 2) '내용' 헤더도 인식
data2 = _xlsx([["제목", "내용"], ["t", "면제 받는 법"]])
rows2 = parse_excel(data2)
check("'내용' 헤더 인식", len(rows2) == 1 and rows2[0]["text"] == "면제 받는 법",
      f"got {rows2}")

# 3) 헤더 없음 → 각 행에서 가장 긴 문자열(>=10자)을 원문으로
data3 = _xlsx([["aa", "이것은 충분히 긴 원문 문장입니다"], ["bb", "짧음"]])
rows3 = parse_excel(data3)
check("헤더 없으면 최장 문자열 사용", len(rows3) == 1 and "충분히 긴 원문" in rows3[0]["text"],
      f"got {rows3}")

# 4) 빈 워크북 → []
check("빈 엑셀 → []", parse_excel(_xlsx([])) == [])

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
