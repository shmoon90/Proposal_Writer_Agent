# PHASE1_REPORT — 공통 기반 구현 완료 보고

작성일 2026-10-15 · 브랜치 `phase/1-foundation` · 관련: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md)

---

## 1. 실행한 검증 명령과 실제 결과

| 명령 | 결과 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | **83 passed, 1 skipped** (4.56s) |
| `.venv\Scripts\python -m pytest -q -rs` | skipped 1건: `test_ensure_within_blocks_symlink_escape` — Windows에서 심볼릭 링크 생성 권한 없음(WinError 1314). 권한이 있는 환경에서는 실행됨 |
| `.venv\Scripts\python -m ruff check src tests` | All checks passed |
| `.venv\Scripts\python -m ruff format --check src tests` | 55 files already formatted |
| `.venv\Scripts\python -m mypy src` | Success: no issues found in 43 source files |
| `streamlit run src/proposal_agent/app.py --server.headless true --server.port 8599` | 기동 1초 후 `GET /` HTTP 200, `/_stcore/health` = ok (수동 확인 후 프로세스 종료) |

LLM(`-m llm`) 테스트는 이 단계에 없으며 실행하지 않았다.

## 2. 생성한 파일

### 소스 (`src/proposal_agent/`, 3,756줄)

| 영역 | 파일 | 내용 |
|---|---|---|
| 진입점 | `app.py` | `st.navigation`으로 시작/프로젝트 페이지 구성 |
| UI | `ui/app_pages/home.py` | 모드 선택(제안/구축), 신규 생성 폼(프로젝트명·발주처·시작일·종료일), 기존 프로젝트 열기(모드 필터), 작업자 이름 |
| | `ui/app_pages/project.py` | 입력 문서 업로드(모드별 필수/선택 종류), 진행 상태 표, 게이트 승인/반려, 미해결 이슈, 저장 위치, 승인 이력 |
| | `ui/components.py` | 값 객체만 받아 그리는 표·패널 |
| | `ui/state.py` | 서비스 캐시(`st.cache_resource`), 선택 프로젝트, 사용자 오류 메시지/기술 로그 분리, API 키 미설정 안내 |
| 서비스 | `services/context.py` | `AppContext.create()`: 설정 → 폴더 → 로깅 → DB 마이그레이션 |
| | `services/project_service.py` | 생성(검증·폴더 14종·workspace·DB·감사), 목록, 열기(누락 폴더 보충, 기존 파일 보존), 상태 변경, 저장 위치 |
| | `services/document_service.py` | 업로드 등록(원본 복사·sha256·중복 거부·형식/크기 검사), 모드별 필수 문서 규칙 |
| | `services/pipeline_service.py` | 제안 13단계/구축 10단계 정의, StepRun 상태 전이, 게이트(반려 사유 필수), 이슈 집계 |
| | `services/audit.py` | 감사 이벤트 + 기술 로그, 비밀값 마스킹 |
| 모델 | `models/enums.py`, `common.py`, `project.py`, `requirement.py`, `pipeline.py`, `deliverable.py`, `audit.py`, `planning.py`, `design.py` | DATA_MODEL.md 엔티티 20종 + StepRun/GateResult, `RequirementDraft`(에이전트 출력용), 상태 전이 표 |
| 저장소 | `storage/db.py` | sqlite3, RLock, WAL, 외래 키, 트랜잭션, 멱등 마이그레이션 |
| | `storage/migrations.py` | 0001_init: 13개 테이블 + 인덱스 |
| | `storage/repositories.py` | 조회 컬럼 + JSON 문서 패턴, 요구사항 물리 삭제 없음, 감사 이벤트 추가 전용, 시퀀스 |
| | `storage/files.py` | 덮어쓰기 금지(`open("xb")`), `name_1.ext` 중복 처리, `stem_vX.Y.ext` 버전 규칙, 해시 |
| 설정 | `config/settings.py` | `.env`→환경변수 우선, `PWA_APP_ENV` dev/prod(prod는 키 필수), 키 마스킹 |
| | `config/paths.py` | `ProjectPaths`, `OUTPUT_SUBDIRS` 14종, `ensure_within`(`..`·절대 경로·심볼릭 링크 탈출 차단), `safe_filename` |
| | `config/logging.py`, `config/errors.py` | 회전 파일 로거, `PWAError(message, cause, resolution)` 계층 |
| 요구사항 | `requirements/id_policy.py` | `REQ-F-###`/`REQ-N-###` 발급, 재발급 금지, 재추출 매칭(정규화 비교), 레거시 ID 체계 이어 발급 |

### 테스트 (`tests/`, 1,129줄, 84건)

