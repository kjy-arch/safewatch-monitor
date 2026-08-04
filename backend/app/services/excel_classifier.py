"""업로드된 엑셀(.xlsx)의 원문을 Monitor 분류기(analyzer)로 분류.

DB에 저장하지 않고 메모리에서 처리·보관한다(임의 엑셀 대상). 분류 로직은
analyze_unclassified와 동일하게 사전필터 → Gemini(analyzer._analyze)를 재사용한다.
"""
import threading
from io import BytesIO

import openpyxl

from app.core.database import supabase
from app.services.analyzer import _analyze
from app.services.keyword_scorer import (
    score_text, is_enabled as prefilter_enabled, PREFILTER_THRESHOLD,
)

# 헤더 후보 — 본문/원문 열을 우선 탐지 (제목은 보조)
_TEXT_HEADERS  = ("원문", "내용", "본문", "content", "text")
_TITLE_HEADERS = ("제목", "title")
_URL_HEADERS   = ("링크", "url", "원문링크")
_SRC_HEADERS   = ("출처", "source", "출처유형")

_lock = threading.Lock()
_state: dict = {"status": "idle", "done": 0, "total": 0, "message": ""}
_results: list = []


def _find_col(headers: list, candidates: tuple) -> int | None:
    for idx, h in enumerate(headers):
        if h and str(h).strip().lower() in candidates:
            return idx
    return None


def parse_excel(data: bytes) -> list[dict]:
    """xlsx 바이트 → [{text, title, url, source}] 목록.

    앞쪽 행에서 '원문/내용/본문' 등이 든 헤더 행을 찾아 그 아래를 데이터로 본다.
    헤더를 못 찾으면 각 행에서 가장 긴 텍스트 셀을 원문으로 사용한다.
    """
    wb = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows:
        return []

    # 헤더 행 탐색 (제목/병합 타이틀 행을 건너뛰기 위해 앞 5행 스캔)
    header_idx = text_col = None
    for i, row in enumerate(rows[:5]):
        c = _find_col(row, _TEXT_HEADERS)
        if c is not None:
            header_idx, text_col = i, c
            break

    out = []
    if header_idx is not None:
        headers = rows[header_idx]
        title_col = _find_col(headers, _TITLE_HEADERS)
        url_col   = _find_col(headers, _URL_HEADERS)
        src_col   = _find_col(headers, _SRC_HEADERS)
        for row in rows[header_idx + 1:]:
            text = _cell(row, text_col)
            if not text:
                continue
            out.append({
                "text":   text,
                "title":  _cell(row, title_col),
                "url":    _cell(row, url_col),
                "source": _cell(row, src_col),
            })
    else:
        # 헤더 없음 → 각 행에서 가장 긴 문자열 셀을 원문으로
        for row in rows:
            texts = [str(v) for v in row if isinstance(v, str) and v.strip()]
            if not texts:
                continue
            longest = max(texts, key=len)
            if len(longest) >= 10:
                out.append({"text": longest, "title": "", "url": "", "source": ""})
    return out


def _cell(row: list, idx: int | None) -> str:
    if idx is None or idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def snapshot() -> dict:
    with _lock:
        s = dict(_state)
        s["results"] = list(_results)
    # 실제 처리 비율로 계산 — 중단(크레딧 소진 등)됐는데 100%로 보이지 않게 한다.
    s["percent"] = round(s["done"] / s["total"] * 100) if s["total"] else 0
    return s


def run(rows: list[dict], limit: int = 200) -> None:
    """rows를 분류해 결과를 메모리에 채운다(백그라운드 태스크로 호출)."""
    rows = rows[:limit]
    departments = supabase.table("departments").select("id, name, keywords").execute().data

    with _lock:
        _state.update(status="running", done=0, total=len(rows), message="")
        _results.clear()

    for i, r in enumerate(rows, 1):
        text = r["text"]
        title = r.get("title") or ""
        try:
            # 출처와 무관하게 동일 임계치 (요구 Q7) — keyword_scorer 주석 참조
            kw_score = score_text(f"{title} {text}") if prefilter_enabled() else -1
            if 0 <= kw_score < PREFILTER_THRESHOLD:
                res = {"label_l2": "단순내용", "subject": "기타", "false_score": 5,
                       "false_level": "낮음", "false_reason": f"키워드 사전필터 (점수 {kw_score})",
                       "department_names": []}
            else:
                res = _analyze(title, text, r.get("source") or "", departments)
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                msg = (f"Gemini 크레딧/쿼터 소진 — {i - 1}건 처리 후 중단. "
                       "결제·쿼터 확인 후 다시 실행하세요.")
                print(f"[excel_classifier] {msg}", flush=True)
                with _lock:
                    _state.update(message=msg)
                break
            print(f"[excel_classifier] {i}번째 분류 실패: {type(e).__name__}: {e}", flush=True)
            res = {"label_l2": "오류", "subject": "", "false_score": None,
                   "false_level": "미분류", "false_reason": f"{type(e).__name__}: {e}",
                   "department_names": []}

        # 통합 분석기는 부서를 관련도 순 배열(department_names)로 준다 — 1순위만 표시
        dept = (res.get("department_names") or [None])[0]

        with _lock:
            _results.append({
                "text": text[:300], "url": r.get("url") or "", "source": r.get("source") or "",
                "department_name": dept,
                **{k: res.get(k) for k in
                   ("false_score", "false_level", "label_l2", "subject",
                    "false_reason")},
            })
            _state["done"] = i

    with _lock:
        _state["status"] = "done"
