"""수집분 본문 조회 — 2단계 검증·표본 측정 전용 (2026-08-07).

수집 단계는 네이버 검색 API의 요약(`description`, 약 120자)만 저장한다
(`crawlers/naver.py`). 그 요약만 보고 삭제대상으로 판정한 글이 실제로는 정상 안내였던
사례가 확인돼(지식인 docId=494564616 — 답변 전문은 병무용 진단서 제도 안내였고 "전화번호"는
지방병무청 상담번호 14개 목록이었다), **판정을 확정하기 전에 본문을 한 번 더 보기 위한**
모듈이다.

⚠️ 이 모듈은 공식 검색 API가 아니라 **렌더링된 페이지를 조회**한다. 디시인사이드·에펨코리아
스크래핑과 같은 범주이며 **D1(회색지대 법무·정보보안 검토) 대상**이다. 그래서 전건이 아니라
삭제대상·표본에만 쓴다.

출처별 가능 여부 (2026-08-07 실측):
  지식인   ⭕ 직접 조회
  SNS      ⭕ iframe 한 단계 더 (blog.naver.com/PostView.naver)
  언론     ⭕ 직접 조회 (매체마다 구조가 달라 선택자 목록 + 최장 블록 폴백)
  커뮤니티 ❌ 네이버 카페는 로그인 벽 — 빈 문자열 반환
  유튜브   — 댓글·영상설명이 이미 전문이라 조회할 이유가 없다

호출자는 요청 사이에 대기를 두어야 한다(`crawlers/dcinside.py`와 같은 0.5초 기준).
"""
from __future__ import annotations

import re
import time

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
}
TIMEOUT = 10

# 본문 조회 대상 출처. 나머지는 이유와 함께 건너뛴다.
FETCHABLE = {"지식인", "SNS", "언론"}
SKIP_REASON = {
    "커뮤니티": "네이버 카페 로그인 벽",
    "유튜브":   "댓글·영상설명이 이미 전문",
}

# 지식인: 질문 + 답변 전체. `.se-main-container`는 블로그와 공용 에디터라 함께 걸린다.
_KIN_SELECTORS = [".questionDetail", ".answerDetail", "._endContentsText"]
# 블로그 본문 (iframe 안쪽)
_BLOG_SELECTORS = [".se-main-container", "#postViewArea", ".post-view", "#viewTypeSelector"]
# 언론: 매체마다 다르다. 흔한 것부터 훑고, 없으면 최장 텍스트 블록으로 폴백한다.
_NEWS_SELECTORS = [
    "#article-view-content-div", "#articleBodyContents", "#dic_area",
    ".article-body", ".article_body", ".news_body", "#newsct_article", "article",
]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _soup(url: str) -> BeautifulSoup | None:
    res = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    if res.status_code != 200:
        print(f"[fulltext] HTTP {res.status_code}: {url[:80]}", flush=True)
        return None
    s = BeautifulSoup(res.text, "html.parser")
    for tag in s(["script", "style", "noscript"]):
        tag.decompose()
    return s


def _by_selectors(soup: BeautifulSoup, selectors: list[str]) -> str:
    """선택자 목록에 걸리는 요소를 모두 이어 붙인다. 중복 텍스트는 한 번만."""
    seen: list[str] = []
    for sel in selectors:
        for el in soup.select(sel):
            t = _clean(el.get_text(" ", strip=True))
            if t and not any(t in s for s in seen):
                seen.append(t)
    return "\n".join(seen)


def _longest_block(soup: BeautifulSoup) -> str:
    """선택자가 하나도 안 맞을 때 — 가장 긴 <div>/<section>을 본문으로 본다.
    네비게이션·푸터가 섞이지만, 요약 120자보다는 판정에 도움이 된다."""
    best = ""
    for el in soup.find_all(["div", "section", "article"]):
        t = _clean(el.get_text(" ", strip=True))
        if len(t) > len(best):
            best = t
    return best


def _fetch_kin(url: str) -> str:
    soup = _soup(url)
    return _by_selectors(soup, _KIN_SELECTORS) if soup else ""


def _fetch_blog(url: str) -> str:
    """네이버 블로그는 본문이 iframe 안에 있다. src를 따라 한 번 더 들어간다."""
    outer = _soup(url)
    if outer is None:
        return ""
    iframe = outer.find("iframe")
    src = iframe.get("src") if iframe else None
    if not src:
        # 이미 본문 페이지인 경우(PostView 직링크 등)
        return _by_selectors(outer, _BLOG_SELECTORS)
    if src.startswith("/"):
        src = "https://blog.naver.com" + src
    time.sleep(0.3)
    inner = _soup(src)
    return _by_selectors(inner, _BLOG_SELECTORS) if inner else ""


def _fetch_news(url: str) -> str:
    soup = _soup(url)
    if soup is None:
        return ""
    return _by_selectors(soup, _NEWS_SELECTORS) or _longest_block(soup)


_FETCHERS = {"지식인": _fetch_kin, "SNS": _fetch_blog, "언론": _fetch_news}


def fetch_fulltext(url: str, source_type: str) -> str:
    """본문을 최대한 가져온다. 불가·실패면 빈 문자열(예외를 올리지 않는다).

    호출자는 반환값이 비었는지 보고 '조회실패'를 기록하면 된다.
    """
    if not url:
        return ""
    if source_type not in FETCHABLE:
        reason = SKIP_REASON.get(source_type, "지원하지 않는 출처")
        print(f"[fulltext] 건너뜀({source_type}): {reason}", flush=True)
        return ""
    try:
        return _FETCHERS[source_type](url)
    except Exception as e:
        print(f"[fulltext] 조회 실패({source_type}): {type(e).__name__}: {e} — {url[:70]}",
              flush=True)
        return ""
