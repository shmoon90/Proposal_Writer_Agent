# PHASE6_REPORT — 구축 단계 변경관리(기준 적재·의미 비교·영향 분석·승인 반영·문서 갱신) 구현 보고

작성일 2026-10-15 · 브랜치 `phase/6-build-changes` → `main` 병합 · 관련: [WORKFLOW_DESIGN.md](WORKFLOW_DESIGN.md) 구축 단계, [DATA_MODEL.md](DATA_MODEL.md), [RISK_REGISTER.md](RISK_REGISTER.md) R-28~R-30

---

## 1. 실행한 검증 명령과 실제 결과

| 명령 | 결과 |
|---|---|
| `pytest -q` (sdk 포함, llm 제외) | **206 passed, 1 skipped, 2 deselected** (약 36s). Phase 6 시나리오 14건 + 보조 1건 + UI AppTest 1건 추가 |
| `ruff check` / `ruff format --check` / `mypy src` | 통과 (99 파일) |
| 스모크 (표준 Excel 4종 적재 → 자연어 CR 3항목 분석 → 수락 → 승인·반영 → 2번째 CR 같은 분에 반영) | 기준 요구사항 6건·WBS 16건 적재, CR-001: ADD/MODIFY/DELETE_REQUEST 분류, 신규 ID `SFR-006`(기존 체계) 승인 후 발급, 문서 4건 `*_202610151125.xlsx`, 2번째 반영은 `_1` 접미사. 반영 중 오류 주입 시 롤백·`error` 상태 확인 |
| 실제 LLM 호출(`semantic_differ`) | **미검증** — 크레딧 부족(R-21). FakeAgentRunner로 덧붙임·실패 시 규칙 결과만 사용하는 경로를 테스트 |

## 2. 핵심 기능과 구현 위치

