# 통합 개발 지시문 단계 5 보고서 — 기준선·변경 관리 (2026-10-16)

범위: `workspace/IMPLEMENTATION_PLAN.md` 단계 5(①~⑥), 승인 A-5(수정 문서 비교 우선순위). A-6(실제 모델 1회 검증) 은 크레딧이 없어 수행하지 못했다(미검증으로 기록). 브랜치 `feature/major-revision`.

## 1. 무엇을 만들었나

| 항목 | 구현 | 위치 |
|---|---|---|
| ① 회의록·인터뷰·질의응답 구조화(§10.1) | 회의록 문서(`MEETING_NOTE`) → **규칙 추출**(줄 머리 표지 `결정:/요청:/미결:/조치:/위험:/의견:`, 담당·기한·요구사항 ID 인식) + **에이전트 보강**(`meeting_analyzer`, 스키마 `MeetingNoteReport`: 고객 요청/내부 의견/공식 결정/미결 질문/조치 항목/위험으로 분류, 권한·날짜·담당을 추정하지 않음) → 전부 `Decision`(DEC-nnn, **제안 상태, 권한 미확인**) 으로 기록. 같은 제목은 병합. | `decisions/service.py`(`extract_meeting_items`, `DecisionService.structure_meeting`), `agents/prompts/meeting_analyzer.md`, `agents/roles.py`, `agents/schemas.py` |
| ① 사람 확정·권한 규칙(§10.2) | `confirm_decision`: **공식 결정이 아니면 승인 불가, 결정 권한이 확인되지 않으면 승인 불가, 승인자 필수**. 승인된 공식 결정(`is_binding`)만 변경 요청으로 전환(`decision_to_change_request`, CR.`decision_ids`). 기한 지난 미결·조치 항목 조회(`overdue_items`). | `decisions/service.py`, 화면 `ui/app_pages/decisions.py` |
| ② 기술 협상·계약 변경(§10.3) | `Negotiation`(NEG-nnn: 변경 전/후·사유·계약/일정/비용 영향·고객 합의·승인자). **고객 합의 확인 + 승인자가 있어야 '합의'**, '반영' 상태는 사람이 설정할 수 없고 변경 요청 반영 시 코드가 기록. 합의된 협상만 변경 요청으로 전환(CR.`negotiation_id`), 승인 조건에 협상 상태 재검사. | `decisions/service.py`(`create_negotiation`·`settle_negotiation`·`negotiation_to_change_request`), `changes/service.py`(`approval_blockers`·`_mark_negotiation_applied`) |
| ③ 수정 문서 비교(§11.1, A-5) | 첨부 종류별 비교: **정의서 Excel** 은 ID 기준으로 행을 대조해 **문구만 변경 / 의미 변경 / 화면 이동 / 추가 / 삭제 / 변경 없음**(`change_kind`) 으로 분류(신뢰도 0.9, 문구만 변경은 확인 불필요). **PPT·Word** 는 텍스트를 쪼개 규칙 분류하되 `uncertain=True`·신뢰도 상한(0.6/0.7)·사용자 확인 필수. 비교 근거(`compare_source`)를 후보에 남김. AI 의미 비교 에이전트에 `change_kind` 출력 추가, 후보 순서로 항목을 넘겨 문서 비교 후보와 정렬. | `changes/compare.py`, `changes/service.py`(`create_request`·`_document_candidates`·`analyze`·`_overlay_agent`), `models/change.py` |
| ④ 변경 상태 8종(§11) | `ChangeStatus` 8종: **분석 대기 → 분석 완료 → 승인 대기 → 승인(반영 중) → 기준선 반영**, 반려·철회·반영 오류. '승인 대기'는 후보가 전부 결정되고 영향 분석이 정상일 때 코드가 전이. `label`·`order`·`CHANGE_STATUS_FLOW`. | `models/enums.py`, `changes/service.py`(`decide_candidate`) |
| ⑤ 영향 분석 확장(§11.2) | `ChangeImpact` 에 화면·단위/통합 테스트(추적표), API·DB 테이블·설계 항목·테스트케이스(연결 엔티티의 `related_requirement_ids`), **보안 검토 필요·사유**(보안 표현, 품질/연계/데이터 관점 변화, API·DB 영향). | `changes/service.py`(`_extend_impact`), 화면 영향 상세 |
| ⑥ 선택 재생성·회귀 | 승인 시 재생성할 산출물 종류를 고를 수 있음(`regenerate_kinds`, 나머지는 이전 버전 유지). 변경 후 통합 QA 실행 뒤 **직전 QA 와 통과·실패·검토 차이를 비교**해 실패가 늘면 경고. | `changes/service.py`(`regenerate(kinds=)`), `ui/app_pages/changes.py` |
| QA | **QA-CON-14 결정·협상 ↔ 기준선 반영 통제**(총 **55항목**): 권한 미확인 승인 결정·승인자 없는 승인·합의 없는 '반영' 협상·승인되지 않은 원천을 가리키는 변경 요청은 실패, 기한 경과 미결·조치는 검토. 두 모드 공통. | `validation/qa_checks/consistency.py`(`_decision_control_issues`), `qa_checks/common.py`·`qa_service.py` |
| 화면·스크립트 | 새 화면 '회의·결정·협상'(회의록 등록·구조화·확정·협상·전환·현황 Markdown). 변경 관리 화면: Excel/PPT 첨부, 변경 종류·비교 근거·불확실 표시, 영향 확장, 선택 재생성, 회귀 비교. 대행 스크립트: 샘플 회의록 등록 → 구조화(규칙 + 대행 에이전트) → 공식 결정 1건 승인(권한 확인). | `app.py`, `ui/app_pages/*.py`, `scripts/run_manual_agents.py` |

