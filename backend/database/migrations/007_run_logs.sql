-- Phase 3: 실행 이력 — 누가·언제·무엇을 돌렸는지 기록.
-- 담당자가 번갈아 쓰는 운영(A가 없을 때 B가 이어받기)에서 인수인계·감사 근거가 된다.
-- Supabase 대시보드 > SQL Editor에서 실행
--
-- ※ 신원 값(operator_name/os_account/host_name)은 **기록이지 인증이 아니다.**
--   로그인이 없으므로 위조 가능하며, 부인방지(non-repudiation)는 성립하지 않는다.
--   실무 파악·인수인계 용도로만 쓸 것.

CREATE TABLE IF NOT EXISTS run_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type      TEXT NOT NULL CHECK (run_type IN ('crawl', 'analyze', 'batch')),
    operator_name TEXT,          -- 담당자가 최초 1회 입력한 이름
    os_account    TEXT,          -- Windows 계정명 (자동)
    host_name     TEXT,          -- PC 이름 (자동)
    status        TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
    started_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at   TIMESTAMP WITH TIME ZONE,
    collected     INT DEFAULT 0, -- 수집 건수
    analyzed      INT DEFAULT 0, -- 분류 건수
    message       TEXT,          -- 요약 또는 실패 사유
    batch_id      UUID REFERENCES batches(id) ON DELETE SET NULL  -- 엑셀 분류일 때
);

-- 최근 이력 조회 + 실행 중 감지(동시 실행 방지)용
CREATE INDEX IF NOT EXISTS idx_run_logs_started ON run_logs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_logs_status  ON run_logs(status);
