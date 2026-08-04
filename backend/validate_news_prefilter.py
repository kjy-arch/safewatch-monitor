"""언론 사전필터 임계치 검증 — NEWS_PREFILTER_THRESHOLD 근거 재현.

일반 임계치(validate_prefilter.py)는 사람이 라벨링한 23~24년 자료 6,430건으로
검증하지만, 그 자료에는 **출처 구분이 없다**(제목·내용·내용구분·과목뿐).
따라서 언론 전용 임계치는 DB에 쌓인 분류 완료 언론 기사로 검증한다.

  ⚠️ 한계: 여기서 쓰는 정답은 사람 라벨이 아니라 Gemini 분류 결과다.
     일반 임계치만큼 강한 근거가 아니므로, 임계치를 올릴 때는 보수적으로 볼 것.

기준: 위험(중간·높음) 언론을 하나도 스킵하지 않는 최대 임계치.

사용법: .venv\\Scripts\\python.exe validate_news_prefilter.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from app.core.database import supabase
from app.services.keyword_scorer import (
    score_text, is_enabled, PREFILTER_THRESHOLD, NEWS_PREFILTER_THRESHOLD,
)

RISK_LEVELS = ("중간", "높음")
PAGE = 1000


def load_news() -> list[dict]:
    """분류가 끝난 언론 기사 전체를 페이지네이션으로 가져온다."""
    rows, offset = [], 0
    while True:
        page = (supabase.table("crawled_articles")
                .select("title, content, false_level, false_reason")
                .eq("source_type", "언론")
                .not_.is_("false_level", "null")
                .range(offset, offset + PAGE - 1).execute().data)
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        offset += PAGE


def main():
    if not is_enabled():
        print("점수 사전 없음 — 먼저 build_keyword_scores.py 실행")
        sys.exit(1)

    rows = load_news()
    # 사전필터로 자동분류된 건은 Gemini 판정이 아니므로 정답에서 제외 (순환 논리 방지)
    rows = [r for r in rows if "사전필터" not in (r.get("false_reason") or "")]
    if not rows:
        print("분류된 언론 기사가 없습니다 — 수집·분류를 먼저 수행하세요.")
        sys.exit(1)

    scored = [(score_text(f"{r.get('title') or ''} {r.get('content') or ''}"),
               r["false_level"] in RISK_LEVELS) for r in rows]
    total = len(scored)
    total_risk = sum(1 for _, risk in scored if risk)

    print(f"검증 풀: {total}건 (Gemini가 분류한 언론 기사, 사전필터 자동분류분 제외)")
    print(f"위험(중간·높음) {total_risk}건 / 낮음 {total - total_risk}건\n")
    if total_risk == 0:
        print("위험 언론이 0건이라 미스율을 계산할 수 없습니다. 데이터가 더 쌓인 뒤 재실행하세요.")
        sys.exit(1)

    risk_scores = [sc for sc, risk in scored if risk]
    print(f"위험 언론의 키워드 점수 최소값: {min(risk_scores)}  (이 값까지는 미스 0)\n")

    print(f"{'임계치':>4} | {'스킵비율(비용절감)':>12} | {'위험 미스율':>8} | 판정")
    print("-" * 55)
    best = 0
    for t in range(0, 16):
        skipped = [(sc, risk) for sc, risk in scored if sc < t]
        skip_ratio = len(skipped) / total
        risk_miss = sum(1 for _, risk in skipped if risk) / total_risk
        ok = risk_miss == 0
        if ok:
            best = t
        print(f"{t:>4} | {skip_ratio*100:>10.1f}% | {risk_miss*100:>7.2f}% | {'OK' if ok else 'X'}")

    print(f"\n권장 언론 임계치: {best} (위험 미스 0인 최대값)")
    print(f"현재 설정값     : NEWS_PREFILTER_THRESHOLD = {NEWS_PREFILTER_THRESHOLD}"
          f" (일반 {PREFILTER_THRESHOLD})")
    if NEWS_PREFILTER_THRESHOLD > best:
        print("  → ⚠️ 설정값이 권장값보다 큽니다. 위험 언론을 스킵할 수 있으니 낮추세요.")
    elif NEWS_PREFILTER_THRESHOLD < best:
        print("  → 설정값이 보수적입니다(안전). 비용을 더 줄이려면 권장값까지 올릴 수 있습니다.")
    else:
        print("  → 일치. 조정 불필요.")


if __name__ == "__main__":
    main()
