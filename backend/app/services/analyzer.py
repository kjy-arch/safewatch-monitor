import json, time
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.database import supabase
from app.core import progress
# Phase 2 — 수집분/업로드분이 같은 프롬프트·파서를 쓴다 (app/services/unified_prompt.py)
from app.services.unified_prompt import SYSTEM_PROMPT, parse_unified
from app.services.keyword_scorer import (
    score_text, is_enabled as prefilter_enabled, PREFILTER_THRESHOLD,
    has_military_context,
)

client = genai.Client(api_key=settings.GEMINI_API_KEY)

# 이번 프로세스에서 분류에 실패한 기사 ID — 같은 실행 안에서 같은 기사를
# 반복 재시도해 배치를 점유하는 것을 방지. 재시작하면 초기화되어 자연 재시도.
_failed_ids: set = set()
_FAILED_IDS_MAX = 500


def analyze_unclassified(limit: int = 20, progress_cb=None) -> int:
    """분석 안 된 수집 기사를 Gemini로 분류 (병무청 공식 분류체계).

    progress_cb(done, total)가 주어지면 매 건 처리 시작 시 호출해 진행률을 보고한다.
    """
    # 최신 저장분부터 분류 — 방금 수집한 기사가 오래된 미분류 백로그에 밀리지 않게.
    # (백로그는 수동 '미분류 분류'(POST /api/crawl/analyze)로 따로 소진한다.)
    query = (
        supabase.table("crawled_articles")
        .select("id, title, content, source_type")
        .is_("false_score", "null")
        .order("created_at", desc=True)
    )
    if _failed_ids:
        query = query.not_.in_("id", list(_failed_ids)[:_FAILED_IDS_MAX])
    articles = query.limit(limit).execute().data
    departments = supabase.table("departments").select("id, name, keywords").execute().data

    # 키워드 점수 사전 필터: 고점수 우선 분류, 임계치 미만은 Gemini 없이 단순정보 처리
    if prefilter_enabled():
        articles.sort(key=lambda a: score_text(f"{a.get('title') or ''} {a['content']}"),
                      reverse=True)

    analyzed = 0
    prefiltered = 0
    for idx, article in enumerate(articles, 1):
        if progress_cb:
            progress_cb(idx, len(articles))
        if idx % 20 == 0:
            print(f"[analyzer] 진행 {idx}/{len(articles)}건 (완료 {analyzed}, 사전필터 {prefiltered})",
                  flush=True)
        try:
            text = f"{article.get('title') or ''} {article['content']}"

            # ① 병역 관련성 게이트 — 병역 단어가 하나도 없으면 Gemini에 보내지 않는다.
            #    글은 그대로 저장해 두므로(삭제 아님) 검수 화면에서 되돌릴 수 있고,
            #    false_reason으로 이 규칙이 처리한 건수를 사후 추적할 수 있다.
            # ② 관련은 있으나 키워드 점수가 임계치 미만이면 사전필터로 자동분류.
            #    ①·②는 출처와 무관하게 동일 적용 (요구 Q7).
            kw_score = score_text(text) if prefilter_enabled() else -1
            off_topic = not has_military_context(text)
            if off_topic or 0 <= kw_score < PREFILTER_THRESHOLD:
                reason = ("병역 관련 단어 없음(자동판정)" if off_topic
                          else f"키워드 사전필터 자동분류 (점수 {kw_score})")
                supabase.table("crawled_articles").update({
                    "false_score":  0 if off_topic else 5,
                    "false_level":  "낮음",
                    "false_reason": reason,
                    "label_l2":     "단순내용",
                    "subject":      "기타",
                    # 축 B도 함께 채워야 통합 집계에서 빈칸으로 남지 않는다
                    "category":     "해당없음",
                    "action_type":  "비대상",
                    "intent_type":  "불명확",
                    "content_type": "문제없음",
                }).eq("id", article["id"]).execute()
                prefiltered += 1
                analyzed += 1
                progress.count_analyzed()
                continue

            result = _analyze(article.get("title") or "", article["content"],
                              article["source_type"], departments)
            dept_ids = _find_depts(result.get("department_names"), departments)

            update_fields = {
                "false_score":  result["false_score"],
                "false_level":  result["false_level"],
                "false_reason": result["false_reason"],
                "label_l2":     result["label_l2"],
                "subject":      result["subject"],
                # 축 B (가이드라인) — Phase 2에서 추가된 컬럼
                "category":     result["category"],
                "action_type":  result["action_type"],
                "intent_type":  result["intent_type"],
                "content_type": result["content_type"],
                "department_id":   dept_ids[0] if dept_ids else None,
                "department_id_2": dept_ids[1] if len(dept_ids) > 1 else None,
            }
            try:
                supabase.table("crawled_articles").update(update_fields).eq("id", article["id"]).execute()
            except Exception:
                # 확장 컬럼 미적용(002·006 마이그레이션 전)이어도 분류 자체는 저장
                for f in ("label_l2", "subject", "category", "action_type",
                          "intent_type", "content_type", "department_id_2"):
                    update_fields.pop(f, None)
                supabase.table("crawled_articles").update(update_fields).eq("id", article["id"]).execute()

            analyzed += 1
            progress.count_analyzed()
            progress.count_risk(result["false_level"])
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                print("[analyzer] Gemini 크레딧/쿼터 소진 — 배치 중단. "
                      "충전 후 재실행하면 미분류분부터 이어서 처리됩니다.")
                break
            print(f"[analyzer] 기사 {article['id']} 분류 실패: {type(e).__name__}: {e}")
            if len(_failed_ids) < _FAILED_IDS_MAX:
                _failed_ids.add(article["id"])
            continue

    if prefiltered:
        print(f"[analyzer] 사전필터로 {prefiltered}건 자동분류 (Gemini 호출 생략)")
    if analyzed < len(articles):
        print(f"[analyzer] {len(articles)}건 중 {len(articles) - analyzed}건 실패")
    return analyzed


