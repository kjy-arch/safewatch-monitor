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


ROWS = [{"id": "x1", "title": "t", "content": "c", "source_type": "커뮤니티"}]


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

    def select(self, *a, **k): return self
    def is_(self, *a): return self
    def limit(self, n): return self

    @property
    def not_(self):
        return FakeNot(self)

    def execute(self):
        if self.name == "departments":
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[r for r in ROWS if r["id"] not in self.excluded])


calls = {"n": 0}


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

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
