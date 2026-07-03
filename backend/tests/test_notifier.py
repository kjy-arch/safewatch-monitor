"""notifier 단위 테스트 — KST 날짜 윈도우 + min_score 필터 (가짜 supabase/SMTP).

실행: .venv\\Scripts\\python.exe tests\\test_notifier.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import app.services.notifier as notifier

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


# ── 1. KST 날짜 윈도우: UTC 23:00(= KST 익일 08:00 스케줄 시각) 기준 ──
print("[1] send_alerts 날짜 윈도우")


class FakeDateTime(datetime):
    FIXED_UTC = datetime(2026, 7, 2, 23, 0, 0, tzinfo=timezone.utc)  # = KST 7/3 08:00

    @classmethod
    def now(cls, tz=None):
        return cls.FIXED_UTC.astimezone(tz) if tz else cls.FIXED_UTC.replace(tzinfo=None)


captured_window = {}


class WindowTable:
    def __init__(self, name):
        self.name = name

    def select(self, *a, **k): return self
    def eq(self, *a): return self
    def order(self, *a, **k): return self

    def gte(self, col, val):
        captured_window["gte"] = val
        return self

    def execute(self):
        if self.name == "alert_settings":
            return SimpleNamespace(data=[{"email": "t@t.kr", "min_score": 0}])
        return SimpleNamespace(data=[])  # 기사 없음 → 발송 전 종료


notifier.supabase = SimpleNamespace(table=lambda n: WindowTable(n))
_real_datetime = notifier.datetime
notifier.datetime = FakeDateTime
notifier.send_alerts()
notifier.datetime = _real_datetime

expected = datetime(2026, 7, 2, 15, 0, 0, tzinfo=timezone.utc).isoformat()  # KST 7/3 00:00
check("컷오프 = KST 오늘 자정", captured_window.get("gte") == expected,
      f"expected {expected}, got {captured_window.get('gte')}")

# ── 2. min_score 필터 ──
print("[2] min_score 필터")

ARTICLES = [
    {"id": "a66", "false_score": 66, "false_level": "중간", "source_type": "커뮤니티",
     "title": "t66", "content": "c66", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "a67", "false_score": 67, "false_level": "높음", "source_type": "커뮤니티",
     "title": "t67", "content": "c67", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "a68", "false_score": 68, "false_level": "높음", "source_type": "언론",
     "title": "t68", "content": "c68", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "aNone", "false_score": None, "false_level": None, "source_type": "유튜브",
     "title": "tN", "content": "cN", "url": "u", "published_at": "2026-07-04T01:00:00"},
]

RECIPIENTS = [
    {"email": "boundary@t.kr", "min_score": 67},   # 67, 68 두 건
    {"email": "all@t.kr",      "min_score": 0},    # 전체 4건
    {"email": "none@t.kr",     "min_score": 100},  # 0건 → 발송 생략
]

captured = {"updates": [], "sends": []}


class FakeTable:
    def __init__(self, name):
        self.name = name
        self._update = None

    def select(self, *a, **k): return self
    def eq(self, *a): return self
    def gte(self, *a): return self
    def order(self, *a, **k): return self

    def update(self, fields):
        self._update = fields
        return self

    def in_(self, col, ids):
        captured["updates"].append(sorted(ids))
        return self

    def execute(self):
        if self.name == "alert_settings":
            return SimpleNamespace(data=RECIPIENTS)
        if self._update is not None:
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=ARTICLES)


def fake_send(to, subject, html, attachment, filename):
    captured["sends"].append(to)
    return True


notifier.supabase = SimpleNamespace(table=lambda n: FakeTable(n))
_real_send = notifier._send
notifier._send = fake_send
notifier.send_alerts()

check("발송 대상 2명 (100점 기준자는 생략)",
      captured["sends"] == ["boundary@t.kr", "all@t.kr"], f"got {captured['sends']}")
check("alert_sent는 발송된 기사만",
      captured["updates"] == [["a66", "a67", "a68", "aNone"]], f"got {captured['updates']}")

captured["updates"].clear()
captured["sends"].clear()
RECIPIENTS[:] = [{"email": "boundary@t.kr", "min_score": 67}]
notifier.send_alerts()
check("경계: 67 포함(>=), 66·미분류 제외",
      captured["updates"] == [["a67", "a68"]], f"got {captured['updates']}")

captured["updates"].clear()
RECIPIENTS[:] = [{"email": "x@t.kr", "min_score": 1}]
notifier.send_alerts()
check("min_score=1: 미분류(None) 제외",
      captured["updates"] == [["a66", "a67", "a68"]], f"got {captured['updates']}")

notifier._send = _real_send

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
