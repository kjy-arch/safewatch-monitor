-- Phase 4: 수집 채널 확장 — 네이버 지식인 + 에펨코리아
-- 근거: 학습자료 색출 실적에서 지식인·에펨코리아가 주요 출처로 확인됨
-- Supabase 대시보드 > SQL Editor에서 실행

-- source_type CHECK 제약에 신규 타입 추가
ALTER TABLE crawl_sources DROP CONSTRAINT IF EXISTS crawl_sources_source_type_check;
ALTER TABLE crawl_sources ADD CONSTRAINT crawl_sources_source_type_check
    CHECK (source_type IN ('naver_news','naver_blog','naver_cafe','naver_kin',
                           'youtube','dcinside','fmkorea'));

-- 신규 소스 (이미 존재하면 중복 삽입 방지)
INSERT INTO crawl_sources (name, source_type, keywords, interval_minutes)
SELECT '네이버 지식인', 'naver_kin',
       ARRAY['병무청','군면제 방법','신검 4급','공익 판정','저체중 공익',
             '정신과 4급','병역판정검사','군대 안가는법','입영연기'], 120
WHERE NOT EXISTS (SELECT 1 FROM crawl_sources WHERE source_type = 'naver_kin');

-- 에펨 검색은 본문 부분일치라 '정공'·'멸공' 단독은 무관 글(정공법 등)을 끌어옴 → 조합형만 사용
INSERT INTO crawl_sources (name, source_type, keywords, interval_minutes)
SELECT '에펨코리아', 'fmkorea',
       ARRAY['병무청','공익 가는법','신검 4급','군면제','정신과 공익','저체중 공익','병역판정'], 60
WHERE NOT EXISTS (SELECT 1 FROM crawl_sources WHERE source_type = 'fmkorea');
