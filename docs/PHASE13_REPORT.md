# Phase 13 보고서 — 발표용 제안서 템플릿·편집 가능 도식·조사 선행 구현 방안 (2026-10-15)

요청: 발표용 제안서 샘플의 작성 형식·방법·구조를 파악하고 발표용 작성·검토 에이전트·모듈을 수정. 공통 요건으로 (1) 제출용·발표용 모두 **구현 가능한 내용**(웹 검색 기반 조사 선행)만 쓰고, (2) 화면 설계·구조·데이터 흐름·호출 절차·배경·목표를 **시각화**하며, (3) 산출 문서의 모든 요소(문자열·표·선·상자)는 **사람이 편집할 수 있어야** 한다.

샘플 분석은 [PROPOSAL_TEMPLATE_ANALYSIS.md §4](PROPOSAL_TEMPLATE_ANALYSIS.md)에 있다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| 편집 가능한 도식 | 그림(PNG) 삽입을 없애고 python-pptx 자동 도형·연결선(화살촉)·텍스트 상자·표로 그리는 모듈 신설: 카드(배경·목표·전략), 단계 흐름(절차·호출 순서), 2열 비교(현황/이슈 ↔ 방안), 데이터 흐름(노드·연결), 화면 설계(와이어프레임), 시스템 구성도(레이어·구성 요소·연결), 일정 축(월 눈금·막대), 공수 막대, 핵심 수치, 비교 표. 텍스트는 상자 용량에 맞춰 자른다 | `generators/pptx/shapes.py` |
| 덱에 적용 | 구성도 3종·간트·공수 슬라이드를 PNG 대신 도형으로 그림(PNG는 `10_Diagrams_Charts_Images`에 별도 산출). 배경·목표(목표 카드), 전략(카드), 요구사항 요약(KPI + 필수 요구 ↔ 구현 방안 2열), 위험(2열)을 시각화. 두 빌더에 `canvas_slide`/`visual_slide` | `generators/pptx/decks.py`, `builder.py`, `template.py` |
| 에이전트 도식 지정 | `ProposalSection.visual`(`VisualSpec`: kind·items·edges·headers/rows)와 `feasibility_basis` 추가. 에이전트가 지정하면 코드가 도형으로 그린다 | `agents/schemas.py`, `agents/prompts/proposal_writer.md` 규칙 10 |
| 발표용 덱 구조 | 표지 → 사업 필요성(카드) → CONTENTS → 장마다 CHAPTER 구분(로마숫자·장 제목·절 목록) → 절(리드 + 도식 + 요점 ≤5) → 핵심 메시지 → 핵심 기술 → (확인 필요 문구). 장 뼈대: 발표용 템플릿 장 → RFP 목차 → 기본 4장(사업의 이해/사업 수행 방안/성능 및 품질/사업 관리 및 지원). 발표에 맞는 섹션만 선별, 자리표시 절은 슬라이드 생략 | `decks.build_presentation_deck`, `PRESENTATION_KEYS` |
| 발표용 템플릿 인식 | 머리글 폭 15% 이상 허용, 2단 머리글은 번호 텍스트일 때만(큰따옴표 리드는 리드로), 장 표지는 로마숫자·CHAPTER 라벨 기준(인용부호·목차 슬라이드 제외), 번호 없는 절 목록, `NN/ 제목`·`(1/2)` 표기 인식 → `section_format`/`continued_format`, 1단 머리글 양식 렌더링, 절 목록 상자 선택, 자리표시자 제외 | `generators/pptx/template.py` |
| 조사 선행·구현 가능 내용 | `run_proposal_writing`은 기술 조사 기록이 없으면 거부(ValidationError)하고, 근거 조사 없는 필수 기능 요구를 감사 기록·요약에 남긴다. 브리프에 `<feasibility>`(요구사항별 구현 방안·근거 조사·구현 가능성·출처 수). 조사 결과(`impact_on_implementation`)가 관련 요구사항(내부 ID 또는 RFP ID)의 구현 방안을 "근거: 조사 …"로 채운다. 프롬프트 규칙 9: feasible/with_risk 조사 근거가 있는 것만 구체화, 없으면 "조사 후 확정" | `orchestrator/runner.py`, `generators/service.py`, `research/service.py`, 프롬프트 |
| QA | **QA-TECH-07** 기능 요구사항 구현 근거(수용된 필수 기능 요구마다 구현 방안·구현 가능 조사 연결; 미비는 검토 필요), **QA-FILE-12** 편집 가능성(생성 PPT에 그림 도형이 있으면 실패, 재생성으로 수정). 넘침 추정은 글꼴 크기 기반. 총 34항목 | `validation/independent_qa.py`, `validation/deliverables.py` |
| 에이전트 문안 보강 | 에이전트 문안이 있어도 요구사항 표·시스템 구성도·일정·인력 섹션은 코드가 보강(`ESSENTIAL_KEYS`) | `generators/pptx/outline.py` |