| 기능 | 모듈 | 동작 |
|---|---|---|
| 기존 산출물 업로드·보존 | `services/document_service.py` (기존) | 정의서·추적표·WBS 필수, 투입계획·기타 선택. 원본은 `01_RFP_Original`에 보존, 동일 파일명은 `_1` |
| 문서 구조 분석·매핑 제안 | `ingest/excel_reader.py` | 시트 종류 판별(표준 시트명 → 동의어 적중 수 → 사용자 지정 종류 우선), 헤더 행 탐색(상위 10행), 필드별 동의어 매핑(신뢰도 1.0/0.9) → 유사도 매핑(≥0.72, **확인 필요**) → 미매핑(필수면 확인 필요). 품질 검사: 중복 ID·식별자 없는 행·날짜 형식·수식 수·필수 컬럼 누락. 손상 파일은 `IngestError` |
| 매핑 확정 | `changes/baseline_service.py` `confirm_mapping` | 사용자가 열 번호를 지정하면 `SourceDocument.column_mapping`에 `confirmed_by`·`overrides`로 규칙 제안과 구분 저장. 필수 컬럼이 미확정이면 적재 거부 |
| 기준 데이터 적재 | `BaselineService.load` | 트랜잭션 안에서 요구사항(**기존 ID 유지**, 재적재 시 이력만 추가)·추적(화면/단위/통합 테스트 레코드 생성, 검토 상태)·WBS(상위 코드·선행 업무·의존관계 시트, 공수·날짜)·역할(투입계획) 적재. `LegacyIdScheme`으로 ID 체계(`SFR-###`)를 추론해 시퀀스를 맞춘다. Revision `v1.0` + 스냅샷 JSON(`12_Revision_History/baseline_snapshot_v1.0.json`) |
| 변경 요청 UI | `ui/app_pages/changes.py` | 입력 방식: 자연어 / 추가 / 수정(선택) / 삭제(선택) / 문서 업로드. 요청자·요청일·사유·제목·첨부, 등록 전 미리보기. 후보별 결정(수락/거절), 분류 변경, 대상 ID·내용·공수·역할 입력(사용자 값은 `user_override`에 별도 저장) |
| 의미 비교·분류 | `changes/semantic.py` | 항목 분리(줄·글머리·번호) → 의도 키워드(삭제/변경/추가) + 유사도(문자 bigram Jaccard·순서·특징 겹침 + 요구사항 명 포함도; **수치 조건이 다르면 '같음' 상한 0.84**) → ADD/MODIFY/DELETE_REQUEST/NO_CHANGE/AMBIGUOUS. 근거·신뢰도·유사도·관련 ID·확인 필요·일정 제약 표현·증거 문장. 두 후보가 근소하면 AMBIGUOUS(수정·삭제 자동 결정 없음) |
| AI 덧붙임 | `agents/roles.py` `semantic_differ` + `prompts/semantic_differ.md` + `schemas.SemanticDiffDraft` | 규칙 결과를 참고 입력으로 주고 항목별 분류·근거를 받는다. 규칙과 일치 → 신뢰도 보정, 불일치 → 근거 병기 + AMBIGUOUS로 낮춤(수정·삭제는 자동 결정하지 않음). 실패 시 `unresolved`에 기록하고 규칙 결과만 사용 |
| 영향 분석 (코드) | `changes/impact.py` | 변경 전·후 계획을 같은 스케줄러로 계산(기존 Task는 `earliest_start`로 계획일 유지 → **여유가 있으면 후행이 밀리지 않음**). MODIFY: 연결 Task 공수 증가(유사도 기반 비율 0.2~0.6, 범위 ±50%) 또는 사용자 확정 공수(Task 수로 균등 분배). ADD: 유사 Task 기준 공수 중앙값(범위)·같은 상위·같은 선행, 후행(시험)이 신규 Task도 기다림, 테스트 추가 항목. DELETE: 전용 Task 제거(보류)·공유 Task는 몫만 감소·선행→후행 우회 의존. 전체 종료일 변화·과제 종료 초과·날짜 바뀐 Task·같은 Task를 쓰는 다른 요구사항·순환 시 `error`로 중단 |
| 공수·인력 | `changes/impact.py` `_staffing` | 변경 전/추가/감소/순증/변경 후 M/D + 상태(확정/추정/범위)·범위·근거·가정. 역할별 전후 MM·필요 인원. 시나리오 1(대응 가능)·2(일정 조정)·3(기간 연장)·4(새 역할)·5(상쇄)·6(투입계획 없음 → 사용자 판단). 비용은 영향 역할 모두 단가가 있을 때만 |
| 승인 흐름 | `changes/service.py` | 등록 → 분석 → 후보 결정(AMBIGUOUS는 분류·대상 지정 전 수락 불가) → `approval_blockers` 0건일 때만 승인 → `Approval(CHANGE_REQUEST)` 기록 → 반영. 반려(사유 필수)·철회는 기준 불변 |
| 반영 (트랜잭션) | `ChangeService.apply` | ADD: 기존 체계로 **승인 후 ID 발급**, `추가 요청자/추가일/변경 상태/변경 내용` 기록. MODIFY: `previous_versions`에 이전 내용 보존, 이력·버전 증가, 추적 링크 '재검토 필요'. DELETE: `change_state=deleted`로 표시(물리 삭제 없음), 링크 유지·재검토. WBS: 신규 Task 삽입·보류 표시·공수/일정 갱신·상위 롤업·새 의존 추가. 투입계획이 있으면(또는 요청 시) 월별 투입 재계산. Revision `vN.0`(변경 전 파일·CR·승인·변경 후 파일 연결) + 스냅샷. 오류 시 롤백, CR 상태 `error`(재시도 가능) |
| 문서 갱신 | `ChangeService.regenerate` | `Requirements_Definition_YYYYMMDDHHMM.xlsx`, `Traceability_Matrix_…`, `WBS_Gantt_…`, (`Staffing_Plan_…`) — 같은 이름이면 `_1`, `_2`. 정의서에 `추가 요청자·추가일·변경 상태·변경 내용` 컬럼과 **변경관리대장** 시트(CR ID·유형·요청자·요청일·사유·기존 ID·변경 전/후·근거·승인 상태/자/일·관련 산출물·일정/공수/비용 영향·결과), 추적표에 `검토 상태·변경 사유`. 생성 직후 `check_xlsx`로 열기·시트·컬럼 검사 |
| 저장 | `storage/migrations.py` 0005 `change_requests`(프로젝트 복합 PK), `models/change.py` | `ChangeRequest`(후보·영향·승인·Revision·파일 연결·사용자 편집 플래그), `Requirement`에 `added_by/added_on/change_state/change_summary/previous_versions`, `RequirementTrace`에 `review_status/review_reason`, 화면·테스트에 `code` |

## 3. 자동 테스트 시나리오 (`tests/unit/test_phase6_changes.py`, `tests/integration/test_ui_build.py`)

