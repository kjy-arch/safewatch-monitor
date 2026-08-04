"""통합본 라우트 구성 테스트 — 모니터·분류자 양쪽 API가 모두 살아있는지 (네트워크 없음).

Phase 1(분류자 백엔드 흡수)의 성공 조건을 고정한다. 이후 단계에서 라우터를
옮기거나 이름을 바꾸다 한쪽이 사라지는 회귀를 막는 것이 목적.

실행: .venv\\Scripts\\python.exe tests\\test_integration_routes.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from app.main import app

failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


routes = [(m, r.path) for r in app.routes if hasattr(r, "methods")
          for m in sorted(r.methods - {"HEAD", "OPTIONS"})]
paths = {p for _, p in routes}

# 모니터 계열 — 수집·진행률·백로그·통계
MONITOR = {
    "/api/health", "/api/crawl/sources", "/api/crawl/run", "/api/crawl/status",
    "/api/crawl/backlog", "/api/crawl/analyze", "/api/articles",
    "/api/articles/export", "/api/stats",
    "/api/classify/excel", "/api/classify/result", "/api/classify/export",
}
# 분류자 계열 — 배치 업로드·부서·보고서·설정
CLASSIFIER = {
    "/api/batches", "/api/batches/upload", "/api/batches/{batch_id}",
    "/api/batches/{batch_id}/analyze", "/api/batches/{batch_id}/stats",
    "/api/batches/{batch_id}/download",
    "/api/departments", "/api/departments/{dept_id}",
    "/api/reports/quarterly/download", "/api/settings",
}

print("[모니터 계열]")
for p in sorted(MONITOR):
    check(p, p in paths)

print("\n[분류자 계열]")
for p in sorted(CLASSIFIER):
    check(p, p in paths)

print("\n[구성 검증]")
dupes = {r for r in routes if routes.count(r) > 1}
check("메서드+경로 중복 없음", not dupes, f"중복: {dupes}")

# 분류자 서비스는 batch/ 네임스페이스에 있어야 한다 — 모니터 analyzer와 섞이면 안 됨
import app.services.analyzer as monitor_analyzer
import app.services.batch.analyzer as batch_analyzer
check("모니터/분류자 analyzer가 서로 다른 모듈",
      monitor_analyzer is not batch_analyzer)
check("모니터 analyzer는 수집분 분류 함수 보유",
      hasattr(monitor_analyzer, "analyze_unclassified"))
check("분류자 analyzer는 배치 분류 함수 보유",
      hasattr(batch_analyzer, "analyze_batch"))

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
