# FINAL_REPORT — 최종 검수 보고서

작성일 2026-10-15 · 프로젝트 루트 `C:\DEV\Claude_Work\Proposal_Writer_Agent` · 브랜치 `phase/8-docs-final` → `main`
근거 문서: [TEST_RESULTS.md](TEST_RESULTS.md), [LIMITATIONS.md](LIMITATIONS.md), [RISK_REGISTER.md](RISK_REGISTER.md), PHASE1~7 보고서

**판정 요약**: 코드·자동 테스트·기능 검수는 통과했다(215 tests, 42 검수 항목, ruff/mypy). 그러나 **실제 Claude 모델 호출을 한 번도 검증하지 못했으므로(크레딧 부족) "최종 완료"로 보고하지 않는다.** 모의 LLM 기준으로는 완료, 실제 LLM 기준으로는 검증 대기 상태다.

---

## 1. 구현 완료 기능

| 영역 | 기능 | 위치 |
|---|---|---|
| 공통 | 프로젝트 생성·열기·모드(제안/구축), 프로젝트별 `Output` 폴더 14종, SQLite(엔티티 JSON + 인덱스 컬럼, 마이그레이션 0001~0006), 설정(.env/환경변수), 로그(회전), 감사 이벤트(비밀값 마스킹), 단계 상태(StepRun)·게이트(GateEvaluation·Approval) | `config/`, `storage/`, `services/`, `ui/` |
| 문서 처리 | DOCX·TXT/MD·텍스트 PDF·스캔 PDF(OCR, 한국어)·혼합 PDF 추출, 블록·위치·신뢰도·검토 필요 표시, 손상·암호화 처리, Gate 0 | `ingest/` |
| 요구사항 | 에이전트 추출(청크) → 코드 ID 발급(접두사 설정) → 출처 검증 → 독립 검증 에이전트 → 지적 사항 → Gate 1, 수동 추가·수정·삭제(상태)·수용 여부 | `requirements/`, `agents/` |
| 에이전트 | Claude Agent SDK 어댑터(구조화 출력, 도구 정책 훅·`can_use_tool`, 예산·턴·시간·취소·재시도, 실패 분류), 역할 10종, 인프로세스 MCP `pwa` 10도구, 외부 MCP 설정, 연결 점검(비용 0) | `agents/`, `services/agent_step_service.py` |
| 기술 조사 | 주제 식별(코드) → tech_researcher(WebSearch/WebFetch) → 출처 신뢰도 규칙·미확인 항목·구현 가능성 비교 저장, 사람 확인 표시 | `research/` |
| 계획 | 기간 결정(UI→RFP→입력 요청), WBS 초안(에이전트/기본값), 영업일 일정(FS/SS/FF/SF·lag·순환 검출·롤업), 공수→인력 월별 MM·인원, 단가 입력 시 비용 | `planning/` |
| 산출물 | 구성도 3종·일정/공수 차트(Pillow), 요구사항 정의서·추적표·WBS/간트·인력 투입계획 Excel, 제출용·발표용 PPT(RFP 목차 우선), 버전 파일명, 최종본 분리 | `generators/` |
| 통합 QA | 독립 검증 30항목(RFP 적합성·기술 타당성·문서 간 일관성·파일 품질), 재생성 한정 자동 수정·재검증(횟수 제한), Gate 2·3·4·5 코드 판정, 보고서(md+json), qa_reviewer 보조 검토 | `validation/` |
| 구축 변경관리 | 기존 Excel 적재(매핑 제안·확정, ID 유지, Revision v1.0), 변경 요청 5가지 입력, 규칙 의미 비교(+AI 덧붙임), 영향 분석(일정·공수·인력 시나리오 1~6·비용), 후보 결정, 승인→트랜잭션 반영(새 ID·이력·삭제 표시·추적 재검토·WBS 갱신·Revision·타임스탬프 문서), 반려·철회·오류 롤백·재시도, 변경관리대장, 변경 후 QA | `changes/`, `ingest/excel_reader.py` |
| 운영 | 회귀 실행기, 최종 검수 스크립트, MCP 점검 스크립트, 문서 세트 | `scripts/`, `docs/` |

## 2. 부분 구현 기능

