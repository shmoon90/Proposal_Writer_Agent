# 통합 개발 지시문 단계 3 보고서 — 제안 전략·상세 기술 검토 (2026-10-16)

범위: `workspace/IMPLEMENTATION_PLAN.md` 단계 3(①~⑤). A-6(실제 모델 1회 검증) 은 크레딧이 없어 수행하지 못했다(미검증으로 기록). 브랜치 `feature/major-revision`.

## 1. 무엇을 만들었나

| 항목 | 구현 | 위치 |
|---|---|---|
| ① 전략 항목 보강·전략 ID(§7.1·§17) | `StrategyItem` 에 발주처 문제·구현 방법·적용 기술·기대 효과(근거 있는 것만)·위험/전제·**미확인 주장** 추가, 프롬프트 규칙 3 보강. 브리프 작성 시 전략을 **`ProposalStrategy`(STR-nnn)** 로 저장(같은 제목은 버전 ↑, 빠진 전략은 dropped). `GenerationContext.strategies` 로 덱에 전달해 '추진 전략' 소절을 **전략 카드 + 표(전략 / 발주처 문제·목표 / 구현 방법·기술 / 차별성 / 기대 효과 / 근거)** 로 그리고 미확인 주장은 ※ 주석으로 표시. 문안 에이전트 소절에 전략 소절이 없으면 코드가 보강 | `agents/schemas.py`, `prompts/strategy_planner.md`, `services/strategy_service.py`(`persist_strategies`·`strategies`), `generators/base.py`·`service.py`, `generators/pptx/outline.py`·`decks.py` |
| ② 요구사항별 기술 검토 14항목(§4.1) | `RequirementAnalysis` 스키마(목적·조건·입출력·업무 규칙·흐름/예외·화면·API/연계·데이터/트랜잭션·인증/개인정보/감사·성능/확장·장애/복구·운영·난이도/의존/일정/비용 영향·테스트/수용). `ApproachItem.analysis` → `Requirement.analysis`(JSON) 저장. 프롬프트 규칙 8(필수 기능·난이도 상 요구에 작성, 가정은 `assumption:`·결정 필요는 `question:`). 요구사항 화면에 '기술 검토 14항목' 패널 | `agents/schemas.py`, `prompts/approach_writer.md`, `models/requirement.py`, `requirements/approach.py`, `ui/app_pages/requirements.py` |
| ③ 대안 비교·비기능 설계(§4.2·§8) | `AlternativeComparison{topic, options[{name, 장점, 단점, 제약, 호환성, 비용/복잡도, 위험, 성능, 적합 조건}], recommended, reason, poc_needed, poc_scope, source}` 와 비기능 설계 5항목(성능·확장 / 장애·복구 / 운영·모니터링 / 인증·보안 / 테스트·수용 기준)을 `ImplementationDesign` 에 추가(필요한 경우만 비교). 묶음 소절에 **'대안 비교' 표(항목 × 대안) + 추천·PoC·근거 글머리**, **'비기능 설계' 2열 표** 를 그린다 | `agents/schemas.py`, `prompts/design_writer.md`, `generators/pptx/req_groups.py`(`design_comparison_blocks`·`design_nonfunctional_rows`), `decks.py` |
| ④ 출처 확인 날짜(§4.3) | 조사 출처는 이미 `ResearchSource.accessed_at` 으로 저장 시각이 기록됨(코드 확인). 설계의 `TechChoice.checked_on`(YYYY-MM-DD) 추가, 적용 기술 표 근거에 `(확인 2026-10-16)` 표기 | `agents/schemas.py`, `req_groups.py` |
| ⑤ 구현 후 재검증(§4.4) | **QA-TECH-08 구현 설계 재검증**(gate2, 검토, 총 **54항목**): 설계 적용 기술이 아키텍처 구성 요소·조사 사실에 없으면 검토(자체 설계·RFP 출처 제외), 대안 비교의 추천안이 대안 목록에 없으면 실패, PoC 필요 항목 검토, 필수 기능 요구사항의 14항목 분석 누락 검토 | `validation/qa_checks/tech.py`(`_design_reverification_issues`) |
| 대행 데이터 | 계산기: 전략 1·설계 대안 비교(decimal/mpmath/BigNumber)·비기능·요구 분석 1건. 실제 RFP fixture(저장소 밖): 전략 4건 보강, 대안 비교 2건(배치 중복 방지, 표 틀고정 방식 — 세션 Claude 가 웹 검색으로 확인한 사실 기준), 비기능 설계 2묶음, 요구 분석 2건, 확인 날짜 | `scripts/run_manual_agents.py`, scratchpad fixture |

## 2. 확인 결과

- pytest 307 passed, 1 skipped(전체, llm 제외; 단계 2 대비 +4: 신규 tests/unit/test_stage3_strategy_tech.py 4건 — 전략·분석·대안 비교 스키마, STR 저장(버전 갱신·dropped), 덱의 전략 표·대안 비교 표·비기능 설계 표·확인 날짜, QA-TECH-08 판정(추천안 정합·PoC·분석 누락·조사에 없는 기술)). ruff·mypy(139 파일) 통과. 민감 용어 검사 통과.
- 계산기 샘플(모의 에이전트, 렌더링): QA 54항목 중 51 실행·43 통과·0 실패·8 검토(TECH-08: PoC 필요 1건, 14항목 분석 없는 필수 기능 요구 5건 검토).
- 실제 고객 RFP(저장소 밖 fixture·템플릿 2종): 전략 4건이 STR-001~004 로 저장되어 제출용 '제안의 특징과 장점' 소절이 전략 카드 + 표(발주처 문제·구현 방법·기술·차별성·기대 효과·근거, 미확인 주장 ※) 2장으로 그려짐; 묶음 소절에 '대안 비교'(배치 중복 실행 방지 3안, 표 틀고정 방식 3안) 표와 추천·PoC, '비기능 설계' 5항목 표, 적용 기술 근거에 '(확인 2026-10-16)' 표기 — 렌더링 PNG 로 확인. 제출용 82장. QA 54 전부 실행·47 통과·0 실패·7 검토(TECH-08: 조사 기록에 없는 적용 기술 1건·PoC 필요 1건·14항목 분석 없는 필수 기능 요구 검토).
- 미검증: 실제 Claude 모델(A-6, 크레딧 없음) — 새 프롬프트 규칙(전략 보강·14항목·대안 비교 '필요한 경우만') 준수 여부는 알 수 없음.

## 3. 남은 것·다음 단계

- 요구사항 14항목 분석은 정의서 Excel 열에는 아직 넣지 않았다(단계 4 추적표·정의서 열 확장에서 함께).
- 대안 비교는 설계 에이전트 출력에 의존하며, 실제 모델이 "필요한 경우만" 규칙을 지키는지는 미검증(A-6).
- QA-TECH-08 의 '조사에 없는 기술' 검사는 토큰 일치라 오탐(제품명 표기 차이)이 있을 수 있어 검토 수준으로만 둔다.
- 다음: 단계 4(제안서·제출 산출물) — 분량 조절(요약/상세), 시각 요소 확장(배포·네트워크·KPI·의사결정 표), 비용 산정 시트, 추적성 Excel 열(전략·설계·테스트·검수·분석), 미리보기 화면.
