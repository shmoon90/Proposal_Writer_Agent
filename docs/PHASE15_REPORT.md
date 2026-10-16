# Phase 15 보고서 — WBS(상세·약식·간트)와 인력 투입계획 양식, planner 수행 조직·마일스톤 (2026-10-16)

요청: 고객이 제공한 개발 일정 계획(상세 WBS)·보고용 일정 계획(약식 WBS)·월별 투입계획 샘플(실과제 자료, 저장소 밖 보관·공개 금지)을 참고해, WBS는 **개발용 상세 WBS와 보고용 약식 WBS를 한 파일의 시트로 분리**하고 개발 조직·개발 항목·개발자·계획/실제 시작·종료일·진척율·간트 차트를 포함하며, 인력 투입계획은 **수행 조직·구성원·등급·월별 공수·합계(월별·사람별)** 를 담도록 계획 수립 모듈과 에이전트를 수정한다.

샘플 구조 분석(식별 정보 없음)은 [WBS_STAFFING_ANALYSIS.md](WBS_STAFFING_ANALYSIS.md)에 있다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| WBS 한 파일, 상세+약식 | **WBS(상세)** 25열: 식별(WBS ID·상위·구분·단계) · 개발 항목(Task 명·상세·수량·요구사항 ID·산출물) · 담당(**개발 조직·담당 역할·개발자**) · 일정(**계획/실제 시작·종료일**·기간·**진척율(%)**·진행 상태) · 공수(M/D·산정 근거) · 관계(선행·후행·업무 유형) · 비고 + 오른쪽 **주 단위 간트**(1행 월 YYYY-MM 병합, 2행 월 내 주차; 단계 진한 파랑·활동 파랑·작업 연파랑·진척 녹색·마일스톤 주황 ◆). **약식WBS(보고용)**: 구분·단계·항목·시작일·종료일 + 같은 간트, 첫 행 `사업관리/마일스톤`에 착수·착수보고·중간보고·완료보고·종료 라벨, 구분·단계 세로 병합. 의존관계·산정근거 시트 유지, 별도 '간트' 시트 제거 | `generators/excel/wbs_gantt.py` (`week_starts`·`write_week_header`·`read_week_header`·`gantt_first_col`·`span_weeks`) |
| 기준 데이터 | `WBSItem`에 `category(구분)`·`organization(개발 조직)`·`assignee(개발자)`·`quantity(수량)`·`progress_pct(진척율)`·`milestone` 추가. `StaffRole.members`와 `member_names()`(인원 수만큼 `역할N` 자리표시) | `models/planning.py` |
| 마일스톤 | planner 초안 `milestones[{name, timing}]`(start / mid / end / after:<code> / ±Nw) → 코드 `0`(사업관리) 아래 공수 0·1일 항목으로 저장하고 날짜를 계산. 에이전트가 주지 않으면 기본 5개(검토 메모). 덱 일정 도식에서는 제외 | `planning/service.py`(`milestone_date`, `_milestone_items`), `generators/pptx/decks.py` |
| 수행 조직 | planner 초안 `team[{organization, role, grade, name, headcount, skills, duties}]` → `StaffRole`(조직·등급·인원·구성원·담당). 월 최대 부하로 계산한 필요 인원보다 적으면 검토 메모, 배분 없는 역할도 행으로 유지 | `planning/service.py`, `agents/schemas.py`(`TeamMemberDraft`·`MilestoneDraft`·`WbsItemDraft` 확장), `agents/prompts/planner.md` 규칙 7~9 |
| 투입계획 양식 | **투입계획**(구성원별): 조직·역할·구성원·기술 등급·담당 업무·투입 시작/종료월·월별 공수(MM)·계(MM, `SUM` 수식)·비고 + 하단 **합계 행**(월별 SUM·총계). 역할 월별 MM을 구성원 수로 균등 분배(`split_members`, 합계 보존), 월 최대 1.0 MM 초과 행에 인원 추가 검토 메모. **역할요약**: 옛 투입계획 열(인원·단가 입력·비용 수식). 공수요약·월별투입 유지 | `generators/excel/staffing_plan.py` |
| 고객 양식 재적재 | WBS ID가 없는 고객 상세 WBS(구분·항목(병합)·세부·수량·담당 + 주 단위 채움)는 병합 셀을 아래로 채우고 **구분(1) > 단계·항목(1.1) > 세부(1.1.1)** 코드를 발급(경고). '항목' 병합 머리글 옆 머리글 없는 열을 세부 항목으로 인식. 동의어: 구분·개발 항목·세부 항목·개발 조직·개발자/담당·수량·진척율·구성원·계(MM) 등. 월별 투입계획의 반복 역할 행을 묶어 인원·구성원·등급·기준 MM 적재. 선언한 문서 종류와 다른 구조로 보여도 그 종류로 간주해 매핑을 제안(확인 필요) | `ingest/excel_reader.py`, `changes/baseline_service.py`(`_synthesize_codes`, `_load_roles`) |
| QA | QA-FILE-08(간트 ↔ 일정)을 WBS 시트 내장 간트(머리글에서 주 월요일 복원 → 기준 데이터 날짜·채움 구간 대조)와 약식WBS 날짜 대조로 재작성. 필수 시트·컬럼 목록 갱신(WBS·약식WBS·투입계획·역할요약) | `validation/independent_qa.py`, `validation/deliverables.py` |
| 수동 대행 스크립트 | planner 초안에 team(PL·프런트엔드·백엔드·QA)·milestones 추가 | `scripts/run_manual_agents.py` |

