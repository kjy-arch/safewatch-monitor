-- SafeWatch Monitor 초기 테이블 생성
-- Supabase 대시보드 > SQL Editor에서 실행

-- 1. 수집 소스 설정
CREATE TABLE IF NOT EXISTS crawl_sources (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    source_type      TEXT NOT NULL CHECK (source_type IN ('naver_news','naver_blog','naver_cafe','youtube','dcinside')),
    keywords         TEXT[] NOT NULL DEFAULT '{}',
    is_active        BOOLEAN NOT NULL DEFAULT true,
    interval_minutes INT NOT NULL DEFAULT 60,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. 수집 원문 + 분석 결과
CREATE TABLE IF NOT EXISTS crawled_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID REFERENCES crawl_sources(id) ON DELETE SET NULL,
    source_type     TEXT NOT NULL,
    title           TEXT,
    content         TEXT NOT NULL,
    url             TEXT UNIQUE,
    author          TEXT,
    published_at    TIMESTAMP WITH TIME ZONE,
    false_score     INT CHECK (false_score BETWEEN 0 AND 100),
    false_level     TEXT CHECK (false_level IN ('낮음','중간','높음')),
    false_reason    TEXT,
    intent_type     TEXT,
    content_type    TEXT,
    department_id   UUID REFERENCES departments(id) ON DELETE SET NULL,
    response_status TEXT NOT NULL DEFAULT '미확인' CHECK (response_status IN ('미확인','검토중','대응완료','무관')),
    response_memo   TEXT,
    alert_sent      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. 이메일 알림 수신자
CREATE TABLE IF NOT EXISTS alert_settings (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email      TEXT NOT NULL UNIQUE,
    min_score  INT NOT NULL DEFAULT 67,
    is_active  BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_crawled_source_type  ON crawled_articles(source_type);
CREATE INDEX IF NOT EXISTS idx_crawled_false_level  ON crawled_articles(false_level);
CREATE INDEX IF NOT EXISTS idx_crawled_created_at   ON crawled_articles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawled_response     ON crawled_articles(response_status);

-- 기본 수집 소스 데이터
INSERT INTO crawl_sources (name, source_type, keywords, interval_minutes) VALUES
    ('네이버 뉴스',   'naver_news',  ARRAY['병무청','병역비리','입영','사회복무'], 60),
    ('네이버 블로그', 'naver_blog',  ARRAY['병무청','병역','입영 후기'], 120),
    ('네이버 카페',   'naver_cafe',  ARRAY['병무청','병역판정','사회복무요원'], 120),
    ('유튜브',        'youtube',     ARRAY['병무청','병역비리','신체검사 비리'], 180),
    ('디시인사이드',  'dcinside',    ARRAY['병무청','병역'], 60)
ON CONFLICT DO NOTHING;
