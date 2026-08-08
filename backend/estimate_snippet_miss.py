"""요약본 판정의 누락률 추정 — 비대상으로 떨어진 글 중 진짜가 얼마나 되나 (2026-08-07).

2단계 검증(services/verify.py)은 **삭제대상으로 올라온 건만** 다시 본다. 1차에서 비대상으로
떨어진 글은 쳐다보지 않으므로 **오탐만 줄고 누락은 그대로**다. 그 누락이 무시할 수준인지
아닌지를 전수 조사 없이 알기 위해, 비대상 판정분에서 표본을 뽑아 본문으로 재판정한다.

읽는 법:
  누락률 1~2%  → 2단계 검증으로 충분하다
  누락률 10%+  → 본문 전면 수집(=네이버 스크래핑, D1 법무검토 대상)을 정면으로 논의해야 한다

실행:
  .venv\\Scripts\\python.exe estimate_snippet_miss.py            # 오늘, 60건
  .venv\\Scripts\\python.exe estimate_snippet_miss.py --n 100 --date 2026-08-07

⚠️ Gemini 호출과 페이지 조회가 표본 수만큼 발생한다. 본문 조회는 공식 API가 아니라
   렌더링된 페이지 조회이며 D1 대상이다(crawlers/fulltext.py 참조).
"""
import argparse
import math
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")

from app.core.database import supabase                      # noqa: E402
from app.crawlers.fulltext import FETCHABLE, fetch_fulltext  # noqa: E402
from app.services.analyzer import _analyze                   # noqa: E402
from app.services.verify import REQUEST_DELAY, VERIFY_MAX_CHARS  # noqa: E402

SEED = 42


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 신뢰구간 — 표본이 작고 비율이 0에 가까울 때 정규근사보다 낫다."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - m) / d), min(1.0, (c + m) / d))


def main() -> None:
    ap = argparse.ArgumentParser(description="요약본 판정의 누락률 추정")
    ap.add_argument("--n", type=int, default=60, help="표본 크기 (기본 60)")
    ap.add_argument("--date", default=None, help="대상 수집일 YYYY-MM-DD (기본 오늘 KST)")
    args = ap.parse_args()

    day = args.date or datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")

    rows = (
        supabase.table("crawled_articles")
        .select("id, title, content, url, source_type, action_type, label_l2, false_reason")
        .gte("created_at", day)
        .eq("action_type", "비대상")
        .execute()
        .data
    )
    pool = [r for r in rows if r["source_type"] in FETCHABLE]
    skipped = Counter(r["source_type"] for r in rows if r["source_type"] not in FETCHABLE)

    print(f"수집일 {day} · 비대상 {len(rows)}건")
    print(f"  조회 가능 모집단 {len(pool)}건 — {dict(Counter(r['source_type'] for r in pool))}")
    print(f"  제외 {sum(skipped.values())}건 — {dict(skipped)} (카페 로그인 벽 / 유튜브 이미 전문)")
    if not pool:
        print("모집단이 비어 있습니다."); return

    # 출처별 층화 — 한 출처가 표본을 독점하지 않게 비례 배분
    by_src: dict[str, list] = defaultdict(list)
    for r in pool:
        by_src[r["source_type"]].append(r)
    rng = random.Random(SEED)
    sample: list = []
    for src, items in sorted(by_src.items()):
        take = max(1, round(args.n * len(items) / len(pool)))
        rng.shuffle(items)
        sample += items[:take]
    rng.shuffle(sample)
    sample = sample[:args.n]

    print(f"\n표본 {len(sample)}건 (seed={SEED}) — {dict(Counter(r['source_type'] for r in sample))}")
    print("본문 조회 + 재판정 중...\n")

    departments = supabase.table("departments").select("id, name, keywords").execute().data
    flipped, checked, failed = [], 0, 0
    per_src: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [검사, 뒤집힘]

    for i, r in enumerate(sample, 1):
        src = r["source_type"]
        try:
            body = fetch_fulltext(r.get("url") or "", src)
            if not body:
                failed += 1
                continue
            res = _analyze(r.get("title") or "", body, src, departments,
                           max_chars=VERIFY_MAX_CHARS)
            checked += 1
            per_src[src][0] += 1
            if res["action_type"] != "비대상":
                per_src[src][1] += 1
                flipped.append((r, res, body))
                print(f"  [{i:3}/{len(sample)}] 뒤집힘 → {res['action_type']} ({src}) "
                      f"{(r.get('title') or '')[:34]}")
        except Exception as e:
            print(f"  [{i:3}/{len(sample)}] 실패: {type(e).__name__}: {e}")
            failed += 1
        finally:
            time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 62)
    if checked == 0:
        print("본문을 하나도 가져오지 못했습니다 — 조회 경로를 점검하세요."); return

    k = len(flipped)
    lo, hi = wilson(k, checked)
    print(f"검사 {checked}건 (조회실패 {failed}) · 뒤집힘 {k}건")
    print(f"누락률 추정 {k/checked:.1%}   95% 신뢰구간 [{lo:.1%}, {hi:.1%}]")
    print(f"→ 비대상 {len(pool)}건 기준 환산 {round(len(pool)*k/checked)}건 "
          f"(구간 {round(len(pool)*lo)}~{round(len(pool)*hi)}건)")

    print("\n출처별")
    for src, (n, f) in sorted(per_src.items()):
        print(f"  {src:6} {f}/{n}" + (f"  {f/n:.0%}" if n else ""))

    if flipped:
        print("\n뒤집힌 건 (1차 요약 → 2차 본문)")
        for r, res, body in flipped[:10]:
            print(f"\n  [{res['action_type']}/{res['label_l2']}] {r['url'][:72]}")
            print(f"    1차 요약({len(r['content'] or '')}자): {(r['content'] or '')[:90]}")
            print(f"    2차 본문({len(body)}자): {body[:90]}")
            print(f"    2차 사유: {res['false_reason'][:80]}")

    print("\n판단 기준: 1~2%면 2단계 검증으로 충분. 10% 이상이면 본문 전면 수집을 논의할 것"
          " (D1 법무검토 대상).")


if __name__ == "__main__":
    main()
