"""담당자 식별 — 실행 이력에 붙일 '누가'를 구한다 (A+B 방식).

  A. Windows 계정명 + PC명  — 자동 수집, 손댈 일 없음
  B. 담당자명               — 최초 1회 입력, 로컬 파일에 저장 후 자동 첨부

⚠️ 이것은 **기록이지 인증이 아니다.** 로그인이 없으므로 값은 위조 가능하고,
   감사에서 본인이 부인하면 반박할 수 없다. 인수인계·업무 파악 용도로만 쓴다.
   부인방지가 필요해지면 로그인 도입이 필요하다.

저장 위치는 저장소 밖(사용자 홈)이라 repo를 다시 받아도 유지된다.
"""
import getpass
import json
import socket
from pathlib import Path

CONFIG_PATH = Path.home() / ".safewatch" / "operator.json"
MAX_NAME_LEN = 40


def _os_account() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _host_name() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return ""


def get_name() -> str | None:
    """저장된 담당자명. 미설정이면 None."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            name = (json.load(f).get("name") or "").strip()
        return name or None
    except (FileNotFoundError, ValueError, OSError):
        return None


def set_name(name: str) -> str:
    """담당자명 저장. 빈 값이면 ValueError."""
    name = (name or "").strip()[:MAX_NAME_LEN]
    if not name:
        raise ValueError("담당자명이 비어 있습니다.")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"name": name}, f, ensure_ascii=False)
    return name


def snapshot() -> dict:
    """실행 이력에 기록할 신원 정보."""
    return {
        "operator_name": get_name(),
        "os_account":    _os_account(),
        "host_name":     _host_name(),
    }


def describe() -> str:
    """로그·화면 표시용 한 줄. 예: '김OO (somes@JJFamily)'"""
    s = snapshot()
    who = f"{s['os_account']}@{s['host_name']}".strip("@")
    return f"{s['operator_name']} ({who})" if s["operator_name"] else (who or "미상")
