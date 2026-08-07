"""2단계 검증 테스트 — 대상 선정·건너뜀·조회실패·**원 분류 불변** (네트워크·DB 없음).

실행: .venv\\Scripts\\python.exe tests\\test_verify.py

가장 중요한 것은 마지막 항목이다. 2차 판정이 원 분류 컬럼(action_type·category·
false_score 등)을 건드리면 ⓐ 왜 바뀌었는지 추적할 수 없고 ⓑ 누적분과 기준이 어긋나
분기 보고서 추세가 왜곡된다. 그래서 컬럼 불변을 테스트로 고정한다.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from types import SimpleNamespace
import app.services.verify as verify

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


ROWS = [
    {"id": "kin1", "title": "질문", "content": "요약 120자",
     "url": "https://kin.naver.com/x", "source_type": "지식인", "action_type": "삭제대상"},
    {"id": "cafe1", "title": "카페글", "content": "요약",
     "url": "https://cafe.naver.com/x", "source_type": "커뮤니티", "action_type": "삭제대상"},
    {"id": "yt1", "title": "댓글", "content": "정치 비판",
     "url": "https://youtube.com/x", "source_type": "유튜브", "action_type": "종합판단"},
    {"id": "kin2", "title": "질문2", "content": "요약",
     "url": "https://kin.naver.com/y", "source_type": "지식인", "action_type": "삭제대상"},
]

updates = {}   # id -> 저장된 필드


class FakeQuery:
    def __init__(self, name):
        self.name = name
        self._update = None
        self._eq_id = None

    def select(self, *a, **k): return self
    def in_(self, *a): return self
    def is_(self, *a): return self
    def order(self, *a, **k): return self
    def limit(self, n): return self

    def update(self, fields):
        self._update = fields
        return self

    def eq(self, col, val):
        self._eq_id = val
        return self

    def execute(self):
        if self._update is not None:
            updates.setdefault(self._eq_id, {}).update(self._update)
            return SimpleNamespace(data=[])
        if self.name == "departments":
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=list(ROWS))


fetched = []


def fake_fetch(url, source_type):
    fetched.append((url, source_type))
    if url.endswith("/y"):
        return ""                      # 조회 실패 재현
    return "본문 전문 " * 200


def fake_analyze(title, text, source_type, departments, max_chars=800):
    check("2차는 긴 상한을 쓴다", max_chars == verify.VERIFY_MAX_CHARS, f"got {max_chars}")
    return {"action_type": "비대상", "false_reason": "본문 확인 결과 정상 안내",
            "label_l2": "단순내용", "false_score": 5}


verify.supabase = SimpleNamespace(table=lambda n: FakeQuery(n))
verify.fetch_fulltext = fake_fetch
verify._analyze = fake_analyze
verify.run_log = SimpleNamespace(start=lambda *a, **k: "run1",
                                 finish=lambda *a, **k: None)
verify.time = SimpleNamespace(sleep=lambda s: None)

print("[1] run()")
res = verify.run(limit=10)

check("4건 처리", res["total"] == 4, f"got {res['total']}")
check("판정 변경 1건", res["overturned"] == 1, f"got {res['overturned']}")
check("조회실패 1건", res["failed"] == 1, f"got {res['failed']}")
check("실행 종료 상태", res["running"] is False)

print("[2] 조회 대상 선별")
check("조회 가능 출처만 fetch 호출", [s for _, s in fetched] == ["지식인", "지식인"],
      f"got {fetched}")
check("카페는 대상아님", updates["cafe1"]["verify_status"] == "대상아님",
      f"got {updates.get('cafe1')}")
check("카페 사유 기록", "로그인" in updates["cafe1"]["verify_reason"])
check("유튜브는 대상아님", updates["yt1"]["verify_status"] == "대상아님")
check("유튜브 사유 기록", "전문" in updates["yt1"]["verify_reason"])

print("[3] 조회 실패 처리")
check("빈 본문 → 조회실패", updates["kin2"]["verify_status"] == "조회실패",
      f"got {updates.get('kin2')}")
check("조회실패는 2차 판정 없음", "verify_action" not in updates["kin2"])

print("[4] 확인완료 기록")
u = updates["kin1"]
check("verify_status 확인완료", u["verify_status"] == "확인완료")
check("verify_action 저장", u["verify_action"] == "비대상", f"got {u.get('verify_action')}")
check("본문 저장", len(u.get("content_full") or "") > 100)
check("verified_at 기록", bool(u.get("verified_at")))

print("[5] ★ 원 분류 컬럼 불변 (가장 중요)")
PROTECTED = ("action_type", "category", "false_score", "false_level", "false_reason",
             "label_l2", "subject", "intent_type", "content_type",
             "department_id", "department_id_2", "content")
for target_id, fields in updates.items():
    bad = [c for c in PROTECTED if c in fields]
    check(f"{target_id}: 원 분류 미변경", not bad, f"덮어쓴 컬럼 {bad}")

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
