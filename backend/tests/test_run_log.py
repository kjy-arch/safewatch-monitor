"""담당자 식별 + 실행 이력 테스트 (네트워크·DB 불필요).

실행: .venv\\Scripts\\python.exe tests\\test_run_log.py
"""
import os, sys, json, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from app.core import operator
from app.services import run_log

failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


# --- 담당자명 저장/조회 (실제 홈 디렉터리를 건드리지 않게 임시 경로로 교체) ---
print("[담당자 식별]")
tmp = tempfile.mkdtemp()
operator.CONFIG_PATH = Path(tmp) / ".safewatch" / "operator.json"

check("미설정이면 None", operator.get_name() is None)

s = operator.snapshot()
check("계정명 자동 수집", bool(s["os_account"]), f"got {s['os_account']!r}")
check("PC명 자동 수집", bool(s["host_name"]), f"got {s['host_name']!r}")
check("미설정 시 담당자명 None", s["operator_name"] is None)
check("미설정 표시는 계정@PC", "@" in operator.describe(), f"got {operator.describe()}")

operator.set_name("  홍길동  ")
check("공백 제거 후 저장", operator.get_name() == "홍길동", f"got {operator.get_name()!r}")
check("표시에 담당자명 포함", operator.describe().startswith("홍길동"), operator.describe())
check("파일로 영속화", operator.CONFIG_PATH.exists())

try:
    operator.set_name("   ")
    check("빈 이름 거부", False, "예외가 발생하지 않음")
except ValueError:
    check("빈 이름 거부", True)

long_name = "가" * 100
operator.set_name(long_name)
check("길이 제한", len(operator.get_name()) == operator.MAX_NAME_LEN,
      f"got {len(operator.get_name())}")

# --- 실행 이력: 죽은 running 건 제외 ---
print("\n[실행 이력 — 죽은 실행 제외]")


def fake_rows(rows):
    class Q:
        def select(self, *a, **k): return self
        def eq(self, *a): return self
        def order(self, *a, **k): return self
        def limit(self, n): return self
        def execute(self): return SimpleNamespace(data=rows)
    return SimpleNamespace(table=lambda n: Q())


now = datetime.now(timezone.utc)
fresh_ts = (now - timedelta(minutes=5)).isoformat()
stale_ts = (now - timedelta(minutes=run_log.STALE_MINUTES + 30)).isoformat()

run_log.supabase = fake_rows([
    {"id": "1", "run_type": "crawl", "started_at": fresh_ts},
    {"id": "2", "run_type": "batch", "started_at": stale_ts},
])
act = run_log.active()
check("최근 실행만 '실행 중'으로 인정", [r["id"] for r in act] == ["1"], f"got {[r['id'] for r in act]}")

run_log.supabase = fake_rows([{"id": "3", "run_type": "crawl", "started_at": None}])
check("started_at 없으면 제외", run_log.active() == [])

run_log.supabase = fake_rows([{"id": "4", "run_type": "crawl", "started_at": "이상한값"}])
check("깨진 시각은 제외", run_log.active() == [])

# --- 이력 기록 실패가 본 작업을 막지 않는지 ---
print("\n[이력 실패는 무시]")


class Boom:
    def table(self, n): raise RuntimeError("DB 다운")


run_log.supabase = Boom()
check("start 실패해도 None 반환(예외 없음)", run_log.start("crawl") is None)
try:
    run_log.finish("some-id", analyzed=3, message="x")
    run_log.fail("some-id", "err")
    check("finish/fail 실패해도 예외 없음", True)
except Exception as e:
    check("finish/fail 실패해도 예외 없음", False, str(e))
check("run_id 없으면 조용히 무시", run_log.finish(None) is None)
check("조회 실패 시 빈 목록", run_log.recent() == [] and run_log.active() == [])

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
