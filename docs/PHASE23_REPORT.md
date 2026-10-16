# Phase 23 보고서 — 요구사항 묶음별 구현 설계(design_writer)·구조/절차 도식·적용 기술 표·QA-CON-13 (2026-10-16)

사용자 검토 의견 "장표의 밀도만 중요한 것이 아니라 **장표 안에 기술되는 내용**이 중요하다 — 실제로 어떻게 구현할지, 어떤 기술을 적용할지, 어떤 구조로 개발할지를, 웹 검색으로 확인한 방법이나 프로그램이 자체 설계한 구조·프로세스로 구체적으로 기술해야 한다"를 반영했다.

## 1. 원인 (검토 결과)

- 묶음 소절(Phase 22)은 **정의서 구현방안을 그대로** 실었다. 구현방안은 정의서용 2~5줄 요약이라 구조·절차·기술 선택 이유·대안·근거가 없고, 그 깊이를 채우는 에이전트 단계가 없었다. 문안 에이전트(`proposal_writer`)는 소절 글머리·도식을 쓰지만 묶음 수준의 설계는 입력에도 출력에도 없었다.
- 기술 조사(`tech_researcher`)는 주제별 사실을 모으지만 "이 요구 묶음을 어떤 구조·절차·기술로 구현하는가"로 이어지지 않았고, QA 는 구현방안 **문장의 반영 여부**(QA-CON-12)만 봤지 설계 **깊이**는 보지 않았다.

