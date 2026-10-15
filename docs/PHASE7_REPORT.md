# PHASE7_REPORT — 통합 QA·회귀 테스트(독립 검증·자동 수정·게이트 정책) 구현 보고

작성일 2026-10-15 · 브랜치 `phase/7-integrated-qa` → `main` 병합 · 관련: [TEST_STRATEGY.md](TEST_STRATEGY.md), [RISK_REGISTER.md](RISK_REGISTER.md) R-31~R-33, 샘플 보고서 [docs/samples/](samples/)

---

## 1. 실제 실행한 검증 (결과는 실행 시점 출력 그대로)

| 명령 | 결과 |
|---|---|
| `pytest -q` (단위·통합·문서 생성·SDK/MCP 연결, `llm` 제외) | **215 passed, 1 skipped, 2 deselected** (약 45~58s) |
| `ruff check` / `ruff format --check` / `mypy src` | 모두 통과 (101 파일) |
| `python scripts/run_regression.py` (pytest 실행 + 제안·구축 E2E + 통합 QA) | pytest exit 0 · 제안 데모: 검증 30건 실행, 통과 25·실패 0·검토 필요 5 → gate2 NEEDS_HUMAN_REVIEW, gate3 PASS, gate4 PASS, gate5 NEEDS_HUMAN_REVIEW · 구축 데모: 19건 실행·11건 해당 없음(PPT·RFP 검사), 통과 19·실패 0 → gate2/3/4 PASS, gate5 NEEDS_HUMAN_REVIEW |
| 실제 LLM 호출 (`qa_reviewer`, `tech_researcher`) | **미실행** — 크레딧 부족(R-21). 에이전트 검토는 FakeAgentRunner로 덧붙임·실패 경로만 테스트 |

데모 보고서 2종은 `docs/samples/통합QA보고서_샘플_{proposal,build}.md`에 복사했다(원본 위치: `Output/<프로젝트>/11_QA_Validation_Reports/통합QA보고서_v1.0.md` + `.json`).

## 2. 독립 QA 구조

| 구성 | 위치 | 역할 |
|---|---|---|
| 검증 엔진 | `validation/independent_qa.py` | 산출물을 만든 생성기·에이전트와 분리된 코드가 원본 RFP 블록, 요구사항 데이터, 기술 조사 기록, 계획 데이터, 변경 이력, 생성 파일을 직접 대조한다. 입력(`QaInputs`)만 받고 저장소를 바꾸지 않는다 |
| 서비스 | `validation/qa_service.py` | 입력 수집 → 검증 → 자동 수정·재검증 루프 → 게이트 2·3·4·5 판정 → `QaRun` 저장·보고서(md+json) → 감사 기록 |
| 모델 | `models/qa.py`, 마이그레이션 0006 `qa_runs` | `QaCheck`(검증 ID·대상·기준·결과·발견 문제·관련 요구사항 ID·영향 파일·수정 제안·수정 여부·재검증 결과·시도 횟수·필수 여부·게이트), `QaRun`(범위·건수·게이트·수정 내역·외부 테스트 결과·미해결 위험·승인 필요·판정) |
| 에이전트 검토(선택) | `qa_reviewer` 역할 (`qa_use_agent` 설정 또는 호출 인자) | 코드 검증 결과·산출물 발췌·요구사항·조사 요약을 주고 독립 검토를 받는다. 결과는 `QA-AI-nn`(NEEDS_HUMAN_REVIEW, 비필수)로만 추가되어 코드 판정을 바꾸지 않는다. 실패하면 '미실행'으로 기록 |
| 회귀 실행기 | `scripts/run_regression.py` | pytest를 실제로 실행해 건수를 수집하고, 임시 루트(또는 `--root` 실제 데이터)에서 제안·구축 전체 흐름을 돌린 뒤 통합 QA 보고서에 pytest 결과를 첨부한다 |

## 3. 검증 항목 (30건)

