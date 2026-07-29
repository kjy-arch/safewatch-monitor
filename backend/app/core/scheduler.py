import holidays
from datetime import date, datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.database import supabase
from app.crawlers.naver import crawl_naver
from app.crawlers.youtube import crawl_youtube
from app.crawlers.dcinside import crawl_dcinside
from app.crawlers.fmkorea import crawl_fmkorea
from app.crawlers.instagram import crawl_instagram
from app.crawlers.x import crawl_x
from app.crawlers.tiktok import crawl_tiktok
from app.services.analyzer import analyze_unclassified
from app.services.notifier import send_alerts
from app.core import progress
from app.core.config import settings

scheduler = BackgroundScheduler(timezone="Asia/Seoul")

# 한국 공휴일 (매년 자동 갱신)
KR_HOLIDAYS = holidays.KR()

# 소스 위험 분류 — 안전(공식 API)은 기본 수집, 회색(스크래핑·비공식)은 화면에서 명시 선택 시에만.
# (D2~D6 미확정 — 잠정 분류. 디시는 회색으로 둠.)
SAFE_TYPES = {"naver_news", "naver_blog", "naver_cafe", "naver_kin", "youtube"}
GRAY_TYPES = {"dcinside", "fmkorea", "instagram", "x", "tiktok"}


def tier_of(source_type: str) -> str:
    return "safe" if source_type in SAFE_TYPES else "gray"


def _is_workday() -> bool:
    """오늘이 근무일(월~금, 공휴일 제외)인지 확인."""
    today = date.today()
    if today.weekday() >= 5:      # 토(5), 일(6)
        return False
    if today in KR_HOLIDAYS:      # 공휴일
        return False
    return True


def run_crawl_and_analyze(force: bool = False, source_ids: list | None = None):
    """크롤링 → AI 분류 → 알림. 스케줄 실행은 근무일에만, 수동 실행(force)은 항상.

    source_ids가 주어지면 그 소스만 수집(화면에서 선택한 것). None이면 안전 소스만
    수집한다 — 회색지대(스크래핑·비공식) 소스는 명시적으로 선택해야만 실행된다.
    """
    if not force and not _is_workday():
        holiday_name = KR_HOLIDAYS.get(date.today(), "주말")
        print(f"[스케줄러] 오늘은 {holiday_name} — 크롤링 건너뜀")
        return

    if progress.is_running():
        print("[스케줄러] 이미 실행 중 — 중복 실행 건너뜀")
        return

    print(f"[스케줄러] 크롤링 시작")
    sources = supabase.table("crawl_sources").select("*").eq("is_active", True).execute().data
    if source_ids is not None:
        wanted = set(source_ids)
        sources = [s for s in sources if s["id"] in wanted]
    else:
        sources = [s for s in sources if s["source_type"] in SAFE_TYPES]

    # 감사 로그 — 회색지대 소스를 포함해 실행한 경우 시각과 함께 기록 (누가·언제는 D4에서 확장)
    gray = [s["name"] for s in sources if s["source_type"] in GRAY_TYPES]
    if gray:
        ts = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
        print(f"[감사] {ts} 회색지대 소스 포함 실행: {', '.join(gray)}")

    progress.start(len(sources))

    total_saved = 0
    failed_sources = []
    for i, src in enumerate(sources, 1):
        stype = src["source_type"]
        sid   = src["id"]
        kws   = src["keywords"]

        try:
            if stype in ("naver_news", "naver_blog", "naver_cafe", "naver_kin"):
                n = crawl_naver(sid, stype, kws)
            elif stype == "youtube":
                n = crawl_youtube(sid, kws)
            elif stype == "dcinside":
                n = crawl_dcinside(sid, kws)
            elif stype == "fmkorea":
                n = crawl_fmkorea(sid, kws)
            elif stype == "instagram":
                n = crawl_instagram(sid, kws)
            elif stype == "x":
                n = crawl_x(sid, kws)
            elif stype == "tiktok":
                n = crawl_tiktok(sid, kws)
            else:
                n = 0
        except Exception as e:
            print(f"[스케줄러] {src['name']} 크롤러 오류: {type(e).__name__}: {e}")
            failed_sources.append(src["name"])
            n = 0

        print(f"  {src['name']}: {n}건 수집")
        total_saved += n
        progress.crawl_step(done=i, collected=total_saved,
                            source_name=src["name"], saved=n)

    summary = f"[스케줄러] 총 {total_saved}건 수집 완료"
    if failed_sources:
        summary += f" (소스 오류: {', '.join(failed_sources)})"
    print(summary)

    try:
        if total_saved > 0:
            progress.start_classify()
            analyzed = analyze_unclassified(limit=total_saved + 10,
                                            progress_cb=progress.classify_step)
            print(f"[스케줄러] AI 분류: {analyzed}건 완료")
            if analyzed > 0:
                progress.start_notify()
                send_alerts()
                print("[스케줄러] 알림 발송 완료")
        progress.finish(summary)
    except Exception as e:
        progress.fail(f"{type(e).__name__}: {e}")
        raise


def start_scheduler():
    if scheduler.running:
        return
    # 테스트 단계에는 자동 수집을 끈다(AUTO_CRAWL=false). 수동 실행(/api/crawl/run)은 항상 동작.
    if not settings.AUTO_CRAWL:
        print("자동 수집 비활성 (AUTO_CRAWL=false) — 수동 실행만 동작")
        return
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
