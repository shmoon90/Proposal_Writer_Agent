# 통합 개발 지시문 단계 4 보고서 — 제안서·제출 산출물 (2026-10-16)

범위: `workspace/IMPLEMENTATION_PLAN.md` 단계 4(①~⑤). A-6(실제 모델 1회 검증) 은 여전히 크레딧이 없어 수행하지 못했다(미검증으로 기록). 브랜치 `feature/major-revision`.

## 1. 무엇을 만들었나

| 항목 | 구현 | 위치 |
|---|---|---|
| ① 분량 조절(§8) | `ProjectSettings.proposal_detail_level`(detailed/summary) 와 `max_slides_per_group`(묶음 소절당 제출용 장 수 상한). **요약 모드** 는 묶음 소절에서 처리 절차 상세 표·대안 비교·데이터/인터페이스·비기능 설계 표를 빼고 구조·절차·적용 기술(4행)·구현방안 표만 남긴다. **장 수 상한** 을 넘는 장은 생략하고 각주에 `분량 상한(N장)으로 M장 생략 — 상세는 요구사항 정의서·구현 설계 JSON` 을 남긴다(임의 삭제가 아니라 표기). 산출물 화면 '제안서 분량' 패널과 대행 스크립트 `--detail`·`--group-cap` 으로 설정 | `models/settings.py`, `generators/pptx/decks.py`(`_detail_level`, `_group_blocks(brief=)`, `_render_group`), `ui/app_pages/deliverables.py`, `scripts/run_manual_agents.py` |
| ② 시각 요소 확장(§8) | 도식 종류 2종 추가(총 16종, 모두 편집 가능 도형): **deployment**(배포·네트워크 구조 — 외부·사용자 / DMZ / 내부망 / 데이터·인프라 영역 열 + 노드 + 연결선, 라벨은 인접 열 사이에만) 과 **decision**(의사결정 표 — 기준 × 가중치 × 대안, 숫자면 가중 합계 행을 코드가 더함). 아키텍처 구성 요소가 있으면 구성도 뒤에 **'배포·네트워크 구조' 소절** 을 코드가 보강(계층 → 영역 매핑, `extra.zone` 우선, `connections` → 화살표). KPI 차트는 Phase 20 네이티브 차트(`chart`) 로 이미 가능 | `generators/pptx/shapes/base.py`(`DEPLOYMENT_ZONES`), `shapes/diagrams.py`(`draw_deployment`, `deployment_items_from_components`, `draw_decision_table`), `shapes/blocks.py`, `outline.py`(`deployment_diagram`), `decks.py` |
| ③ 비용 산정(§6·§14, A-3) | `planning/cost.py` `estimate_cost(settings, roles, allocations, budget_hints)`: 역할별 배정 공수(MD→MM) × 단가(설정 `cost_rates` ∪ 역할 `unit_cost_per_mm`) = 직접비, + 간접비율 = 원가; 매출은 설정 예산 → 없으면 RFP 예산 문구(`parse_krw`); **단가나 공수가 없으면 `unavailable` 과 이유만** 남기고 수치를 만들지 않는다. 인력투입계획 Excel 에 **'비용산정' 시트**(역할·MM·단가·금액·비고 + 직접비·간접비·원가·매출·마진/마진율 또는 '산정 불가' 행). 사업성 평가 7번 항목이 같은 함수를 쓰도록 교체(중복 코드 제거). 대행 스크립트 `--rate 역할=원/MM`·`--budget 원` | `planning/cost.py`, `generators/excel/staffing_plan.py`(`SHEET_COST`), `feasibility/service.py` |
| ④ 추적성 Excel 열(§17) | `GenerationContext.design_links`(요구사항 ID → 전략/API/DB 테이블/설계 항목/코드 모듈/테스트케이스 코드, `GenerationService._design_links` 가 STR·API·TBL·DSG·MOD·TC 저장소에서 수집, dropped 전략 제외). 추적표에 **전략 ID·API ID·DB 테이블 ID·설계 항목 ID·기술검토(14항목 n/14)·코드 모듈 ID·테스트케이스 ID** 열 추가(없으면 '미정'). 정의서에 **'기술검토(14항목)'** 열(채운 항목 수 + 목적·규칙·데이터·연계·성능·장애·테스트 중 앞 3개 첫 줄) | `generators/base.py`, `generators/service.py`, `excel/trace_matrix.py`, `excel/requirement_spec.py`(`_analysis_summary`) |
| ⑤ 미리보기 화면 | 산출물 화면에 **'렌더링 미리보기'** 패널: `11_QA_Validation_Reports/render/<덱>/slide_NN.png` 를 덱·슬라이드 선택으로 표시, PowerPoint 가 있으면 '지금 렌더링' 버튼으로 최신 제출용·발표용을 바로 렌더링 | `ui/app_pages/deliverables.py` |

## 2. 확인 결과

