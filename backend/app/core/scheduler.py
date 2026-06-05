import holidays
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.database import supabase
from app.crawlers.naver import crawl_naver
from app.crawlers.youtube import crawl_youtube
from app.crawlers.dcinside import crawl_dcinside
from app.services.analyzer import analyze_unclassified
from app.services.notifier import send_alerts

scheduler = BackgroundScheduler(timezone="Asia/Seoul")

# 한국 공휴일 (매년 자동 갱신)
KR_HOLIDAYS = holidays.KR()


def _is_workday() -> bool:
    """오늘이 근무일(월~금, 공휴일 제외)인지 확인."""
    today = date.today()
    if today.weekday() >= 5:      # 토(5), 일(6)
        return False
    if today in KR_HOLIDAYS:      # 공휴일
        return False
    return True


def run_crawl_and_analyze():
    """크롤링 → AI 분류 → 알림 (근무일에만 실행)."""
    if not _is_workday():
        holiday_name = KR_HOLIDAYS.get(date.today(), "주말")
        print(f"[스케줄러] 오늘은 {holiday_name} — 크롤링 건너뜀")
        return

    print(f"[스케줄러] 크롤링 시작")
    sources = supabase.table("crawl_sources").select("*").eq("is_active", True).execute().data

    total_saved = 0
    for src in sources:
        stype = src["source_type"]
        sid   = src["id"]
        kws   = src["keywords"]

        if stype in ("naver_news", "naver_blog", "naver_cafe"):
            n = crawl_naver(sid, stype, kws)
        elif stype == "youtube":
            n = crawl_youtube(sid, kws)
        elif stype == "dcinside":
            n = crawl_dcinside(sid, kws)
        else:
            n = 0

        print(f"  {src['name']}: {n}건 수집")
        total_saved += n

    print(f"[스케줄러] 총 {total_saved}건 수집 완료")

    if total_saved > 0:
        analyzed = analyze_unclassified(limit=total_saved + 10)
        print(f"[스케줄러] AI 분류: {analyzed}건 완료")
        if analyzed > 0:
            send_alerts()
            print("[스케줄러] 알림 발송 완료")


def start_scheduler():
    if not scheduler.running:
        # 평일(월~금) 오전 08:00에 실행 — 공휴일은 실행 시 내부에서 건너뜀
        scheduler.add_job(
            run_crawl_and_analyze,
            CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
            id="main_crawl",
            replace_existing=True,
        )
        scheduler.start()
        print("스케줄러 시작 완료 (평일 08:00, 공휴일 자동 제외)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
