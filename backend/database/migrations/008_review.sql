-- Phase 6: 검수·재분류 + 이력 (사이버조사과 요구 Q3)
--   "담당자가 직접 결과를 수정할 필요는 없고, 분석 결과를 검수하여 정보를 재분류하는
--    기능이 필요합니다. (재분류 이력 관리 포함)"
-- Supabase 대시보드 > SQL Editor에서 실행
--
-- 담당자가 AI 판정을 뒤집으면 무엇을·왜·누가·언제 바꿨는지 남긴다.
-- 이 기록이 없으면 삭제 요청의 근거를 사후에 추적할 수 없다.

-- 1) 업로드분에도 대응상태 — 수집분과 동일한 '삭제 요청 대상 선정' 워크플로를 쓰게 한다 (요구 Q1)
ALTER TABLE articles ADD COLUMN IF NOT EXISTS response_status TEXT NOT NULL DEFAULT '미확인'
    CHECK (response_status IN ('미확인','검토중','대응완료','무관'));
ALTER TABLE articles ADD COLUMN IF NOT EXISTS response_memo TEXT;

-- 2) 재분류 이력 — 바뀐 필드마다 1행 (무엇이 어떻게 바뀌었는지 그대로 읽히게)
CREATE TABLE IF NOT EXISTS reclassify_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_table  TEXT NOT NULL CHECK (target_table IN ('crawled_articles','articles')),
    target_id     UUID NOT NULL,
    field         TEXT NOT NULL,   -- action_type / category / false_level / response_status ...
    old_value     TEXT,            -- 변경 전 (AI 판정값)
    new_value     TEXT,            -- 변경 후 (담당자 판정값)
    reason        TEXT,            -- 재분류 사유
    operator_name TEXT,            -- 담당자가 입력한 이름
    os_account    TEXT,            -- Windows 계정 (자동)
    host_name     TEXT,            -- PC 이름 (자동)
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reclassify_target  ON reclassify_logs(target_table, target_id);
CREATE INDEX IF NOT EXISTS idx_reclassify_created ON reclassify_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_response  ON articles(response_status);

-- ※ run_logs와 마찬가지로 신원 값은 **인증이 아니라 기록**이다.
--   로그인이 없어 위조 가능하며 부인방지는 성립하지 않는다.
