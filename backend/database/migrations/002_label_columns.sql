-- 병무청 공식 분류체계 컬럼 추가 (Phase 1: 분류 체계 교체)
-- Supabase 대시보드 > SQL Editor에서 실행

ALTER TABLE crawled_articles
    ADD COLUMN IF NOT EXISTS label_l2 TEXT
        CHECK (label_l2 IN ('방법문의','방법안내','브로커의심','신뢰저하','의도의심','단순문의','단순내용'));

ALTER TABLE crawled_articles
    ADD COLUMN IF NOT EXISTS subject TEXT;

CREATE INDEX IF NOT EXISTS idx_crawled_label_l2 ON crawled_articles(label_l2);
