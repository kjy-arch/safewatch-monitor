"""키워드 사전 필터 테스트 — 스코어링 + analyzer 자동분류 경로 (API 호출 없음).

실행: .venv\\Scripts\\python.exe tests\\test_prefilter.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
          "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(k, "dummy" if "URL" not in k else "https://dummy.supabase.co")

from types import SimpleNamespace
import app.services.keyword_scorer as scorer
import app.services.analyzer as analyzer

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")
    if not cond:
        failures.append(name)


# ── 1. score_text / should_skip ──
print("[1] keyword_scorer")
scorer._scores = {"공익": 4, "면제": 4, "정공": 8}
scorer._load_attempted = True

# ── 병역 관련성 게이트 ──
# 실수집 676건 중 32%가 병무 무관(육아·운세·잡담)이라 호출이 그대로 낭비됐다.
print("[0] has_military_context")
for t in ["군대 안가는 방법 아는사람", "신검 4급 받고싶다", "예비군 훈련 언제임",
          "군생활 힘들었다", "전역하고 뭐하지", "정공 4급"]:
    check(f"병역 글 통과: {t[:14]}", scorer.has_military_context(t))
for t in ["초6여아 갈수록 키가안자라는데 문제일까요?", "2026년 8월 5일 띠별운세",
          "오늘 점심 뭐 먹지", "14년생 뼈나이 판독 부탁드려요"]:
    check(f"무관 글 차단: {t[:14]}", not scorer.has_military_context(t))
check("빈 문자열은 무관", not scorer.has_military_context(""))
check("None도 안전", not scorer.has_military_context(None))


check("매칭 합산", scorer.score_text("정공으로 공익 갈까") == 12)
check("무관 텍스트 0점", scorer.score_text("오늘 점심 뭐 먹지") == 0)
check("skip: 0점 < 임계치", scorer.should_skip("오늘 점심 뭐 먹지") is True)
# 임계치는 실측에 따라 조정되므로(2 → 5, 2026-08-05) 고정값이 아니라 상대적으로 검증한다
below = "공익 가능?"                     # 4점
above = "정공으로 공익 면제 노린다"        # 16점
check("skip 판정은 임계치 기준",
      scorer.should_skip(below) is (scorer.score_text(below) < scorer.PREFILTER_THRESHOLD))
check("no-skip: 임계치 이상", scorer.should_skip(above) is False,
      f"점수 {scorer.score_text(above)} / 임계치 {scorer.PREFILTER_THRESHOLD}")

scorer._scores = None
check("사전 없으면 -1", scorer.score_text("공익") == -1)
check("사전 없으면 skip 안 함", scorer.should_skip("아무거나") is False)
scorer._scores = {"공익": 4, "면제": 4, "정공": 8}

# ── 2. analyzer 사전필터 경로 ──
print("[2] analyzer 통합")

ROWS = [
    {"id": "junk", "title": "점심 메뉴", "content": "뭐 먹지", "source_type": "커뮤니티"},
    {"id": "hot",  "title": "정공 가능?", "content": "공익 가고싶다", "source_type": "커뮤니티"},
]
captured = {"updates": {}, "gemini_calls": []}


class FakeQuery:
    def __init__(self, name):
        self.name = name
        self._update = None
        self._eq_id = None

    def select(self, *a, **k): return self
    def is_(self, *a): return self
    def limit(self, n): return self
    def order(self, *a, **k): return self  # analyzer가 최신순 정렬 후 조회

    @property
    def not_(self):
        return SimpleNamespace(in_=lambda col, ids: self)

    def update(self, fields):
        self._update = fields
        return self

    def eq(self, col, val):
        self._eq_id = val
        return self

    def execute(self):
        if self._update is not None:
            captured["updates"][self._eq_id] = self._update
            return SimpleNamespace(data=[])
        if self.name == "departments":
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=list(ROWS))


def fake_analyze(title, text, source_type, departments):
    captured["gemini_calls"].append(title)
    # Phase 2 통합 축 — unified_prompt.parse_unified가 돌려주는 형태와 같아야 한다
    return {"label_l1": "조장정보", "label_l2": "의도의심", "subject": "정신과",
            "category": "편법·속임수·공정성 훼손", "action_type": "삭제대상",
            "intent_type": "악의적 유포", "content_type": "과장/왜곡",
            "false_score": 40, "false_level": "중간", "false_reason": "r",
            "department_names": []}


analyzer.supabase = SimpleNamespace(table=lambda n: FakeQuery(n))
analyzer._analyze = fake_analyze
analyzer._failed_ids.clear()

n = analyzer.analyze_unclassified(limit=10)

check("2건 모두 처리", n == 2, f"got {n}")
check("무관 글은 Gemini 미호출", captured["gemini_calls"] == ["정공 가능?"],
      f"got {captured['gemini_calls']}")
junk = captured["updates"].get("junk", {})
check("무관 글 자동분류: 단순내용", junk.get("label_l2") == "단순내용", f"got {junk}")
# 무관 글은 병역 게이트가 먼저 잡는다 → 점수 0 + 사유에 근거 표시
check("무관 글 점수 0", junk.get("false_score") == 0, f"got {junk.get('false_score')}")
check("무관 글 사유에 근거", "병역 관련 단어 없음" in (junk.get("false_reason") or ""),
      f"got {junk.get('false_reason')}")
hot = captured["updates"].get("hot", {})
check("병역 글은 Gemini 결과로 저장", hot.get("label_l2") == "의도의심", f"got {hot}")

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
