"""엑셀 업로드 분석도 담당자 제외 규칙을 Gemini보다 먼저 적용한다."""
import os
import sys
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

import app.services.batch.analyzer as analyzer

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


ARTICLE = {
    "id": "a1",
    "original_text": "반복되는 정상 병무 안내문입니다. 제출 서류와 처리 절차를 안내합니다.",
    "source_type": "언론",
    "source_url": "https://example.test/notice",
}
updates = []


class Query:
    def __init__(self, table):
        self.table = table
        self.fields = None
        self.count_mode = False
        self.status = None

    def select(self, fields, **kwargs):
        self.fields = fields
        self.count_mode = kwargs.get("count") == "exact"
        return self

    def eq(self, col, value):
        if col == "status":
            self.status = value
        return self

    def neq(self, *args): return self
    def range(self, *args): return self
    def update(self, fields): self.fields = fields; return self

    def execute(self):
        if isinstance(self.fields, dict):
            updates.append((self.table, self.fields))
            return SimpleNamespace(data=[])
        if self.table == "departments":
            return SimpleNamespace(data=[])
        if self.table == "articles" and self.count_mode:
            return SimpleNamespace(data=[], count=1 if self.status == "done" else 0)
        if self.table == "articles":
            return SimpleNamespace(data=[ARTICLE])
        return SimpleNamespace(data=[])


analyzer.supabase = SimpleNamespace(table=lambda name: Query(name))
rule = {"id": "rule-1", "rule_type": "content_hash", "reason": "반복 정상 안내"}
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
analyzer._analyze_single = lambda *args, **kwargs: (_ for _ in ()).throw(
    AssertionError("제외 건은 Gemini 경로에 도달하면 안 됨")
)

result = analyzer.analyze_batch("batch-1")
article_updates = [fields for table, fields in updates
                   if table == "articles" and isinstance(fields, dict)]
check("1건 처리", result == {"analyzed": 1, "failed": 0, "total": 1}, result)
check("비대상·무관·완료 저장", any(
    u.get("action_type") == "비대상" and u.get("response_status") == "무관"
    and u.get("status") == "done" for u in article_updates
), article_updates)
check("적중 이력 기록", matched == [("rule-1", "articles", "a1")], matched)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