| 분류 | ID | 기준 (요약) | 결과 규칙 |
|---|---|---|---|
| RFP 적합성 | QA-RFP-01 필수 요구사항 누락 | 의무 표현 블록이 요구사항 출처/인용으로 덮이는가 | 누락 → 검토 필요 |
| | QA-RFP-02 과잉 해석 | 부가 제안·범위 외가 필수로 표시되면 FAIL, 필수에 출처 없으면 검토 | |
| | QA-RFP-03 원문과 다른 내용 | `rfp_quote`가 원문 블록에 없으면 FAIL | |
| | QA-RFP-04 제출 조건 누락 / QA-RFP-05 평가 기준 대응 누락 | RFP 표현 대비 SUB-/EVA- 요구사항과 제출용 PPT 반영 | 검토 필요(비필수) |
| | QA-RFP-06 원본 출처 오류 | 출처 문서·블록 ID가 실제 존재하지 않으면 FAIL | |
| 기술 타당성 | QA-TECH-01 구현 불가 | infeasible 조사 + 수용 → FAIL, unknown/위험 동반 → 검토 | Gate 2 |
| | QA-TECH-02 미확인 솔루션 기능, -03 버전 호환성, -05 보안·성능·운영 위험, -06 근거 없는 기술 주장 | 조사 기록·구성 요소 대조 | 검토 필요(비필수) |
| | QA-TECH-04 연계 불가 | 없는 구성 요소 연결 → FAIL, RFP 연계 대상에 연계 구성 요소 없음 → 검토 | |
| 문서 간 일관성 | QA-CON-01 PPT↔정의서, -02 정의서↔추적표 | ID 집합·핵심 수치·필수 요구사항 추적 | FAIL(재생성으로 자동 수정 가능) |
| | QA-CON-03 요구사항↔WBS, -04 WBS↔일정(FS·상위 범위·기간), -05 WBS↔인력 | 데이터 대조 | FAIL (Gate 3, 자동 수정 불가 → 수정 제안) |
| | QA-CON-06 조사↔아키텍처 | 권고 스택과 구성 요소 기술 | 검토 필요 |
| | QA-CON-07 변경 이력↔기준 데이터 | 반영 CR의 상태·이전 버전·Revision·변경 후 파일 | FAIL |
| | QA-CON-08 발표용 미확정 표기 | '미정/검토 필요' 과다 | 검토 필요(비필수) |
| 파일 품질 | QA-FILE-01 열기, -02 방향·규격, -03 잘림, -04 겹침, -05 Excel 시트·컬럼, -06 날짜·수식, -07 요구사항 ID, -08 간트↔일정(시작·종료·채움 주), -09 파일 경로(Output 안·존재), -10 산출물 누락 | 파일을 실제로 열어 검사 | FAIL(대부분 재생성으로 자동 수정 가능), 잘림·겹침은 검토 필요 |

모드별로 해당 없는 항목(구축 단계의 RFP·PPT 검사)은 `미실행 · 해당 없음`으로 표시하고 통과로 세지 않으며 게이트도 막지 않는다. 실행할 수 없었던 항목(예: WBS 파일 없음)은 검토 필요로 남아 게이트를 막는다.

## 4. 자동 수정과 재검증

- 허용되는 자동 수정은 **기준 데이터로 산출물 재생성**뿐이다(`FIX_REGENERATE`). 요구사항·WBS·기술 데이터·변경 이력은 바꾸지 않는다. 원본 요구사항과 충돌하거나 기술 위험을 높이는 수정은 `fix_suggestion`으로 제안만 한다.
- 루프: 재생성으로 고칠 수 있는 FAIL이 있으면 재생성 → 전체 재검증 → 해당 항목에 `fix_applied`·`reverified`·`attempts` 기록. 횟수는 `qa_max_fix_rounds`(기본 2, `PWA_QA_MAX_FIX_ROUNDS`)로 제한하며, 한도 뒤에도 실패면 통과시키지 않고 NEEDS_HUMAN_REVIEW로 전환한다. 재생성 자체가 실패하면 `fix_applied=False`로 보류하고 FAIL을 유지한다.
- 테스트: 추적표 파일 삭제 → 1회 재생성으로 PASS(`test_auto_fix_regenerates_missing_deliverable_and_reverifies`), 재생성 불가 상황 → 보류·FAIL·최종 확정 차단, 복구 후 재검증 PASS(`test_auto_fix_limit_turns_into_human_review`).

