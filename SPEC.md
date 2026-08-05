# SafeWatch Monitor — 프로젝트 스펙

> 병무청 관련 언론·SNS·커뮤니티·유튜브 콘텐츠를 수집하고, AI로 허위성·의도·부서를
> 분류하여 운영 대시보드·이메일 알림·엑셀 산출물로 제공하는 모니터링 시스템.

*최종 갱신: 2026-08-05*

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | SafeWatch Monitor |
| GitHub | kjy-arch/safewatch-monitor |
| 로컬 경로 | C:\Users\somes\projects\safewatch-monitor |
| 운영 환경 | 외부망 전용 |
| DB | Supabase (kjy-arch/safewatch-classifier와 동일 프로젝트) |
| 실행 | 바탕화면 아이콘 → `backend/run_monitor.bat` → http://localhost:8001 |

### 설치 절차 (PC마다 최초 1회)

`backend/setup.bat` 실행 — 가상환경 → 의존성 → **키워드 점수 사전** 순으로 진행한다.

1. `python -m venv .venv`
2. `pip install -r requirements.txt`
3. **`build_keyword_scores.py`** — 사전 필터용 점수 사전 생성
4. **`npm install && npm run build`** (frontend) — React 화면 빌드
5. `backend/.env`에 Supabase·Gemini 키 입력
6. Supabase SQL Editor에서 `backend/database/migrations/*.sql` 실행

> **4번(화면 빌드)을 건너뛰면 구형 단일 HTML로 자동 폴백한다.** 수집은 되지만
> 보고서·실행 이력·관리자 화면이 없다. `frontend/dist`는 `.gitignore` 대상이라
> git으로 받은 PC에는 없으므로, **Node.js LTS가 설치돼 있어야 전체 화면을 쓸 수 있다.**
> (Node 설치가 불가한 PC가 있으면 `dist`를 저장소에 커밋하는 방식으로 바꿔야 한다.)

> ⚠️ **3번을 건너뛰면 사전 필터가 조용히 꺼진 채로 동작한다.**
> `app/data/keyword_scores.json`은 병무청 학습자료 파생물이라 `.gitignore` 대상이므로
> git으로 받은 PC에는 존재하지 않는다. 없으면 **모든 글이 Gemini로 가서 API 비용이 급증**한다.
> 원본 `키워드.xlsx`는 PC마다 위치가 다르므로 아래 중 하나로 지정한다:
> ```
> build_keyword_scores.py --xlsx "경로\키워드.xlsx"
> set KEYWORD_XLSX=경로\키워드.xlsx
> ```
> **확인 방법**: `GET /api/health` → `prefilter.enabled`가 `true`인지 본다.
> `false`면 같은 응답의 `prefilter.warning`에 조치 방법이 들어 있다.

### 학습자료 갱신
`키워드.xlsx`가 새로 나오면 그 파일로 `build_keyword_scores.py`를 다시 돌리면 된다
(같은 원본이면 결과도 동일 — 재현 가능). 단 사전이 바뀌면 임계치 근거가 달라지므로
`validate_prefilter.py`로 재검증할 것. 은어 고정 가중치(`HIGH_SIGNAL`)는 스크립트 안에
하드코딩되어 있어 **신규 은어 추가는 코드 수정이 필요하다.**

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | Python 3.11 / FastAPI + uvicorn |
| 크롤러 | httpx + BeautifulSoup4 / 네이버 검색 API / YouTube Data API v3 / Meta Graph API / X API v2 / TikTok Research API |
| 스케줄러 | APScheduler (평일 08:00, `AUTO_CRAWL`로 on/off) |
| AI 분류 | Google Gemini 2.5 Flash + 키워드 사전필터(`keyword_scorer.py`) |
| 진행 상태 | 수집 진행률은 인메모리(`core/progress.py`) · 엑셀 분석 상태·실행 이력은 DB |
| 엑셀 | openpyxl — 이메일 첨부·서버 저장·다운로드 공통 서식 |
| 알림 | SMTP 이메일 (엑셀 첨부) |
| 프론트엔드 | **React 19 + Vite + Tailwind**(`frontend/`). FastAPI가 `frontend/dist`를 `/`에 서빙하며, 빌드가 없으면 구형 `app/dashboard.html`로 폴백 |
| DB | Supabase (PostgreSQL) |

---

## 3. 수집 채널

`crawl_sources` 테이블로 관리하며, 대시보드에서 이번 실행에 포함할 소스를 선택한다.