## 2. 실제 확인 결과

- pytest **243 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_shapes_presentation.py` 5건(도식 종류별 도형·연결선·표 생성과 그림 없음, 일정·구성도, 발표용 덱 구조·에이전트 도식 반영·QA-FILE-12/04/TECH-07, 그림 삽입 검출, 구현 근거 검토). 기존 테스트는 조사 선행(작성 전 `run_tech_research`)과 검증 항목 수(실행 32)로 조정. `ruff check/format`, `mypy src` 통과.
- 실샘플(저장소 밖, 고객 자료·공개 금지): 발표용 샘플(30.3×21.6 cm, 35장)을 프로파일링해 머리글 1단(`NN/ 제목`, top 1.1 cm), 큰따옴표 리드(top 4.06 cm, 16pt), 장 Ⅰ~Ⅴ, 표기 `{no:02d}/ {title}`·`({i}/{n})`을 인식(경고 0). 계산기 RFP에 제출용(Ⅰ장 샘플)+발표용 템플릿을 등록한 전체 흐름(마지막 수정 후 재실행 완료): 발표용 19장·제출용 18장, 그림 도형 0(모든 도식이 도형·연결선), 통합 QA 34항목 중 33 실행·29 통과·0 실패·4 검토 필요(기술 조사 미확인 3, QA-TECH-07 구현 근거 1)·1 미실행(QA-RFP-07), gate4 PASS. 발표용 덱은 템플릿 샘플의 장(Ⅰ~Ⅴ) 제목만 뼈대로 쓰고 절은 기준 데이터에서 만들며(샘플 절 내용은 복사하지 않음), 내용 없는 장은 CONTENTS에만 남긴다. TEST_RESULTS §1 참조
- 실제 Claude 모델로 proposal_writer·tech_researcher를 실행한 결과는 없다(크레딧 부족). 조사 선행 규칙과 도식 지정은 FakeAgentRunner로만 검증했다.

## 3. 한계·다음 작업

- 도식은 코드가 그리는 10종이며 샘플처럼 아이콘·사진·자유 곡선은 넣지 않는다(편집 가능성을 우선). 레이아웃은 영역 안 격자 배치라 복잡한 흐름(교차 연결)은 겹칠 수 있어 QA-FILE-04가 검토 항목으로 올린다.
- 발표용 템플릿의 장별 레이아웃(예: 3·5·9·10_사용자 지정)은 로마숫자 라벨이 없어 장과 자동 연결되지 않으며 가장 많이 쓰인 레이아웃 하나를 쓴다.
- 요구사항별 화면 설계·데이터 흐름·호출 절차는 에이전트가 `visual`로 지정해야 그려진다(기본값은 구성도·일정·공수·목표 카드만). 실제 모델 실행 후 프롬프트 보정이 필요하다.
