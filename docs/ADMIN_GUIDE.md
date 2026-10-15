# ADMIN_GUIDE — 운영 절차

문서 버전 1.0 · 2026-10-15 · 대상: 설치·운영 담당자 (단일 PC, Windows)

이 시스템은 로그인·권한 체계가 없는 **단일 사용자용 로컬 애플리케이션**이다. 승인자 이름은 `PWA_APPROVER_NAME`(또는 화면 입력)으로 기록될 뿐 인증되지 않는다. 다중 사용자·네트워크 공개 운영은 검증되지 않았다 ([LIMITATIONS.md](LIMITATIONS.md)).

---

## 1. 일상 운영

| 작업 | 명령·위치 |
|---|---|
| 기동 | `.venv\Scripts\Activate.ps1` → `streamlit run src\proposal_agent\app.py` |
| 종료 | 터미널 `Ctrl+C` (진행 중인 에이전트 단계는 실패로 기록되고 재실행 가능) |
| 로그 확인 | `workspace\logs\app.log` (5MB×3 회전), 콘솔 |
| 상태 확인 | 프로젝트 화면의 단계 진행 표·미해결 이슈, DB `step_runs`·`gate_evaluations`·`audit_events` |
| 연결 점검(비용 0) | `python scripts\check_mcp.py` 또는 에이전트 화면의 **연결 점검** |

## 2. 설정 변경

- 설정은 `.env`(개발) 또는 OS 환경변수(운영)로 바꾸고 앱을 재시작한다. 전체 목록은 [INSTALLATION.md 3절](INSTALLATION.md).
- 비용 통제(2026-10-15 추가): 추출·검증은 실행 전에 **실행 계획**(청크 수, 건너뛸 청크, 캐시 재사용, 호출 수, 최대 비용)을 코드가 산정해 요구사항 화면에 표시하고, `PWA_MAX_AGENT_CALLS_PER_STEP`(호출 수)·`PWA_MAX_BUDGET_USD_PER_PROJECT`(프로젝트 누적 비용)를 넘으면 호출 전에 중단한다. 실행 중에도 매 호출 전에 누적 비용을 재검사하며, 처리한 청크 결과는 보존된다. 같은 청크 입력은 캐시(`workspace\<project>\cache`)에서 재사용되어 재실행 비용이 0이고, 요구사항 표현이 없는 청크는 호출하지 않는다.
- 비용 통제: `PWA_MAX_BUDGET_USD_PER_STEP`(단계당, 역할 상한은 3배까지), 역할별 `max_turns`·`max_budget_usd`·`timeout_s`·`retries`는 `src/proposal_agent/agents/roles.py`. 단계가 예산을 넘으면 `AgentRunError(error_max_budget_usd)`로 실패하고 자동 재시도하지 않는다.
- 모델: `PWA_MODEL_PRIMARY`(분석·검증·설계), `PWA_MODEL_WORKER`(보조). 변경 후 비용·품질은 실제 실행으로 다시 확인해야 한다.
- 영업일 계산 공휴일: `PWA_HOLIDAYS`. 요구사항 ID 접두사: `PWA_ID_PREFIXES`(프로젝트 생성 후에는 바꾸지 말 것 — 기존 ID와 충돌).
- 통합 QA: `PWA_QA_MAX_FIX_ROUNDS`(자동 수정 횟수), `PWA_QA_USE_AGENT`(qa_reviewer 덧붙임).

## 3. 백업과 복구

데이터는 두 곳에 있다. 항상 **함께** 백업한다.

