"""키워드 점수 기반 사전 필터 — Gemini 호출 전 저비용 우선순위/스킵 판단.

점수 사전(app/data/keyword_scores.json)은 build_keyword_scores.py로 생성한다.
사전 파일이 없으면 스코어링이 비활성화되어 모든 기사가 Gemini로 간다 (기존 동작).

임계치는 23~24년 라벨 데이터로 검증해 결정 (validate_prefilter.py):
조장정보를 스킵하는 비율(promo miss)이 2% 이하가 되는 최대값.
"""
import json, os

from app.services.text_normalize import compact, normalize

_SCORES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "keyword_scores.json")

# ── 난독화 대응 ────────────────────────────────────────────────
# 조장 게시물은 구분자 삽입(병.역.면.제 / 병 역 면 제)과 zero-width 문자로 키워드 필터를
# 회피한다. 원문만 비교하면 그런 글이 게이트를 넘지 못하고 '비대상'으로 자동 확정된 뒤
# Gemini에 가지 않는다(analyzer.py). 그래서 세 형태를 **합집합**으로 본다:
#   ① 원문        — 현행 그대로. 지금 잡히던 건 하나도 잃지 않는다.
#   ② normalize() — NFKC·zero-width·제어문자 제거. 어절 경계를 안 바꿔 오탐 위험 0.
#   ③ compact()   — 공백·구분자까지 제거. 난독화를 뚫지만 **어절 경계를 넘어 매치된다.**
#
# ③의 적용 범위는 게이트와 사전이 다르다 — **오탐 비용이 다르기 때문**이다.
# 로컬 실데이터(게시물 제목 504 · Gemini 산문 504 · 한국어 산문 문단 477)로
# "원문엔 없고 compact에만 있는 매치"를 전수 조사해 정했다.
#
# ▸ 게이트(MILITARY_TERMS 31개) = **전 용어 적용**
#   오탐 비용은 Gemini 호출 1건, 누락 비용은 조장 글이 '비대상'으로 조용히 확정되는 것.
#   비대칭이 크고, 실측도 안전했다 — 게이트 통과율 63.2% -> 63.5%(**+0.27%p**),
#   압축 유발 6건 중 5건이 정당(`군 면제 구매 문의`는 실제 브로커 광고였다).
#   경계 아티팩트는 '이제 대조'->제대 **1건/1,485건(0.07%)**.
#   길이 3 이상으로 제한하면 병역·면제·군대가 전부 빠져 **대표 사례 '병.역.면.제'를
#   못 잡는다** — 제한이 목적을 무력화한다.
#
# ▸ 사전(keyword_scores.json 493개) = **길이 3 이상만**
#   - 길이 3 이상: 60건 전부 정당(군면제/병역기피/병역판정/양극성장애 …). **오탐 0건**
#   - 길이 2 이하: 94건 중 대부분 경계 아티팩트. 게이트와 달리 사전에는 일상어가 많다 —
#       '조장 기저율'->장기 · '점수 사전'->수사 · '확인 대안'->인대 · '형들의 지식'->의지
#       '노예의 사슬'->의사 · '신체검사 시'->사시 · '여호와의 증인'->의증
#   - 2음절 은어도 예외 없음: **'병역판정 공정성' -> '정공'** 오탐 2건이 실측됐다.
#     난독화된 2음절 은어(정.공)는 사전 점수를 못 받지만, 게이트와 원문 매칭(①)이 받는다.
#
# 측정 스크립트는 일회성이라 저장소에 두지 않았다. 사전이 바뀌면 다시 잴 것.
_COMPACT_MIN_LEN = 3

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


# 게이트는 길이 제한 없이 전 용어를 압축형으로도 본다 (위 측정 근거).
_MILITARY_COMPACT = tuple(compact(k) for k in MILITARY_TERMS)


def has_military_context(text: str) -> bool:
    """병역 관련 단어가 하나라도 있는지. 없으면 Gemini에 보낼 가치가 없다.

    원문 → 정규화형 → 압축형 순으로 보고 하나라도 걸리면 통과시킨다(합집합)."""
    t = text or ""
    if any(k in t for k in MILITARY_TERMS):
        return True
    if any(k in normalize(t) for k in MILITARY_TERMS):
        return True
    return any(k in compact(t) for k in _MILITARY_COMPACT)

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


_compact_cache: dict[str, str] = {}


def _compact_term(word: str) -> str:
    """사전 단어의 압축형 — 단어 수가 493개라 호출마다 다시 만들지 않고 메모한다.
    (테스트가 `_scores`를 직접 주입하므로 로드 시점이 아니라 조회 시점에 캐시한다)"""
    c = _compact_cache.get(word)
    if c is None:
        c = _compact_cache[word] = compact(word)
    return c


def score_text(text: str) -> int:
    """본문에 등장하는 사전 단어의 가중치 합 (0~SCORE_CAP). 사전 없으면 -1.

    원문 ∪ 정규화형 ∪ 압축형(길이 3 이상)으로 매칭한다 — 한 단어는 어느 형태로
    걸리든 한 번만 가산된다."""
    scores = _load()
    if scores is None:
        return -1
    text = text or ""
    norm = normalize(text)
    comp = compact(text)
    total = 0
    for word, weight in scores.items():
        cw = _compact_term(word)
        if (word in text
                or word in norm
                or (len(cw) >= _COMPACT_MIN_LEN and cw in comp)):
            total += weight
            if total >= SCORE_CAP:
                return SCORE_CAP
    return total


def should_skip(text: str) -> bool:
    """임계치 미만이면 True — Gemini 없이 단순정보로 자동 처리 가능."""
    if not is_enabled():
        return False
    return score_text(text) < PREFILTER_THRESHOLD