## 2. 확인 결과

- pytest 324 passed, 1 skipped(전체, llm 제외; 단계 4 대비 +8: 신규 tests/unit/test_stage5_change_control.py — 회의록 규칙 추출(종류·담당·기한·요구 ID)·권한 미확인 승인 금지·공식 결정만 승인·승인 결정만 변경 요청 전환·기한 경과, 에이전트 보강(FakeAgentRunner meeting_analyzer, 같은 항목 병합, 권한 힌트 무시), 협상 고객 합의 통제·'반영'은 코드만·변경 요청 전환 → 분석 → 승인 대기(8종) → 승인(정의서만 선택 재생성) → NEG 반영 전이·요구사항 수정, 상태 8종·흐름·라벨, 정의서 Excel 비교(문구만/의미/삭제/추가/변경 없음·신뢰도 0.9)·화면 이동 판정, 첨부 흐름(Excel ID 비교, 영향 확장 API·화면·보안, PPT 판독 불확실·신뢰도 ≤0.6, Word ≤0.7), QA-CON-14 판정). 기존 테스트 3곳 갱신(역할 목록 +meeting_analyzer, 문서 첨부 분석 출처 ["rule","document","ai"], E2E executed 52). ruff·mypy(144 파일) 통과. 민감 용어 검사 통과.
- 계산기 샘플(모의 에이전트, 렌더링): 회의록(7줄 표지) 등록 → 구조화 6건(규칙 7건 + 대행 에이전트 6건을 제목·근거 문장으로 병합; 병합 전에는 11건으로 중복이 남아 근거 문장 비교를 추가) → 공식 결정 DEC 1건을 권한 확인으로 승인. QA 55항목 중 52 실행·44 통과·0 실패·8 검토(단계 4 대비 통과 +1 = QA-CON-14 PASS, 검토 항목 동일).
- 실제 고객 RFP(저장소 밖 fixture·템플릿 2종): 회의록 구조화·결정 승인 동일. QA 55 전부 실행·48 통과·0 실패·7 검토(단계 4 대비 통과 +1, gate4 PASS). QA-CON-14 PASS(권한 미확인 결정은 '제안' 상태로만 남아 실패 없음).
- 구축 모드 시나리오는 단위 테스트로 검증(실샘플은 제안 모드): 수정 정의서 Excel(명칭만 변경·수치 변경·행 삭제·새 행) → 후보 분류 6종, 수락·승인 → 기준선 반영·Revision·정의서만 재생성, 협상 NEG-001 합의 → CR → 반영 시 NEG '반영' 전이.
- 미검증: 실제 Claude 모델(A-6) — meeting_analyzer 가 논의 사실과 결정을 실제로 구분하는지, semantic_differ 의 change_kind 판단 정확도. 화면(회의·결정·협상, 변경 관리 확장)은 Streamlit 을 띄워 보지 않고 코드·타입 검사만 했다.

## 3. 남은 것·다음 단계

- 회의록 구조화의 규칙 추출은 줄 머리 표지가 있을 때만 잡는다. 표지 없는 자유 서술 회의록은 에이전트(실모델 미검증, A-6)에 의존한다.
- PPT·Word 수정본 비교는 텍스트 판독이라 설계상 불확실로만 표시하며(A-5), 표·도형 안 문구 순서가 바뀌면 추가·삭제로 오인할 수 있어 사용자 확인을 요구한다.
- 영향 분석 확장의 API·DB·설계 항목·테스트케이스 열은 단계 6·7에서 엔티티가 채워져야 값이 나온다(지금 실샘플은 비어 있음).
- 회귀 비교는 직전 QA 실행과의 건수 차이만 본다. 항목별 차이(어느 항목이 새로 실패했는지)는 단계 8 통합 품질에서 보강.
- 다음: 단계 6(화면·DB·API 설계 — 코드 생성 입력 규격 깊이, 발주처 문맥 주입, 구현 방안 구체성 검사; D-21·D-22).
