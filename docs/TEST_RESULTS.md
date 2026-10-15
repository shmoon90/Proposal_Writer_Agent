# TEST_RESULTS — 실제 실행한 테스트와 결과

문서 버전 1.0 · 실행일 2026-10-15 · 환경: Windows 11 Pro 10.0.26200, Python 3.12.10, 브랜치 `phase/8-docs-final` (main `87df2b2` 기준)

여기 적힌 결과는 모두 이 날 실제로 실행한 명령의 출력이다. 실행하지 않은 검사는 "미실행"으로만 적고 통과로 세지 않았다.

---

## 1. 자동 테스트 (pytest)

명령: `python -m pytest -q -rs` (기본 `-m 'not llm'`)

결과: **231 passed, 1 skipped, 2 deselected** (48.8s, 2026-10-15 Phase 11 반영. Phase 8 시점 215 passed)

- skipped 1: `tests/unit/test_paths.py::test_ensure_within_blocks_symlink` — 이 PC 계정에 심볼릭 링크 생성 권한이 없음(WinError 1314). 코드 결함이 아니라 환경 제약.
- deselected 2: `tests/integration/llm/` — 실제 Claude API 호출이 필요한 LLM 계약 테스트. **크레딧 부족으로 실행하지 않음.**

| 파일 | 건수 | 대상 |
|---|---|---|
| tests/unit/test_agent_controls.py | 22 | 도구 정책·취소·시간 제한·훅·비밀값 마스킹 |
| tests/unit/test_ingest.py | 18 | DOCX/TXT/PDF/스캔 PDF 추출, OCR, 손상·암호화 처리, Gate 0 |
| tests/unit/test_extraction_optimizer.py | 11 | (Phase 10) 저신호 청크 건너뛰기·캐시·검증 창 병합·호출/예산 상한 |
| tests/unit/test_rfp_profile.py | 5 | (Phase 11) 절 분류·잡음 정리, 구조화 RFP 픽스처의 ID 색인·블록 태그·목차/평가/제출, 청크 태그·저신호 예외, RFP ID 커버리지 경고·QA-RFP-07 |
| tests/unit/test_planning.py | 16 | 영업일 달력, FS/SS/FF/SF 일정, 롤업, 순환 검출, 인력 월별 분배 |
| tests/unit/test_phase6_changes.py | 15 | 구축 단계 14 시나리오(적재·매핑·분류·영향·승인·롤백·버전 파일) |
| tests/unit/test_paths.py | 15 | 경로 제한·안전한 파일명·프로젝트 폴더 |
| tests/unit/test_storage.py | 14 | 마이그레이션·리포지토리·시퀀스·복합 키 |
| tests/unit/test_requirements_phase2.py | 12 | 요구사항 추출·ID·출처 검증·독립 검증·Gate 1 |
| tests/unit/test_generators.py | 11 | Excel 4종·PPT 2종·구성도·목차·QA·Gate 5·최종본 |
| tests/unit/test_pipeline_service.py | 9 | 단계 정의·상태 전이·게이트 기록 |
| tests/unit/test_agent_step_service.py | 9 | 역할 실행·재사용·기술 조사·실패 복구·감사 |
| tests/integration/test_phase7_qa.py | 9 | 제안·구축 E2E, 자동 수정 한도, 실패 복구, 격리, 경로, 게이트 정책, 에이전트 검토 |
| tests/unit/test_project_service.py | 8 | 프로젝트 생성·열기·폴더 |
| tests/integration/test_ui_flow.py | 8 | Streamlit AppTest: 시작·프로젝트·문서 등록 |
| tests/unit/test_settings.py | 7 | .env·환경변수 우선순위·prod 키 필수 |
| tests/unit/test_models.py | 6 | 엔티티·상태 전이 |
| tests/unit/test_mcp_tools.py | 6 | 인프로세스 pwa 도구(읽기 전용·경로 제한) |
| tests/unit/test_id_policy.py | 6 | ID 발급·레거시 체계·정규화 |
| tests/unit/test_document_service.py | 6 | 업로드 규칙·중복·보존 |
| tests/unit/test_agent_roles.py | 6 | 역할 10종·금지 도구·재사용 선언 |
| tests/unit/test_audit_logging.py | 5 | 감사 이벤트·마스킹·로그 |
| tests/integration/test_ui_phase2.py | 3 | AppTest: 추출·요구사항 화면 |
| tests/integration/test_sdk_connection.py | 3 | **실제 번들 Claude Code 프로세스**로 pwa·외부 HTTP MCP 연결, 깨진 서버 실패 보고 (모델 호출 없음) |
| tests/integration/test_ui_deliverables.py | 1 | AppTest: 생성→QA→Gate 5 승인→최종본 |
| tests/integration/test_ui_build.py | 1 | AppTest: 구축 기준 문서→변경 요청→승인 |