## 5. 게이트 정책 (코드 판정, `GateEvaluation` 기록)

| 게이트 | 판정 범위 | 규칙 |
|---|---|---|
| Gate 0 문서 추출 품질 / Gate 1 요구사항 완전성·독립 검증 | 기존(Phase 2) | 변경 없음. Gate 5는 제안 단계에서 두 게이트가 FAIL/미평가면 FAIL |
| Gate 2 기술적 구현 가능성 | QA-TECH-*, QA-CON-06 | 필수 FAIL → FAIL, 검토 필요 있으면 NEEDS_HUMAN_REVIEW, 아니면 PASS |
| Gate 3 WBS·일정·공수 일관성 | QA-CON-03/04/05 | 동일 |
| Gate 4 산출물 생성·파일 무결성 | QA-FILE-*, QA-CON-02 | 동일 |
| Gate 5 최종 독립 QA | 전체 | 필수 FAIL → FAIL. 그 외는 항상 NEEDS_HUMAN_REVIEW(사람 승인 필요). **최종 확정(`run_finalize`)은 Gate 5 PASS(사람 승인 포함)에서만** 가능하며, 필수 검증 실패가 있으면 승인할 수 없다 |

## 6. 테스트 범위 대응

| 범위 | 테스트 |
|---|---|
| 단위·통합·문서 생성·SDK/MCP 연결 | 기존 206건 유지(gate4→gate5 전환 반영) |
| 제안 단계 전체 흐름 | `test_proposal_full_flow_independent_qa_gates_and_finalize`: 추출→요구사항→검증→생성→통합 QA 30건→Gate 5 승인→최종본 9건 |
| 구축 단계 전체 흐름·변경 승인·반려·변경 후 정합성 | `test_build_full_flow_change_approve_reject_and_post_change_qa`: 적재→CR 승인 반영→CR 반려→통합 QA(QA-CON-07 PASS)→이력 불일치 주입 시 FAIL |
| 파일 생성 실패 복구 | `test_generation_failure_recovery`: 생성기 예외→단계 failed·부분 기록 없음→복구 후 재생성·QA PASS |
| 프로젝트 간 데이터 격리 | `test_project_isolation`: 같은 ID 체계의 두 프로젝트, 변경·산출물·보고서가 서로 섞이지 않음 |
| 경로·권한 | `test_path_and_permission_checks`: 경로 탈출 거부, 타 프로젝트 폴더를 가리키는 산출물 → QA-FILE-09 FAIL·Gate 4 FAIL |
| 게이트 정책 | `test_mandatory_failure_blocks_final_state`: 필수 실패→FAIL, 비필수 실패→검토 필요 |
| 에이전트 검토 | `test_agent_review_is_advisory_only`: 에이전트 'fail'이 코드 판정을 바꾸지 않음, 실패 시 미실행 기록 |
| 회귀 | `pytest -q` 전체 + `scripts/run_regression.py` |

## 7. 주요 발견 사항(데모 실행)과 미해결 위험

- 제안 데모의 검토 필요 5건: 의무 표현 블록 1건 미연결(RFP-01), 평가 기준 요구사항 없음(RFP-05), 기술 조사 미실행(TECH-01), 근거 조사 없는 기술명 'HTML5 브라우저'(TECH-06), 발표용 PPT '미정' 13회(CON-08). 모두 사람 판단이 필요한 항목이며 자동 통과시키지 않았다.
- 미해결 위험: R-31(키워드 기반 RFP 검사 한계), R-32(자동 수정은 재생성뿐), R-33(기술 조사 없으면 Gate 2가 항상 검토 필요). 실제 LLM 기반 조사·검토는 크레딧 확보 후 실행해야 한다.
- 승인 필요 항목: 각 보고서 9절에 열거(검토 필요 항목 + Gate 5 사람 승인).

## 8. 최종 판정

- 코드·테스트: 통과(215 passed, ruff/mypy 통과). 병합 가능.
- 데모 프로젝트 2건의 통합 QA 판정: 모두 **NEEDS_HUMAN_REVIEW** (필수 검증 실패 0건, 사람 승인 대기). 실행하지 않은 검사(에이전트 검토, 실제 LLM 호출)는 통과로 표시하지 않았다.