def _find_depts(names, departments) -> list:
    """AI가 관련도 순으로 준 부서명들을 ID로 매핑 (최대 2개, 중복 제거)."""
    ids = []
    for name in (names or []):
        for d in departments:
            if d["name"] == name or name in d["name"]:
                if d["id"] not in ids:
                    ids.append(d["id"])
                break
        if len(ids) == 2:
            break
    return ids


def _analyze(title: str, text: str, source_type: str, departments: list,
             max_chars: int = 800) -> dict:
    """한 건을 Gemini로 판정.

    `max_chars`는 프롬프트에 실을 본문 길이 상한이다. 기본 800은 수집분이 검색 API 요약
    (약 120자)이라 넉넉했던 값이고, 2단계 검증(services/verify.py)은 조회한 본문 전문을
    넣어야 하므로 더 큰 값을 준다.
    """
    source_label = {"언론": "언론 기사", "SNS": "SNS 게시물",
                    "커뮤니티": "커뮤니티 게시물", "유튜브": "유튜브 댓글",
                    "지식인": "지식인 질문글"}.get(source_type, "텍스트")
    dept_list = "\n".join(f"- {d['name']}" for d in departments)

    system = f"{SYSTEM_PROMPT}\n\n[부서 목록]\n{dept_list}"
    prompt = f"출처: {source_label}\n제목: {title[:150]}\n내용: {text[:max_chars]}"

    # Gemini 호출 — 실패 시 최대 3회 재시도
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))  # 5초, 10초 대기 후 재시도
            else:
                raise e

    return _parse_response(response.text)


def _parse_response(raw: str) -> dict:
    """Gemini 응답 JSON을 검증·보정해 저장용 dict로 변환 (두 축 공통 파서 사용)."""
    raw = raw.strip()
    if raw.startswith("```"):  # JSON 모드 실패 대비 안전망
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return parse_unified(json.loads(raw.strip()))
