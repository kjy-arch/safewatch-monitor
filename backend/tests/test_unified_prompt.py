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

print("\n[모순 가드 — 풍자/비판인데 삭제대상 (2026-08-07)]")
# 2026-08-07 실측: 정치 비판 댓글 27건이 삭제대상으로 판정됐고, 그중 6건은 Gemini가
# intent_type="풍자/비판"이라 해놓고 category는 삭제대상 계열을 골랐다. 결정적 매핑이
# 그대로 삭제대상을 확정해, 공공기관이 정치 비판을 삭제 요청 후보로 올리는 결과가 됐다.
# 비대상으로 낮추지 않고 종합판단으로 강등한다 — 풍자 형식의 실제 조장 글이 있을 수 있다.
for cat in ("편법·속임수·공정성 훼손", "허위·조작"):
    r = parse_unified({"label_l2": "신뢰저하", "category": cat,
                       "intent_type": "풍자/비판", "false_score": 60})
    check(f"{cat}: 풍자/비판이면 종합판단", r["action_type"] == "종합판단",
          f"got {r['action_type']}")
    # 종합판단이면 삭제대상 하한(67)이 안 걸려 알림 임계(min_score 67) 아래에 머문다
    check(f"{cat}: 점수 하한 미적용", r["false_score"] == 60, f"got {r['false_score']}")
    check(f"{cat}: 알림 임계 미만", r["false_score"] < DELETE_SCORE_FLOOR)

r = parse_unified({"label_l2": "방법안내", "category": "편법·속임수·공정성 훼손",
                   "intent_type": "악의적 유포", "false_score": 85})
check("풍자/비판이 아니면 삭제대상 유지", r["action_type"] == "삭제대상",
      f"got {r['action_type']}")

r = parse_unified({"label_l2": "신뢰저하", "category": "정책비판",
                   "intent_type": "풍자/비판", "action_type": "비대상", "false_score": 60})
check("정책비판/비대상은 그대로", r["action_type"] == "비대상", f"got {r['action_type']}")

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
