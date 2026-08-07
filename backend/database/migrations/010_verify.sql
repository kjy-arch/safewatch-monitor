-- 2단계 검증: 삭제대상 판정을 본문으로 재확인 (2026-08-07)
-- Supabase 대시보드 > SQL Editor에서 실행
--
-- 배경: 수집은 네이버 검색 API의 요약(description, 약 120자)만 저장한다.
--   2026-08-07 실측 — 지식인 본문 중앙값 128자, 삭제대상 38건은 전부 200자 미만이었다.
--   지식인 docId=494564616은 요약만 보면 "면제로 받고 싶다면 ~ 전화번호로 문의"라 브로커
--   광고와 형태가 같았지만, 답변 전문은 병무용 진단서 제도 안내였고 그 "전화번호"는
--   지방병무청 상담번호 14개 목록이었다. 요약 기반 판정의 구조적 한계다.
--
-- 방침: 삭제대상·종합판단으로 올라온 건만 본문을 조회해 다시 판정한다.
--   **원 분류 컬럼(action_type·category·false_score 등)은 건드리지 않는다.**
--   덮어쓰면 ⓐ "왜 바뀌었나"를 추적할 수 없고 ⓑ 8/5·8/7 누적분과 기준이 어긋나
--   분기 보고서 추세가 왜곡된다. 최종 판단은 담당자가 기존 검수 기능으로 한다.
--
-- ※ reclassify_logs에는 넣지 않는다 — 그건 **사람이 바꾼 기록**(요구 Q3)이고,
--   AI 2차 판정을 섞으면 감사 추적이 오염된다.

ALTER TABLE crawled_articles
    -- 조회한 본문 원문. 재현·감사용이며 화면에서 1차 요약과 나란히 보여준다.
    ADD COLUMN IF NOT EXISTS content_full  TEXT,
    -- 대상아님: 카페(로그인 벽)·유튜브(이미 전문) 등 조회할 이유가 없는 출처
    ADD COLUMN IF NOT EXISTS verify_status TEXT
        CHECK (verify_status IN ('확인완료','조회실패','대상아님')),
    -- 2차 판정 결과 (원 컬럼과 별개)
    ADD COLUMN IF NOT EXISTS verify_action TEXT
        CHECK (verify_action IN ('삭제대상','비대상','종합판단')),
    ADD COLUMN IF NOT EXISTS verify_reason TEXT,
    ADD COLUMN IF NOT EXISTS verified_at   TIMESTAMP WITH TIME ZONE;

-- 미검증 대상을 빠르게 찾기 위한 부분 인덱스
CREATE INDEX IF NOT EXISTS idx_crawled_verify_pending
    ON crawled_articles(action_type)
    WHERE verify_status IS NULL;

-- 1차와 2차가 갈린 건 = 검수 우선순위. 화면에서 이 조건으로 정렬한다.
CREATE INDEX IF NOT EXISTS idx_crawled_verify_mismatch
    ON crawled_articles(verified_at DESC)
    WHERE verify_status = '확인완료';

-- 실행 이력에 'verify' 추가 — 007의 CHECK가 crawl/analyze/batch만 허용해서
-- 그대로 두면 검증 실행이 이력에 남지 않는다(run_log.start가 조용히 None을 반환).
ALTER TABLE run_logs DROP CONSTRAINT IF EXISTS run_logs_run_type_check;
ALTER TABLE run_logs ADD CONSTRAINT run_logs_run_type_check
    CHECK (run_type IN ('crawl', 'analyze', 'batch', 'verify'));

-- ※ 본문 조회는 공식 검색 API가 아니라 렌더링된 페이지 조회다. 디시·에펨 스크래핑과
--   같은 범주이며 D1(회색지대 법무·정보보안 검토) 대상이다. 그래서 전건이 아니라
--   삭제대상·종합판단으로 범위를 좁혔다.