| 파일 | 검증 항목 (사용자 요구 7절 대응) |
|---|---|
| `unit/test_paths.py` | 프로젝트별 폴더·필수 폴더 14종 생성, 중복 식별자, 기존 파일 보존, **잘못된 경로 차단**(`..`, 절대 경로, 심볼릭 링크, 알 수 없는 하위 폴더), 파일명 정규화 |
| `unit/test_settings.py` | **설정 누락 처리**(키 없음→`ConfigError`, prod 필수, 잘못된 env/숫자), `.env`·환경변수 우선순위, 키 마스킹 |
| `unit/test_storage.py` | 마이그레이션 멱등성, **DB 저장·조회**, 제약 위반, **프로젝트 간 격리**, 물리 삭제 없음, 조회 컬럼 화이트리스트, 감사 추가 전용, 시퀀스, 롤백, **파일명 중복 처리**, 덮어쓰기 거부, 버전 파일명 |
| `unit/test_models.py` | ID 자동 발급, JSON 왕복, 날짜 검증, Draft 스키마(ID/상태 제외, draft-07 호환), 상태 전이 |
| `unit/test_id_policy.py` | 순차 발급·타입별·프로젝트별, 재발급 금지, 재추출 매칭, 레거시 체계 |
| `unit/test_project_service.py` | **프로젝트 생성·조회**, 폴더·DB·감사, 잘못된 입력, 모드 필터, 열기(누락 폴더 복구/폴더 삭제 시 명확한 오류), **데이터 격리** |
| `unit/test_document_service.py` | 원본 복사, 같은 파일명 보존, 중복 내용 거부, 모드별 필수/선택 규칙, 형식·빈 파일 |
| `unit/test_pipeline_service.py` | 모드별 단계 정의, 상태 전이, 게이트 승인/반려(사유 필수), 재시도, 실패 기록, 건너뛰기 제한, 이슈 집계 |
| `unit/test_audit_logging.py` | **오류 로그 기록**(DB 감사 이벤트 + 로그 파일 내용 확인), 비밀값 마스킹 |
| `integration/test_ui_flow.py` | **모드별 화면 흐름**(AppTest): 키 미설정 안내, 제안 생성→프로젝트 화면→RFP 필수 경고, 구축 모드 문서 종류 5종·필수 3종, 빈 이름→사용자 오류, 미선택 시 안내, 기존 열기, 게이트 승인/반려 버튼 |

### 기타

`.env.example`(빈 값, `PWA_APP_ENV` 포함), `requirements.lock.txt`, `pyproject.toml`(pandas 2.x 고정, mypy pandas 오버라이드), `docs/` 4종 갱신.

## 3. 요구사항 대비 구현 여부

| 요구 | 상태 |
|---|---|
| 신규 생성 / 기존 열기 / 모드 선택 / 프로젝트명 / 시작·종료일 | 구현 |
| RFP 또는 구축 기준 문서 업로드, 제안=RFP 필수, 구축=정의서·추적표·WBS 필수·인력계획 선택 | 구현 (등록·보관·필수 검사까지. 내용 추출/파싱은 Phase 2·6) |
| 진행 상태·미해결 이슈·저장 위치·단계별 승인 상태 | 구현 |
| ProjectPaths(루트·작업·Output·유형별·workspace·로그), 안전 생성, 기존 파일 보존, 경로 탈출 방어 | 구현 |
| Pydantic + SQLite: 프로젝트·모드·문서 메타·요구사항·단계/Gate·산출물·승인·변경 이력·감사 | 구현 (테이블 13종) |
| 마이그레이션 방법 | 구현 (`migrations.py` 버전 튜플 + `schema_migrations`) |
| .env 관리, 미커밋, .env.example, 키 없을 때 이해 가능한 오류, 로그에 비밀값 금지, dev/prod 구분 | 구현 (`.env`는 Git 미추적 확인) |
| UI/서비스/데이터 접근 분리, 타입 힌트, 단일 책임 | 구현 (mypy 통과) |

## 4. 미구현·보류 사항

- **단계 실행 로직 없음**: `PipelineService`는 상태 기록만 한다. 실제 추출·에이전트·생성기는 Phase 2~5에서 `orchestrator/runner.py`로 연결한다. UI 진행 탭의 게이트 승인은 `needs_review` 상태의 StepRun이 있을 때만 나타난다.
- **Agent SDK 런타임 어댑터(`agents/runner.py`)와 스모크 스크립트**: 이번 프롬프트 범위에 없어 작성하지 않았다. API 키는 설정되어 있으므로 다음 단계에서 실제 호출 검증이 가능하다.
- **WBS·인력·기술조사·아키텍처·화면·테스트 테이블**: Pydantic 모델만 정의, DB 테이블은 Phase 3 마이그레이션 0002로 추가.
- **업로드 문서 내용 처리**: 텍스트 추출(PDF/DOCX/OCR), Excel 컬럼 매핑은 Phase 2·6.
- **Streamlit 장기 작업 브리지(`orchestrator/jobs.py`)**: 에이전트 호출이 생기는 Phase 2에서 스파이크 예정 (RISK R-06).
- **심볼릭 링크 탈출 테스트**는 현재 Windows 권한으로 skip. 코드 경로(`resolve()` 기반)는 구현되어 있으나 이 환경에서 실행으로 증명하지 못했다.

## 5. 이 단계에서 발생한 문제와 처리

- 이전에 중단했던 별도 세션이 제가 보낸 안내 메시지를 큐에서 받아 재개되어, 같은 폴더의 `storage/*`, `requirements/id_policy.py`, `models/*` 일부를 동시에 덮어썼다. 해당 세션을 다시 중단하고 유휴 상태를 확인한 뒤, 설계와 맞는 제 구현으로 되돌렸다. 그 세션이 중단 요청 이후에 만든 파일은 삭제하지 않고 `workspace/_phase1_session_leftovers/`에 보존했다(Git 제외 폴더). 그 세션의 `models/base.py`·`drafts.py`·`schema.py`·`test.py`, `storage/migrations/0001_init.sql`은 현재 코드에서 사용하지 않는다.
- `sqlite3.executescript`가 실행 전 보류 트랜잭션을 커밋하는 동작 때문에 마이그레이션 트랜잭션이 깨졌다. 스크립트 안에 `BEGIN/COMMIT`을 직접 포함하도록 수정했다(테스트 `test_migrate_is_idempotent_and_records_version`).

## 6. 실행 방법

```powershell
.venv\Scripts\Activate.ps1
python -m pytest -q
streamlit run src/proposal_agent/app.py
```