| 기능 | 현재 상태 | 남은 일 |
|---|---|---|
| 에이전트 역할 전부 | 코드·프롬프트·스키마·연결은 구현, **실제 응답 품질 미검증** | 크레딧 확보 후 `scripts/run_phase2_llm.py`·`pytest -m llm` 실행, 프롬프트·예산 보정 |
| 의미 기반 비교 | 규칙 분류 동작, AI 덧붙임은 모의 검증만 | 실제 호출 검증, 경계 사례 보정 |
| 변경 영향 공수 추정 | 휴리스틱(유사도 비율·유사 Task 중앙값), 사용자 확정값으로 대체 가능 | 실측 데이터로 비율 조정 |
| RFP 적합성·기술 타당성 QA | 키워드·조사 기록 기반, 검토 필요 위주 판정 | 실제 조사 결과와 함께 운영하며 규칙 보강 |
| PPT 레이아웃 검사 | 좌표·글자 수 추정 | 최종 제출 전 육안 확인 절차 유지 |
| OCR | 모의 이미지 검증 | 실제 스캔본으로 임계값(`ocr_review_threshold`) 조정 |

## 3. 미구현 기능과 이유

| 기능 | 이유 |
|---|---|
| HWP/HWPX/DOC 추출 | 순수 Python 변환기 부재, 외부 변환기 도입 정책 미확정(D-08). 안내 메시지로 대체 |
| 제안 → 구축 데이터 승계(6.7) | 범위 제외. 제안 산출물 Excel 업로드로 대체 가능 |
| 사용자 PPT 템플릿 적용(D-06) | 미착수 |
| 프로젝트 삭제/아카이브 UI, DB 자동 복원 | 보존 원칙·범위 외 |
| 다중 사용자·인증 | 단일 PC 로컬 도구로 설계(D-09) |
| 외부 전송 고지·마스킹 정책(D-10) | 정책 미확정 |

## 4. 실제 사용한 Python 및 주요 라이브러리 버전 (`pip list`, 2026-10-15)

| 항목 | 버전 |
|---|---|
| OS / Python | Windows 11 Pro 10.0.26200 (x64) / **3.12.10** |
| claude-agent-sdk | 0.2.167 (설계 시 0.2.165, 설치 시 상향) |
| mcp | 2.3.0 |
| streamlit | 1.66.0 |
| pydantic / pydantic_core | 2.14.1 / 2.50.1 |
| openpyxl / python-pptx / python-docx | 3.1.5 / 1.0.2 / 1.2.0 |
| pdfplumber / pypdf / pypdfium2 | 0.11.10 / 6.20.1 / 5.14.0 |
| rapidocr / onnxruntime | 3.10.0 / 1.31.0 (한국어 모델 `korean_PP-OCRv5_rec_mobile`) |
| pillow / pandas | 12.3.0 / 2.3.3 |
| pytest / ruff / mypy / python-dotenv / reportlab(dev) | 9.1.1 / 0.17.0 / 2.4.0 / 1.2.4 / 5.0.1 |

PyMuPDF·matplotlib은 이 PC의 앱 제어 정책이 DLL을 차단해 사용하지 않는다(R-19, R-25). 전체 고정 목록은 `requirements.lock.txt`.

## 5. 실제 연결된 Claude Agent SDK와 MCP 도구

