-- Phase 5: 법정 대규모 정보통신 서비스제공자 SNS 채널 확장 — 인스타그램·X·틱톡
-- 근거: 「병무청 불법·허위·조작정보 처리절차 및 사례」('26.7.22)가 규정한 9개 사업자 중
--       조작정보·딥페이크 주무대인 메타(인스타)·X·틱톡이 누락되어 있었음.
-- Supabase 대시보드 > SQL Editor에서 실행
--
-- ※ 자격증명(각 API 토큰/키)이 아직 없어 신규 소스는 is_active=false로 삽입한다.
--   .env에 토큰을 넣은 뒤 아래로 활성화:
--     UPDATE crawl_sources SET is_active = true WHERE source_type IN ('instagram','x','tiktok');

-- source_type CHECK 제약에 신규 타입 추가
ALTER TABLE crawl_sources DROP CONSTRAINT IF EXISTS crawl_sources_source_type_check;
ALTER TABLE crawl_sources ADD CONSTRAINT crawl_sources_source_type_check
    CHECK (source_type IN ('naver_news','naver_blog','naver_cafe','naver_kin',
                           'youtube','dcinside','fmkorea',
                           'instagram','x','tiktok'));

-- 인스타그램: Graph API는 해시태그 검색만 지원 → 키워드는 공백 없는 해시태그형으로.
-- 고유 해시태그 30개/7일 한도 내(고정셋 반복은 1개로 카운트)에서 운영.
INSERT INTO crawl_sources (name, source_type, keywords, interval_minutes, is_active)
SELECT '인스타그램', 'instagram',
       ARRAY['병무청','병역면탈','병역기피','공익판정','사회복무요원','신검4급','군면제'], 120, false
WHERE NOT EXISTS (SELECT 1 FROM crawl_sources WHERE source_type = 'instagram');

-- X: recent search는 자유 텍스트 질의 가능 → 조합형 키워드 사용.
INSERT INTO crawl_sources (name, source_type, keywords, interval_minutes, is_active)
SELECT 'X', 'x',
       ARRAY['병무청','병역면탈','병역비리','군면제 방법','신검 4급','공익 판정'], 120, false
WHERE NOT EXISTS (SELECT 1 FROM crawl_sources WHERE source_type = 'x');

-- 틱톡: Research API 키워드 질의.
INSERT INTO crawl_sources (name, source_type, keywords, interval_minutes, is_active)
SELECT '틱톡', 'tiktok',
       ARRAY['병무청','병역면탈','군면제','공익 판정','신검 꿀팁'], 120, false
WHERE NOT EXISTS (SELECT 1 FROM crawl_sources WHERE source_type = 'tiktok');