| 채널 | source_type | 방법 | 위험 분류 | 자격증명 |
|------|-------------|------|-----------|----------|
| 네이버 뉴스 | naver_news | 네이버 검색 API | 안전 | NAVER_CLIENT_ID/SECRET |
| 네이버 블로그 | naver_blog | 네이버 검색 API | 안전 | 동일 |
| 네이버 카페 | naver_cafe | 네이버 검색 API | 안전 | 동일 |
| 네이버 지식인 | naver_kin | 네이버 검색 API | 안전 | 동일 |
| 유튜브(영상+댓글) | youtube | YouTube Data API v3 | 안전 | YOUTUBE_API_KEY |
| 디시인사이드 | dcinside | BeautifulSoup 스크래핑 | 회색 | 불필요 |
| 에펨코리아 | fmkorea | BeautifulSoup 스크래핑 | 회색 | 불필요 |
| 인스타그램 | instagram | Graph API 해시태그 검색(recent_media) | 회색 | INSTAGRAM_ACCESS_TOKEN / _BUSINESS_ACCOUNT_ID |
| X | x | X API v2 recent search | 회색 | X_BEARER_TOKEN |
| 틱톡 | tiktok | TikTok Research API(video/query) | 회색 | TIKTOK_CLIENT_KEY / _CLIENT_SECRET |

### 위험 분류와 소스 선택 정책
`core/scheduler.py`의 `SAFE_TYPES` / `GRAY_TYPES`로 구분한다.

- **안전(공식 API)** — 기본 수집 대상. `source_ids` 미지정 시 안전 소스만 실행된다.
- **회색(스크래핑·비공식 접근)** — 대시보드에서 **명시적으로 선택해야만** 수집된다.
  선택 시 확인 팝업이 뜨고, 서버 로그에 `[감사] {시각} 회색지대 소스 포함 실행: …`으로 기록된다.
- 회색 소스 수집 방법의 법적 정당성은 **기관 법무·정보보안 검토 대기 중**(미결).

