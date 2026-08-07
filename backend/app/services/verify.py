"""2단계 검증 — 삭제대상 판정을 본문으로 재확인 (2026-08-07, 마이그레이션 010).

수집은 네이버 검색 API의 요약(약 120자)만 저장한다. 그 요약만 보고 삭제대상으로 판정한
글이 실제로는 정상 안내였던 사례가 확인돼(지식인 docId=494564616), 삭제 요청 후보로
올라온 건만 본문을 다시 보고 판정한다.

**원 분류 컬럼은 절대 건드리지 않는다.** 2차 결과는 `verify_*` 컬럼에만 쌓고, 화면에서
1차와 나란히 보여준 뒤 최종 판단은 담당자가 기존 검수 기능(services/review.py)으로 한다.
덮어쓰면 ⓐ 왜 바뀌었는지 추적할 수 없고 ⓑ 누적분과 기준이 어긋나 분기 보고서가 왜곡된다.

이 모듈은 **한계가 분명하다** — 1차에서 비대상으로 떨어진 글은 보지 않는다. 즉 오탐만
줄이고 누락은 그대로다. 누락 규모는 `estimate_snippet_miss.py`로 따로 측정한다.
"""
import time
from datetime import datetime, timezone

from app.core.database import supabase
from app.crawlers.fulltext import FETCHABLE, SKIP_REASON, fetch_fulltext
from app.services import run_log
from app.services.analyzer import _analyze

# 2차 확인 대상 — 삭제 요청 후보로 올라온 것만. 비대상은 보지 않는다(위 한계).
TARGET_ACTIONS = ("삭제대상", "종합판단")

# 본문 전문을 프롬프트에 실을 상한. 지식인 1.8천자·블로그 8천자·언론 1.1만자가 실측값이라
# 3000자면 지식인은 전문, 긴 글은 앞부분이 들어간다. 토큰 비용과의 절충.
VERIFY_MAX_CHARS = 3000

# 요청 사이 대기 — crawlers/dcinside.py와 같은 기준
REQUEST_DELAY = 0.5

# 진행 상태 (인메모리). 수집 진행률(core/progress.py)과 섞지 않으려고 따로 둔다.
_state: dict = {"running": False, "done": 0, "total": 0,
                "confirmed": 0, "overturned": 0, "failed": 0, "message": ""}


def status() -> dict:
    return dict(_state)


def pending(limit: int = 200) -> list[dict]:
    """아직 2차 확인을 안 한 삭제대상·종합판단 목록 (조회 가능한 출처만)."""
    rows = (
        supabase.table("crawled_articles")
        .select("id, title, content, url, source_type, action_type, false_reason")
        .in_("action_type", list(TARGET_ACTIONS))
        .is_("verify_status", "null")
        .order("false_score", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    return rows


def run(limit: int = 200) -> dict:
    """대상 전건을 본문으로 재판정한다. 반환은 요약 통계."""
    rows = pending(limit)
    run_id = run_log.start("verify")
    _state.update({"running": True, "done": 0, "total": len(rows),
                   "confirmed": 0, "overturned": 0, "failed": 0, "message": ""})
    if not rows:
        _state.update({"running": False, "message": "확인할 대상이 없습니다."})
        run_log.finish(run_id, analyzed=0, message="대상 없음")
        return status()

    departments = supabase.table("departments").select("id, name, keywords").execute().data
    now = datetime.now(timezone.utc).isoformat()

    for i, row in enumerate(rows, 1):
        _state["done"] = i
        src = row["source_type"]

        # 카페(로그인 벽)·유튜브(이미 전문)는 조회 자체가 무의미하다
        if src not in FETCHABLE:
            supabase.table("crawled_articles").update({
                "verify_status": "대상아님",
                "verify_reason": SKIP_REASON.get(src, "지원하지 않는 출처"),
                "verified_at":   now,
            }).eq("id", row["id"]).execute()
            continue

        try:
            body = fetch_fulltext(row.get("url") or "", src)
            if not body:
                supabase.table("crawled_articles").update({
                    "verify_status": "조회실패",
                    "verify_reason": "본문을 가져오지 못했습니다(삭제·비공개·구조 변경 가능).",
                    "verified_at":   now,
                }).eq("id", row["id"]).execute()
                _state["failed"] += 1
                continue

            result = _analyze(row.get("title") or "", body, src, departments,
                              max_chars=VERIFY_MAX_CHARS)
            overturned = result["action_type"] != row["action_type"]
            supabase.table("crawled_articles").update({
                "content_full":  body[:20000],
                "verify_status": "확인완료",
                "verify_action": result["action_type"],
                "verify_reason": result["false_reason"],
                "verified_at":   now,
            }).eq("id", row["id"]).execute()
            _state["overturned" if overturned else "confirmed"] += 1
            if overturned:
                print(f"[검증] 판정 변경 {row['action_type']} → {result['action_type']} "
                      f"({src}) {(row.get('title') or '')[:30]}", flush=True)
        except Exception as e:
            print(f"[검증] {row['id'][:8]} 실패: {type(e).__name__}: {e}", flush=True)
            _state["failed"] += 1
        finally:
            time.sleep(REQUEST_DELAY)

    _state["running"] = False
    _state["message"] = (f"{_state['total']}건 확인 — 유지 {_state['confirmed']} · "
                         f"변경 {_state['overturned']} · 실패 {_state['failed']}")
    print(f"[검증] {_state['message']}", flush=True)
    run_log.finish(run_id, analyzed=_state["confirmed"] + _state["overturned"],
                   message=_state["message"])
    return status()
