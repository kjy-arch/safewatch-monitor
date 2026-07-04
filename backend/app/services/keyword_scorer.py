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
PREFILTER_THRESHOLD = 2
SCORE_CAP = 100

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