**Phase 11 실문서 점검 (저장소 밖 샘플, 커밋하지 않음)**: 고객 제공 RFP 샘플 PDF(48쪽, 저장소 밖·공개 금지)를 추출해 프로파일러를 돌린 결과 절 9종 인식, RFP ID 22건(SCR 5·SFR 3·UIXR 3·DAR 2·PCR 2·QUR 2·PER/PMR/SER/TOR/TSR 각 1, 자리수 3), 요구사항 절 블록 257개 중 225개에 ID 태그, 세로 라벨 잡음 220줄 제거, 제안서 목차 Ⅰ~Ⅴ 5항목, 평가 항목 19행(기술 90·가격 10 포함), 청크 14개 중 요구사항 청크는 ID 경계에서 분할됨. 이 문서로 에이전트 추출은 실행하지 않았다(API 크레딧 없음).

## 2. 정적 검사

| 명령 | 결과 |
|---|---|
| `python -m ruff check src tests scripts` | All checks passed |
| `python -m ruff format --check src tests scripts` | 통과 |
| `python -m mypy src` | Success: no issues found in 101 source files |

## 3. 회귀 실행기 (`scripts/run_regression.py`)

pytest 전체 실행 + 임시 루트에서 제안·구축 데모 프로젝트 전체 흐름 + 통합 QA 보고서(pytest 결과 첨부).

| 항목 | 결과 |
|---|---|
| pytest | exit 0, 215 passed, 1 skipped, 2 deselected (57.6s) |
| 회귀_제안 (proposal) | 검증 30건 실행 / 통과 25 · 실패 0 · 검토 필요 5 → gate2 NEEDS_HUMAN_REVIEW, gate3 PASS, gate4 PASS, gate5 NEEDS_HUMAN_REVIEW |
| 회귀_구축 (build) | 검증 19건 실행 / 11건 해당 없음(RFP·PPT) / 통과 19 · 실패 0 → gate2·3·4 PASS, gate5 NEEDS_HUMAN_REVIEW |

보고서 샘플: `docs/samples/통합QA보고서_샘플_proposal.md`, `docs/samples/통합QA보고서_샘플_build.md`.

## 4. 최종 기능 검수 (`scripts/final_inspection.py`)

격리된 임시 루트에서 사용자 기능 전부를 실제로 실행했다. 결과 **42항목 PASS / 0 FAIL** (2.2s). "LLM=모의" 4항목은 에이전트 응답을 FakeAgentRunner로 대체한 것이며 실제 모델 호출이 아니다.

