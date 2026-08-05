"""통합 조회 중복 제거 테스트 (네트워크·DB 불필요).

분기 보고서가 같은 글을 두 번 세지 않는지가 핵심. 수집 엑셀을 다시 올려
재분류한 배치가 실제로 있어(314행 전량 중복) 이중 계상 위험이 있었다.

실행: .venv\\Scripts\\python.exe tests\\test_unified_query.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from app.services.unified_query import merge, normalize_crawled, normalize_uploaded

failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


BODY = "지금 172에 53kg인데 눈 딱감고 5kg만 빡세게 빼면 공익 가능하냐? 확정임?"

print("[정규화]")
c = normalize_crawled({"content": BODY, "url": "http://a", "source_type": "커뮤니티",
                       "category": "편법·속임수·공정성 훼손", "false_level": "높음"})
u = normalize_uploaded({"original_text": BODY, "source_url": "링크 바로가기",
                        "source_type": "커뮤니티", "category": None})
check("수집분 origin", c["origin"] == "수집")
check("업로드분 origin", u["origin"] == "업로드")
check("수집분 본문은 content에서", c["text"] == BODY)
check("업로드분 본문은 original_text에서", u["text"] == BODY)

print("\n[중복 제거]")
rows, removed = merge([c], [u])
check("같은 글은 1건으로", len(rows) == 1, f"got {len(rows)}")
check("제거 건수 보고", removed == 1, f"got {removed}")
check("분석이 채워진 쪽을 남김", rows[0]["category"] == "편법·속임수·공정성 훼손",
      f"got {rows[0]['category']!r}")

# URL이 서로 달라도(하이퍼링크 표시 텍스트) 원문으로 잡아야 한다
check("URL이 달라도 중복 판정", rows[0]["url"] in ("http://a", "링크 바로가기"))

# 업로드분에만 분석이 있으면 그쪽을 남긴다
c2 = normalize_crawled({"content": BODY, "category": None})
u2 = normalize_uploaded({"original_text": BODY, "category": "허위·조작"})
rows, removed = merge([c2], [u2])
check("수집분이 비면 업로드분 채택", rows[0]["category"] == "허위·조작", f"got {rows[0]['category']!r}")

# 둘 다 분석이 있으면 원본(수집분) 유지
c3 = normalize_crawled({"content": BODY, "category": "정상정보"})
u3 = normalize_uploaded({"original_text": BODY, "category": "허위·조작"})
rows, _ = merge([c3], [u3])
check("둘 다 있으면 수집분 우선", rows[0]["origin"] == "수집", f"got {rows[0]['origin']}")

print("\n[서식 차이 흡수]")
c4 = normalize_crawled({"content": BODY})
u4 = normalize_uploaded({"original_text": "  지금 172에  53kg인데 눈 딱감고 5kg만 빡세게 빼면 공익 가능하냐? 확정임?  "})
rows, removed = merge([c4], [u4])
check("공백 차이는 같은 글로", len(rows) == 1 and removed == 1, f"got {len(rows)}건 / 제거 {removed}")

print("\n[중복 아닌 경우]")
c5 = normalize_crawled({"content": "군면제 받는법 아는사람 있냐 진짜 급하다 도와줘라 제발"})
u5 = normalize_uploaded({"original_text": "병무청이 병역판정검사 일정을 변경한다고 공지했다 자세한 내용은"})
rows, removed = merge([c5], [u5])
check("다른 글은 둘 다 유지", len(rows) == 2 and removed == 0, f"got {len(rows)}건 / 제거 {removed}")

# 원문이 비면 중복 판정 불가 — 합치지 말고 그대로 둔다
rows, removed = merge([normalize_crawled({"content": ""})], [normalize_uploaded({"original_text": ""})])
check("빈 원문은 합치지 않음", len(rows) == 2 and removed == 0, f"got {len(rows)}건")

print("\n[순서 보존]")
a = normalize_crawled({"content": "가나다라마바사아자차카타파하 첫 번째 글입니다 내용"})
b = normalize_crawled({"content": "두 번째 글입니다 다른 내용이 들어 있습니다 확인용"})
rows, _ = merge([a, b], [])
check("입력 순서 유지", [r["text"][:5] for r in rows] == ["가나다라마", "두 번째 "],
      f"got {[r['text'][:5] for r in rows]}")

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
