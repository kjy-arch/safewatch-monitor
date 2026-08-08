"""analyzer 영구 실패 기사 스킵 테스트 — 실패한 기사가 다음 배치에서 제외되는지.

실행: .venv\\Scripts\\python.exe tests\\test_analyzer_skip.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from types import SimpleNamespace
import app.services.analyzer as analyzer
import app.services.keyword_scorer as scorer

# 이 테스트는 Gemini 경로의 실패 스킵만 검증 — 사전필터는 비활성화
scorer._scores = None
scorer._load_attempted = True

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


# 병역 관련성 게이트를 통과해야 _analyze까지 도달한다(게이트는 test_prefilter가 검증)
ROWS = [{"id": "x1", "title": "군면제 문의", "content": "신검 4급 받는법 알려주셈",
         "url": "https://example.test/x1", "source_type": "커뮤니티"}]


class FakeNot:
    def __init__(self, q):
        self.q = q

    def in_(self, col, ids):
        self.q.excluded = set(ids)
        return self.q


class FakeQuery:
    def __init__(self, name):
        self.name = name
        self.excluded = set()
        self._update = None
        self._id = None

    def select(self, *a, **k): return self
    def is_(self, *a): return self
    def limit(self, n): return self
    def order(self, *a, **k): return self  # analyzer가 최신순 정렬 후 조회
    def update(self, fields): self._update = fields; return self
    def eq(self, col, value): self._id = value; return self

    @property
    def not_(self):
        return FakeNot(self)

    def execute(self):
        if self._update is not None:
            updates.append((self._id, self._update))
            return SimpleNamespace(data=[])
        if self.name == "departments":
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[r for r in ROWS if r["id"] not in self.excluded])


calls = {"n": 0}
updates = []


def failing_analyze(*a, **k):
    calls["n"] += 1
    raise ValueError("모의 분류 실패")


analyzer.supabase = SimpleNamespace(table=lambda n: FakeQuery(n))
analyzer._analyze = failing_analyze
analyzer._failed_ids.clear()

n1 = analyzer.analyze_unclassified(limit=10)
check("1차: 실패 → 0건 처리", n1 == 0)
check("1차: 실패 ID 기록", analyzer._failed_ids == {"x1"}, f"got {analyzer._failed_ids}")
check("1차: _analyze 1회 호출", calls["n"] == 1)

n2 = analyzer.analyze_unclassified(limit=10)
check("2차: 실패 기사 쿼리에서 제외", calls["n"] == 1, f"호출 {calls['n']}회 (재시도되면 안 됨)")
check("2차: 0건 반환", n2 == 0)

print("[제외 규칙 — Gemini 호출 전 차단]")
rule = {"id": "rule-1", "rule_type": "url", "reason": "반복 정상 안내"}
matched = []
analyzer.exclusions.load_active_rules = lambda: {"url": {}, "content_hash": {}}
analyzer.exclusions.match_rule = lambda rules, url, content: rule
analyzer.exclusions.excluded_fields = lambda r: {
    "false_score": 0, "false_level": "낮음", "action_type": "비대상",
    "response_status": "무관",
}
analyzer.exclusions.record_match = lambda rule_id, table, target_id: matched.append(
    (rule_id, table, target_id)
)
analyzer._failed_ids.clear()
before_calls = calls["n"]
n3 = analyzer.analyze_unclassified(limit=10)
check("제외 건 처리 완료", n3 == 1)
check("Gemini 미호출", calls["n"] == before_calls)
check("비대상·무관 저장", updates[-1][1]["action_type"] == "비대상"
      and updates[-1][1]["response_status"] == "무관")
check("적중 이력 기록", matched == [("rule-1", "crawled_articles", "x1")])

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
