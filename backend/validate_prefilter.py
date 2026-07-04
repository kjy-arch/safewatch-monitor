"""사전 필터 임계치 검증 — 23~24년 라벨 데이터 전체(6,430건)로 무손실 측정.

임계치별로: 스킵 비율(=Gemini 비용 절감), 조장정보 미스율(스킵된 조장/전체 조장).
기준: 조장 미스율 ≤ 2%인 최대 임계치 채택.

사용법: .venv\\Scripts\\python.exe validate_prefilter.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from eval_classifier import load_samples
from app.services.classifier_prompt import PROMOTION_LABELS
from app.services.keyword_scorer import score_text, is_enabled


def main():
    if not is_enabled():
        print("점수 사전 없음 — 먼저 build_keyword_scores.py 실행")
        sys.exit(1)

    pool = load_samples()
    print(f"검증 풀: {len(pool)}건 (23~24년 라벨 데이터)")

    scored = [(score_text(s["title"] + " " + s["content"]),
               s["gold_l2"] in PROMOTION_LABELS) for s in pool]
    total = len(scored)
    total_promo = sum(1 for _, p in scored if p)

    print(f"조장정보 {total_promo}건 / 단순 {total - total_promo}건\n")
    print(f"{'임계치':>4} | {'스킵비율(비용절감)':>12} | {'조장 미스율':>8} | 판정")
    print("-" * 55)
    best = None
    for t in range(0, 16):
        skipped = [(sc, p) for sc, p in scored if sc < t]
        skip_ratio = len(skipped) / total
        promo_miss = sum(1 for _, p in skipped if p) / total_promo
        ok = promo_miss <= 0.02
        if ok:
            best = t
        print(f"{t:>4} | {skip_ratio*100:>10.1f}% | {promo_miss*100:>7.2f}% | {'OK' if ok else 'X'}")

    print(f"\n권장 임계치: {best} (조장 미스율 ≤ 2%인 최대값)")
    print("keyword_scorer.PREFILTER_THRESHOLD와 일치하는지 확인할 것")


if __name__ == "__main__":
    main()
