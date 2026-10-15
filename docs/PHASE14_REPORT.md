# Phase 14 보고서 — 요구사항 정의서·추적표 양식, 요구사항별 구현 방안 자동 작성, 문맥 기반 변경 비교 (2026-10-15)

요청: 고객이 제공한 요구사항 정의서 2건·요구사항 추적표 1건(실과제 자료, 저장소 밖 보관·공개 금지)의 형식·내용·구조를 파악해 정의서·추적표 작성 모듈과 에이전트를 수정한다. 기존 정의서에 **구현방안이 기술되지 않았던 문제**를 고쳐 요구사항마다 구현 가능한 방안을 제안서보다 간략하게 자동 작성하고, 구축 단계 변경 시 **단순 문자열 비교가 아니라 문맥을 검토**해 추가·변경·삭제와 구현 난이도에 따른 공수·일정 변경의 기준 문서가 되게 한다. 샘플의 색과 추가 항목을 고려해 컬럼을 구성한다.

샘플 구조 분석(식별 정보 없음)은 [REQUIREMENT_DOCS_ANALYSIS.md](REQUIREMENT_DOCS_ANALYSIS.md)에 있다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| 정의서 양식 | 표지 → 개정이력 → 요구사항목록 → 기능/비기능/제약·평가·제출 본문 → 변경이력 → (변경관리대장) → 작성가이드. 본문은 **묶음 머리글(1행, 묶음별 색) + 컬럼 머리글(2행) + 데이터(3행~)** 31열: 식별(No·요구사항 ID·RFP 고유번호·대분류·중분류·명) · 요구사항 내용(상세·유형·출처·RFP 원문 근거) · 구현 방안(**구현방안·구현 난이도·난이도 근거·구현 근거(조사·출처)·검증 방법·검사 기준**) · 수용·우선순위(수용여부·중요도·필수·범위·검토/검증 상태) · 변경 정보(변경여부·내용·일자·근거·추가 요청자·추가일) · 협의·비고(검토 및 협의 내용·연결 산출물·비고). 변경 상태별 행 색(추가=연녹, 변경=연노랑, 삭제 요청=연주황, 삭제=회색+취소선), 같은 RFP 번호 묶음 교대 띠, 목록 유효성(수용·난이도·중요도·검증 방법·변경여부·중분류), 틀 고정·필터·인쇄 제목 행 | `generators/excel/requirement_spec.py`, `style.py`(`write_grouped_table`, `add_cover_sheet`, `add_revision_sheet`, `add_guide_sheet`, `find_header_row`) |
| 추적표 양식 | 표지 → 개정이력 → 추적표 → 검사기준(비기능) → 테스트상세 → 미추적 → 작성가이드. 추적표 25열을 요구사항(연파랑) → 수용(연주황) → 설계(화면·구성 요소·담당 역할, 황갈) → 구현(WBS·Task·단위테스트, 진황갈) → 테스트(통합테스트, 보라) → 검사 기준(판정 기준·완료여부, 연녹) → 검토 묶음으로 재구성. 비기능은 요구 내용·구현 내용·검사 기준·수행 결과 시트 | `generators/excel/trace_matrix.py` |
| 구현 방안 자동 작성 | 새 에이전트 **`approach_writer`**(WebSearch/WebFetch 허용): 요구사항 20건 묶음마다 구현방안(글머리 2~5줄·300자 내외)·난이도(상/중/하)·난이도 근거·검증 방법·검사 기준·근거 조사 ID·새 출처를 쓴다. 새 출처는 조사 기록(`TechnologyResearch`)으로 저장해 조사 선행 원칙(QA-TECH-07)과 잇는다. 에이전트가 빠뜨린 항목은 **조사·구성 요소·기술 선택 데이터만으로 규칙 초안**을 만들어 `[자동 초안]`으로 표시하고, 사람이 쓴 방안(`approach_source=user`)은 덮어쓰지 않는다. 산출물 생성 전에는 빈 항목을 규칙 초안으로 채워 정의서의 구현방안 칸이 비지 않게 한다. 조사 단계의 한 줄 채움도 글머리로 정규화하고 `research` 출처로 표시 | `requirements/approach.py`, `requirements/difficulty.py`, `agents/prompts/approach_writer.md`, `agents/schemas.py`(`ApproachReport`), `agents/roles.py`, `orchestrator/runner.py`(`run_approach_writing`, `run_generation`), `services/pipeline_service.py`(단계 `impl_approach`), `research/service.py` |
| 기준 데이터 | `Requirement`에 `approach_source`·`approach_basis`·`difficulty`·`difficulty_basis`·`acceptance_criteria`·`business_area`·`review_notes`·`related_requirement_ids` 추가(JSON 저장, 마이그레이션 불필요). `Difficulty` 열거(상/중/하, 공수 가중치 0.7/1.0/1.4), `RequirementCategory.label/from_label`, `Priority.label` | `models/enums.py`, `models/requirement.py`, `requirements/service.py` |
| 문맥 기반 변경 비교 | `context_delta(before, after)`가 주체·행위·수치 조건·화면·품질 조건·연계·데이터·입출력·규칙·범위 관점으로 **문맥 차이**를 내고, `change_difficulty`가 요구 텍스트·분류·관점 수·기존 난이도로 변경 난이도를 산정한다. 후보(`ChangeCandidate`)에 `change_aspects`·`difficulty`·`difficulty_basis` 추가, 근거 문장에 "문맥 차이: …" 표기. 공수 추정은 **변경 비율(유사도 + 관점 수) × 난이도 가중치**, 신규 Task도 난이도 가중. `semantic_differ` 에이전트가 `change_aspects`·`difficulty`·`effort_hint`를 내면 코드가 우선 반영. 변경관리대장에 '변경 관점(문맥)'·'구현 난이도' 열, 반영 시 추가 요구에 난이도·규칙 초안, 변경 요구에 난이도 갱신·구현 방안 재검토 메모 | `changes/semantic.py`, `changes/impact.py`, `changes/service.py`, `models/change.py`, `agents/prompts/semantic_differ.md` |
| 고객 양식 재적재 | 동의어 확장(분석 요구사항ID, 요구사항 해결 방안/구현내용, 대분류/중분류/Level1·2, 난이도, 검사·판정 기준, 고유번호, 변경여부, 검토 및 협의 내용, 화면/보고서ID, 단위/통합테스트케이스ID, 완료여부 …), 제목 행·묶음 머리글 아래 컬럼 행 자동 탐색, 수용여부에 사유가 붙은 값(`일부제외 - 제외: …`)·`협의중`·`이관` 해석, 유형(성능/품질/보안/시스템…)→비기능, 정의서 '요구사항목록' 요약 시트·표지·개정이력·작성가이드·검사기준(비기능) 시트 제외, 추적표 판정 기준을 정의서 검사 기준으로 보존 | `ingest/excel_reader.py`, `changes/baseline_service.py` |
| QA | **QA-CON-09** 요구사항 정의서 구현 방안·난이도(수용된 구현 대상 요구마다 구현 방안·난이도·검사 기준이 기준 데이터와 파일에 있는가; 빈 구현 방안은 실패, 규칙 초안·난이도 미기재는 검토). QA-TECH-07은 규칙 초안을 '구현 방안 미확정'으로 검토. 파일 검사는 머리글 행을 자동 탐색. 총 **35항목** | `validation/independent_qa.py`, `validation/deliverables.py` |
| UI | 에이전트·조사 화면에 '구현 방안 작성(에이전트)' 버튼과 빈 항목 수, 요구사항 편집 폼에 구현 난이도·검사 기준(구현 방안을 직접 고치면 `user`로 표시되어 보존) | `ui/app_pages/agents.py`, `requirements.py` |
| 수동 대행 스크립트 | `approach_writer` 대행 응답(사람 작성, 요구사항 이름 키워드 매칭)과 단계 호출 | `scripts/run_manual_agents.py` |

