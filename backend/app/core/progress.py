"""수집·분류 실행 진행 상태 (인메모리).

스케줄러/수동 실행이 한 번에 하나만 도므로 단일 전역 상태로 충분하다.
APScheduler 스레드와 FastAPI 요청이 동시에 접근하므로 Lock으로 보호한다.
"""
import threading
from datetime import datetime, timezone, timedelta

_lock = threading.Lock()

_state: dict = {
    "status":      "idle",   # idle | running | done | error
    "phase":       "",       # 크롤링 | 분류 | 알림
    "phase_done":  0,
    "phase_total": 0,
    "collected":   0,        # 이번 실행 수집 건수
    "analyzed":    0,        # 이번 실행 분류 건수
    "high":        0,        # 이번 실행 위험 높음 건수
    "mid":         0,        # 이번 실행 위험 중간 건수
    "started_at":  None,
    "finished_at": None,
    "message":     "",
}


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=9))).isoformat()


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def start(total_sources: int) -> None:
    with _lock:
        _state.update(
            status="running", phase="크롤링",
            phase_done=0, phase_total=total_sources,
            collected=0, analyzed=0, high=0, mid=0,
            started_at=_now(), finished_at=None, message="",
        )


def crawl_step(done: int, collected: int) -> None:
    with _lock:
        _state.update(phase="크롤링", phase_done=done, collected=collected)


def start_classify() -> None:
    with _lock:
        _state.update(phase="분류", phase_done=0, phase_total=0)


def classify_step(done: int, total: int) -> None:
    with _lock:
        _state.update(phase="분류", phase_done=done, phase_total=total, analyzed=done)


def count_risk(level: str) -> None:
    """분류 결과의 위험도를 이번 실행 카운터에 반영 (높음/중간만)."""
    with _lock:
        if level == "높음":
            _state["high"] += 1
        elif level == "중간":
            _state["mid"] += 1


def start_notify() -> None:
    with _lock:
        _state.update(phase="알림")


def finish(message: str = "") -> None:
    with _lock:
        _state.update(status="done", phase="완료", finished_at=_now(), message=message)


def fail(message: str) -> None:
    with _lock:
        _state.update(status="error", finished_at=_now(), message=message)


def snapshot() -> dict:
    """현재 상태 + 계산된 진행률(%). 진행률은 현재 단계의 처리/전체 비율."""
    with _lock:
        s = dict(_state)
    total = s["phase_total"]
    if s["status"] == "done":
        s["percent"] = 100
    elif total > 0:
        s["percent"] = round(s["phase_done"] / total * 100)
    else:
        s["percent"] = 0
    return s
