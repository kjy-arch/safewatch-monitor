r"""로컬 전용 운영의 네트워크 보안 기본값 회귀 테스트.

실행: .venv\Scripts\python.exe tests\test_security_defaults.py
"""
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import Settings


failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


required = {
    "SUPABASE_URL": "https://dummy.supabase.co",
    "SUPABASE_SECRET_KEY": "dummy",
    "GEMINI_API_KEY": "dummy",
    "NAVER_CLIENT_ID": "dummy",
    "NAVER_CLIENT_SECRET": "dummy",
    "YOUTUBE_API_KEY": "dummy",
}
defaults = Settings(_env_file=None, **required)
origins = {origin.strip() for origin in defaults.CORS_ORIGINS.split(",")}

print("[CORS 기본값]")
check("와일드카드 미허용", "*" not in origins, f"got {origins}")
check("Vite localhost 허용", "http://localhost:5173" in origins, f"got {origins}")
check("Vite loopback 허용", "http://127.0.0.1:5173" in origins, f"got {origins}")

print("\n[운영 실행 바인딩]")
launcher = (Path(__file__).parents[1] / "run_monitor.bat").read_text(encoding="utf-8")
check("loopback 바인딩", "--host 127.0.0.1" in launcher)
check("전체 인터페이스 바인딩 금지", "--host 0.0.0.0" not in launcher)

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
