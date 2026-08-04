"""통합 파서 테스트 — 두 축 정규화·점수 보정 (API 호출 없음).

실행: .venv\\Scripts\\python.exe tests\\test_unified_prompt.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from app.services.unified_prompt import parse_unified, DELETE_SCORE_FLOOR

failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


print("[축 A — 병무청 7분류]")
r = parse_unified({"label_l2": "브로커의심", "subject": "병무관련", "false_score": 95,
                   "category": "편법·속임수·공정성 훼손"})
check("라벨 유지", r["label_l2"] == "브로커의심")
check("L1 파생", r["label_l1"] == "조장정보")
check("과목 유지", r["subject"] == "병무관련")

r = parse_unified({"label_l2": "없는라벨", "subject": "없는과목"})
check("미지 라벨 → 단순내용", r["label_l2"] == "단순내용")
check("미지 과목 → 기타", r["subject"] == "기타")
check("단순 라벨 → 단순병역정보", r["label_l1"] == "단순병역정보")

print("\n[축 B — 가이드라인]")
r = parse_unified({"label_l2": "방법안내", "category": "허위·조작"})
check("삭제기준 유지", r["category"] == "허위·조작")
check("조치유형 결정적 매핑", r["action_type"] == "삭제대상")

r = parse_unified({"label_l2": "단순내용", "category": "정책비판", "action_type": "종합판단"})
check("정책비판은 AI 판단 존중", r["action_type"] == "종합판단")

r = parse_unified({"label_l2": "단순내용", "category": "정책비판", "action_type": "이상한값"})
check("잘못된 조치유형 → 비대상", r["action_type"] == "비대상")

r = parse_unified({"label_l2": "단순내용", "intent_type": "엉뚱", "content_type": "엉뚱"})
check("미지 의도유형 → 불명확", r["intent_type"] == "불명확")
check("미지 내용유형 → 문제없음", r["content_type"] == "문제없음")

print("\n[점수 보정]")
# 라벨 구간 클램프 — 브로커의심은 90~100
r = parse_unified({"label_l2": "브로커의심", "false_score": 10, "category": "해당없음"})
check("구간 하한으로 끌어올림", r["false_score"] == 90, f"got {r['false_score']}")
check("높음 판정", r["false_level"] == "높음")

r = parse_unified({"label_l2": "단순내용", "false_score": 99, "category": "해당없음"})
check("구간 상한으로 내림", r["false_score"] == 33, f"got {r['false_score']}")
check("낮음 판정", r["false_level"] == "낮음")

# 삭제대상 하한 — 축 A가 낮게 봐도 삭제대상이면 '높음'까지 올린다
r = parse_unified({"label_l2": "단순내용", "false_score": 10, "category": "허위·조작"})
check("삭제대상은 하한 적용", r["false_score"] == DELETE_SCORE_FLOOR, f"got {r['false_score']}")
check("삭제대상은 높음", r["false_level"] == "높음")
check("삭제대상인데 낮음인 모순 없음",
      not (r["action_type"] == "삭제대상" and r["false_level"] == "낮음"))

r = parse_unified({"label_l2": "브로커의심", "false_score": 95, "category": "허위·조작"})
check("하한이 상위 점수를 깎지 않음", r["false_score"] == 95, f"got {r['false_score']}")

r = parse_unified({"label_l2": "단순내용", "false_score": "숫자아님", "category": "해당없음"})
check("비정상 점수 → 구간 하한", r["false_score"] == 0, f"got {r['false_score']}")

print("\n[부서 — 복수 매칭]")
r = parse_unified({"label_l2": "단순내용", "department_names": ["가", "나", "다"]})
check("최대 2개로 제한", r["department_names"] == ["가", "나"], f"got {r['department_names']}")
r = parse_unified({"label_l2": "단순내용", "department_names": "단일문자열"})
check("문자열도 허용", r["department_names"] == ["단일문자열"])
r = parse_unified({"label_l2": "단순내용"})
check("없으면 빈 배열", r["department_names"] == [])

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
