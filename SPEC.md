# SafeWatch Monitor — 프로젝트 스펙

> 병무청 관련 언론·SNS·커뮤니티·유튜브 콘텐츠를 자동으로 수집하고,
> AI로 허위성·의도·부서를 분류하여 실시간 알림과 대시보드를 제공하는 자동 모니터링 시스템.

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | SafeWatch Monitor |
| GitHub | kjy-arch/safewatch-monitor |
| 로컬 경로 | C:\Users\somes\projects\safewatch-monitor |
| 운영 환경 | 외부망 전용 |
| DB | Supabase (kjy-arch/safewatch-classifier와 동일 프로젝트) |

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | Python 3.11 / FastAPI |
| 크롤러 | httpx + BeautifulSoup4 / YouTube Data API v3 / 네이버 검색 API |
| 스케줄러 | APScheduler |
| AI 분류 | Google Gemini 2.5 Flash API |
| 알림 | SMTP 이메일 |
| 프론트엔드 | React (Vite + Tailwind CSS) |
| DB | Supabase (PostgreSQL) |

---

## 3. 수집 채널

| 채널 | 방법 | API 키 |
|------|------|--------|
| 네이버 뉴스 | 네이버 검색 API | NAVER_CLIENT_ID/SECRET |
| 네이버 블로그 | 네이버 검색 API | 동일 |
| 네이버 카페 | 네이버 검색 API | 동일 |
| 유튜브 댓글 | YouTube Data API v3 | YOUTUBE_API_KEY |
| 디시인사이드 | BeautifulSoup 스크래핑 | 불필요 |

---

## 4. DB 테이블 구조

### crawl_sources (수집 소스 설정)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid PK | |
| name | text | 소스명 (예: 네이버뉴스) |
| source_type | text | naver_news / naver_blog / naver_cafe / youtube / dcinside |
| keywords | text[] | 검색 키워드 목록 |
| is_active | bool | 활성화 여부 |
| interval_minutes | int | 수집 주기 (분) |
| created_at | timestamp | |

### crawled_articles (수집 원문)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid PK | |
| source_id | uuid FK | crawl_sources 참조 |
| source_type | text | 출처 유형 |
| title | text | 제목 |
| content | text | 본문/댓글 |
| url | text | 원문 링크 |
| author | text | 작성자/채널명 |
| published_at | timestamp | 원문 게시일 |
| false_score | int | 조장 위험도 점수 0~100 (라벨별 구간) |
| false_level | text | 낮음/중간/높음 |
| false_reason | text | 판단 이유 |
| label_l2 | text | 병무청 공식 내용구분: 방법문의/방법안내/브로커의심/신뢰저하/의도의심/단순문의/단순내용 (002 마이그레이션) |
| subject | text | 과목: 병무관련/정신과/신장체중 등 15종 (002 마이그레이션) |
| intent_type | text | (구버전) 의도 유형 — label_l2로 대체됨 |
| content_type | text | (구버전) 내용 유형 — label_l2로 대체됨 |
| department_id | uuid FK | 소관 부서 |
| response_status | text | 미확인/검토중/대응완료/무관 |
| response_memo | text | 대응 메모 |
| alert_sent | bool | 알림 발송 여부 |
| created_at | timestamp | |

### alert_settings (알림 설정)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid PK | |
| email | text | 수신 이메일 |
| min_score | int | 알림 기준 점수 (기본 67) |
| is_active | bool | 활성화 여부 |
| created_at | timestamp | |

---

## 5. API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/articles | 수집 기사 목록 (필터링) |
| GET | /api/articles/{id} | 기사 상세 |
| PATCH | /api/articles/{id}/status | 대응 상태 변경 |
| GET | /api/sources | 수집 소스 목록 |
| POST | /api/sources | 소스 추가 |
| PUT | /api/sources/{id} | 소스 수정 |
| DELETE | /api/sources/{id} | 소스 삭제 |
| POST | /api/crawl/run | 수동 크롤링 실행 |
| GET | /api/stats | 통계 (대시보드용) |
| GET | /api/alerts | 알림 수신자 목록 |
| POST | /api/alerts | 알림 수신자 추가 |
| DELETE | /api/alerts/{id} | 알림 수신자 삭제 |

---

## 6. 폴더 구조

```
safewatch-monitor/
├── SPEC.md
├── backend/
│   ├── .env
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── api/           # FastAPI 라우터
│       ├── core/          # 설정, DB, 스케줄러
│       ├── crawlers/      # 채널별 크롤러
│       │   ├── naver.py
│       │   ├── youtube.py
│       │   └── dcinside.py
│       ├── models/        # Pydantic 모델
│       └── services/      # AI 분류, 알림
│           ├── analyzer.py
│           └── notifier.py
├── frontend/              # React 대시보드
│   └── src/
└── database/
    └── migrations/
```

---

## 7. 개발 단계

| 단계 | 내용 | 상태 |
|------|------|------|
| 1 | 프로젝트 구조 + SPEC.md | ✅ 완료 |
| 2 | DB 테이블 생성 (Supabase) | ✅ 완료 (001, 002는 실행 필요) |
| 3 | FastAPI 기본 세팅 + 환경설정 | ✅ 완료 |
| 4 | 네이버 크롤러 (뉴스/블로그/카페) | ✅ 완료 |
| 5 | 유튜브 크롤러 | ✅ 완료 |
| 6 | 디시인사이드 크롤러 | ✅ 완료 |
| 7 | AI 분류 연동 (Gemini) | ✅ 완료 — 병무청 공식 7라벨 체계 (classifier_prompt.py) |
| 8 | APScheduler 자동 스케줄링 | ✅ 완료 (평일 08:00, 공휴일 제외) |
| 9 | 이메일 알림 | ✅ 완료 (min_score 필터, 엑셀 첨부) |
| 10 | React 대시보드 UI | ⬜ 대기 |

### 미구현 API (SPEC 5장 대비)
`/api/articles/{id}` 상세, `/api/sources` CRUD, `/api/alerts` CRUD — 대시보드(10단계) 착수 시 함께 구현 예정.

### 분류 체계 (2026-07 교체)
'2024년 학습자료(도입시)' 라벨링 데이터 기반 병무청 공식 분류를 사용:
- **조장정보**: 방법문의(65~85점) / 방법안내(80~95) / 브로커의심(90~100) / 신뢰저하(50~70) / 의도의심(35~55)
- **단순병역정보**: 단순문의 / 단순내용 (0~33)
- 성능 검증: `backend/eval_classifier.py` (23~24년 라벨 데이터), 단위 테스트: `backend/tests/`
