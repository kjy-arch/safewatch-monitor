-- Phase 2: 분류 축 통합 — 수집분(crawled_articles)과 업로드분(articles)이
-- 같은 분석 필드를 갖게 한다. 통합 분기 보고서에서 두 경로를 함께 집계하기 위함.
-- Supabase 대시보드 > SQL Editor에서 실행
--
-- ※ 기존 데이터는 새 컬럼이 NULL로 남는다. 전량 재분석하면 Gemini 비용이 그만큼
--   다시 발생하므로, 필요할 때 대시보드 「미분류 분류」로 채운다.

-- 1) 수집분에 축 B(불건전정보 가이드라인) 필드 추가
ALTER TABLE crawled_articles ADD COLUMN IF NOT EXISTS category      TEXT;  -- 가이드라인 삭제기준
ALTER TABLE crawled_articles ADD COLUMN IF NOT EXISTS action_type   TEXT;  -- 삭제대상 / 비대상 / 종합판단
-- intent_type, content_type은 001에서 이미 생성됨 (그동안 채워지지 않았을 뿐)
ALTER TABLE crawled_articles ADD COLUMN IF NOT EXISTS intent_type   TEXT;
ALTER TABLE crawled_articles ADD COLUMN IF NOT EXISTS content_type  TEXT;
-- 복수 부서 매칭 (사이버조사과 요구 Q4) — 2순위 부서
ALTER TABLE crawled_articles ADD COLUMN IF NOT EXISTS department_id_2 UUID REFERENCES departments(id) ON DELETE SET NULL;

-- 2) 업로드분에 축 A(병무청 공식 분류체계) 필드 추가
ALTER TABLE articles ADD COLUMN IF NOT EXISTS label_l2 TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS subject  TEXT;

-- 3) 조회 인덱스 — 삭제대상 선별(Q1)과 분기 보고서 집계에서 쓰인다
CREATE INDEX IF NOT EXISTS idx_crawled_action_type ON crawled_articles(action_type);
CREATE INDEX IF NOT EXISTS idx_crawled_category    ON crawled_articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_label_l2   ON articles(label_l2);