| # | 시나리오 | 확인 내용 |
|---|---|---|
| 1 | 표준 산출물 적재 | 원본 보존, ID 그대로(`SFR-001…SNR-001`), WBS 16·의존 7·화면 5·테스트 5/3·역할 5, Revision v1.0·스냅샷, 재적재해도 ID 불변 |
| 2 | 비표준 양식 | 제목 2줄 아래 헤더(3행), `번호/명칭/내용/구분` 동의어 매핑, 확인 없이 적재, 종류 `비기능` 판별 |
| 3 | 확신 없는 매핑 | 필수 컬럼 미매핑 → 적재 거부 → 사용자 열 지정 확정(`confirmed_by`) → 적재 |
| 4 | 손상 파일·필수 누락 | `IngestError`, 필수 문서 부족 거부, 기준 없이 CR 등록 거부 |
| 5 | 자연어 분류 | ADD/MODIFY/DELETE_REQUEST/NO_CHANGE/AMBIGUOUS, 수치만 다른 문장은 MODIFY, 다항목 분리, 근거·신뢰도 |
| 6 | 버튼 입력 | 수정·삭제 선택(여러 건), 추가 버튼 중복 감지 → AMBIGUOUS, 출처 `user` |
| 7 | 문서 업로드 + AI 덧붙임 | DOCX 발췌 → 후보, AI 일치 시 보정·불일치 시 AMBIGUOUS, AI 실패 시 규칙만 + 미해결 기록 |
| 8 | 영향: 신규 Task·여유 | 신규 Task 공수 범위·테스트 추가, 여유 5일 Task에 3 M/D 추가해도 후행·종료일 불변(확정 상태) |
| 9 | 영향: 삭제 | 전용 Task 제거, 공유 Task 1/3 감소, 영향 요구사항·의존 우회, 순증 음수 → 시나리오 5 |
| 10 | 순환 의존 | `error`로 중단, 승인 차단, 기준 불변 |
| 11 | 인력 시나리오 | 6(투입계획 없음), 4(새 역할), 3(기간 연장, 단가 없으면 비용 None), 단가 입력 시 비용 산출 |
| 12 | 승인 흐름·버전 파일 | 승인 전 불변, AMBIGUOUS 수락 거부, 승인 후 새 ID(기존 체계)·이력·이전 버전·삭제 표시·링크 재검토·보류 Task·신규 Task, Revision 연결, 타임스탬프 파일명·`_1` 충돌, 정의서 컬럼·변경관리대장·추적표 검토 상태, 반려 무변경, 대장 행 |
| 13 | 반영 오류 롤백 | 예외 주입 → 요구사항·WBS·Revision 불변, 상태 `error`, 재시도 성공 |
| 14 | 투입계획 선택 | 없으면 Staffing 문서 미생성 + 안내, 있으면 생성·월별 재계산, `update_staffing=False`로 끔 |
| UI | 구축 화면 2종 | 적재 비활성 → 구조 분석 → 적재 → CR 등록 → 분석 → 결정 → 승인 → 변경관리대장 |

## 4. 작동 원칙 (코드로 보장)

- 승인 전에는 기준 데이터(요구사항·WBS·추적·인력)를 바꾸지 않는다. 분석 결과는 `ChangeRequest` 안에만 있다.
- 사용자가 직접 입력·수정한 값(`user_edits`, `user_decision`, `user_override`, 매핑 `overrides`)과 규칙/AI 추론(`source`=rule/ai/rule+ai)은 분리 저장·표시한다.
- 새 ID는 승인 후에만, 기존 문서 ID 체계로 발급한다. 삭제는 상태 표시·이력 보존만 한다. 추적 링크는 자동 삭제하지 않고 '재검토 필요'로 둔다.
- 일정·공수·인력 수치는 모두 코드가 계산한다(에이전트는 분류·근거만). 계산 불가(순환)면 중단하고 사유를 표시한다.
- 투입계획이 없으면 인력 자동 갱신을 주장하지 않고 시나리오 6으로 사용자 판단에 맡긴다.

## 5. 미해결·제약

- `semantic_differ` 실제 LLM 경로 미검증(크레딧). 규칙 분류는 한국어 bigram 기반이라 긴 복합 문장·영문 혼용 문장에서 ADD/AMBIGUOUS 경계가 보수적이다(모호하면 사용자 확인).
- 수정 공수 추정은 유사도 비율 휴리스틱(0.2~0.6)이다. 화면에서 공수 확정값을 입력하면 '확정'으로 대체된다.
- 문서 업로드 변경 요청은 줄 단위로 항목을 나누므로 제목·머리글 줄도 후보로 올라올 수 있다(거절로 처리).
- 제안 → 구축 데이터 승계(6.7)는 이번 범위에 포함하지 않았다(제안 산출물 Excel을 업로드하면 동일 경로로 적재 가능).
- `Project.end_date`가 없으면 과제 종료 초과 여부를 판단하지 않고 안내만 한다.