## 2. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| 구현 설계 에이전트 | 새 역할 **`design_writer`**(WebSearch/WebFetch 허용, `pwa.get_requirement`·`list_research`): 요구사항 묶음마다 `ImplementationDesign{title, requirement_ids, key_message, overview, structure[](구성 요소·계층·기술·역할), flows[](담당·처리·분기), tech_choices[](영역·선택·선정 이유·대안·근거·verified), data_interfaces[], premises[], risks[], sources[]}`. 입력은 코드 제안 묶음(RFP 번호·분류)+정의서 구현방안, 조사 기록(사실·출처), 아키텍처 구성 요소, 기술 선택 비교. 규칙: 묶음마다 구조 2·절차 3~8·기술 선택 1·데이터/인터페이스 1 이상, "어디에·어떤 방식으로·왜"를 쓰고 제품·버전·표준은 조사·아키텍처·열람한 URL 에 있는 것만 단정(`verified`), 아니면 미확인·`research_needed` | `agents/schemas.py`(DesignComponent·DesignStep·TechChoice·ImplementationDesign·DesignReport), `agents/roles.py`, `agents/prompts/design_writer.md`, `requirements/design.py`(브리프·결과·커버리지·요약) |
| 파이프라인 | 단계 **`impl_design`(요구사항 묶음별 구현 설계)** 를 아키텍처 설계 다음·WBS 앞에 추가(총 16단계). `StepRunner.run_design_writing`, 화면 '구현 설계 작성(에이전트, 웹 검색)' 버튼과 요약 캡션. `GenerationContext.designs` 로 덱·QA 에 전달, 문안 브리프 `<data>.designs` 와 규칙 18(설계 묶음을 그대로 따름) | `services/pipeline_service.py`, `orchestrator/runner.py`, `services/__init__.py`, `ui/app_pages/agents.py`, `generators/base.py`, `generators/service.py`, `prompts/proposal_writer.md` |
| 묶음 결정 | `group_requirements`: ① 구현 설계 묶음(`source=design`, 설계 첨부) ② 문안 에이전트 `requirement_groups` ③ 코드(RFP 번호·분류). 설계 묶음은 나누지 않고 구현방안이 없는 요구도 포함(설계 자체가 구현 내용) | `generators/pptx/req_groups.py` |
| 묶음 소절 내용 | 제출용: **결론형 제목 → 요점(대응 요구·설계 개요) → '구현 구조' 계층 띠 도식(사용자·화면 → 웹 → 응용 → 배치 → 연계 → 데이터 → 인프라 → 외부; 상자에 기술·역할) → '처리 절차' 레인 도식(담당별, 분기 ◆) + '처리 절차 상세' 표(단계·담당·처리·분기/예외) → '적용 기술·선정 이유' 표(구분·적용 기술·선정 이유와 검토한 대안·근거(출처 도메인·확인/미확인)) → '데이터·인터페이스 설계·위험 대응' → 정의서 구현방안 전문 표**. 발표용: 묶음마다 요점+구조 도식 1장, 절차 도식+기술 표(4행) 1장. 설계가 없으면 Phase 22 구성(기능 블록·구현방안 표) 유지 | `generators/pptx/decks.py`(`_group_blocks`·`_paginate_blocks`·`_render_group`), `req_groups.py`(`design_structure_spec`·`design_flow_spec`·`flow_table_rows`·`tech_choice_rows`·`design_texts`) |
| 장 배분 | `_paginate_blocks`: 블록 추정 높이로 장을 나누고 표는 행 단위(장당 최소 2행)로 '(계속)' 장에 잇는다. 도식은 최소 높이까지 줄여서라도 같은 장에 두고, 요점만 있는 장에는 크더라도 넣는다. 그린 뒤 표 행이 덜 그려졌거나 블록이 아예 못 그려졌으면 다음 장으로 넘긴다(유실 방지). 템플릿 덱의 '(계속)' 장은 **소절 번호를 올리지 않는다** | `decks.py`, `template.py`(`canvas_slide`) |
| 도식 | 좁은 용지(A4 세로)에서 단계가 많은 절차는 **세로 절차**(담당 열 머리글, 단계 위→아래, 화살표)로 자동 전환(`_draw_procedure_vertical`, 높이 추정도 단계 수 비례). 레인 라벨 폭 2.8cm, 계층 띠 상자 글자 상한(2개 이하 120자). 전제 ※ 주석 중복 제거 | `shapes.py`, `req_groups.py` |
| 프롬프트 | `approach_writer` 규칙 2: "무엇으로"는 제품·버전·표준·패턴을 **이름으로**(예: CSS position: sticky, SXSSF 스트리밍, RBAC), 방법 없는 문장 금지 | `prompts/approach_writer.md` |
| QA | **QA-CON-13 구현 설계 깊이 ↔ 제안서 반영**(gate5, 재생성으로 자동 수정): 설계가 없으면 검토(설계 작성 필요), 묶음마다 구조 2·절차 3·기술 1·데이터 1 미만이면 실패, 구성 요소 이름·절차 제목·적용 기술이 제출용 PPT 본문에 없으면 실패, 출처 미확인(`verified=false`) 기술 선택과 설계에서 빠진 요구사항은 검토. 총 **52항목**(CON 13) | `validation/independent_qa.py` |
| 대행 스크립트 | `design_writer` 대행 응답(`DESIGNS`, 계산기 샘플 2묶음 내장, `--fixture` 로 교체), 단계 호출, '@별칭' 해결 대상에 포함 | `scripts/run_manual_agents.py` |

## 3. 실제 확인 결과

