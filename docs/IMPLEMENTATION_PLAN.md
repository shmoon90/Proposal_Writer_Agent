# IMPLEMENTATION_PLAN — 단계별 구현 계획

문서 버전 0.1 · 2026-10-15 · 관련: [TEST_STRATEGY.md](TEST_STRATEGY.md), [RISK_REGISTER.md](RISK_REGISTER.md)

---

## 0. 원칙

- 한 Phase는 독립적으로 실행·테스트 가능한 수직 슬라이스를 만든다.
- 각 Phase 종료 시 `pytest`(llm 마커 제외)와 `ruff check` 통과, 커밋, `docs/` 갱신.
- LLM 호출 테스트는 `-m llm`으로 분리하고, API 키가 있을 때만 수동 실행한다. 실행하지 않은 테스트는 통과로 보고하지 않는다.
- Phase 내 미완 항목은 다음 Phase로 넘기지 않고 Phase 종료 보고에 명시한다.

## Phase 0 — 설계 (완료)

- 산출물: `docs/` 8종, `pyproject.toml`, `.gitignore`, 디렉터리 골격, Git 초기화.
- 완료 조건: 문서 간 엔티티·에이전트·단계 명칭 일관성 확인, 첫 커밋.

## Phase 1 — 기반 구축 (2026-10-15 구현, 세부 보고는 `docs/PHASE1_REPORT.md`)

| 작업 | 세부 | 산출 |
|---|---|---|
| 1.1 가상환경 | `py -3.12 -m venv .venv`, `pip install -e .[dev]` | `.venv/`, `requirements.lock.txt`(pip freeze) |
| 1.2 의존성 검증 | streamlit 1.66 + pandas 버전 호환 확인, pandas 2.x 고정 여부 결정 (R-09) | pyproject 갱신 |
| 1.3 설정·경로 | `config/settings.py`(.env 로드, 필수 키 검사), `config/paths.py`(`ProjectPaths`, `OUTPUT_SUBDIRS`, 중복 폴더 식별자), `config/logging.py`, `config/errors.py` | |
| 1.4 데이터 모델 | `models/*` Pydantic 엔티티 + enum, `*Draft` 스키마, `model_json_schema()` draft-07 호환 확인 | |
| 1.5 저장소 | `storage/db.py`(sqlite3, 마이그레이션 0001), `repositories.py`(CRUD, 삭제=상태변경), `files.py`(덮어쓰기 금지, 버전 파일명) | |
| 1.6 ID 정책 | `requirements/id_policy.py` 시퀀스 발급·재발급 금지 | |
| 1.7 UI 골격 | `app.py` 모드 선택 → 프로젝트 생성/열기 → 빈 파이프라인 화면, `orchestrator/pipeline.py` Step 추상, `jobs.py` 스레드+asyncio 브리지 | |
| 1.8 Agent SDK 연결 스모크 | `agents/runner.py` 최소 구현 + `scripts/smoke_agent.py`(API 키 필요, 수동) | |

**완료 조건**
- 단위 테스트: 모델 직렬화/역직렬화, 리포지토리 CRUD, ID 발급 단조성, 폴더 중복 식별자, 덮어쓰기 거부 — 모두 통과.
- `streamlit run src/proposal_agent/app.py`로 모드 선택과 프로젝트 생성이 동작하고 Output 폴더 14종이 생성됨.
- API 키가 있으면 `smoke_agent.py`가 구조화 출력 1건을 반환(수동 확인, 결과를 보고서에 기록).

## Phase 2 — 문서 입력 + 요구사항 추출·검증

| 작업 | 세부 |
|---|---|
| 2.1 ingest | PyMuPDF 텍스트·페이지 추출, python-docx 추출, `chunker.py`(섹션 제목 감지, 페이지 좌표), 텍스트 비율 기반 OCR 필요 판정 |
| 2.2 OCR 스파이크 | `rapidocr-onnxruntime` 한국어 모델 가용성 vs `pytesseract`+Tesseract 설치 비교 → 결정 후 `ocr.py` 플러그인 구현 (R-07) |
| 2.3 SDK MCP 도구 | `agents/tools/project_tools.py` 읽기 전용 도구 9종, `create_sdk_mcp_server("pwa")` |
| 2.4 훅 | `PreToolUse(Write\|Edit)` 거부, `PostToolUse(WebFetch\|WebSearch)` 출처 기록 |
| 2.5 P1 RFP 분석 | 프롬프트, `RfpAnalysis` 스키마, 02_RFP_Analysis 저장 |
| 2.6 P2 추출 | 프롬프트, `RequirementExtraction`, 섹션 서브에이전트, ID 발급·중복 매칭 |
| 2.7 P3 독립 검증 | 별도 프롬프트, `VerificationReport` → ValidationResult 반영 |
| 2.8 UI | RFP 업로드, 추출 진행 표시, 요구사항 표 편집(제한 컬럼), 게이트 1 승인 → Revision v1.0 |
| 2.9 샘플 RFP | `tests/fixtures/sample_rfp.pdf`(자체 작성, 저작권 문제 없는 문서) |

