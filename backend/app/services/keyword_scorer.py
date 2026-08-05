"""키워드 점수 기반 사전 필터 — Gemini 호출 전 저비용 우선순위/스킵 판단.

점수 사전(app/data/keyword_scores.json)은 build_keyword_scores.py로 생성한다.
사전 파일이 없으면 스코어링이 비활성화되어 모든 기사가 Gemini로 간다 (기존 동작).

임계치는 23~24년 라벨 데이터로 검증해 결정 (validate_prefilter.py):
조장정보를 스킵하는 비율(promo miss)이 2% 이하가 되는 최대값.
"""
import json, os

_SCORES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "keyword_scores.json")

# validate_prefilter.py 실측(23~24년 라벨 6,430건)으로 결정:
# 임계치 2 = 조장 미스율 0.34% (기준 2% 이내), 임계치 3부터 6.17%로 초과.
# 절감 효과는 병역 단어가 없는 라이브 수집 노이즈에서 발생. 사전 재생성 시 재검증할 것.
#
# 출처와 무관하게 이 값 하나만 쓴다 — 사이버조사과 요구 Q7("언론·SNS·커뮤니티·유튜브 등
# 출처별로 판단 기준이나 판단 방식은 동일하게 적용"). 과거 언론에만 임계치 4를 적용했으나,
# 재검증 결과 실익이 호출 3.7% 절감(임계치 2는 2.3%)에 그쳐 요구사항 상충을 감수할
# 이유가 없다고 판단해 2026-08-05 제거했다. 근거: validate_news_prefilter.py
#
# 2026-08-05 실수집 676건 분석으로 2 → 3 상향:
#   임계치 2는 실제로 한 건도 거르지 못했다(라벨 자료는 이미 병역 글만 모은 것이라
#   점수가 높게 나와, 라이브 수집의 노이즈 분포와 달랐다).
#   절감의 대부분은 병역 관련성 게이트(has_military_context)가 담당하고 이 값은 보조다.
#   5까지 올려도 놓치는 삭제대상은 2건으로 같았지만(절감 12.7%), 삭제 요청 누락을
#   더 꺼려 3으로 낮췄다 — 사용자 결정, 2026-08-05. 게이트+3 = 절감 8.1%.
#   사전 재생성·데이터 변동 시 validate_prefilter.py로 재검증할 것.
PREFILTER_THRESHOLD = 3

SCORE_CAP = 100

# ── 병역 관련성 게이트 ──────────────────────────────────────────────
# 이 단어가 본문에 하나도 없으면 병역·병무 얘기가 아니라고 본다.
# 실수집 676건 중 '해당없음'(병무 무관)이 216건(32%)이었고, 성장·육아 카페 글이나
# 운세·잡담이 대량 유입돼 Gemini 호출이 그대로 낭비됐다.
#
# 목록 선정 근거 (676건 실측):
#   기본 25단어만  → 95건 스킵 / 정확도 86.3% / 삭제대상 2건 놓침
#   +군대류 6단어  → 61건 스킵 / 정확도 100%  / 놓침 0건   ← 채택
#   여기에 은어·'병무청'을 더해도 결과가 같아(스킵 61건 동일) 목록을 늘리지 않았다.
# 사전필터 점수와 달리 가중치 없이 '있냐/없냐'만 본다.
MILITARY_TERMS = (
    # 병역 제도·절차
    "병역", "병무", "입영", "입대", "징병", "징집", "복무", "사회복무",
    "신검", "신체검사", "병역판정", "재검", "예비군", "동원훈련",
    # 판정 결과·등급
    "현역", "보충역", "공익", "면제", "면탈", "군면제", "4급", "5급", "6급",
    # 은어
    "정공", "멸공",
    # 군 일반 — 이걸 빼면 "군대 가서는" 같은 조장 글을 놓친다(실측)
    "군대", "군인", "훈련소", "군생활", "전역", "제대",
)


def has_military_context(text: str) -> bool:
    """병역 관련 단어가 하나라도 있는지. 없으면 Gemini에 보낼 가치가 없다."""
    t = text or ""
    return any(k in t for k in MILITARY_TERMS)

_scores: dict | None = None
_load_attempted = False


def _load() -> dict | None:
    global _scores, _load_attempted
    if not _load_attempted:
        _load_attempted = True
        try:
            with open(_SCORES_PATH, encoding="utf-8") as f:
                _scores = json.load(f)
            print(f"[prefilter] 키워드 점수 사전 로드: {len(_scores)}단어")
        except FileNotFoundError:
            print("[prefilter] keyword_scores.json 없음 — 사전 필터 비활성 (전건 Gemini 분류)")
            _scores = None
        except Exception as e:
            print(f"[prefilter] 사전 로드 실패: {type(e).__name__}: {e} — 비활성")
            _scores = None
    return _scores


def is_enabled() -> bool:
    return _load() is not None


def score_text(text: str) -> int:
    """본문에 등장하는 사전 단어의 가중치 합 (0~SCORE_CAP). 사전 없으면 -1."""
    scores = _load()
    if scores is None:
        return -1
    total = 0
    for word, weight in scores.items():
        if word in text:
            total += weight
            if total >= SCORE_CAP:
                return SCORE_CAP
    return total


def should_skip(text: str) -> bool:
    """임계치 미만이면 True — Gemini 없이 단순정보로 자동 처리 가능."""
    if not is_enabled():
        return False
    return score_text(text) < PREFILTER_THRESHOLD
