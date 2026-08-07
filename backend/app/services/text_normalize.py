"""텍스트 정규화 + 난독 해제 — 키워드 매칭 전처리.

병역면탈 조장 게시물은 구분자 삽입(``병.역.면.제``, ``병 역 면 제``)과 zero-width 문자로
키워드 필터를 회피한다. 이 모듈이 없으면 그런 글이 병역 관련성 게이트를 넘지 못하고
`비대상`으로 자동 확정된 뒤 Gemini에 가지 않는다(analyzer.py 사전필터 경로).

두 가지 출력:
  * ``normalize(s)``  -> 읽을 수 있는 정규화 텍스트(NFKC, 제어문자·zero-width 제거,
    공백 정리, 반복 축약). **어절 경계를 바꾸지 않으므로 오탐 위험이 없다.**
  * ``compact(s)``    -> 공백·구분자를 전부 지우고 라틴 문자를 소문자화한 매칭 전용 형태.
    난독화를 뚫지만 **어절 경계를 넘어 매치될 수 있다** — ``"그러면 제가"`` 가
    ``"그러면제가"`` 가 되어 ``면제`` 를 포함한다. 적용 범위는 keyword_scorer.py 참조.

---
출처: 데이터분석팀 safewatch-classifier `src/safewatch/io/normalize.py`.
원본은 git 커밋이 없어(해당 프로젝트가 버전관리 미사용) 리비전을 특정할 수 없다.
이 프로젝트에서 쓰지 않는 ``compact_map()``·``find_span()`` 은 가져오지 않았다
(후자는 ``schema.EvidenceSpan`` 의존을 끌고 온다). 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import re
import unicodedata

# 토큰을 쪼개는 데 흔히 쓰이는 zero-width / BOM / joiner.
_ZERO_WIDTH = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E], None
)

# 매칭 회피용으로 글자 *사이에* 끼워 넣는 구분자.
# compact 형태를 만들 때만 제거한다(표시용 텍스트에서는 절대 지우지 않는다).
_SEP_CHARS = set(" \t\r\n.,·・‥…‧∙•*/\\|~^_-—–=+'\"`´’‘“”()[]{}<>「」『』〈〉!?@#$%&:;")

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTISPACE_RE = re.compile(r"[ \t　]+")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")


def _strip_zero_width(s: str) -> str:
    return s.translate(_ZERO_WIDTH)


def _collapse_repeats(s: str, keep: int = 3) -> str:
    """같은 문자가 ``keep`` 회를 넘겨 반복되면 ``keep`` 회로 줄인다
    (``ㅋㅋㅋㅋㅋㅋ`` -> ``ㅋㅋㅋ``). 은어 노이즈를 줄이되 없애지는 않는다."""
    out: list[str] = []
    run_char = ""
    run_len = 0
    for ch in s:
        if ch == run_char:
            run_len += 1
            if run_len <= keep:
                out.append(ch)
        else:
            run_char, run_len = ch, 1
            out.append(ch)
    return "".join(out)


def normalize(s: str | None) -> str:
    """읽을 수 있는 정규화 형태: NFKC, zero-width·제어문자 제거, 공백·반복 정리.
    어절 경계와 낱말 구조를 보존한다."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _strip_zero_width(s)
    s = _CONTROL_RE.sub("", s)
    s = _collapse_repeats(s, keep=3)
    s = _MULTISPACE_RE.sub(" ", s)
    s = _MULTINEWLINE_RE.sub("\n\n", s)
    return s.strip()


def compact(s: str | None) -> str:
    """매칭 전용 형태: 정규화 텍스트에서 공백과 구분자를 전부 지우고 라틴 문자를
    소문자화한다. ``카 톡 상담`` / ``병.역.면.제`` 가 ``카톡상담`` / ``병역면제`` 로
    매치되게 하는 것이 목적이다.

    **주의**: 낱말을 의도적으로 붙이므로 탐지에만 쓴다. 어절 경계를 넘는 오탐이
    구조적으로 가능하다(``"그러면 제가"`` -> ``"그러면제가"`` 안의 ``면제``)."""
    s = normalize(s)
    return "".join(ch for ch in s if ch not in _SEP_CHARS).lower()