## 2. 실제 확인 결과

- pytest **249 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase14_requirement_docs.py` 6건: 정의서 묶음·색·변경 행·목록·가이드, 추적표 묶음·비기능 시트·미추적, 에이전트 작성+규칙 초안+사람 작성 보존+조사 기록 생성+QA-CON-09, 규칙 초안·난이도 추정, 문맥 차이·난이도 가중 공수, 고객 양식(제목 행·묶음 머리글·동의어) 정의서·추적표 재적재. 기존 테스트는 머리글 행(2행)·단계 수(14)·역할 목록·변경관리대장 열 위치·QA 실행 수(33)로 조정. `ruff check/format`, `mypy src` 통과.
- 실샘플 재검증(저장소 밖 고객 템플릿 2종 등록, 계산기 RFP, API 키 없이 대행 응답): 구현 방안 **12건 에이전트 작성·0건 규칙 초안**(평가·제출 조건 제외), 정의서 31열·추적표 25열 생성, 통합 QA **35항목 중 34 실행·30 통과·0 실패·4 검토 필요**(기술 조사 위험·미확인 3, QA-TECH-07 근거 조사 없음 1)·1 미실행(QA-RFP-07), gate3·gate4 PASS, gate2·gate5 NEEDS_HUMAN_REVIEW. QA-CON-09 통과.
- 고객 정의서·추적표 원본은 분석에만 썼고 저장소·문서에 식별 정보를 넣지 않았다(`.sensitive-terms.local` 43개 용어로 커밋 전 검사 통과).
- 실제 Claude 모델로 `approach_writer`·`semantic_differ`를 실행한 결과는 없다(크레딧 부족). FakeAgentRunner와 수동 대행 응답으로만 검증했다.

## 3. 한계·다음 작업

- 규칙 초안(`[자동 초안]`)은 조사·구성 요소·분류 골격으로 만든 문장이라 **설계 판단이 아니다**. QA-CON-09·TECH-07이 검토 항목으로 올리고 사람이 확정해야 한다. 에이전트 작성본도 조사 근거(출처)가 없으면 `unknown`으로 남는다.
- 난이도 규칙 추정은 단어·수치·분류 신호 기반이다. 에이전트 판단이나 사람 입력이 있으면 그것이 우선하며, 공수 가중치(0.7/1.0/1.4)는 설정값이 아니라 코드 상수다(필요 시 조정).
- 문맥 비교는 단어 집합(주체·행위·수치·화면·연계·데이터·입출력·규칙) 차이로 관점을 잡는다. 동의어·문장 구조 변화는 `semantic_differ` 에이전트가 보완해야 하며, 실제 모델 실행 후 프롬프트 보정이 필요하다.
- 샘플에 있던 '이관 합의 정보'(이관팀·고객 부서·확정 증빙·개발 담당자)는 컬럼으로 넣지 않았다(기준 데이터에 대응 필드 없음). 필요하면 다음 단계에서 추가한다.
- 다음 샘플 예정: WBS·인력투입계획. 같은 원칙(저장소 밖 참고, 구조만 기록)으로 진행한다.