- pytest **289 passed, 1 skipped**(전체, `tests/integration/llm` 제외). 신규 `tests/unit/test_phase23_design.py` 5건: 스키마·최소 요건·RFP 번호 → 세부 요구 해석, 설계 → 문안 → 코드 순 묶음과 도식/표 spec(계층 순서·분기 표시·근거 표기: 도메인(확인/미확인)·자체 설계), 덱에 구현 구조·처리 절차·적용 기술·데이터/인터페이스·정의서 구현방안이 실리고 QA-CON-13 통과/실패/검토 판정, 장 배분(표 행 분할·유실 없음·요점+도식 같은 장), 파이프라인 단계 순서. E2E 는 QA 52항목·49 실행으로 조정. `ruff`·`mypy src`(117 파일) 통과. 민감 용어 검사 통과.
- 계산기 샘플(대행 응답, 렌더링 켬): 구현 설계 2묶음(요구 11건) → 제출용 40장·발표용 25장, QA 52항목 중 49 실행·43 통과·0 실패·6 검토(TECH-01/02/05/07 조사 미확인, CON-13 출처 미확인 기술 선택 1건(Python decimal 공식 문서 미열람), FILE-03 기존 '사업 이해' 리드 넘침 추정).
- 실제 고객 RFP PDF(저장소 밖, 템플릿 2종, 대행 응답·대행 승인·렌더링 켬): 세션의 Claude 가 **웹 검색으로 확인한 사실**(전자정부 표준프레임워크 4.3 실행환경 Spring 5.3.37·JDK 8+, JEUS 7 ↔ WebtoB 4.1·Java EE 6, CSS position: sticky 지원 범위·th 적용, 알림톡 템플릿 검수·SMS 대체 발송 조건, Apache POI SXSSF 윈도우·dispose, Chart.js 캔버스 접근성·ECharts aria, KWCAG 2.2(33검사항목·명도 대비 4.5:1), WAI-ARIA 툴팁 패턴, 반응형 표 패턴, Rocky Linux 8/9 지원 기간, ojdbc6 11.2.0.4 JDK 8 호환, TOTP RFC 6238 기본값, ShedLock/Quartz 선택 기준, 행안부 개발보안 가이드·스패로우)에 근거해 **구현 설계 7묶음**(요구사항 31건, 적용 기술 27건 중 확인 18건)을 대행 작성하고 조사 기록의 confirmed_facts·출처도 보강했다. 결과: 제출용 **80장**(묶음 소절 29~63장, 묶음당 4~6장: 요점·구현 구조 → 세로 절차 도식+상세 표 → 적용 기술 표 → 데이터·인터페이스 → 정의서 구현방안 표)·발표용 60장(묶음 24~46장). 통합 QA **52항목 전부 실행·47 통과·0 실패·5 검토**(RFP-01 미연결 의무 문장, TECH-01/02/05 조사 미확인, CON-13 출처 미확인 기술 선택 — 공통컴포넌트 목록·KISA 비밀번호 저장 권고·JEUS 7 JDK 범위·비식별 솔루션 벤더 주장), gate3·gate4 PASS, QA-FILE-13 페이지 제한(100쪽) 통과, 렌더링 성공. 렌더링 PNG 를 보며 3회 수정했다: 절차 상자 글자 잘림(제목만 + 상세 표), 가로 레인 상자가 너무 좁은 문제(세로 절차 자동 전환), 발표용 절차 도식 축소로 인한 겹침(QA-FILE-04 → 세로 절차 축소 금지·장 분리), 도식 아래 빈 공간(최소 높이·요점 장 합침), 표 행 유실(이월), '(계속)' 장의 소절 번호 증가(유지), 복합 장표 ※ 주석 넘침(높이 가변), 자체 설계 선택이 '미확인'으로 표시되던 것(근거 표기 구분).
- 실제 Claude 모델 호출은 없다(크레딧 부족). `design_writer` 가 실제로 얼마나 구체적인 설계를 내는지는 미검증이며, 이번 실샘플의 설계 내용은 세션의 Claude 가 검색 결과 요약을 근거로 쓴 것이다.

## 4. 남은 한계

- 실제 Claude 모델로 `design_writer` 를 실행한 결과는 없다(크레딧 없음). 이번 실샘플의 구현 설계는 세션의 Claude 가 **웹 검색 결과(검색 요약)로 확인한 사실**에만 `verified=True` 를 붙여 작성했고(페이지 전문 열람은 아님), 확인하지 못한 항목(JEUS 7 의 JDK 8 지원 범위, 표준프레임워크 4.3 공통컴포넌트 목록, KISA 비밀번호 저장 권고 세부)은 미확인·`research_needed` 로 남겼다.
- 묶음 소절 분량이 늘었다(실샘플 제출용 묶음 7개 → 약 27장). RFP 페이지 제한(QA-FILE-13)은 통과했지만, 제안서 전체 분량 조절(요약 모드)은 사람 판단이 필요하다.
- 절차 도식 상자에는 단계 제목만 들어가고 처리 내용은 표에 있다(상자 글자 잘림 방지). 세로/가로 절차 전환은 폭·단계 수 기준의 코드 판단이다.
