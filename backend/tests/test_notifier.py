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
     "action_type": "삭제대상", "title": "t66", "content": "c66", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "a67", "false_score": 67, "false_level": "높음", "source_type": "커뮤니티",
     "action_type": "삭제대상", "title": "t67", "content": "c67", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "a68", "false_score": 68, "false_level": "높음", "source_type": "언론",
     "action_type": "비대상", "title": "t68", "content": "c68", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "aNone", "false_score": None, "false_level": None, "source_type": "유튜브",
     "action_type": "삭제대상", "title": "tN", "content": "cN", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "verified-safe", "false_score": 90, "false_level": "높음", "source_type": "지식인",
     "action_type": "삭제대상", "verify_status": "확인완료", "verify_action": "비대상",
     "title": "safe", "content": "safe", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "verified-delete", "false_score": 91, "false_level": "높음", "source_type": "지식인",
     "action_type": "종합판단", "verify_status": "확인완료", "verify_action": "삭제대상",
     "title": "delete", "content": "delete", "url": "u", "published_at": "2026-07-04T01:00:00"},
    {"id": "verify-failed", "false_score": 92, "false_level": "높음", "source_type": "언론",
     "action_type": "삭제대상", "verify_status": "조회실패",
     "title": "failed", "content": "failed", "url": "u", "published_at": "2026-07-04T01:00:00"},
]

RECIPIENTS = [
    {"email": "boundary@t.kr", "min_score": 67},
    {"email": "all@t.kr",      "min_score": 0},
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
      captured["updates"] == [["a66", "a67", "aNone", "verified-delete"]], f"got {captured['updates']}")

captured["updates"].clear()
captured["sends"].clear()
RECIPIENTS[:] = [{"email": "boundary@t.kr", "min_score": 67}]
notifier.send_alerts()
check("경계: 67 포함(>=), 66·미분류 제외",
      captured["updates"] == [["a67", "verified-delete"]], f"got {captured['updates']}")

captured["updates"].clear()
RECIPIENTS[:] = [{"email": "x@t.kr", "min_score": 1}]
notifier.send_alerts()
check("min_score=1: 미분류(None) 제외",
      captured["updates"] == [["a66", "a67", "verified-delete"]], f"got {captured['updates']}")

check("비대상·2차 비대상·조회실패는 자동 알림 제외",
      all(x not in captured["updates"][-1] for x in ["a68", "verified-safe", "verify-failed"]))

notifier._send = _real_send


# ── 3. 엑셀 서식 + 부서 임베드 회귀 방지 ──
# crawled_articles → departments 외래키가 1·2순위 2개라, 조회 시 어느 쪽인지 명시하지
# 않으면 PostgREST가 "more than one relationship was found"로 거부한다(006 이후).
# 실제로 이 때문에 엑셀 저장·이메일·기사목록이 한꺼번에 깨졌다.
print()
print("[3] 부서 임베드 명시 + 엑셀 서식")
import io, pathlib, openpyxl

for name, src in [("exporter", pathlib.Path("app/services/exporter.py").read_text(encoding="utf-8")),
                  ("notifier", pathlib.Path("app/services/notifier.py").read_text(encoding="utf-8")),
                  ("crawl API", pathlib.Path("app/api/crawl.py").read_text(encoding="utf-8"))]:
    bare = "departments(name)" in src and "crawled_articles_department_id_fkey" not in src
    check(f"{name}: 부서 임베드에 외래키 명시", not bare,
          "departments(name)만 쓰면 부서 FK가 2개라 조회가 실패한다")

rows = [{
    "source_type": "커뮤니티", "published_at": "2026-08-05T09:00:00Z",
    "false_score": 85, "false_level": "높음", "label_l2": "방법안내", "subject": "정신과",
    "category": "편법·속임수·공정성 훼손", "action_type": "삭제대상",
    "intent_type": "악의적 유포", "content_type": "과장/왜곡", "false_reason": "수법 안내",
    "dept1": {"name": "병역조사과"}, "dept2": {"name": "병역판정검사과"},
    "title": "5급 받는 법", "content": "정공 4급인 사람들 5급 받는법", "url": "http://t.test/1",
    "response_status": "미확인",
}]
wb = openpyxl.load_workbook(io.BytesIO(notifier._build_excel(rows)))
ws = wb.active
hdr = [c.value for c in ws[2]]
row = [c.value for c in ws[3]]
cell = dict(zip(hdr, row))

for col in ["분류구분", "조치유형", "의도유형", "내용유형", "소관부서2", "제목"]:
    check(f"엑셀에 '{col}' 열", col in hdr, f"열 목록 {hdr}")
check("1순위 부서", cell.get("소관부서") == "병역조사과", f"got {cell.get('소관부서')}")
check("2순위 부서(요구 Q4)", cell.get("소관부서2") == "병역판정검사과", f"got {cell.get('소관부서2')}")
check("제목 채워짐(요구 R2)", cell.get("제목") == "5급 받는 법", f"got {cell.get('제목')}")
check("조치유형 채워짐", cell.get("조치유형") == "삭제대상", f"got {cell.get('조치유형')}")
check("내용유형 값 보존", cell.get("내용유형") == "과장/왜곡",
      f"got {cell.get('내용유형')}")
link_cell = ws.cell(row=3, column=hdr.index("링크") + 1)
check("링크 열에 URL 표시", link_cell.value == "http://t.test/1", f"got {link_cell.value!r}")
check("링크 열 실제 URL", link_cell.hyperlink is not None
      and link_cell.hyperlink.target == "http://t.test/1",
      f"got {link_cell.hyperlink.target if link_cell.hyperlink else None!r}")
check("자동필터가 전체 18열", ws.auto_filter.ref == "A2:R3",
      f"got {ws.auto_filter.ref!r}")

# 구버전 응답(부서 임베드가 departments 키)도 깨지지 않아야 한다
legacy = [dict(rows[0], dept1=None, dept2=None, departments={"name": "홍보과"})]
ws2 = openpyxl.load_workbook(io.BytesIO(notifier._build_excel(legacy))).active
c2 = dict(zip([c.value for c in ws2[2]], [c.value for c in ws2[3]]))
check("구버전 departments 키 폴백", c2.get("소관부서") == "홍보과", f"got {c2.get('소관부서')}")

malicious = [dict(rows[0], title="=HYPERLINK(\"https://evil.test\")",
                  content="  +CMD", url="@SUM(1,1)", false_reason="-1+1")]
mw = openpyxl.load_workbook(io.BytesIO(notifier._build_excel(malicious)), data_only=False).active
mh = [c.value for c in mw[2]]
mcells = dict(zip(mh, mw[3]))
for column, prefix in [("제목", "'="), ("원문", "'  +"), ("링크", "'@"), ("판단이유", "'-")]:
    check(f"{column} 수식 삽입 방지",
          mcells[column].data_type != "f" and mcells[column].value.startswith(prefix),
          f"got {mcells[column].value!r} ({mcells[column].data_type})")

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
