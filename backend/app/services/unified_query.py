"""수집분 + 업로드분 통합 조회 (Phase 4).

분기 보고서·통계는 두 경로의 결과를 함께 집계해야 한다.

  수집분   crawled_articles  (크롤러가 모은 글)
  업로드분 articles          (엑셀로 올려 분류한 글)

⚠️ 단순 합산은 **이중 계상**을 낳는다. Monitor 수집 엑셀을 다시 올려 재분류한
   배치가 있기 때문이다(실측: 314행 전량이 수집분과 동일한 글이었다).
   URL로는 걸러지지 않는다 — Monitor 엑셀의 링크 열은 하이퍼링크라 재업로드 시
   표시 텍스트('링크 바로가기')가 저장되기 때문. 그래서 **원문 앞부분으로 대조**한다.

중복 시 어느 쪽을 남기는가:
   분석이 더 채워진 쪽(축 B category가 있는 쪽)을 남긴다. 둘 다 있거나 둘 다
   없으면 원본인 수집분을 남긴다. 집계에서 정보가 덜 손실되는 선택이다.
"""
from datetime import datetime

from app.core.database import supabase

DEDUP_PREFIX = 60      # 원문 앞 N자로 동일 글 판정
PAGE = 1000

CRAWLED_COLS = ("created_at, published_at, source_type, title, content, url, "
                "false_score, false_level, label_l2, subject, category, action_type, "
                "intent_type, content_type, department_id, department_id_2, response_status")
UPLOADED_COLS = ("created_at, source_type, original_text, source_url, "
                 "false_score, false_level, label_l2, subject, category, action_type, "
                 "intent_type, content_type, department_id, department_id_2")


def _key(text: str | None) -> str:
    """중복 판정 키 — 공백을 접어 서식 차이를 흡수한다."""
    return " ".join((text or "").split())[:DEDUP_PREFIX]


def normalize_crawled(r: dict) -> dict:
    return {
        "origin":       "수집",
        "created_at":   r.get("created_at"),
        "source_type":  r.get("source_type"),
        "text":         r.get("content") or r.get("title") or "",
        "url":          r.get("url") or "",
        "false_score":  r.get("false_score"),
        "false_level":  r.get("false_level"),
        "label_l2":     r.get("label_l2"),
        "subject":      r.get("subject"),
        "category":     r.get("category"),
        "action_type":  r.get("action_type"),
        "intent_type":  r.get("intent_type"),
        "content_type": r.get("content_type"),
        "department_id":   r.get("department_id"),
        "department_id_2": r.get("department_id_2"),
    }


def normalize_uploaded(r: dict) -> dict:
    return {
        "origin":       "업로드",
        "created_at":   r.get("created_at"),
        "source_type":  r.get("source_type"),
        "text":         r.get("original_text") or "",
        "url":          r.get("source_url") or "",
        "false_score":  r.get("false_score"),
        "false_level":  r.get("false_level"),
        "label_l2":     r.get("label_l2"),
        "subject":      r.get("subject"),
        "category":     r.get("category"),
        "action_type":  r.get("action_type"),
        "intent_type":  r.get("intent_type"),
        "content_type": r.get("content_type"),
        "department_id":   r.get("department_id"),
        "department_id_2": r.get("department_id_2"),
    }


def merge(crawled: list[dict], uploaded: list[dict]) -> tuple[list[dict], int]:
    """정규화된 두 목록을 중복 제거해 합친다. (합친 목록, 제거 건수) 반환."""
    picked: dict[str, dict] = {}
    order: list[str] = []
    removed = 0

    for row in list(crawled) + list(uploaded):
        k = _key(row.get("text"))
        if not k:                      # 원문이 비면 중복 판정 불가 — 그대로 둔다
            order.append(f"__keep{len(order)}")
            picked[order[-1]] = row
            continue
        prev = picked.get(k)
        if prev is None:
            picked[k] = row
            order.append(k)
            continue
        removed += 1
        # 분석이 더 채워진 쪽을 남긴다 (축 B category 보유 여부)
        if not prev.get("category") and row.get("category"):
            picked[k] = row

    return [picked[k] for k in order], removed


def fetch(from_dt: datetime, to_dt: datetime) -> dict:
    """기간 내 분석완료 건을 두 테이블에서 모아 중복 제거해 반환."""
    crawled = _page("crawled_articles", CRAWLED_COLS, from_dt, to_dt,
                    lambda q: q.not_.is_("false_level", "null"))
    uploaded = _page("articles", UPLOADED_COLS, from_dt, to_dt,
                     lambda q: q.eq("status", "done"))

    rows, removed = merge([normalize_crawled(r) for r in crawled],
                          [normalize_uploaded(r) for r in uploaded])
    return {
        "rows": rows,
        "crawled": len(crawled),
        "uploaded": len(uploaded),
        "deduped": removed,
    }


def _page(table: str, cols: str, from_dt: datetime, to_dt: datetime, refine) -> list[dict]:
    out, off = [], 0
    while True:
        q = (supabase.table(table).select(cols)
             .gte("created_at", from_dt.isoformat())
             .lte("created_at", to_dt.isoformat()))
        page = refine(q).range(off, off + PAGE - 1).execute().data
        out.extend(page)
        if len(page) < PAGE:
            return out
        off += PAGE
