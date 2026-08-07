# SafeWatch

병무청 관련 온라인 콘텐츠를 수집해 **불법·허위·조작정보를 자동 분류**하고,
담당자가 검수·선정한 뒤 **삭제 요청 대상과 분기 통계**를 산출하는 시스템.

수집형(모니터)과 엑셀 분석형(분류자)을 하나로 합친 **통합본**이다.

## 빠른 시작

```
backend\setup.bat          최초 1회 (PC마다)
backend\run_monitor.bat    실행 → http://localhost:8001
```

`setup.bat`이 가상환경 → 의존성 → **키워드 사전** → **화면 빌드** 순으로 진행한다.
이후 `backend\.env`에 키를 넣고, Supabase SQL Editor에서
`backend/database/migrations/*.sql`을 순서대로 실행한다.

> ⚠️ **설치 후 반드시 확인**: `http://localhost:8001/api/health` → `prefilter.enabled`
> `false`면 키워드 사전이 없어 **모든 글이 Gemini로 가서 API 비용이 급증**한다.
> 같은 응답의 `prefilter.warning`에 조치 방법이 들어 있다.

## 화면

| 탭 | 하는 일 |
|----|---------|
| 수집 | 소스 선택(안전 자동 / 회색 opt-in) · 수동 수집 · 진행률 · 미분류 분류 |
| 분석하기 | 임의 엑셀 업로드 → 분석 |
| 결과 목록 | 지난 배치 열람 (다른 담당자가 올린 것도 보임) |
| 검수/선정 | AI 판정 재분류(사유 필수·이력 기록) · 삭제 요청 대상 선정 |
| 보고서 | 분기 집계 미리보기 + 엑셀 (수집분+업로드분 통합) |
| 실행 이력 | 누가·언제·몇 건 |
| 관리자 | 부서·키워드 · 위험 임계값 · 공식문서 |

## 분류 체계

한 번의 Gemini 호출로 두 축을 동시에 판정한다.

- **축 A — 병무청 공식 분류체계**: `label_l2`(7종) · `subject`(과목 15종)
- **축 B — 불건전정보 가이드라인**: `category`(삭제기준) · `action_type`(삭제대상/비대상/종합판단) · `intent_type` · `content_type`

수집분(`crawled_articles`)과 업로드분(`articles`)이 **같은 필드**를 갖기 때문에
분기 보고서에서 함께 집계된다(같은 글이 양쪽에 있으면 중복 제거).

## 알아둘 것

- **인증이 없다.** 담당자 이름·Windows 계정·PC명을 이력에 남기지만 이는 **기록이지 인증이 아니다**
  (위조 가능, 부인방지 불가). 기본 실행은 `127.0.0.1:8001`로 제한되어 같은 PC에서만
  접속할 수 있다. LAN·다중 PC·서버 배포로 바꾸려면 먼저 인증을 추가해야 한다.
- **회색지대 소스**(디시·에펨 등)의 실행 경고는 법적 허용이나 서버 권한 통제를 대신하지 않는다.
  초기 마이그레이션과 실제 운영 DB의 활성값이 다를 수 있으므로, 기관 검토 전에는 운영값을
  별도로 확인해야 한다.
- **분류 결과는 참고 자료**다. 삭제 요청 여부는 담당자가 검수해 결정하고,
  뒤집은 판정은 사유와 함께 이력에 남는다.
- Gemini 전송 직전 전화번호·이메일·주민등록번호 형태·계좌번호를 마스킹한다.
  DB 원문은 바꾸지 않으며, 작성자·닉네임과 민감 내용의 별도 처리 여부는 결정 대기 중이다.

## 문서

| 문서 | 내용 |
|------|------|
| [SPEC.md](SPEC.md) | 전체 스펙 — 수집 채널 · DB · API · 화면 · 환경변수 · 분류 체계 |
| [docs/요구사항_대조.md](docs/요구사항_대조.md) | 사이버조사과 요구 20건 ↔ 구현 대조 + 통합 중 잡은 결함 |
| [docs/다음_할일.md](docs/다음_할일.md) | **남은 작업** — 사용자 액션 · 결정 필요 · 개발 항목 |
| [docs/운영_보안_감사.md](docs/운영_보안_감사.md) | 2026-08-07 기준 데이터 흐름·보안·개인정보·수집원 정책 감사 |

## 개발

```
백엔드   cd backend  && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
프론트   cd frontend && npm run dev        (5173, /api는 8001로 프록시)
```

테스트는 네트워크·DB 없이 돈다.

```
cd backend
for %f in (tests\test_*.py) do .venv\Scripts\python.exe %f
```

분류 정확도 회귀 검증(실제 Gemini 호출 — 비용 발생):

```
.venv\Scripts\python.exe eval_classifier.py --per-label 5        축 A (7분류)
.venv\Scripts\python.exe eval\eval_batch.py --golden eval\golden_set.csv   축 B
.venv\Scripts\python.exe validate_prefilter.py                   사전필터 임계치
```