| 대상 | 경로 | 내용 |
|---|---|---|
| SQLite DB | `workspace\pwa.sqlite3` | 프로젝트·문서·요구사항·계획·변경 요청·게이트·감사 기록 (엔티티는 `data` JSON 컬럼) |
| 산출물 | `Output\Project_*\` | 원본 문서, 에이전트 결과 JSON, Excel/PPT/PNG, QA 보고서, Revision 스냅샷, 최종본 |

절차: 앱 종료 → 두 경로를 날짜 폴더로 복사 → 복구 시 같은 위치에 되돌리고 앱 재시작. DB와 파일이 어긋나면 통합 QA의 `QA-FILE-09`(파일 경로)·`QA-CON-07`(변경 이력)과 `scripts\final_inspection.py`의 "DB↔파일 일치" 항목이 불일치를 보고한다.

Revision 스냅샷(`12_Revision_History\*.json`)은 기준 데이터 전체(JSON)를 담고 있어, DB를 잃어도 당시 요구사항·WBS를 사람이 확인할 수 있다(자동 복원 기능은 없다).

## 4. 마이그레이션과 업그레이드

- 코드를 새 버전으로 바꾼 뒤 처음 기동하면 `storage/migrations.py`의 미적용 마이그레이션이 자동 적용된다(현재 0001~0006). 업그레이드 전에 3절대로 백업한다.
- 의존성 변경 시 `pip install -e ".[dev]"`를 다시 실행하고 `python -m pytest -q`로 확인한다.

## 5. 비용·외부 API 통제

- 에이전트 실행은 Anthropic API 과금 대상이다. 단계별 비용은 `step_runs.cost_usd`·`agent_outputs.cost_usd`·감사 이벤트에 기록되고 화면 요약에 표시된다.
- 기술 조사 역할만 내장 `WebSearch`/`WebFetch`로 외부 웹에 접근한다. 접근한 URL은 감사 이벤트에 남는다. 그 밖의 역할은 외부 접근 권한이 없다.
- 프롬프트에는 RFP 블록·요구사항·조사 결과가 포함되어 Anthropic으로 전송된다. 외부 전송이 허용되지 않는 문서는 올리지 말 것(D-10 정책은 미확정).
- 크레딧 부족·인증 오류·예산 초과는 즉시 실패하며 재시도하지 않는다. 일시 오류(rate limit·overloaded·connection)만 역할별 `retries` 횟수만큼 재시도한다.

## 6. 보안

- `.env`는 `.gitignore`에 포함되어 있다. 키는 로그·DB·감사 기록에 쓰지 않으며 감사 payload의 `*key*`·`*token*`·`*secret*` 항목은 `***`로 마스킹된다. `scripts\final_inspection.py`가 코드·문서·로그·DB에 키 패턴과 실제 키 값이 없는지 검사한다(2026-10-15 통과).
- 에이전트에는 파일 쓰기 도구(Bash/Write/Edit/NotebookEdit)가 어떤 역할에도 없고, PreToolUse 훅과 `can_use_tool`이 허용 목록 밖 도구를 거부한다.
- 모든 파일 경로는 프로젝트 `Output` 폴더 안으로 제한된다(`ensure_within`, 위반 시 `PathSecurityError`).
- 산출물 다운로드·외부 공유는 사람이 파일 탐색기로 수행한다. 앱은 파일을 외부로 보내지 않는다.

### 6.1 고객 샘플 자료 취급 (필수)

- 고객이 제공한 실과제 자료(RFP, 제출용·발표용 제안서, 요구사항 정의서, 요구사항 추적표, WBS, 인력 투입계획 등)는 **참고 전용**이며 외부 유출·저장소 업로드를 금지한다. 저장소 밖 폴더(예: 별도 드라이브)에만 두고, 앱에는 프로젝트 `Output\…\01_RFP_Original`(git 제외)로만 등록한다.
- 코드·테스트·문서에는 고객사명·사업명·제품명·담당자·연락처·원문 문장·파일명을 적지 않는다. 서식·구조·통계(장 수, 좌표, 글꼴 크기, 검사 결과 수치)만 기록한다. 테스트 픽스처는 가상 내용으로 만든다.
- 커밋 전 검사: `python scripts\check_sensitive_terms.py --install-hook`로 pre-commit 훅을 설치하면 스테이징된 파일에서 금지 용어와 문서 바이너리(pdf/pptx/docx/xlsx/hwp)를 검사해 커밋을 막는다. 금지 용어 목록은 저장소에 올리지 않는 `.sensitive-terms.local`(한 줄에 하나)에 둔다. 전체 점검은 `--all`.
- 이미 올라간 경우: 해당 내용을 익명화한 커밋으로 이력을 다시 쓰고(`git push --force-with-lease`) 원격의 옛 커밋은 GitHub 가비지 컬렉션 전까지 캐시될 수 있으므로 필요하면 GitHub 지원에 삭제를 요청한다(2026-10-15 Phase 11~13 커밋에 적용).

## 7. 장애 대응

| 증상 | 확인 | 조치 |
|---|---|---|
| 기동 실패 `ConfigError` | `.env`·환경변수 | `PWA_APP_ENV=prod`면 API 키 필수. 값 확인 후 재시작 |
| 에이전트 단계 실패 `Credit balance is too low` / `authentication` | 화면 오류의 원인·조치, `app.log` | 크레딧 충전 / 키 재발급. 단계는 재실행 가능 |
| 단계가 "실행 중"으로 남음 | 앱 강제 종료 후 | 프로젝트 화면에서 해당 단계를 실패 처리하거나 재실행(중복 실행은 거부됨) |
| 파일 열기 실패·QA FAIL | `11_QA_Validation_Reports` 보고서 | 통합 QA 재실행(재생성으로 자동 수정) → 그래도 실패면 보고서의 수정 제안에 따라 데이터 수정 |
| 변경 반영 중 오류(`error` 상태) | 변경 관리 화면 | 기준 데이터는 롤백되어 있다. 원인 해결 후 **반영 재시도** |
| 스캔 PDF 추출 실패 | 인터넷·OCR 모델 다운로드 | 온라인에서 한 번 실행해 모델을 받거나, 텍스트 PDF/DOCX로 변환 |
| DLL 차단(ImportError) | 앱 제어 정책 | PyMuPDF·matplotlib은 사용하지 않음. 다른 네이티브 패키지(onnxruntime 등)가 차단되면 정책 예외 필요 |

## 8. 정기 점검

- 회귀: `python scripts\run_regression.py` (pytest 전체 + 제안·구축 데모 + 통합 QA 보고서). 실패하면 종료 코드 1.
- 기능 검수: `python scripts\final_inspection.py` → `workspace\final_inspection.md`.
- 린트·타입: `python -m ruff check src tests scripts`, `python -m mypy src`.
- 실제 모델 호출 점검(비용 발생): `python scripts\run_phase2_llm.py`, `python -m pytest -m llm -q`.

## 9. 데이터 정리

- 프로젝트 삭제 기능은 없다(의도적: 산출물·이력 보존). 불필요한 프로젝트는 백업 후 `Output\Project_*` 폴더와 DB 레코드를 수동으로 정리한다.
- `workspace\<project_id>\`는 에이전트 작업 폴더(추출 텍스트·청크)로, 프로젝트를 정리할 때 함께 삭제해도 된다.
