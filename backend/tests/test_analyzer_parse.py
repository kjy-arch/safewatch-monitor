"""analyzer._parse_response 단위 테스트 (API 호출 없음).

실행: .venv\\Scripts\\python.exe tests\\test_analyzer_parse.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from app.services.analyzer import _parse_response

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


# 1. 정상 JSON
r = _parse_response('{"label_l2":"방법문의","subject":"정신과","false_score":75,"reason":"수법 질문","department_name":null}')
check("정상: label_l1 유도", r["label_l1"] == "조장정보")
check("정상: 점수 유지", r["false_score"] == 75)
check("정상: level 높음", r["false_level"] == "높음")

# 2. 점수가 라벨 구간 밖 → 구간으로 클램프
r = _parse_response('{"label_l2":"브로커의심","subject":"병무관련","false_score":10,"reason":"x"}')
check("클램프: 브로커의심 최소 90", r["false_score"] == 90, f"got {r['false_score']}")
r = _parse_response('{"label_l2":"단순내용","subject":"정신과","false_score":99,"reason":"x"}')
check("클램프: 단순내용 최대 33", r["false_score"] == 33, f"got {r['false_score']}")
check("클램프: 단순내용 L1", r["label_l1"] == "단순병역정보")

# 3. 알 수 없는 라벨 → 단순내용 폴백
r = _parse_response('{"label_l2":"이상한라벨","subject":"정신과","false_score":50,"reason":"x"}')
check("폴백: 미지 라벨 → 단순내용", r["label_l2"] == "단순내용")

# 4. 알 수 없는 과목 → 기타
r = _parse_response('{"label_l2":"방법안내","subject":"성형외과","false_score":85,"reason":"x"}')
check("폴백: 미지 과목 → 기타", r["subject"] == "기타")

# 5. 마크다운 펜스 안전망
r = _parse_response('```json\n{"label_l2":"의도의심","subject":"기타","false_score":40,"reason":"x"}\n```')
check("펜스 제거", r["label_l2"] == "의도의심")

# 6. 점수 비정상 타입 → 라벨 구간 최소값
r = _parse_response('{"label_l2":"신뢰저하","subject":"병무관련","false_score":"높음","reason":"x"}')
check("비정상 점수 → 구간 최소 50", r["false_score"] == 50, f"got {r['false_score']}")

# 7. reason 100자 절단
long_reason = "가" * 200
r = _parse_response(f'{{"label_l2":"단순문의","subject":"내과","false_score":10,"reason":"{long_reason}"}}')
check("reason 100자 절단", len(r["false_reason"]) == 100)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
