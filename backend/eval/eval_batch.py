"""분류자 성능 평가 — 골든셋으로 현행 분류기의 정확도 기준선을 측정.

골든셋(golden_set.csv)의 각 행을 현재 분석 파이프라인(_analyze_single)에 통과시켜
예측값과 정답을 비교한다. 프롬프트·RAG를 손보기 전/후 같은 골든셋으로 돌려
정확도가 실제로 올랐는지 회귀 검증하는 것이 목적이다.

지표:
  - 조치유형 정확도 (삭제대상/비대상/종합판단)
  - '삭제대상' 재현율(최우선: 삭제할 것을 놓치지 않는가) / 정밀도(과잉 삭제 안 하는가)
  - 분류구분(category) 정확도 + 카테고리별 정확도 + 혼동행렬
  - 거짓척도 정확도(정확 일치 / ±1 인접 허용)

사용법 (backend 디렉토리에서):
  .venv\\Scripts\\python.exe eval\\eval_classifier.py
  .venv\\Scripts\\python.exe eval\\eval_classifier.py --golden eval\\golden_set.csv

주의: 실제 Gemini API를 호출하므로 .env(GEMINI_API_KEY, SUPABASE_*)가 필요하고
      호출 건수만큼 API 비용이 발생한다. 골든셋 텍스트는 합성 예문이라 개인정보 없음.
"""
import sys, os, csv, time, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.batch.analyzer import analyze_text
from app.core.database import supabase

HERE = os.path.dirname(os.path.abspath(__file__))
DELETE_ACTION = "삭제대상"
LEVEL_ORDER = {"낮음": 0, "중간": 1, "높음": 2}


def load_golden(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if r.get("text", "").strip()]


def level_gap(gold: str, pred: str) -> int | None:
    """거짓척도 간 거리(0=정확, 1=인접). 정답 척도가 비면 None."""
    if gold not in LEVEL_ORDER or pred not in LEVEL_ORDER:
        return None
    return abs(LEVEL_ORDER[gold] - LEVEL_ORDER[pred])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=os.path.join(HERE, "golden_set.csv"))
    parser.add_argument("--sleep", type=float, default=0.6, help="API 호출 간 대기(초)")
    args = parser.parse_args()

    pool = load_golden(args.golden)
    print(f"골든셋: {len(pool)}건 로드 ({args.golden})")

    try:
        departments = supabase.table("departments").select("id, name, keywords").execute().data
    except Exception as e:
        print(f"  [경고] 부서 목록 조회 실패({e}) — 부서 없이 진행")
        departments = []

    results = []
    for i, s in enumerate(pool, 1):
        text, source = s["text"], s.get("source_type", "언론")
        try:
            pred, _ = analyze_text(text, source, departments)
        except Exception as e:
            print(f"  [{i}/{len(pool)}] 호출 실패: {type(e).__name__}: {e}", flush=True)
            continue

        cat_ok = (s["expected_category"] == pred["category"])
        act_ok = (s["expected_action"] == pred["action_type"])
        lgap = level_gap(s.get("expected_level", ""), pred["false_level"])
        results.append({
            "id": s.get("id", i),
            "gold_category": s["expected_category"], "pred_category": pred["category"],
            "gold_action": s["expected_action"],     "pred_action": pred["action_type"],
            "gold_level": s.get("expected_level", ""), "pred_level": pred["false_level"],
            "score": pred["false_score"], "reason": pred["false_reason"],
            "text": text[:50],
        })
        mark = "O" if cat_ok else ("~" if act_ok else "X")
        print(f"  [{i}/{len(pool)}] {mark} cat정답={s['expected_category']} 예측={pred['category']}"
              f" | 조치 {s['expected_action']}→{pred['action_type']} | {text[:28]}", flush=True)
        time.sleep(args.sleep)

    if not results:
        print("평가 결과 없음")
        return

    n = len(results)
    cat_acc = sum(1 for r in results if r["gold_category"] == r["pred_category"]) / n
    act_acc = sum(1 for r in results if r["gold_action"] == r["pred_action"]) / n

    # '삭제대상' 재현율/정밀도 — 운영상 가장 중요(놓침·과잉 삭제)
    gold_del = [r for r in results if r["gold_action"] == DELETE_ACTION]
    pred_del = [r for r in results if r["pred_action"] == DELETE_ACTION]
    tp = sum(1 for r in gold_del if r["pred_action"] == DELETE_ACTION)
    del_recall = tp / len(gold_del) if gold_del else None
    del_prec = tp / len(pred_del) if pred_del else None

    # 거짓척도 정확도(정확/인접)
    gaps = [level_gap(r["gold_level"], r["pred_level"]) for r in results]
    gaps = [g for g in gaps if g is not None]
    lvl_exact = sum(1 for g in gaps if g == 0) / len(gaps) if gaps else None
    lvl_adj = sum(1 for g in gaps if g <= 1) / len(gaps) if gaps else None

    print(f"\n{'='*64}")
    print(f"평가 결과 (n={n})")
    print(f"  분류구분(category) 정확도 : {cat_acc:.3f}")
    print(f"  조치유형 정확도           : {act_acc:.3f}")
    if del_recall is not None:
        print(f"  '삭제대상' 재현율         : {del_recall:.3f}  (놓치면 안 됨 · 목표 ≥ 0.90)")
    if del_prec is not None:
        print(f"  '삭제대상' 정밀도         : {del_prec:.3f}  (과잉 삭제 방지)")
    if lvl_exact is not None:
        print(f"  거짓척도 정확도           : {lvl_exact:.3f} (정확) / {lvl_adj:.3f} (±1 인접)")

    print("\n[카테고리별 정확도]")
    for label in sorted({r["gold_category"] for r in results}):
        rs = [r for r in results if r["gold_category"] == label]
        acc = sum(1 for r in rs if r["pred_category"] == label) / len(rs)
        print(f"  {label}: {acc:.2f} ({len(rs)}건)")

    # 혼동행렬 (정답 행 × 예측 열)
    labels = sorted({r["gold_category"] for r in results} | {r["pred_category"] for r in results})
    print("\n[혼동행렬] 행=정답, 열=예측")
    w = max(len(l) for l in labels)
    print(" " * (w + 2) + " ".join(l[:6].rjust(6) for l in labels))
    for g in labels:
        row = [sum(1 for r in results if r["gold_category"] == g and r["pred_category"] == p) for p in labels]
        print(g.rjust(w + 1), " ".join(str(c).rjust(6) for c in row))

    out = os.path.join(HERE, f"eval_result_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        wri = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wri.writeheader()
        wri.writerows(results)
    print(f"\n상세 결과 저장: {out}")


if __name__ == "__main__":
    main()
