"""담당자가 등록한 URL·동일 내용 제외 규칙.

일치해도 원문은 지우지 않는다. 감사·재현을 위해 저장하고, AI 호출만 생략한 뒤
비대상·무관으로 기록한다. 내용 규칙은 유사도가 아니라 정규화 후 완전일치다.
"""
import hashlib
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from app.core import operator
from app.core.database import supabase
from app.services.pii_masking import mask_pii

RULE_TYPES = {"url", "content_hash"}
MIN_CONTENT_LEN = 30

_migration_warning_shown = False


class ExclusionError(ValueError):
    pass


def normalize_url(value: str | None) -> str:
    raw = (value or "").strip()
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                       parts.query, ""))


def normalize_content(value: str | None) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_active_rules() -> dict[str, dict[str, dict]]:
    """한 분석 실행에서 한 번 읽어 재사용할 활성 규칙."""
    global _migration_warning_shown
    try:
        rows = (
            supabase.table("exclusion_rules").select("*")
            .eq("is_active", True).execute().data
        )
    except Exception as e:
        if not _migration_warning_shown:
            print(f"[제외규칙] 011 미적용 또는 조회 실패 — 규칙 적용 생략: "
                  f"{type(e).__name__}: {e}", flush=True)
            _migration_warning_shown = True
        rows = []
    out = {"url": {}, "content_hash": {}}
    for row in rows:
        if row.get("rule_type") in out:
            out[row["rule_type"]][row["match_value"]] = row
    return out


def match_rule(rules: dict, url: str | None, content: str | None) -> dict | None:
    normalized_url = normalize_url(url)
    if normalized_url:
        rule = rules.get("url", {}).get(_hash(normalized_url))
        if rule:
            return rule
    normalized_content = normalize_content(content)
    if len(normalized_content) >= MIN_CONTENT_LEN:
        return rules.get("content_hash", {}).get(_hash(normalized_content))
    return None


def register(rule_type: str, raw_value: str, reason: str) -> dict:
    reason = (reason or "").strip()[:500]
    if not reason:
        raise ExclusionError("제외 사유를 입력하세요.")
    if rule_type == "url":
        normalized = normalize_url(raw_value)
        if not normalized:
            raise ExclusionError("등록할 수 있는 HTTP/HTTPS URL이 없습니다.")
        # 관리 화면에는 쿼리 토큰·개인식별값을 복제하지 않는다. 매칭은 전체 URL 해시로 한다.
        parts = urlsplit(normalized)
        display = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:500]
    elif rule_type == "content_hash":
        normalized = normalize_content(raw_value)
        if len(normalized) < MIN_CONTENT_LEN:
            raise ExclusionError(f"내용 제외는 정규화 후 {MIN_CONTENT_LEN}자 이상만 등록할 수 있습니다.")
        display = mask_pii(normalized[:200])
    else:
        raise ExclusionError(f"지원하지 않는 제외 유형입니다: {rule_type}")

    match_value = _hash(normalized)
    fields = {
        "rule_type": rule_type,
        "match_value": match_value,
        "display_value": display,
        "reason": reason,
        "is_active": True,
        "deactivated_at": None,
        **operator.snapshot(),
    }
    # 같은 규칙을 동시에 등록해도 UNIQUE 충돌 대신 한 규칙으로 합친다.
    return (supabase.table("exclusion_rules").upsert(
        fields, on_conflict="rule_type,match_value"
    ).execute().data[0])


def list_rules(active_only: bool = True, limit: int = 200) -> list[dict]:
    q = supabase.table("exclusion_rules").select("*")
    if active_only:
        q = q.eq("is_active", True)
    return q.order("created_at", desc=True).limit(limit).execute().data


def deactivate(rule_id: str) -> dict:
    rows = (supabase.table("exclusion_rules").update({
        "is_active": False,
        "deactivated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", rule_id).execute().data)
    if not rows:
        raise ExclusionError("제외 규칙을 찾을 수 없습니다.")
    return rows[0]


def excluded_fields(rule: dict) -> dict:
    kind = "URL" if rule.get("rule_type") == "url" else "동일 내용"
    return {
        "false_score": 0,
        "false_level": "낮음",
        "false_reason": f"담당자 등록 제외 규칙 일치 ({kind})",
        "label_l2": "단순내용",
        "subject": "기타",
        "category": "해당없음",
        "action_type": "비대상",
        "intent_type": "불명확",
        "content_type": "문제없음",
        "response_status": "무관",
        "response_memo": f"제외 규칙: {(rule.get('reason') or '')[:500]}",
    }


def record_match(rule_id: str, target_table: str, target_id: str) -> None:
    try:
        (supabase.table("exclusion_matches").upsert({
            "rule_id": rule_id,
            "target_table": target_table,
            "target_id": target_id,
        }, on_conflict="rule_id,target_table,target_id", ignore_duplicates=True)
         .execute())
    except Exception as e:
        print(f"[제외규칙] 적중 이력 저장 실패: {type(e).__name__}: {e}", flush=True)