**완료 조건**
- 단위: 청크 좌표 정확성, OCR 판정 임계, ID 매칭, 승인 전 baseline 불변.
- 통합(모의 LLM): 추출 → 검증 → 승인 파이프라인이 Fake runner로 끝까지 실행.
- LLM(수동): 샘플 RFP에서 요구사항 ≥ 10건, 출처 누락 0건, 검증 보고서 생성. 결과와 비용을 Phase 보고서에 기록.

## Phase 3 — 기술 조사 + 일정·공수·인력 계산

| 작업 | 세부 |
|---|---|
| 3.1 P4 기술 조사 | WebSearch/WebFetch 허용, `ResearchReport`, `research/sources.py` 도메인 기반 신뢰도 분류, 04_ 저장 |
| 3.2 P5 아키텍처 | `ArchitectureDraft` → ArchitectureComponent |
| 3.3 planning | `calendar.py`(영업일·공휴일 설정), `scheduler.py`(의존 검증·순환 거부·CPM 전진 계산), `effort.py`, `staffing.py`(월별 M/M, 비용) |
| 3.4 P6 계획가 | `WBSDraft`(날짜 없음) → 코드 일정 계산 |
| 3.5 UI | 조사 결과 검토(게이트 2), 간트 미리보기, 공수·인력 표, 게이트 3 |

**완료 조건**
- planning 단위 테스트: 영업일 계산, FS/SS/FF/SF + lag, 순환 탐지, 공수 합계, 배정 합 검증 — 결정적 결과 고정(golden).
- 통합(모의): 요구사항 baseline → 계획 승인까지 Fake runner 실행.
- LLM(수동): 조사 결과에 출처 ≥ 1건/항목, 공식 문서 비율 보고.

## Phase 4 — 문서 생성

| 작업 | 세부 |
|---|---|
| 4.1 generator base | 출력 경로·버전·sha256·Deliverable 등록, 덮어쓰기 금지 |
| 4.2 Excel 4종 | openpyxl, 필수 시트·컬럼 상수화(validation과 공유) |
| 4.3 다이어그램 3종 | matplotlib 레이어 박스 렌더링, 한글 폰트 설정(R-10) |
| 4.4 P7 문안 | `ProposalContent` 제출용/발표용 프로필 |
| 4.5 PPT 2종 | python-pptx, 템플릿 .pptx 선택 가능, 표·이미지 삽입 |
| 4.6 요약 | 00_Project_Summary |

**완료 조건**
- 생성 파일을 openpyxl/python-pptx로 재오픈해 필수 시트·컬럼·슬라이드 수 검증 테스트 통과.
- 샘플 데이터로 4 Excel + 2 PPT + 3 PNG 생성, 사람이 열어 확인(보고서에 스크린샷 또는 확인 기록).

## Phase 5 — QA·승인·버전

| 작업 | 세부 |
|---|---|
| 5.1 validation | `file_integrity.py`, `consistency.py`(요구사항 수·ID 일치·추적 누락), `rules.py` 레지스트리 |
| 5.2 P8 QA 에이전트 | 파일 추출 텍스트 + 기준 데이터 비교, `QaReport` → 11_ 저장 |
| 5.3 Revision | 스냅샷 JSON, 12_, 13_Final 복사, sha256 대조 |
| 5.4 UI | 게이트 4, 비용 누적 패널, AuditEvent 뷰 |

**완료 조건**
- error 0건일 때만 최종 승인 가능함을 테스트로 보장.
- 제안 단계 E2E(모의 LLM) 통과.

## Phase 6 — 구축 단계

| 작업 | 세부 |
|---|---|
| 6.1 excel_reader | 매핑 프로파일 기반 파싱, 필수 필드 검사, 원본 ID 유지·이어 발급 |
| 6.2 B1 구조 분석 | `ColumnMappingProposal`, 매핑 UI |
| 6.3 변경 요청 | `change_request.py` 수명주기, UI(추가/변경/삭제) |
| 6.4 diff | 결정적 필드 diff, 유사 후보(정규화 문자열) |
| 6.5 B2/B3 | 의미 비교, 영향 분석, `impact.py` 그래프 탐색, planning 재계산 |
| 6.6 적용·갱신 | 승인 후 Requirement 갱신, B4, generators 새 버전, 변경이력 시트 |
| 6.7 제안→구축 승계 | 제안 프로젝트 데이터 가져오기 |

**완료 조건**
- 승인 전 기준 데이터 불변, 삭제=상태변경, 새 버전 파일명, 변경 이력 보존을 테스트로 보장.
- 구축 단계 E2E(모의 LLM) 통과.

## Phase 7 — 안정화·운영

- E2E(실제 LLM) 1회 전체 실행 및 비용 보고, 사용자 매뉴얼(`docs/USER_GUIDE.md`), 설정 가이드, 로그 로테이션, 예외 메시지 정리, 성능(대형 RFP 300p) 점검.

## 의존성 설치 절차 (Phase 1.1)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pip freeze > requirements.lock.txt
```

설치 전 `pip index versions <pkg>`로 버전을 재확인하고, 변경 시 `PROJECT_OVERVIEW.md` 표를 갱신한다.

## Git 운용

- 브랜치: `main`(안정), `phase/<n>-<slug>` 작업 브랜치, Phase 완료 시 `main`에 병합.
- 커밋 메시지: `<영역>: <요약>` (예: `models: Requirement/Trace 엔티티 추가`).
- 태그: Phase 완료마다 `v0.<phase>.0`.
