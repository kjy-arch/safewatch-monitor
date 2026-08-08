"""담당자 URL·동일 내용 제외 규칙 — 정규화·완전일치·안전 경계."""
import hashlib
import os
import sys
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from app.services import exclusions

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


print("[URL 정규화·완전일치]")
url = "HTTPS://Example.COM/path?q=1#section"
normalized_url = exclusions.normalize_url(url)
check("호스트·스킴 소문자 + fragment 제거",
      normalized_url == "https://example.com/path?q=1", normalized_url)
url_rule = {"id": "u1", "rule_type": "url", "reason": "반복 공지",
            "match_value": digest(normalized_url)}
rules = {"url": {url_rule["match_value"]: url_rule}, "content_hash": {}}
check("같은 URL 일치", exclusions.match_rule(rules, url, "다른 내용") == url_rule)
check("경로가 다르면 불일치",
      exclusions.match_rule(rules, "https://example.com/path2?q=1", "다른 내용") is None)
check("HTTP/HTTPS 아닌 주소 거부", exclusions.normalize_url("javascript:alert(1)") == "")

print("[내용 정규화·완전일치]")
content = "병역 관련 정상 안내입니다.   제출 서류와 절차를 확인하세요.  문의는 관할 기관으로 바랍니다."
normalized_content = exclusions.normalize_content(content)
content_rule = {"id": "c1", "rule_type": "content_hash", "reason": "반복 안내",
                "match_value": digest(normalized_content)}
rules = {"url": {}, "content_hash": {content_rule["match_value"]: content_rule}}
check("공백 차이는 같은 내용", exclusions.match_rule(
    rules, None, content.replace("   ", "\n\t")) == content_rule)
check("한 글자라도 다르면 불일치", exclusions.match_rule(
    rules, None, content + " 추가") is None)
check("부분 포함만으로 제외하지 않음", exclusions.match_rule(
    rules, None, normalized_content[:35] + " 완전히 다른 글") is None)
check("30자 미만은 매칭 대상 아님", exclusions.match_rule(
    rules, None, "짧은 정상 안내") is None)

print("[자동 제외 판정]")
fields = exclusions.excluded_fields(content_rule)
check("비대상", fields["action_type"] == "비대상")
check("무관", fields["response_status"] == "무관")
check("점수 0", fields["false_score"] == 0)
check("규칙 사유 보존", "반복 안내" in fields["response_memo"])

print("[등록 입력 검증]")
try:
    exclusions.register("content_hash", "너무 짧음", "사유")
    check("짧은 내용 등록 거부", False)
except exclusions.ExclusionError:
    check("짧은 내용 등록 거부", True)
try:
    exclusions.register("url", "javascript:alert(1)", "사유")
    check("위험 URL 등록 거부", False)
except exclusions.ExclusionError:
    check("위험 URL 등록 거부", True)
try:
    exclusions.register("url", "https://example.com", "")
    check("빈 사유 등록 거부", False)
except exclusions.ExclusionError:
    check("빈 사유 등록 거부", True)

print("[등록 저장값 최소화]")
saved = []


class RuleTable:
    def upsert(self, fields, **kwargs):
        saved.append((fields, kwargs))
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": "r1", **saved[-1][0]}])


real_supabase = exclusions.supabase
real_snapshot = exclusions.operator.snapshot
exclusions.supabase = SimpleNamespace(table=lambda name: RuleTable())
exclusions.operator.snapshot = lambda: {
    "operator_name": "담당자", "os_account": "user", "host_name": "pc"
}
exclusions.register("url", "https://example.com/path?token=secret#part", "반복 URL")
check("URL 표시값에서 쿼리·fragment 제거",
      saved[-1][0]["display_value"] == "https://example.com/path",
      saved[-1][0]["display_value"])
check("원문 대신 SHA-256 저장", len(saved[-1][0]["match_value"]) == 64)
exclusions.register("content_hash",
                    "정상 안내문입니다. 문의 전화는 010-1234-5678이며 제출 절차를 안내합니다.",
                    "반복 내용")
check("내용 미리보기 개인정보 마스킹",
      "010-1234-5678" not in saved[-1][0]["display_value"]
      and "[전화번호]" in saved[-1][0]["display_value"])
check("동시 등록은 복합키 upsert",
      saved[-1][1].get("on_conflict") == "rule_type,match_value")
exclusions.supabase = real_supabase
exclusions.operator.snapshot = real_snapshot

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