- Claude Agent SDK 0.2.167 번들 CLI 프로세스 기동 확인(`tests/integration/test_sdk_connection.py` 3건 통과, `scripts/check_mcp.py`). 인증은 `ANTHROPIC_API_KEY`만.
- 인프로세스 MCP `pwa`: `connected`, 도구 10종(get_project, list_requirements, get_requirement, search_source_text, get_source_block, list_research, list_findings, list_gates, get_prior_output, verify_deliverable_file). 모두 읽기 전용, 경로는 프로젝트 폴더 내부로 제한.
- 외부 HTTP MCP `claude-code-docs`(https://code.claude.com/docs/mcp): `connected`, 도구 3종(예시 구성, 역할 미사용).
- 내장 `WebSearch`/`WebFetch`: 세션 도구 목록에 노출 확인(tech_researcher 전용). **실제 검색 실행은 미검증.**
- 금지 도구(Bash/Write/Edit/NotebookEdit/Agent)는 어떤 역할에도 없음.

## 6. 실제 실행한 테스트와 결과

| 실행 | 결과 |
|---|---|
| `python -m pytest -q -rs` | 215 passed, 1 skipped(심볼릭 링크 권한), 2 deselected(llm) — 43.3s |
| `ruff check` / `ruff format --check` / `mypy src` | 통과 / 통과 / 101 파일 이상 없음 |
| `scripts/run_regression.py` | pytest 215 passed + 제안 데모(30건 실행, 실패 0, 검토 필요 5) + 구축 데모(19건 실행, 실패 0) |
| `scripts/final_inspection.py` | 42 PASS / 0 FAIL (모의 LLM 항목 4) |
| 실제 LLM 호출(`-m llm`, `run_phase2_llm.py`) | **미실행** (크레딧 부족) |

상세는 [TEST_RESULTS.md](TEST_RESULTS.md).

## 7. 생성된 주요 파일 및 경로

저장소(추적 파일 168개, 소스 약 21,300줄, 테스트 약 5,800줄):

| 경로 | 내용 |
|---|---|
| `src/proposal_agent/` | config · models(엔티티 29종) · storage(migrations 0001~0006) · ingest · requirements · agents(roles 10, prompts 10, tools) · research · orchestrator · planning · generators(excel·pptx·diagrams) · validation(deliverables·independent_qa·qa_service) · changes · services · ui(app_pages 8) · app.py |
| `tests/` | unit 18파일, integration 6파일(+llm 수동), fixtures(builders·excel_builders) |
| `scripts/` | check_mcp.py · run_phase2_llm.py · run_regression.py · final_inspection.py |
| `docs/` | 설계 7종, 운영·사용 문서 9종, PHASE1~7 보고서, samples/ 통합QA보고서 2종 |

실행 시 생성(프로젝트별, git 제외): `Output\Project_<날짜>_<이름>\00_~13_`([OUTPUT_STRUCTURE.md](OUTPUT_STRUCTURE.md)), `workspace\pwa.sqlite3`, `workspace\logs\app.log`. 검수 실행에서 만든 파일 예: `07_Submission_Proposal_PPT\제안서_제출용_v1.0.pptx`, `09_Excel_Deliverables\요구사항정의서_v1.0.xlsx`, `11_QA_Validation_Reports\통합QA보고서_v1.0.md`, `13_Final_Deliverables\`(9건), 구축 `09_Excel_Deliverables\Requirements_Definition_202610151217.xlsx`, `12_Revision_History\revision_CR-001_v1.0.json`.

## 8. 남아 있는 버그와 위험 (우선순위 순)

| 우선순위 | 항목 | 해결 방법 |
|---|---|---|
| 1 | 실제 LLM 경로 미검증 (R-21) — 프롬프트·스키마·예산이 실제 모델에서 유효한지 모름 | 크레딧 확보 → `run_phase2_llm.py` → `pytest -m llm` → 역할별로 1회씩 실행하며 예산·턴 조정 |
| 2 | 기술 조사 미실행 시 Gate 2가 항상 검토 필요 (R-33) | 실제 조사 실행 또는 조사 결과 수동 등록 절차 마련 |
| 3 | 규칙 의미 비교·RFP 적합성 검사의 한계 (R-28, R-31) | 경계 사례를 사용자 확인으로 처리(현재 동작). 실제 데이터로 임계값 보정 |
| 4 | 변경 공수 휴리스틱 (R-29) | 사용자 확정값 입력 유도, 실측 반영 |
| 5 | 산출물 기본값이 '미정/검토 필요'로 들어감 (R-26) | 아키텍처·계획 에이전트 실행 후 재생성 |
| 6 | PPT 레이아웃 추정 검사 (R-27) | 제출 전 육안 확인 |
| 7 | 심볼릭 링크 차단 테스트 미실행(환경) | 관리자 권한 계정에서 1회 실행 |
| 8 | 오프라인 PC에서 OCR 모델 다운로드 불가 | 온라인에서 1회 실행해 캐시 확보 |

알려진 코드 버그는 2026-10-15 현재 없다(열린 테스트 실패 0건). 발견된 결함은 모두 테스트로 재현·수정했다(PHASE 보고서 참조).

## 9. 비용 또는 외부 API 사용상 제약

- 에이전트 단계는 Anthropic API 과금 대상. 단계별 `cost_usd`가 기록되며 역할별 상한(`max_budget_usd`)과 `PWA_MAX_BUDGET_USD_PER_STEP`로 통제한다. 2026-10-15 추가: 프로젝트 누적 상한(`PWA_MAX_BUDGET_USD_PER_PROJECT`), 단계당 호출 수 상한(`PWA_MAX_AGENT_CALLS_PER_STEP`), 실행 전 예상 호출·최대 비용 표시, 청크 캐시(재실행 비용 0), 신호 없는 청크 건너뛰기, 검증 창 병합(추출 청크의 2배)으로 호출 수를 줄였다(`requirements/optimizer.py`). 설계 추정치(PHASE3)는 제안 1건당 약 $11~29이나 실측하지 못했다.
- 현재 계정은 `Credit balance is too low` 상태로 모든 실제 호출이 실패한다.
- API 키 방식만 지원(구독 로그인 불가). 기술 조사 역할만 외부 웹 접근 권한이 있다.
- 프롬프트에 RFP 원문 블록·요구사항·조사 결과가 포함되어 외부로 전송된다. 전송 불가 문서는 입력하지 말 것.

## 10. 실행 방법

```powershell
cd C:\DEV\Claude_Work\Proposal_Writer_Agent
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env          # ANTHROPIC_API_KEY 입력
python -m pytest -q                   # 215 passed 기대
streamlit run src\proposal_agent\app.py
```

세부: [INSTALLATION.md](INSTALLATION.md), 사용: [USER_GUIDE.md](USER_GUIDE.md), 운영: [ADMIN_GUIDE.md](ADMIN_GUIDE.md).

## 11. 사용자 확인 또는 수동 작업이 필요한 항목

1. **크레딧 충전 후 실제 LLM 검증** 실행과 결과 검토(1순위).
2. Gate 0·1·5 사람 승인, 구축 단계 변경 요청 승인·반려 — 모두 코드가 대신하지 않는다.
3. 요구사항 수용 여부(수용/조건부/미수용), 인력 단가, 과제 기간 입력.
4. 구축 단계에서 비표준 Excel 양식의 컬럼 매핑 확정.
5. 통합 QA 보고서의 "검토 필요" 항목(RFP 의무 표현 미연결, 평가 기준 요구사항, 근거 없는 기술명, 발표용 '미정' 표기 등) 판단.
6. 제출 전 PowerPoint·Excel에서 최종 육안 확인.
7. 미확정 정책 결정: D-04(역할별 모델), D-06(PPT 템플릿), D-08(HWP), D-09(승인자 식별), D-10(외부 전송 고지).
8. 백업 절차 운영(DB와 `Output` 동시 백업).

## 12. 독립 점검 결과 (2026-10-15, 브랜치 `phase/9-verification`)

| 항목 | 결과 |
|---|---|
| 요구사항 구현 | **부분 완료** — 코드·문서·테스트는 전 단계 구현. 실제 Claude 모델 응답 경로만 미검증 |
| 실제 실행 테스트 | **통과** — `pytest -q` 215 passed · 1 skipped(심볼릭 링크 권한) · 2 deselected(llm); `compileall`·`ruff`·`mypy` 통과; `scripts/final_inspection.py` 42 PASS; `pytest -m llm` 1 failed(크레딧) |
| 외부 연동 | **확인(부분)** — SDK 프로세스·`pwa` MCP(10 도구)·외부 HTTP MCP 실제 연결 `connected`, 깨진 서버 `failed` 보고(`scripts/check_mcp.py`). Anthropic API 호출은 인증까지 도달하나 `Credit balance is too low`로 응답 미검증 |
| 발견한 문제 | `services/pipeline_service.py`: 존재하지 않는 역할 키 `deliverable_qa`와 구현과 다른 게이트 제목("게이트 4: 최종 승인", "게이트 5: 변경 승인", "게이트 6")이 UI 단계 표에 노출 · `agents/runner.py`: 실패 메시지가 범주 대신 SDK 서브타입("success")을 표시 · 미사용 함수 4건(`baseline_service.business_date_or_none`, `impact.md_summary`, `ingest/service.describe_error`, `ingest/base.render_table_markdown`) · 설계 문서(AGENT_DESIGN §4, WORKFLOW_DESIGN §4, ARCHITECTURE §3, DATA_MODEL §4)가 원안 그대로여서 구현과 불일치 |
| 수정한 문제 | `pipeline_service.py` 단계 정의를 `qa_reviewer`·게이트 5·"변경 승인(사람)"으로 정정 · `runner.py` 메시지에 실패 범주 표시 · 미사용 함수 4건 삭제, `sha256_file`은 검수 스크립트에서 사용 · `ARCHITECTURE.md` 디렉터리 구조를 실제 트리로 교체, `AGENT_DESIGN.md`·`WORKFLOW_DESIGN.md`·`DATA_MODEL.md`에 구현 대조 절 추가 |
| 잔여 문제 | 실제 LLM 응답 품질·비용 미검증(크레딧) · 내장 WebSearch 실제 실행 미검증 · 심볼릭 링크 차단 테스트 미실행(권한) · 규칙 기반 의미 비교·RFP 검사 한계(R-28, R-31) · 공수 휴리스틱(R-29) |
| 다음 단계 진행 가능 여부 | **보류** — 모의 LLM 기준 기능은 완료되었으나, 실제 모델 호출 검증이 끝나기 전에는 운영 투입(다음 단계)을 보류한다. 크레딧 확보 후 `scripts/run_phase2_llm.py` → `pytest -m llm` 순으로 검증 |
