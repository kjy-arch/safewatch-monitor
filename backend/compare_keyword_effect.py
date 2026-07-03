"""키워드 확장 효과 측정 — 확장 전 기준선 저장 후, 일정 기간 뒤 비교.

사용법:
  .venv\\Scripts\\python.exe compare_keyword_effect.py --baseline   # 003 적용 전 실행
  .venv\\Scripts\\python.exe compare_keyword_effect.py --compare    # 1주 후 실행

측정: 일평균 수집량, 조장정보(label_l2) 비율, 라벨·출처 분포.
한계: 기사별 매칭 키워드는 저장하지 않으므로 "신규 키워드로만 잡힌 글"은
직접 셀 수 없다 — 수집량·조장비율 변화로 간접 판단한다.
"""
import sys, json, argparse
from datetime import datetime, timezone, timedelta
sys.stdout.reconfigure(encoding="utf-8")

from app.core.database import supabase

BASELINE_FILE = "keyword_baseline.json"
WINDOW_DAYS = 7


def collect_stats(start_iso: str, end_iso: str) -> dict:
    def fetch(columns):
        return (
            supabase.table("crawled_articles")
            .select(columns)
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
            .execute()
            .data
        )

    try:
        rows = fetch("created_at, source_type, false_score, label_l2")
    except Exception:
        # 002 마이그레이션 전(label_l2 없음) — 점수 기반으로만 집계
        rows = fetch("created_at, source_type, false_score")
    days = max(1, (datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)).days)
    promo_labels = {"방법문의", "방법안내", "브로커의심", "신뢰저하", "의도의심"}

    by_label, by_source = {}, {}
    promo = 0
    for r in rows:
        label = r.get("label_l2") or "미분류"
        by_label[label] = by_label.get(label, 0) + 1
        src = r.get("source_type") or "-"
        by_source[src] = by_source.get(src, 0) + 1
        if label in promo_labels or (r.get("false_score") or 0) >= 67:
            promo += 1

    return {
        "window": [start_iso, end_iso],
        "total": len(rows),
        "daily_avg": round(len(rows) / days, 1),
        "promo_count": promo,
        "promo_ratio": round(promo / len(rows), 3) if rows else 0,
        "by_label": by_label,
        "by_source": by_source,
    }


def show(stats: dict, tag: str):
    print(f"\n[{tag}] {stats['window'][0][:10]} ~ {stats['window'][1][:10]}")
    print(f"  총 수집: {stats['total']}건 (일평균 {stats['daily_avg']}건)")
    print(f"  조장정보: {stats['promo_count']}건 ({stats['promo_ratio']*100:.1f}%)")
    print(f"  출처별: {stats['by_source']}")
    print(f"  라벨별: {stats['by_label']}")


def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--baseline", action="store_true")
    g.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=WINDOW_DAYS)).isoformat()

    if args.baseline:
        stats = collect_stats(start, now.isoformat())
        stats["saved_at"] = now.isoformat()
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        show(stats, "기준선 (확장 전 최근 7일)")
        print(f"\n저장: {BASELINE_FILE} — 003 마이그레이션 적용 후 1주 뒤 --compare 실행")
        return

    try:
        with open(BASELINE_FILE, encoding="utf-8") as f:
            base = json.load(f)
    except FileNotFoundError:
        print(f"{BASELINE_FILE} 없음 — 먼저 --baseline을 실행하세요.")
        sys.exit(1)

    current = collect_stats(start, now.isoformat())
    show(base, "기준선 (확장 전)")
    show(current, "현재 (확장 후)")

    d_daily = current["daily_avg"] - base["daily_avg"]
    d_ratio = current["promo_ratio"] - base["promo_ratio"]
    print(f"\n변화: 일평균 {d_daily:+.1f}건, 조장 비율 {d_ratio*100:+.1f}%p")
    if d_daily > 0 and d_ratio >= -0.02:
        print("판정: 수집량 증가 + 조장 비율 유지 → 키워드 확장 유효")
    elif d_daily > 0:
        print("판정: 수집량은 늘었으나 조장 비율 하락 → 노이즈 키워드 재선별 검토")
    else:
        print("판정: 수집량 변화 없음/감소 → 키워드·크롤러 동작 점검 필요")


if __name__ == "__main__":
    main()
