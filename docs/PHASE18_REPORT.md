# Phase 18 보고서 — 목차·전략 브리프와 Gate P(목차·전략 승인) (2026-10-16)

[개선 계획](IMPROVEMENT_PLAN_2026-10.md) 18단계. 요청서 §4(목차·전략 수립 단계에서 사용자 승인)에 해당한다. **브리프 형식과 승인 화면은 사용자 확인 대상이다.**

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| §4 브리프 10항목 | 새 역할 `strategy_planner` → `StrategyBrief`: ① RFP 분석 요약 ② 요구사항별 중요도 ③ 대응 방향(`requirement_directions`) ④ 제안서 목차 초안(`toc`, RFP 지정 목차 보존·`rfp_mandatory`·`toc_change_requests`) ⑤ 전략 3~5 ⑥ 차별화 근거·근거 구분(`strategies[].differentiator/evidence`) ⑦ 핵심 기술·구현 방향(`key_technologies`, 조사 근거) ⑧ 위험·대응(`risks`) ⑨ 제출용/발표용 구성 차이 ⑩ 자료 부족·확인 필요(`open_questions`). 프롬프트는 RFP 목차 보존·근거 없는 수치 금지·비전문가 용어 설명을 요구 | `agents/schemas.py`, `agents/roles.py`, `agents/prompts/strategy_planner.md` |
| §4 승인 흐름 (Gate P) | `StrategyService.run`: 브리프 작성 → Markdown(`07_Submission_Proposal_PPT/전략브리프_vX.Y.md`) 저장 → **Gate P 평가(항상 사람 승인 대기)**. 코드 점검 사유: RFP 지정 목차 장 보존 여부·전략 수(3~5)·목차 변경 요청·확인 필요 건수. 승인/반려는 기존 Approval 기록(`GateService.approve_human_review/reject_human_review`). 반려 사유는 `<reviewer_comments>`로 재작성에 반영. 브리프 없이도 평가를 만들어 승인할 수 있으나 사유에 남는다 | `services/strategy_service.py`, `orchestrator/gates.py`(`gateP`), `orchestrator/runner.py`(`run_strategy_brief`), `services/pipeline_service.py`(단계 `strategy_brief`, 15단계) |
| §4 승인 전 차단 | `run_proposal_writing`(전체 문안)·`run_finalize`(최종 확정, 제안 단계)는 Gate P 통과 필수. `run_generation`은 **시안**으로 허용되며 검토 메모를 남김 | `orchestrator/runner.py` |
| 목차 반영 | RFP 지정 목차가 없으면 브리프 목차를 **제출용 덱 뼈대·제안 문안 브리프(`<rfp_toc>`)** 로 사용(발표용은 기본 장 구성 유지). 브리프 절 중 기준 데이터에 없는 절은 "사람 작성 필요" 자리표시 슬라이드가 되며 제안 문안 에이전트가 채운다 | `generators/pptx/outline.py`(`brief_toc_tree`), `generators/service.py` |
| QA | **QA-RFP-08 목차·전략 승인(Gate P)**: 승인이면 통과(브리프 없이 승인 시 검토 메모), 미승인이면 검토 필요, 반려면 실패. 총 **36항목** | `validation/independent_qa.py`, `validation/qa_service.py` |
| UI | 산출물 화면에 "목차·전략 브리프 (Gate P)" 패널: 브리프 작성 버튼, 상태·평가 사유, 브리프 내용(Markdown), 검토 의견, **검토 후 Gate P 승인** / **반려(수정 요청)**. '제안 문안 작성' 버튼은 Gate P 승인 후 활성화 | `ui/app_pages/deliverables.py` |
| 기타 | 브리프 프롬프트는 `build_context`를 쓰지 않는다(계획·구성 요소 기본값을 저장하는 부작용 제거). 템플릿 장 라벨 상자보다 긴 장 제목은 글꼴을 폭에 맞춰 줄임(넘침 방지). 수동 대행 스크립트에 브리프·Gate P 대행 승인 추가 | `services/strategy_service.py`, `generators/pptx/template.py`, `scripts/run_manual_agents.py` |

## 2. 실제 확인 결과

- pytest **265 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase18_strategy_gate.py` 3건: 브리프 작성 → Gate P 검토 대기 → 문안 작성 차단 → 승인 후 해제(조사 선행 규칙으로 넘어감), 반려 → 의견 반영 재작성 → RFP 지정 목차 보존 검사(누락 장 사유·재작성 후 해소), QA-RFP-08 상태 전이와 브리프 목차 → 덱 뼈대 변환. 기존 테스트는 단계 수(15)·게이트 수(5)·역할 목록·최종 확정 전 Gate P 승인·QA 실행 수(34)·UI 승인 흐름으로 조정. `ruff check/format`, `mypy src` 통과.
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답·대행 승인): 브리프(목차 4장·전략 3·핵심 기술 3·위험 2·확인 필요 3) 저장, Gate P 대행 승인 후 생성·QA. 통합 QA **36항목 중 35 실행·31 통과·0 실패·4 검토 필요**(기술 조사 위험·미확인 3 + QA-TECH-07 1)·1 미실행(QA-RFP-07), gate3·gate4 PASS, QA-RFP-08 통과. 브리프 장 제목("사업 수행 방안")이 템플릿 장 라벨 상자보다 길어 생긴 넘침(QA-FILE-03)은 한글 글자 폭 기준 글꼴 맞춤으로 해소했다(22pt → 10.2pt). 제출용 덱은 브리프 목차(Ⅰ 사업 이해 / Ⅱ 사업 수행 방안 / Ⅲ 사업 관리 방안 / Ⅳ 지원 방안)를 뼈대로 쓰고, 기준 데이터가 없는 절(계산 엔진·정밀도 등)은 자리표시 슬라이드로 남았다(대행 문안이 해당 절을 쓰지 않았기 때문).
- 실제 Claude 모델로 `strategy_planner`를 실행한 결과는 없다(크레딧 부족).

## 3. 사용자 확인 요청 (승인 절차)

1. **브리프 형식**: 위 10항목 구성과 Markdown 표기(`전략브리프_vX.Y.md`)가 검토에 충분한가. 추가로 넣을 항목(예: 평가 항목별 대응, 경쟁사 비교)이 있는가.
2. **승인 화면**: 산출물 화면의 패널(작성 → 내용 확인 → 의견 입력 → 승인/반려)로 충분한가, 아니면 별도 화면·항목별 편집(목차 직접 수정)이 필요한가.
3. **차단 범위**: 승인 전 '제안 문안 작성'·'최종 확정'을 막고 '산출물 생성(시안)'은 허용하는 현재 규칙이 적절한가.

## 4. 한계·다음 작업

- 브리프 목차의 절을 사람이 화면에서 직접 고치는 기능은 없다(반려 의견으로 재작성). 필요하면 19단계에서 목차 편집 폼을 추가한다.
- 브리프 절 중 데이터가 없는 절은 자리표시로 남는다. 제안 문안 에이전트가 `<rfp_toc>`로 브리프 목차를 받으므로 실제 실행에서는 채워져야 하며, 미채움은 QA-CON-08·사람 검토로 드러난다.
- 다음: 19단계(슬라이드별 명세·기술 구체성·비전문가 표현·QA-CON-10/11).
