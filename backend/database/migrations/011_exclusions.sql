-- 검수 제외 규칙: 특정 URL 또는 동일 내용은 AI 호출 없이 비대상·무관 처리
-- Supabase 대시보드 > SQL Editor에서 실행
--
-- 원문은 삭제하지 않는다. 감사·재현을 위해 저장하되 분류 비용과 반복 검수를 줄인다.
-- URL과 본문 원문 대신 SHA-256 해시를 match_value에 저장한다.

CREATE TABLE IF NOT EXISTS exclusion_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_type       TEXT NOT NULL CHECK (rule_type IN ('url','content_hash')),
    match_value     TEXT NOT NULL,
    display_value   TEXT NOT NULL,
    reason          TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    operator_name   TEXT,
    os_account      TEXT,
    host_name       TEXT,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deactivated_at  TIMESTAMP WITH TIME ZONE,
    UNIQUE (rule_type, match_value)
);

CREATE TABLE IF NOT EXISTS exclusion_matches (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id       UUID NOT NULL REFERENCES exclusion_rules(id),
    target_table  TEXT NOT NULL CHECK (target_table IN ('crawled_articles','articles')),
    target_id     UUID NOT NULL,
    matched_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (rule_id, target_table, target_id)
);

CREATE INDEX IF NOT EXISTS idx_exclusion_rules_active
    ON exclusion_rules(rule_type, match_value) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_exclusion_matches_rule
    ON exclusion_matches(rule_id, matched_at DESC);

-- ※ operator_name·os_account·host_name은 인증이 아니라 작업 이력이다.
