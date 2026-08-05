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


# ── 본문 기준 중복 차단 (같은 글이 다른 URL로 올라오는 경우) ──
# 실측: 예비군 훈령·업무보고 영상 등이 하루 3~6회 중복 수집돼 Gemini 호출이 낭비됐다.
print()
print("[본문 중복 차단]")

BODY = "예비군훈령 조편운 제9조(지역예비군 편성기준 및 방법)에 따라 편성한다 " * 2


class ContentDB:
    """content 조회(.order/.limit)를 지원하는 더블."""
    def __init__(self, stored):
        self.stored = stored
        self.upserted = []

    def table(self, name):
        db = self
        class Q:
            def select(self, *a, **k): self._sel = a[0] if a else ""; return self
            def order(self, *a, **k): return self
            def limit(self, n): return self
            def in_(self, col, vals): self._in = vals; return self
            def upsert(self, rows, **k): db.upserted = rows; return self
            def execute(self):
                if getattr(self, "_sel", "") == "content":
                    return SimpleNamespace(data=[{"content": c} for c in db.stored])
                if hasattr(self, "_in"):
                    return SimpleNamespace(data=[])
                return SimpleNamespace(data=db.upserted)
        return Q()


db = ContentDB(stored=[BODY])
storage.supabase = db
n = storage.save_articles([
    {"url": "http://a/1", "content": BODY},                    # 이미 있는 본문 (다른 URL)
    {"url": "http://a/2", "content": "군면제 받는법 아는사람 진짜 급하다 도와줘라 제발 부탁이야"},
])
check("같은 본문·다른 URL은 제외", n == 1, f"got {n}")
check("남은 것은 새 글", len(db.upserted) == 1 and db.upserted[0]["url"] == "http://a/2",
      f"got {[r['url'] for r in db.upserted]}")

# 같은 배치 안의 중복도 제거
db = ContentDB(stored=[])
storage.supabase = db
n = storage.save_articles([
    {"url": "http://b/1", "content": BODY},
    {"url": "http://b/2", "content": BODY},
    {"url": "http://b/3", "content": "  " + " ".join(BODY.split()) + "  "},   # 공백만 다름
])
check("배치 내 중복도 1건으로", n == 1, f"got {n}")

# 짧은 본문은 우연히 겹칠 수 있어 원문 대조를 하지 않는다
db = ContentDB(stored=["짧은글"])
storage.supabase = db
n = storage.save_articles([{"url": "http://c/1", "content": "짧은글"}])
check("짧은 본문은 대조 대상 아님", n == 1, f"got {n}")

# 본문 조회가 실패해도 저장 자체는 진행돼야 한다
class BrokenDB(ContentDB):
    def table(self, name):
        q = super().table(name)
        orig = q.execute
        def execute():
            if getattr(q, "_sel", "") == "content": raise RuntimeError("DB 다운")
            return orig()
        q.execute = execute
        return q

db = BrokenDB(stored=[])
storage.supabase = db
n = storage.save_articles([{"url": "http://d/1", "content": BODY}])
check("본문 조회 실패해도 저장은 진행", n == 1, f"got {n}")

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
