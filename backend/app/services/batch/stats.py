"""분석 결과 집계 — 결과화면 통계 요약과 분기 보고서가 공유."""
from collections import Counter

UNSET = "(미분류)"
UNASSIGNED = "(미배정)"


def _count_by(articles: list, key: str) -> dict:
    c = Counter()
    for a in articles:
        v = a.get(key)
        c[v if v not in (None, "") else UNSET] += 1
    return dict(c)


def _dept_counts(articles: list, dept_map: dict) -> dict:
    """1순위 부서 기준 건수 (2순위도 별도 합산)."""
    primary, secondary = Counter(), Counter()
    for a in articles:
        d1 = a.get("department_id")
        primary[dept_map.get(d1, UNASSIGNED) if d1 else UNASSIGNED] += 1
        d2 = a.get("department_id_2")
        if d2:
            secondary[dept_map.get(d2, UNASSIGNED)] += 1
    return {"primary": dict(primary), "secondary": dict(secondary)}


def _risk_count(articles: list, threshold: int) -> int:
    """거짓점수가 임계값 이상인 '위험' 건수."""
    n = 0
    for a in articles:
        s = a.get("false_score")
        if isinstance(s, (int, float)) and s >= threshold:
            n += 1
    return n


def summarize(articles: list, dept_map: dict, risk_threshold: int = 70) -> dict:
    """배치/기간 단위 분포 요약."""
    return {
        "total": len(articles),
        "risk_threshold": risk_threshold,
        "risk_count": _risk_count(articles, risk_threshold),
        "false_level": _count_by(articles, "false_level"),
        "action_type": _count_by(articles, "action_type"),
        "category": _count_by(articles, "category"),
        "intent_type": _count_by(articles, "intent_type"),
        "content_type": _count_by(articles, "content_type"),
        "source_type": _count_by(articles, "source_type"),
        "department": _dept_counts(articles, dept_map),
    }