- pytest 316 passed, 1 skipped(전체, llm 제외; 단계 3 대비 +9: 신규 tests/unit/test_stage4_deliverables.py — parse_krw, estimate_cost(단가 없음→unavailable, 설정 단가+RFP 예산 문구→원가·마진, 설정 예산 우선), 비용산정 시트, 추적표 7열·'미정', 정의서 기술검토 열, build_context design_links(STR dropped 제외·API/TBL/DSG/MOD/TC), 요약 모드·장 수 상한 각주·장 수 감소, 배포 소절(구성 요소 없으면 생략)·영역 매핑·연결, draw_deployment/draw_decision_table 도형·가중 합계). 기존 테스트 2곳은 도식 종류 수 14→16 으로 갱신. ruff·mypy(140 파일) 통과. 민감 용어 검사 통과.
- 계산기 샘플(모의 에이전트, 렌더링; `--rate` 4개 역할·`--budget` 1.2억 입력): QA 54항목 중 51 실행·43 통과·0 실패·8 검토(단계 3과 같은 기준선; FILE-03 '사업 개요' 리드 문장 넘침 추정은 이전부터 있던 검토). 인력투입계획 '비용산정' 시트: 직접비 2,486만 원·매출(설정 예산) 1.2억·마진 79.3%. 제출용 48장에 '배포·네트워크 구조' 소절(28장: 외부·사용자/DMZ/내부망/데이터·인프라 4영역·구성 요소 6·연결 5, 발표용 10장) — 렌더링 PNG 확인. 사업성 평가의 비용 산정은 bid_assessment 시점(WBS 전) 이라 '산정 불가' 로 남음(정상).
- 계산기 요약 모드(`--detail summary --group-cap 2`, 단가·예산 없음): 제출용 39장(상세 48장), 묶음 소절 2곳에 '※ 분량 상한(2장)으로 N장 생략 — 상세는 요구사항 정의서·구현 설계 JSON' 각주. QA 51 실행·42 통과·0 실패·9 검토 — 추가된 QA-CON-12 검토는 상한으로 구현방안 표 일부가 빠진 것을 정확히 잡은 것(의도된 동작). 비용산정 시트는 '산정 불가(단가 없는 역할…)' 행만.
- 실제 고객 RFP(저장소 밖 fixture·템플릿 2종; `--rate` 8개 역할, 예산은 RFP 문구 '약 4.5억원'): QA 54 전부 실행·47 통과·0 실패·7 검토(단계 3과 동일, gate4 PASS). 비용산정 시트: 역할 8개 공수 28.3MM, 직접비 2억 4,737만 원·매출 4.5억(RFP 예산 문구)·마진 45.0%. 추적표 42행 중 전략 ID 18행(STR-001~004), 기술검토 2행(14/14), API·DB·설계·코드·테스트케이스 열은 '미정'(단계 5~7 엔티티 전). 정의서 '기술검토(14항목)' 열 2건. 제출용 83장: '배포·네트워크 구조' 가 Ⅲ.1.3(시스템 구성 방안 아래) 로 들어가 10개 구성 요소·9개 연결이 영역별로 그려짐 — 렌더링 PNG 확인. 첫 실행에서는 소절이 마지막 장(Ⅴ.4)에 붙고 연결 라벨끼리 겹쳐 QA-FILE-04 검토가 났는데, 앞 소절의 장·절 지정 상속과 같은 틈의 가까운 라벨 생략·낮은 상자 제목만 표기로 고쳐 통과했다.
- 미검증: 실제 Claude 모델(A-6, 크레딧 없음) — 설계 에이전트가 배포 영역(zone)·연결을 채우는지, 의사결정 표 도식(decision) 을 선택하는지는 알 수 없음. 산출물 화면의 분량 패널·렌더링 미리보기는 Streamlit 화면을 띄워 보지 않고 코드·타입 검사만 했다.

## 3. 남은 것·다음 단계

- 비용 산정은 단가·예산 **입력이 있을 때만** 수치를 내므로(A-3), 화면의 프로젝트 설정 '역할별 단가'·'예산' 입력이 사용 전제다. 부가세·간접비 처리 방식은 입력값 기준이며 세부 회계 규칙은 반영하지 않았다.
- 추적표의 API·DB·설계·코드·테스트케이스 열은 단계 5~7(설계·개발·테스트 관리) 에서 엔티티가 채워져야 '미정' 이 사라진다. 단계 4 시점 실샘플에서는 전략 ID·기술검토 열만 값이 있다.
- 배포 구조 소절은 구성 요소의 계층을 영역으로 추정한다(`extra.zone` 이 없으면). 실제 망 구성(이중화·방화벽 구간) 은 설계 에이전트가 `zone`·`connections` 를 채워야 정확해진다 — 실제 모델 미검증(A-6).
- `decks.py`·`changes/service.py` 분할은 아직이다(동작 불변 리팩터링, 단계 8 정리 때).
- 다음: 단계 5(설계·구축 단계 지원 — 화면/DB/API 설계 산출물, 설계 항목 엔티티 채우기).