> 채널 근거: 「병무청 불법·허위·조작정보 처리절차 및 사례」('26.7.22)의 법정 대규모
> 정보통신 서비스제공자 9개(네이버·카카오·다음·네이트·디시인사이드·구글·메타·X·틱톡).
> 인스타·X·틱톡은 자격증명 미확보 상태로 `is_active=false`이며, 크롤러는 키가 없으면
> no-op(로그 후 0건 반환)한다(005 마이그레이션).

---

## 4. DB 테이블 구조

### crawl_sources (수집 소스 설정)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid PK | |
| name | text | 소스명 (예: 네이버 뉴스) |
| source_type | text | naver_news / naver_blog / naver_cafe / naver_kin / youtube / dcinside / fmkorea / instagram / x / tiktok |
| keywords | text[] | 검색 키워드 목록 |
| is_active | bool | 활성화 여부 (인스타·X·틱톡은 false) |
| interval_minutes | int | 수집 주기 (분) |
| created_at | timestamp | |

### crawled_articles (수집 원문 + 분류 결과)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid PK | |
| source_id | uuid FK | crawl_sources 참조 |
| source_type | text | 언론/SNS/커뮤니티/유튜브/지식인 (분류 프롬프트 라벨과 연동) |
| title | text | 제목 |
| content | text | 본문/댓글 |
| url | text UNIQUE | 원문 링크 (중복 저장 방지) |
| author | text | 작성자/채널명 |
| published_at | timestamp | 원문 게시일 |
| false_score | int | 조장 위험도 점수 0~100 (라벨별 구간). **null이면 미분류** |
| false_level | text | 낮음/중간/높음 |
| false_reason | text | 판단 이유 |
| label_l2 | text | 병무청 공식 내용구분 7종 (002 마이그레이션) |
| subject | text | 과목 15종 (002 마이그레이션) |
| category | text | 가이드라인 삭제기준 6종 (006) |
| action_type | text | 삭제대상 / 비대상 / 종합판단 (006) |
| intent_type | text | 의도 유형 5종 (006에서 실제 사용 시작) |
| content_type | text | 내용 유형 5종 (006에서 실제 사용 시작) |
| department_id | uuid FK | 소관 부서 (1순위) |
| department_id_2 | uuid FK | 소관 부서 2순위 — 복수 부서 매칭 (006) |
| response_status | text | 미확인/검토중/대응완료/무관 |
| response_memo | text | 대응 메모 |
| alert_sent | bool | 알림 발송 여부 |
| created_at | timestamp | 수집 시각 |

### batches / articles (엑셀 업로드 분석 — 분류자 계열)
`batches`(업로드 단위) + `articles`(행별 원문·분석결과). `status`(pending/done/failed)와
`error_reason`으로 실패분만 재분석할 수 있다. Phase 2에서 `label_l2`·`subject`가 추가돼
수집분과 같은 필드를 갖는다.

### reclassify_logs (재분류 이력 — 008)
담당자가 AI 판정을 바꾸면 **바뀐 필드마다 1행**을 남긴다.
`target_table`/`target_id` · `field` · `old_value` · `new_value` · `reason`(필수) ·
담당자·계정·PC명 · `created_at`.
재분류 가능 항목은 코드의 화이트리스트(`services/review.py` `EDITABLE`)로 제한되며,
목록 밖 컬럼·허용값 밖 값은 거부된다.

### run_logs (실행 이력 — 007)
`run_type`(crawl/analyze/batch) · `operator_name` · `os_account` · `host_name` ·
`status` · `collected` · `analyzed` · `started_at`/`finished_at` · `message`.

> ⚠️ 신원 값은 **인증이 아니라 기록**이다. 로그인이 없어 위조 가능하며 부인방지는
> 성립하지 않는다. 인수인계·업무 파악 용도로만 쓴다.

### alert_settings (알림 설정)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid PK | |
| email | text | 수신 이메일 |
| min_score | int | 알림 기준 점수 (기본 67) |
| is_active | bool | 활성화 여부 |
| created_at | timestamp | |

### 마이그레이션
`backend/database/migrations/` — Supabase SQL Editor에서 순서대로 실행.

| 파일 | 내용 |
|------|------|
| 001_initial_tables.sql | 초기 3개 테이블 + 기본 소스 |
| 002_label_columns.sql | label_l2 / subject 컬럼 |
| 003_expand_keywords.sql | 키워드 확장(학습자료 기반) |
| 004_new_sources.sql | 지식인 · 에펨코리아 추가 |
| 005_sns_sources.sql | 인스타 · X · 틱톡 추가 (is_active=false) |
| 006_unified_classification.sql | 분류 축 통합 — 수집분에 축 B 컬럼 + `department_id_2`, 업로드분에 축 A 컬럼 |
| 007_run_logs.sql | 실행 이력 테이블 |
| 008_review.sql | 검수·재분류 이력 + 업로드분 대응상태 |

---

## 5. API 엔드포인트

### 구현됨
| Method | Path | 설명 |
|--------|------|------|
| GET | / | **통합 화면**(React 빌드, 없으면 단일 HTML 폴백) |
| GET | /api/health | 상태 확인 + `prefilter.enabled` |
| **수집** | | |
| POST | /api/crawl/run | 수동 수집. body `{source_ids: []}` — 미지정 시 안전 소스만 |
| GET | /api/crawl/status | 진행 상태(단계·%·건수·출처별·엑셀 경로) |
| GET | /api/crawl/sources | 소스 목록 + 위험 분류(safe/gray) |
| GET | /api/crawl/backlog | 미분류 건수 |
| POST | /api/crawl/analyze | 미분류 백로그 분류. body `{limit}` |
| GET | /api/articles | 수집 기사 목록 (필터링) |
| PATCH | /api/articles/{id}/status | 대응 상태 변경 |
| GET | /api/articles/export | 결과 엑셀 (`scope=today\|all`) |
| GET | /api/stats | 통계 (누적) |
| **엑셀 분석** | | |
| POST | /api/batches/upload | 엑셀 업로드 → 행 저장 |
| POST | /api/batches/{id}/analyze | 분석 시작 (미완료·실패 행만 → 실패분 재분석 겸용) |
| GET | /api/batches | 배치 목록 |
| GET | /api/batches/{id} | 배치 + 행별 결과 |
| GET | /api/batches/{id}/stats | 배치 통계 |
| GET | /api/batches/{id}/download | 결과 엑셀 |
| **보고서** | | |
| GET | /api/reports/quarterly/summary | 분기 집계(JSON) — 수집분+업로드분 통합, 중복 제거 내역 포함 |
| GET | /api/reports/quarterly/download | 분기 보고서 엑셀 |
| **관리** | | |
| GET/POST/PUT/DELETE | /api/departments | 부서·키워드 CRUD |
| GET/PUT | /api/settings | 위험 임계값 |
| GET/POST/DELETE | /api/docs | RAG 공식문서 |
| **검수** | | |
| GET | /api/review/queue | 검수 대상 (수집분+업로드분, 위험도순) |
| GET | /api/review/fields | 재분류 가능 항목·허용값 |
| PATCH | /api/review/{table}/{id} | 재분류 + 이력 기록. body `{changes, reason}` |
| GET | /api/review/history | 전체 재분류 이력 |
| GET | /api/review/{table}/{id}/history | 항목별 재분류 이력 |
| **이력** | | |
| GET/PUT | /api/operator | 담당자 조회·설정 |
| GET | /api/runs | 최근 실행 이력 |
| GET | /api/runs/active | 실행 중 작업 |

### 미구현
`GET /api/articles/{id}` 상세 · `/api/sources` CRUD · `/api/alerts` CRUD

---

## 6. 화면 (React 통합, `/`)

Phase 5에서 모니터 대시보드와 분류자 React를 하나로 합쳤다. FastAPI가 `frontend/dist`를
서빙하며, 빌드가 없으면 구형 `backend/app/dashboard.html`로 폴백한다.

| 탭 | 내용 | 충족 요구 |
|----|------|----------|
| **수집** | 소스 선택(안전 자동/회색 opt-in), 수동 수집, 진행률, 출처별 실적, 미분류 분류 | — |
| **분석하기** | 엑셀 업로드 → 분석 시작 (결과는 DB 저장) | R2 |
| **결과 목록** | 지난 배치 열람 — 다른 담당자가 올린 것도 보임 | Q2 |
| **보고서** | 분기 집계 미리보기 + 엑셀 다운로드 (수집분+업로드분 통합) | Q5·R10·R5 |
| **검수/선정** | AI 판정 재분류(사유 필수) + 이력, 대응상태로 삭제 요청 대상 선정 | **Q3**·Q1 |
| **실행 이력** | 누가·언제·몇 건 (담당자·계정·PC명) | Q1 |
| **관리자** | 부서·키워드 CRUD, 위험 임계값, 공식문서 | R1·R6·Q8 |

헤더에 담당자 표시·등록. 미등록이면 경고 표시.

## 7. 환경 변수 (`backend/.env`)

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| SUPABASE_URL / SUPABASE_SECRET_KEY | ✅ | — | DB 접속 |
| GEMINI_API_KEY | ✅ | — | AI 분류 (선불 크레딧 소진 시 분류 중단) |
| NAVER_CLIENT_ID / NAVER_CLIENT_SECRET | ✅ | — | 네이버 검색 API |
| YOUTUBE_API_KEY | ✅ | — | YouTube Data API v3 |
| INSTAGRAM_ACCESS_TOKEN / _BUSINESS_ACCOUNT_ID | | "" | 없으면 인스타 크롤러 no-op |
| X_BEARER_TOKEN | | "" | 없으면 X 크롤러 no-op |
| TIKTOK_CLIENT_KEY / _CLIENT_SECRET | | "" | 없으면 틱톡 크롤러 no-op |
| SMTP_HOST / PORT / USER / PASSWORD | | ""/587 | 미설정 시 알림 미발송(로그만) |
| **AUTO_CRAWL** | | **false** | 평일 08:00 자동 수집. **테스트 단계에는 false(수동 실행만)** |
| **EXPORT_DIR** | | "" | 결과 엑셀 저장 폴더. 미설정 시 `~/Downloads` |
| APP_ENV / APP_PORT | | development/8001 | |
| CORS_ORIGINS | | * | 운영 배포 시 대시보드 도메인으로 제한 |

---

## 8. 폴더 구조

```
safewatch-monitor/
├── SPEC.md
├── backend/
│   ├── .env                      # 환경 변수 (git 미추적)
│   ├── requirements.txt
│   ├── run_monitor.bat           # 실행 런처 (바탕화면 아이콘 대상)
│   ├── app/
│   │   ├── main.py               # FastAPI 앱 (stdout UTF-8 고정)
│   │   ├── dashboard.html        # 운영 대시보드 (단일 HTML)
│   │   ├── api/
│   │   │   ├── crawl.py          # 수집·분류·엑셀 API
│   │   │   ├── dashboard.py      # `/` 대시보드 서빙
│   │   │   └── health.py
│   │   ├── core/
│   │   │   ├── config.py         # 설정(pydantic-settings)
│   │   │   ├── database.py       # Supabase 클라이언트
│   │   │   ├── progress.py       # 실행 진행 상태(인메모리)
│   │   │   └── scheduler.py      # 실행 오케스트레이션 + 소스 위험 분류
│   │   ├── crawlers/             # naver / youtube / dcinside / fmkorea
│   │   │   ├── instagram.py · x.py · tiktok.py
│   │   │   └── storage.py        # 중복 제거 + 일괄 저장
│   │   ├── data/keyword_scores.json   # 사전필터 점수 사전
│   │   ├── models/               # (빈 폴더)
│   │   └── services/
│   │       ├── analyzer.py           # Gemini 분류
│   │       ├── classifier_prompt.py  # 병무청 7라벨 프롬프트
│   │       ├── keyword_scorer.py     # 키워드 사전필터
│   │       ├── excel_classifier.py   # 업로드 엑셀 분류
│   │       ├── exporter.py           # 엑셀 조회·생성·파일 저장
│   │       └── notifier.py           # 이메일 알림 + 엑셀 서식
│   ├── tests/                    # 파싱·저장·분류 단위 테스트 (네트워크·DB 불필요)
│   └── database/migrations/      # 001~005 SQL
├── frontend/                     # (빈 골격 — React 미착수)
└── docs/                         # (빈 폴더)
```

---

## 9. 개발 단계

| 단계 | 내용 | 상태 |
|------|------|------|
| 1 | 프로젝트 구조 + SPEC.md | ✅ 완료 |
| 2 | DB 테이블 생성 (Supabase) | ✅ 완료 (001~005 적용) |
| 3 | FastAPI 기본 세팅 + 환경설정 | ✅ 완료 |
| 4 | 네이버 크롤러 (뉴스/블로그/카페/지식인) | ✅ 완료 |
| 5 | 유튜브 크롤러 | ✅ 완료 |
| 6 | 디시인사이드 · 에펨코리아 크롤러 | ✅ 완료 |
| 7 | AI 분류 연동 (Gemini) | ✅ 완료 — 병무청 공식 7라벨 |
| 8 | APScheduler 자동 스케줄링 | ✅ 완료 — **`AUTO_CRAWL=false`로 비활성(테스트 단계)** |
| 9 | 이메일 알림 | ✅ 완료 (min_score 필터, 엑셀 첨부) |
| 10 | 운영 대시보드 UI | ✅ 완료 — 단일 HTML. React 고도화는 미착수 |
| 11 | SNS 채널 확장 (인스타·X·틱톡) | ✅ 코드 완료 — 자격증명 확보 후 활성화 |
| 12 | 진행률·엑셀 산출·소스 선택·백로그 분류 | ✅ 완료 |
| 13 | 회색 소스 법무·정보보안 검토 | ⬜ 대기 (사용자 액션) |

---

## 10. 분류 체계

'2024년 학습자료(도입시)' 라벨링 데이터 기반 병무청 공식 분류.

- **조장정보**: 방법문의(65~85) / 방법안내(80~95) / 브로커의심(90~100) / 신뢰저하(50~70) / 의도의심(35~55)
- **단순병역정보**: 단순문의 / 단순내용 (0~33)
- 척도: 0~33 낮음 / 34~66 중간 / 67~100 높음

### 키워드 사전필터 (비용 절감)
`keyword_scorer.py`가 Gemini 호출 전에 병역 관련 키워드 점수를 매겨, 임계치 미만이면
호출 없이 '단순내용'으로 자동 분류한다.

**출처와 무관하게 임계치는 하나(`PREFILTER_THRESHOLD = 2`)만 쓴다** — 요구 Q7
("언론·SNS·커뮤니티·유튜브 등 출처별로 판단 기준이나 판단 방식은 동일하게 적용").

| 검증 | 스크립트 | 결과 (2026-08-05) |
|------|---------|------|
| 임계치 산정 | `validate_prefilter.py` | 사람 라벨 6,430건 — 권장 **2**, 조장 미스율 0.34% |
| 언론 구간 안전성 | `validate_news_prefilter.py` | 분류된 언론 218건 — 무손실 상한 4, 설정값 2는 **안전** |

언론 검증이 따로 있는 이유: 사람 라벨 자료에는 **출처 구분이 없어**, 언론 구간에서
위험 기사를 놓치지 않는지를 그 검증만으로는 알 수 없다. 다만 이쪽 정답은 사람 라벨이
아니라 Gemini 분류 결과이므로 참고 지표로만 본다.

> **이력**: 한때 언론에만 임계치 4를 적용했으나(호출 3.7% 절감), 임계치 2도 2.3%를
> 절감해 실익 차이가 1.4%p에 불과했다. 요구 Q7과의 상충을 감수할 이유가 없어
> 2026-08-05 제거하고 단일 임계치로 되돌렸다.

### 분류 대상 선정
`analyze_unclassified`는 **최신 저장분부터**(`created_at desc`) 처리한다. 수집 실행은
그 실행의 수집 건수만큼만 분류하므로, 과거 미분류 백로그는 대시보드
「미분류 분류」로 따로 소진한다.

### 검증
- 성능 검증: `backend/eval_classifier.py` (23~24년 라벨 데이터)
- 단위 테스트: `backend/tests/` — 크롤러 파싱, storage, 사전필터, 엑셀 파싱 (네트워크·DB 불필요)
