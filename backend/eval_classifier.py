"""분류기 성능 평가 — 23~24년 라벨링 데이터로 Gemini 분류기를 검증.

사용법:
  .venv\\Scripts\\python.exe eval_classifier.py --per-label 5    # 파일럿 (35건)
  .venv\\Scripts\\python.exe eval_classifier.py --per-label 72   # 본평가 (~500건)

지표: 조장정보 L1 재현율(최우선) / L1 정밀도 / L2 정확도 / 과목 정확도.
개인정보(닉네임·아이디·URL)는 API로 전송하지 않는다 (제목+내용만).
"""
import sys, csv, time, random, argparse
sys.stdout.reconfigure(encoding="utf-8")
import openpyxl

from app.services.analyzer import _analyze
from app.services.classifier_prompt import PROMOTION_LABELS, ALL_LABELS
from app.core.database import supabase

DATA_ROOT = (r"C:\Users\somes\OneDrive\Desktop\전문인재\개별과제"
             r"\2024년 학습자료(도입시)외2_암호화 완료\2024년 학습자료(도입시)외2"
             r"\2024년 학습자료(도입시)\23~24년 자료(6,902건)")

# 파일명 → 기본 라벨 (셀의 내용구분이 있으면 셀 우선)
FILES = [
    ("2023 방법문의.xlsx",   "방법문의"),
    ("2023 방법안내.xlsx",   "방법안내"),
    ("2023 브로커의심.xlsx", "브로커의심"),
    ("2023 신뢰저하.xlsx",   "신뢰저하"),
    ("2023 의도의심.xlsx",   "의도의심"),
    ("2024 방법문의.xlsx",   "방법문의"),
    ("2024 방법안내.xlsx",   "방법안내"),
    ("2024 브로커의심.xlsx", "브로커의심"),
    ("2024 신뢰저하.xlsx",   "신뢰저하"),
    ("2024 의도의심.xlsx",   "의도의심"),
    ("23-24 단순병역정보.xlsx", None),  # 시트별 내용구분 셀 사용
]


def load_samples() -> list[dict]:
    """모든 평가 파일에서 (제목, 내용, 정답라벨, 과목) 로드."""
    samples = []
    for fname, default_label in FILES:
        try:
            wb = openpyxl.load_workbook(f"{DATA_ROOT}\\{fname}", read_only=True, data_only=True)
        except Exception as e:
            print(f"  [로드 실패] {fname}: {e}")
            continue
        for ws in wb.worksheets:
            header = None
            for row in ws.iter_rows(values_only=True):
                if header is None:
                    if row and any(v == "제목" for v in row if v):
                        header = {str(v).strip().split("\n")[0]: i for i, v in enumerate(row) if v}
                    continue
                try:
                    title   = str(row[header["제목"]] or "").strip()
                    content = str(row[header.get("내용", header.get("게시내용"))] or "").strip()
                    gubun_i = header.get("내용구분")
                    subj_i  = header.get("과목")
                    gold    = str(row[gubun_i] or "").strip() if gubun_i is not None else ""
                    subject = str(row[subj_i] or "").strip() if subj_i is not None else ""
                    # 라벨 정규화: 셀 우선, 없으면 파일명 라벨
                    if gold in ("단순내용", "단순문의"):
                        pass
                    elif gold in ALL_LABELS:
                        pass
                    elif default_label:
                        gold = default_label
                    else:
                        continue
                    if title and content and len(content) >= 5:
                        samples.append({"title": title, "content": content,
                                        "gold_l2": gold, "gold_subject": subject})
                except Exception:
                    continue
        wb.close()
    return samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-label", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    pool = load_samples()
    print(f"평가 풀: {len(pool)}건 로드")

    by_label = {}
    for s in pool:
        by_label.setdefault(s["gold_l2"], []).append(s)
    picked = []
    for label, items in sorted(by_label.items()):
        random.shuffle(items)
        picked += items[:args.per_label]
        print(f"  {label}: {len(items)}건 중 {min(args.per_label, len(items))}건 샘플")

    try:
        departments = supabase.table("departments").select("id, name, keywords").execute().data
    except Exception:
        departments = []

    results = []
    for i, s in enumerate(picked, 1):
        try:
            pred = _analyze(s["title"], s["content"], "커뮤니티", departments)
        except Exception as e:
            print(f"  [{i}/{len(picked)}] 호출 실패: {type(e).__name__}: {e}")
            continue
        gold_l1 = "조장정보" if s["gold_l2"] in PROMOTION_LABELS else "단순병역정보"
        results.append({
            "title":        s["title"][:60],
            "gold_l2":      s["gold_l2"],
            "pred_l2":      pred["label_l2"],
            "gold_l1":      gold_l1,
            "pred_l1":      pred["label_l1"],
            "gold_subject": s["gold_subject"],
            "pred_subject": pred["subject"],
            "score":        pred["false_score"],
            "reason":       pred["false_reason"],
        })
        mark = "O" if s["gold_l2"] == pred["label_l2"] else ("△" if gold_l1 == pred["label_l1"] else "X")
        # flush=True: 파이프/리다이렉트로 실행해도 로그에 실시간 기록되도록
        print(f"  [{i}/{len(picked)}] {mark} 정답={s['gold_l2']} 예측={pred['label_l2']} | {s['title'][:35]}",
              flush=True)
        time.sleep(0.6)  # API 부하 방지

    if not results:
        print("평가 결과 없음")
        return

    # ── 지표 ──
    n = len(results)
    gold_promo = [r for r in results if r["gold_l1"] == "조장정보"]
    pred_promo = [r for r in results if r["pred_l1"] == "조장정보"]
    tp = sum(1 for r in gold_promo if r["pred_l1"] == "조장정보")

    l1_recall    = tp / len(gold_promo) if gold_promo else 0
    l1_precision = tp / len(pred_promo) if pred_promo else 0
    l2_acc       = sum(1 for r in results if r["gold_l2"] == r["pred_l2"]) / n
    subj_pairs   = [r for r in results if r["gold_subject"]]
    subj_acc     = (sum(1 for r in subj_pairs if r["gold_subject"] == r["pred_subject"])
                    / len(subj_pairs)) if subj_pairs else None

    print(f"\n{'='*60}")
    print(f"평가 결과 (n={n})")
    print(f"  조장정보 L1 재현율: {l1_recall:.3f}  (목표 ≥ 0.85)")
    print(f"  조장정보 L1 정밀도: {l1_precision:.3f}")
    print(f"  L2 정확도(7라벨):   {l2_acc:.3f}")
    if subj_acc is not None:
        print(f"  과목 정확도:        {subj_acc:.3f} (n={len(subj_pairs)})")

    print("\n라벨별 L2 정확도:")
    for label in sorted(by_label):
        rs = [r for r in results if r["gold_l2"] == label]
        if rs:
            acc = sum(1 for r in rs if r["pred_l2"] == label) / len(rs)
            print(f"  {label}: {acc:.2f} ({len(rs)}건)")

    out = f"eval_result_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"\n상세 결과 저장: {out}")


if __name__ == "__main__":
    main()
