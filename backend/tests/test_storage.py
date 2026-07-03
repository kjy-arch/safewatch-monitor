"""crawlers/storage.py 단위 테스트 — upsert 일괄 저장·중복 제거 (가짜 supabase).

실행: .venv\\Scripts\\python.exe tests\\test_storage.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from types import SimpleNamespace
import app.crawlers.storage as storage

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


class FakeTable:
    def __init__(self, db):
        self.db = db
        self._mode = None
        self._urls = []
        self._rows = []

    def select(self, *a, **k):
        self._mode = "select"
        return self

    def in_(self, col, urls):
        self._urls = urls
        return self

    def upsert(self, rows, on_conflict=None, ignore_duplicates=False):
        assert on_conflict == "url" and ignore_duplicates, "ON CONFLICT DO NOTHING 사용해야 함"
        self._mode = "upsert"
        self._rows = rows
        return self

    def execute(self):
        if self._mode == "select":
            return SimpleNamespace(data=[{"url": u} for u in self._urls if u in self.db.existing])
        # ON CONFLICT DO NOTHING 시뮬레이션: 기존 URL은 스킵, 새 행만 반환
        new_rows = [r for r in self._rows if r["url"] not in self.db.existing]
        self.db.inserted.extend(new_rows)
        return SimpleNamespace(data=new_rows)


class FakeDB:
    def __init__(self, existing):
        self.existing = existing
        self.inserted = []

    def table(self, name):
        return FakeTable(self)


db = FakeDB(existing={"u2"})
storage.supabase = db
rows = [
    {"url": "u1", "title": "a"},
    {"url": "u1", "title": "a-dup"},   # 배치 내 중복
    {"url": "u2", "title": "b"},       # DB 기존
    {"url": "u3", "title": "c"},
]
n = storage.save_articles(rows)
check("저장 건수 2 (u1, u3)", n == 2, f"got {n}")
check("insert된 URL", sorted(r["url"] for r in db.inserted) == ["u1", "u3"],
      f"got {[r['url'] for r in db.inserted]}")
check("빈 배치는 0", storage.save_articles([]) == 0)
check("existing_urls 일괄 조회", storage.existing_urls(["u2", "u9"]) == {"u2"})
check("existing_urls 빈 입력", storage.existing_urls([]) == set())

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
