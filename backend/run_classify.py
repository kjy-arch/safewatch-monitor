import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from app.core.database import supabase
from app.services.analyzer import analyze_unclassified
from app.services.notifier import send_alerts

print("AI 분류 시작 (자동 재시도 포함)...")
start = time.time()
total_analyzed = 0
fail_streak = 0  # 연속 실패 횟수

while True:
    undone = len(supabase.table('crawled_articles').select('id').is_('false_score', 'null').execute().data)
    total  = len(supabase.table('crawled_articles').select('id').execute().data)
    done   = total - undone
    elapsed = int(time.time() - start)
    mins = elapsed // 60
    secs = elapsed % 60

    print(f"  [{mins}분 {secs}초 경과] {done}/{total}건 ({done/total*100:.1f}%) — 남은 {undone}건")

    if undone == 0:
        print("모든 기사 분류 완료!")
        break

    n = analyze_unclassified(limit=10)
    total_analyzed += n

    if n == 0:
        fail_streak += 1
        if fail_streak >= 5:
            # 5번 연속 실패 → 완전 종료
            print(f"연속 {fail_streak}회 실패 — 종료합니다.")
            break
        # 실패 시 잠깐 대기 후 재시도
        wait = fail_streak * 10
        print(f"  ⚠️  처리 실패 ({fail_streak}회) — {wait}초 대기 후 재시도...")
        time.sleep(wait)
    else:
        fail_streak = 0
        # 성공 시에도 1초 텀을 줘서 API 부하 방지
        time.sleep(1)

print(f"\n총 {total_analyzed}건 분류 완료")
print("이메일 발송 중...")
send_alerts()
print("완료! Gmail을 확인해주세요.")
