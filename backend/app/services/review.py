"""검수·재분류 + 이력 (Phase 6, 요구 Q3).

담당자가 AI 판정을 뒤집을 수 있게 하되, **무엇을·왜·누가·언제 바꿨는지 반드시 남긴다.**
이 기록이 없으면 삭제 요청의 근거를 사후에 추적할 수 없다.

수집분(crawled_articles)과 업로드분(articles) 양쪽을 같은 방식으로 다룬다.
"""
from app.core.database import supabase
from app.core import operator
from app.services.unified_prompt import (
    VALID_CATEGORIES, VALID_ACTIONS, VALID_INTENTS, VALID_CONTENTS,
)
from app.services.classifier_prompt import ALL_LABELS, SUBJECTS

TABLES = {"crawled_articles", "articles"}
RESPONSE_STATUSES = {"미확인", "검토중", "대응완료", "무관"}
LEVELS = {"낮음", "중간", "높음"}

# 재분류 허용 필드와 허용값 — 화이트리스트 밖의 컬럼은 절대 쓰지 않는다.
# (사용자 입력이 그대로 UPDATE 컬럼명이 되면 임의 컬럼 변조가 가능해지므로)
EDITABLE: dict[str, set | None] = {
    "action_type":     VALID_ACTIONS,
    "category":        VALID_CATEGORIES,
    "label_l2":        ALL_LABELS,
    "subject":         set(SUBJECTS),
    "intent_type":     VALID_INTENTS,
    "content_type":    VALID_CONTENTS,
    "false_level":     LEVELS,
    "response_status": RESPONSE_STATUSES,
    "response_memo":   None,     # 자유 텍스트
}

# 본문 컬럼명이 테이블마다 다르다
TEXT_COL = {"crawled_articles": "content", "articles": "original_text"}
URL_COL  = {"crawled_articles": "url", "articles": "source_url"}


class ReviewError(ValueError):
    """검수 요청이 잘못된 경우 (허용되지 않은 필드·값 등)."""


def validate(changes: dict) -> dict:
    """허용 필드·허용값만 통과시킨다. 위반 시 ReviewError."""
    if not changes:
        raise ReviewError("변경할 내용이 없습니다.")
    clean = {}
    for field, value in changes.items():
        if field not in EDITABLE:
            raise ReviewError(f"수정할 수 없는 항목입니다: {field}")
        allowed = EDITABLE[field]
        if allowed is None:
            clean[field] = str(value)[:1000] if value is not None else None
            continue
        if value not in allowed:
            raise ReviewError(f"{field}의 값이 올바르지 않습니다: {value}")
        clean[field] = value
    return clean


def fetch_one(table: str, target_id: str) -> dict:
    if table not in TABLES:
        raise ReviewError(f"알 수 없는 대상입니다: {table}")
    rows = supabase.table(table).select("*").eq("id", target_id).execute().data
    if not rows:
        raise ReviewError("대상을 찾을 수 없습니다.")
    return rows[0]


def reclassify(table: str, target_id: str, changes: dict, reason: str = "") -> dict:
    """재분류 적용 + 이력 기록. 실제로 값이 바뀐 필드만 기록한다."""
    clean = validate(changes)
    before = fetch_one(table, target_id)

    diff = {f: v for f, v in clean.items() if (before.get(f) or None) != (v or None)}
    if not diff:
        return {"changed": 0, "message": "변경된 항목이 없습니다.", "logged": 0}

    supabase.table(table).update(diff).eq("id", target_id).execute()

    who = operator.snapshot()
    logs = [{
        "target_table": table,
        "target_id":    target_id,
        "field":        f,
        "old_value":    None if before.get(f) is None else str(before.get(f)),
        "new_value":    None if v is None else str(v),
        "reason":       (reason or "")[:500],
        **who,
    } for f, v in diff.items()]

    logged = 0
    try:
        supabase.table("reclassify_logs").insert(logs).execute()
        logged = len(logs)
    except Exception as e:
        # 이력이 남지 않으면 추적이 불가능하므로 조용히 넘기지 않고 알린다.
        print(f"[검수] 이력 기록 실패: {type(e).__name__}: {e}", flush=True)
        return {"changed": len(diff), "logged": 0,
                "message": "값은 변경됐지만 이력 기록에 실패했습니다. 관리자에게 알리세요."}

    print(f"[검수] {table}/{target_id[:8]} {list(diff)} — {operator.describe()}", flush=True)
    return {"changed": len(diff), "logged": logged, "fields": list(diff),
            "message": f"{len(diff)}개 항목을 재분류했습니다."}


def history(table: str | None = None, target_id: str | None = None, limit: int = 100) -> list:
    q = supabase.table("reclassify_logs").select("*")
    if table:
        q = q.eq("target_table", table)
    if target_id:
        q = q.eq("target_id", target_id)
    return q.order("created_at", desc=True).limit(limit).execute().data


def queue(action_type: str | None = None, response_status: str | None = None,
          limit: int = 100) -> list:
    """검수 대상 목록 — 수집분·업로드분을 합쳐 위험도 순으로.

    기본은 '삭제대상'을 위로 올려 삭제 요청 선정(요구 Q1)에 바로 쓰게 한다.
    """
    out = []
    for table in ("crawled_articles", "articles"):
        cols = ("id, source_type, false_score, false_level, label_l2, subject, category, "
                f"action_type, intent_type, content_type, response_status, response_memo, "
                f"created_at, {TEXT_COL[table]}, {URL_COL[table]}")
        q = supabase.table(table).select(cols).not_.is_("false_level", "null")
        if action_type:
            q = q.eq("action_type", action_type)
        if response_status:
            q = q.eq("response_status", response_status)
        rows = q.order("false_score", desc=True).limit(limit).execute().data
        for r in rows:
            out.append({
                "table":  table,
                "origin": "수집" if table == "crawled_articles" else "업로드",
                "text":   r.pop(TEXT_COL[table], "") or "",
                "url":    r.pop(URL_COL[table], "") or "",
                **r,
            })
    out.sort(key=lambda r: (r.get("false_score") or 0), reverse=True)
    return out[:limit]