## 2. 실제 확인 결과

- pytest **253 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase15_wbs_staffing.py` 4건: team·milestones·구분/조직/개발자/수량 반영(마일스톤 날짜 start/after/end), WBS 파일(묶음 머리글·간트 주 복원·작업/단계 채움색·◆ 마일스톤·약식 병합·라벨·간트 시트 없음), 투입계획(구성원 행·계/합계 수식·2명 분배 합 = 역할 월별 MM·자리표시 메모·`split_members`), 고객 양식(WBS ID 없음 → 코드 발급·담당/수량 적재, 월별 투입계획 역할 묶음). 기존 테스트는 WBS 머리글 행(2행)·간트 열·투입계획/역할요약 시트·마일스톤 수로 조정. `ruff check/format`, `mypy src` 통과.
- 실샘플 재검증(저장소 밖 고객 템플릿 2종 + 계산기 RFP, API 키 없이 대행 응답): WBS 파일 `WBS`(30행·38열: 25열 + 간트 13주)·`약식WBS`(마일스톤 행 + 13행)·의존관계·산정근거, 투입계획 `투입계획`(구성원 4행 + 합계 행, 계·합계 수식)·`역할요약`·공수요약·월별투입. 통합 QA **35항목 중 34 실행·30 통과·0 실패·4 검토 필요**(기술 조사 위험·미확인 3, QA-TECH-07 1)·1 미실행(QA-RFP-07), gate3·gate4 PASS, gate2·gate5 NEEDS_HUMAN_REVIEW. QA-FILE-08(간트 ↔ 일정) 통과.
- 고객 WBS·투입계획 원본은 분석에만 썼고 저장소·문서에 식별 정보를 넣지 않았다(커밋 전 민감 용어 검사 통과).
- 실제 Claude 모델로 `planner`를 실행한 결과는 없다(크레딧 부족). team·milestones는 FakeAgentRunner와 수동 대행 응답으로만 검증했다.

## 3. 한계·다음 작업

- 구성원별 월별 공수는 역할 배분을 인원 수로 **균등 분배**한 값이다. 개인별 투입 비율(예: 0.5 MM 겸임)은 사람이 투입계획 시트에서 조정해야 하며, 조정값을 기준 데이터로 되읽는 기능은 없다.
- 개발자 이름·실제 시작/종료일·진척율은 제안 단계에서 빈값/0이며 구축 단계에서 사람이 갱신한다. 재적재 시 진척율·개발자는 읽지만 간트 셀의 메모 텍스트는 읽지 않는다.
- 날짜 없는 고객 상세 WBS(주 단위 채움만)는 코드만 발급하고 일정은 비워 둔다(연도를 알 수 없음). 구축 단계 변경 영향 계산에는 날짜가 있는 보고용 WBS 또는 날짜 열이 있는 문서를 쓰는 편이 정확하다.
- 마일스톤 기본값(착수·착수보고·중간보고·완료보고·종료)은 고객 보고 체계와 다를 수 있다. 에이전트가 `milestones`를 주거나 사람이 코드 `0.n` 항목을 고쳐야 한다.
