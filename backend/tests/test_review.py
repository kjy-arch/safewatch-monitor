"""검수·재분류 테스트 (네트워크·DB 불필요).

핵심 두 가지:
  1) 허용 목록 밖의 필드·값이 DB에 절대 쓰이지 않는가 (임의 컬럼 변조 차단)
  2) 실제로 바뀐 필드만, 변경 전/후와 함께 이력에 남는가

실행: .venv\\Scripts\\python.exe tests\\test_review.py
"""
import os, sys
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from app.services import review
from app.services.review import ReviewError

failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


ROW = {
    "id": "abc-123", "action_type": "삭제대상", "category": "허위·조작",
    "label_l2": "방법안내", "subject": "정신과", "false_level": "높음",
    "intent_type": "악의적 유포", "content_type": "과장/왜곡",
    "response_status": "미확인", "response_memo": None,
}


class FakeDB:
    """update/insert 호출을 잡아 두는 최소 더블."""
    def __init__(self):
        self.updates, self.inserts = [], []

    def table(self, name):
        db = self
        class Q:
            def select(self, *a, **k): return self
            def eq(self, *a): self._eq = a; return self
            def order(self, *a, **k): return self
            def limit(self, n): return self
            def update(self, fields): db.updates.append((name, fields)); return self
            def insert(self, rows): db.inserts.append((name, rows)); return self
            def execute(self): return SimpleNamespace(data=[dict(ROW)])
        return Q()


print("[허용 목록 — 임의 컬럼 변조 차단]")
for bad in ["false_score", "id", "created_at", "url", "content", "department_id"]:
    try:
        review.validate({bad: "x"})
        check(f"{bad} 거부", False, "허용돼 버림")
    except ReviewError:
        check(f"{bad} 거부", True)

print("\n[허용값 검증]")
try:
    review.validate({"action_type": "아무거나"}); check("잘못된 조치유형 거부", False)
except ReviewError: check("잘못된 조치유형 거부", True)
try:
    review.validate({"response_status": "처리함"}); check("잘못된 대응상태 거부", False)
except ReviewError: check("잘못된 대응상태 거부", True)
try:
    review.validate({}); check("빈 변경 거부", False)
except ReviewError: check("빈 변경 거부", True)

ok = review.validate({"action_type": "비대상", "response_status": "검토중"})
check("정상 값 통과", ok == {"action_type": "비대상", "response_status": "검토중"}, f"got {ok}")
memo = review.validate({"response_memo": "가" * 2000})
check("자유 텍스트는 길이 제한", len(memo["response_memo"]) == 1000, f"got {len(memo['response_memo'])}")

print("\n[재분류 — 실제 바뀐 것만 기록]")
db = FakeDB(); review.supabase = db
res = review.reclassify("crawled_articles", "abc-123",
                        {"action_type": "비대상", "category": "허위·조작"},  # category는 기존과 동일
                        "실제 병력 기반 문의라 삭제대상 아님")
check("바뀐 필드 1개만 적용", res["changed"] == 1, f"got {res['changed']}")
check("동일 값은 UPDATE에서 제외",
      db.updates and db.updates[0][1] == {"action_type": "비대상"}, f"got {db.updates}")
check("이력 1행", res["logged"] == 1, f"got {res['logged']}")

log = db.inserts[0][1][0]
check("이력 테이블", db.inserts[0][0] == "reclassify_logs")
check("변경 전 값 보존", log["old_value"] == "삭제대상", f"got {log['old_value']}")
check("변경 후 값 기록", log["new_value"] == "비대상", f"got {log['new_value']}")
check("사유 기록", "삭제대상 아님" in (log["reason"] or ""))
check("담당자 정보 포함", "os_account" in log and "host_name" in log)
check("대상 식별 기록", log["target_table"] == "crawled_articles" and log["target_id"] == "abc-123")

print("\n[변경 없음]")
db2 = FakeDB(); review.supabase = db2
res = review.reclassify("crawled_articles", "abc-123", {"action_type": "삭제대상"}, "사유")
check("같은 값이면 UPDATE 안 함", not db2.updates, f"got {db2.updates}")
check("같은 값이면 이력도 없음", res["changed"] == 0 and not db2.inserts)

print("\n[이력 기록 실패 시]")
class FailInsert(FakeDB):
    def table(self, name):
        if name == "reclassify_logs":
            class Boom:
                def insert(self, rows): raise RuntimeError("DB 다운")
            return Boom()
        return super().table(name)

review.supabase = FailInsert()
res = review.reclassify("crawled_articles", "abc-123", {"action_type": "비대상"}, "사유")
check("이력 실패를 조용히 넘기지 않음", res["logged"] == 0 and "이력" in res["message"], f"got {res}")

print("\n[알 수 없는 테이블]")
review.supabase = FakeDB()
try:
    review.reclassify("users", "abc-123", {"action_type": "비대상"}, "사유")
    check("허용되지 않은 테이블 거부", False)
except ReviewError:
    check("허용되지 않은 테이블 거부", True)

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