| 영역 | 기능 | 결과 | LLM | 근거 |
|---|---|---|---|---|
| 제안 | 프로젝트 생성 | PASS | - | `Project_20261015_검수_제안` 생성 |
| 제안 | RFP Word 입력 | PASS | - | `01_RFP_Original/rfp.docx` |
| 제안 | RFP TXT 입력 | PASS | - | `01_RFP_Original/rfp.txt` |
| 제안 | RFP PDF 입력 | PASS | - | `01_RFP_Original/rfp.pdf` |
| 제안 | 문서 분석(추출, DOCX·TXT·PDF) | PASS | - | 문서 3건, 블록 76개, 방식 docx/txt/pdf 모두 text, gate0=PASS |
| 제안 | 요구사항 추출·독립 검증(Gate 1) | PASS | 모의 | 요구사항 11건(CON-001, CON-002, FR-001…), gate1=PASS |
| 제안 | RFP 분석(에이전트) | PASS | 모의 | `02_RFP_Analysis/rfp_analysis_v1.0.json` |
| 제안 | 기술 조사·구현 가능성 검토(에이전트) | PASS | 모의 | 조사 3건, 주제 14개, 미확인 2건, 구현 가능성 비교 1건 |
| 제안 | 아키텍처 설계(에이전트) | PASS | 모의 | `05_Architecture_Design/architecture_v1.0.json` |
| 제안 | 산출물 생성 실행 | PASS | - | 산출물 9건, 검토 필요 6건 |
| 제안 | 제출용 PPT 생성 | PASS | - | `07_Submission_Proposal_PPT/제안서_제출용_v1.0.pptx` |
| 제안 | 발표용 PPT 생성 | PASS | - | `08_Presentation_PPT/제안서_발표용_v1.0.pptx` |
| 제안 | 요구사항 정의서 생성 | PASS | - | `09_Excel_Deliverables/요구사항정의서_v1.0.xlsx` |
| 제안 | 요구사항 추적표 생성 | PASS | - | `09_Excel_Deliverables/요구사항추적표_v1.0.xlsx` |
| 제안 | WBS·간트 차트 생성 | PASS | - | `06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx` |
| 제안 | 인력 투입계획 생성 | PASS | - | `06_WBS_Effort_Schedule/인력투입계획_v1.0.xlsx` |
| 제안 | 구성도 PNG 생성 | PASS | - | `10_Diagrams_Charts_Images/시스템구성도_v1.0.png` |
| 제안 | 통합 QA(독립 검증) 실행 | PASS | - | 통과 22·실패 0·검토 필요 8·미실행 0 → gate5 NEEDS_HUMAN_REVIEW, 보고서 `11_QA_Validation_Reports/통합QA보고서_v1.0.md` |
| 제안 | QA 승인(Gate 5)·최종본 확정 | PASS | - | 최종본 9건 → `13_Final_Deliverables` |
| 구축 | 프로젝트 생성 | PASS | - | `Project_20261015_검수_구축` |
| 구축 | 기존 Excel 문서 입력·구조 분석 | PASS | - | 4종 등록, 표준 양식 자동 매핑(확인 필요 0) |
| 구축 | 기준 데이터 적재(Revision v1.0) | PASS | - | Revision v1.0 + 스냅샷 |
| 구축 | 기존 요구사항 조회 | PASS | - | SFR-001~005, SNR-001 |
| 구축 | 요구사항 추가·변경·삭제 요청 등록 | PASS | - | CR-001 (자연어 3항목) |
| 구축 | 의미 기반 비교(규칙; AI 덧붙임 미실행) | PASS | - | C01=ADD, C02=MODIFY:SNR-001, C03=DELETE_REQUEST:SFR-005 |
| 구축 | 일정·공수 영향 분석 | PASS | - | 종료 2027-03-12→2027-04-13(+22영업일), 공수 190.0→215.6 M/D(범위), 인력 시나리오 3 |
| 구축 | 문서별 변경안 확인(후보·전후 비교) | PASS | - | 후보별 before/after |
| 보호 | 승인 전 기준 데이터 불변 | PASS | - | 분석 후 요구사항 6건 변경 없음 |
| 구축 | 사용자 결정(수락) | PASS | - | 후보 3건 수락 |
| 구축 | 사용자 승인·기준 반영 | PASS | - | Revision v2.0, 신규 ID SFR-006, 문서 4건 |
| 구축 | 신규 버전 파일 생성(타임스탬프) | PASS | - | `Requirements_Definition_202610151217.xlsx` 외 3건 |
| 구축 | 사용자 반려(기준 불변) | PASS | - | CR-002 rejected, SFR-004 불변 |
| 구축 | 변경 이력 조회(변경관리대장) | PASS | - | 행 4건, Revision v1.0·v2.0 |
| 구축 | 변경 후 QA | PASS | - | 19건 실행·11건 해당 없음, 실패 0 → gate2·3·4 PASS |
| 보호 | 산출물 경로가 프로젝트 폴더 안에 존재 (제안/구축) | PASS | - | 9건/4건, 문제 없음 |
| 보호 | DB↔파일 일치 (해시·존재) (제안/구축) | PASS | - | 불일치 0 |
| 보호 | 프로젝트별 파일이 섞이지 않음 | PASS | - | 교차 0 |
| 보호 | 기존 파일 덮어쓰기 금지 | PASS | - | 같은 이름 저장 거부(FileExistsConflict), 보존 저장 `_1` |
| 보호 | 경로 탈출 거부 | PASS | - | PathSecurityError |
| 보호 | API 키·비밀값 미노출 | PASS | - | 코드·문서 키 패턴 0건, 추적 파일 168개·로그·DB에 실제 키 값 없음 |

## 5. SDK·MCP 연결 (실제 프로세스, 모델 호출 없음)

`tests/integration/test_sdk_connection.py` 3건이 1절 결과에 포함되어 통과했다(번들 Claude Code 프로세스 기동, `pwa` 연결·도구 10종, 외부 HTTP 문서 서버 연결, 깨진 stdio 서버 `failed` 보고). `scripts/check_mcp.py`의 2026-10-15 결과도 같다.

## 6. 실행하지 않은 것

| 항목 | 이유 |
|---|---|
| `pytest -m llm`, `scripts/run_phase2_llm.py`(실제 Claude 호출) | 크레딧 부족 (`Credit balance is too low`). 크레딧 확보 후 실행 필요 |
| 실제 웹 검색 실행(tech_researcher) | 위와 동일 |
| 스캔 PDF 실제 문서 OCR | 모의 이미지로만 검증(신뢰도 0.94~0.97) |
| 다른 OS·Python 버전 | 미시도 |
| PPT·Excel 육안 검토 | Phase 4에서 구성도·간트 PNG만 육안 확인. 최종 제출 전 PowerPoint·Excel에서 사람이 확인해야 함 |
