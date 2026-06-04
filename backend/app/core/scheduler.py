from apscheduler.schedulers.background import BackgroundScheduler
from app.core.database import supabase
from app.crawlers.naver import crawl_naver
from app.crawlers.youtube import crawl_youtube
from app.crawlers.dcinside import crawl_dcinside
from app.services.analyzer import analyze_unclassified
from app.services.notifier import send_alerts

scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def run_crawl_and_analyze():
    """전체 크롤링 → AI 분류 → 알림 실행."""
    sources = supabase.table("crawl_sources").select("*").eq("is_active", True).execute().data

    total_saved = 0
    for src in sources:
        stype = src["source_type"]
        sid   = src["id"]
        kws   = src["keywords"]

        if stype in ("naver_news", "naver_blog", "naver_cafe"):
            total_saved += crawl_naver(sid, stype, kws)
        elif stype == "youtube":
            total_saved += crawl_youtube(sid, kws)
        elif stype == "dcinside":
            total_saved += crawl_dcinside(sid, kws)

    if total_saved > 0:
        analyzed = analyze_unclassified(limit=total_saved + 10)
        if analyzed > 0:
            send_alerts()


def start_scheduler():
    if not scheduler.running:
        # 매 60분마다 실행 (조정 가능)
        scheduler.add_job(run_crawl_and_analyze, "interval", minutes=60, id="main_crawl")
        scheduler.start()
        print("스케줄러 시작 완료 (60분 주기)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
