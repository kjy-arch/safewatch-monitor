"""본평가 결과에서 파일럿(프롬프트 튜닝에 사용된) 샘플을 제외하고 지표 재계산.

파일럿 21건은 같은 seed로 추출돼 본평가 504건의 부분집합이다. 파일럿 오답을 보고
경계 규칙을 보강했으므로, 엄밀한 지표는 해당 21건을 제외하고 산출해야 한다.

사용법:
  .venv\\Scripts\\python.exe eval_exclude_pilot.py <본평가.csv> <파일럿.csv>
"""
import sys, csv
sys.stdout.reconfigure(encoding="utf-8")

PROMOTION = {"방법문의", "방법안내", "브로커의심", "신뢰저하", "의도의심"}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def metrics(rows, tag):
    n = len(rows)
    gold_promo = [r for r in rows if r["gold_l2"] in PROMOTION]
    pred_promo = [r for r in rows if r["pred_l2"] in PROMOTION]
    tp = sum(1 for r in gold_promo if r["pred_l2"] in PROMOTION)
    l2_ok = sum(1 for r in rows if r["gold_l2"] == r["pred_l2"])

    print(f"\n[{tag}] n={n}")
    print(f"  조장정보 L1 재현율: {tp / len(gold_promo):.3f}" if gold_promo else "  (조장 표본 없음)")
    print(f"  조장정보 L1 정밀도: {tp / len(pred_promo):.3f}" if pred_promo else "")
    print(f"  L2 정확도(7라벨):   {l2_ok / n:.3f}")
    labels = sorted({r["gold_l2"] for r in rows})
    for label in labels:
        rs = [r for r in rows if r["gold_l2"] == label]
        acc = sum(1 for r in rs if r["pred_l2"] == label) / len(rs)
        print(f"    {label}: {acc:.2f} ({len(rs)}건)")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    full = load(sys.argv[1])
    pilot_keys = {(r["gold_l2"], r["title"]) for r in load(sys.argv[2])}
    clean = [r for r in full if (r["gold_l2"], r["title"]) not in pilot_keys]

    print(f"본평가 {len(full)}건 중 파일럿 중복 {len(full) - len(clean)}건 제외")
    metrics(full, "전체 (오염 포함)")
    metrics(clean, "파일럿 제외 (공식 지표)")


if __name__ == "__main__":
    main()
