# 개발 진행 상태 (DEVELOPMENT_STATUS)

갱신: 2026-10-16 (Phase 23 — 요구사항 묶음별 구현 설계 에이전트 `design_writer`·구조/절차 도식·적용 기술 표·QA-CON-13; Phase 22 요구사항 묶음·복합 장표 뒤 사용자 검토 의견 '장표 내용의 구체성' 반영) · 기계 판독용은 `DEVELOPMENT_STATUS.json`, 작업 순서 기록은 `../WORK_LOG.md`, 계획은 `../docs/IMPROVEMENT_PLAN_2026-10.md`.


## 통합 개발 지시문 — 단계 0 진단 (2026-10-16, branch `feature/major-revision`)
- 현재 단계: **main 병합 완료(2026-10-19, fast-forward 3c86ead) — 지시문 단계 0~8 전부 main 에 반영**. 병합 후 재검증: 334 passed·8 failed — 실패 8건은 전부 Streamlit AppTest 화면 테스트로, pyarrow DLL 이 Windows 애플리케이션 제어 정책에 새로 차단된 환경 문제(같은 커밋 10-16 에는 342 passed). 코드 결함 아님, 정책 해제 후 재실행 필요 — 상세 `docs/DIRECTIVE_STAGE8_REPORT.md`, 최종 보고 `docs/DIRECTIVE_FINAL_REPORT.md`
- 단계 8 결과: 전체 흐름 통합 테스트(제안→기준선→변경→설계→테스트→복원), 보안 점검 테스트(업로드·경로·로그·프롬프트·도구·SQL), Revision 복원 절차·화면, 대용량 RFP 성능 측정(PERFORMANCE.md), 최종 보고서(§20). pytest 342 passed, 3 skipped(llm 제외, Docker 실행 테스트는 PWA_RUN_DOCKER_TESTS=1 로 1회 통과) | ruff·mypy 통과 | 단계 8 신규 테스트: 보안 5건(업로드·경로·로그·프롬프트 데이터 선언/읽기 전용 MCP·SQL 바인딩), 전체 흐름 통합 1건(제안→기준선 적재→변경 승인·반영→설계→JUnit 반입→구축 QA 실패 0→복원) | 회귀(run_regression.py --skip-pytest): 회귀_제안 58항목 중 53 실행·실패 0, 회귀_구축 23 실행·실패 0 | 성능(measure_large_rfp.py, 모의 에이전트): 요구 50건 11.8초/11.7MB(QA 53 실행·42 통과·0 실패), 200건 59.6초/32MB(53·4
- (이전) 단계 7 완료(2026-10-16) — 상세 `docs/DIRECTIVE_STAGE7_REPORT.md`
- 단계 7 결과: development/(정적 검사·Docker JUnit·안전 작업 폴더·배치·템플릿), developer/code_qa/code_fixer 역할(구조화 출력, D-23), 코드 생성→검사→테스트→QA 수정 루프, WBS 모듈 분해, TC·DEF·검수·운영 이관 문서, QA-CON-16(58항목), 개발·테스트 화면. - pytest 337 passed, 2 skipped(전체, llm 제외; 단계 6 대비 +8: 신규 tests/unit/test_stage7_development.py — 정적 검사 규칙(package·금지 import·금지 호출·중괄호·테스트 ID·내부 import·JS 금지 패턴·중첩 제네릭 메서드), 배치 계획(의존 순서·테스트 마지막·규칙 밖 모듈 제외), 작업 폴더 안전성(경로 탈출·절대 경로·패키지 밖·확장자·배치 밖·새 파일 금지·크기·복원)·템플릿, 생성→검사→모듈 상태→실행기 스텁 테스트→TC 실패·DEF 생성→QA 수정 루프(스텁)→DEF 종료·정적 오류 시 테스트 금지, surefire 해석·결과 판정, 테스트 계획(중복 없음)·검수 규칙·추적 사슬 판정·문서 4종, WBS 모듈 분해
- (이전) 단계 6 완료(2026-10-16) — 상세 `docs/DIRECTIVE_STAGE6_REPORT.md`
- 단계 6 결과: detail_designer(화면·DB·API·모듈·규칙 → SCR/TBL/API/MOD/DSG, 추적 연결), 발주처 문맥 주입(approach/design/detail 프롬프트), 추적·누락·모순·DB 호환성 검사(QA-CON-15), 구현 방안 구체성 검사(QA-TECH-09, 총 57항목), 설계서 Excel/MD, 코드 생성 입력 패키지(D-22), 설계 화면. - pytest 329 passed, 1 skipped(전체, llm 제외; 단계 5 대비 +5: 신규 tests/unit/test_stage6_detail_design.py — 발주처 문맥 블록(분석+설정 병합, 없는 항목 "(없음)"), 상세 설계 스키마·추적/누락/모순/DB 호환성 판정(FK 없음·존재하지 않는 요구·순환·필수 연결 없음·개인정보 API 인증·DB 불일치), 엔티티 저장(코드 발급·RFP 고유번호 변환·갱신 버전·dropped·추적 연결)·코드 생성 패키지·설계서 Excel/MD·추적표 열 채움·generate_design_docs, 파이프라인 단계 순서·FakeAgentRunner 실행, QA-TECH-09 판정). 기존 테스트 4곳 갱신(역할 목록, E2E executed 53·no
- (이전) 단계 5 완료(2026-10-16) — 상세 `docs/DIRECTIVE_STAGE5_REPORT.md`
- 단계 5 결과: 회의록 구조화(규칙+meeting_analyzer)·권한 미확인 승인 금지·협상 합의 통제·변경 요청 전환, 수정 문서 비교(Excel ID 기준 분류 6종, PPT/Word 불확실), 상태 8종, 영향 확장, 선택 재생성·회귀 비교, QA-CON-14(55항목). - pytest 324 passed, 1 skipped(전체, llm 제외; 단계 4 대비 +8: 신규 tests/unit/test_stage5_change_control.py — 회의록 규칙 추출(종류·담당·기한·요구 ID)·권한 미확인 승인 금지·공식 결정만 승인·승인 결정만 변경 요청 전환·기한 경과, 에이전트 보강(FakeAgentRunner meeting_analyzer, 같은 항목 병합, 권한 힌트 무시), 협상 고객 합의 통제·'반영'은 코드만·변경 요청 전환 → 분석 → 승인 대기(8종) → 승인(정의서만 선택 재생성) → NEG 반영 전이·요구사항 수정, 상태 8종·흐름·라벨, 정의서 Excel 비교(문구만/의미/삭제/추가/변경 없음·신뢰도 0.9)·화면 이동 판정, 첨부 흐름(Excel I
- (이전) 단계 4 완료(2026-10-16) — 남은 단계 5·6·7·8, main 병합은 맨 마지막. 단계 6 에 문맥 주입·구현 방안 구체성 검사 추가(D-21) — 상세 `docs/DIRECTIVE_STAGE4_REPORT.md`
- 단계 4 결과: 분량 모드·장 수 상한, 배포 구조·의사결정 표 도식(16종)·배포 소절, 비용 산정(`planning/cost.py`·비용산정 시트·사업성 평가 공유), 추적표 7열·정의서 기술검토 열, 렌더링 미리보기 화면. - pytest 316 passed, 1 skipped(전체, llm 제외; 단계 3 대비 +9: 신규 tests/unit/test_stage4_deliverables.py — parse_krw, estimate_cost(단가 없음→unavailable, 설정 단가+RFP 예산 문구→원가·마진, 설정 예산 우선), 비용산정 시트, 추적표 7열·'미정', 정의서 기술검토 열, build_context design_links(STR dropped 제외·API/TBL/DSG/MOD/TC), 요약 모드·장 수 상한 각주·장 수 감소, 배포 소절(구성 요소 없으면 생략)·영역 매핑·연결, draw_deployment/draw_decision_table 도형·가중 합계). 기존 테스트 2곳은 도식 종류 수 14→16 
- (이전) 단계 3 완료(2026-10-16) — 상세 `docs/DIRECTIVE_STAGE3_REPORT.md`
- 단계 3 결과: 전략 항목 보강·STR 저장·덱 전략 표, 요구사항 분석 14항목(Requirement.analysis·화면), 대안 비교·비기능 설계(설계 스키마·덱 표), 출처 확인 날짜, QA-TECH-08(총 54항목). - pytest 307 passed, 1 skipped(전체, llm 제외; 단계 2 대비 +4: 신규 tests/unit/test_stage3_strategy_tech.py 4건 — 전략·분석·대안 비교 스키마, STR 저장(버전 갱신·dropped), 덱의 전략 표·대안 비교 표·비기능 설계 표·확인 날짜, QA-TECH-08 판정(추천안 정합·PoC·분석 누락·조사에 없는 기술)). ruff·mypy(139 파일) 통과. 민감 용어 검사 통과. - 계산기 샘플(모의 에이전트, 렌더링): QA 54항목 중 51 실행·43 통과·0 실패·8 검토(TECH-08: PoC 필요 1건, 14항목 분석 없는 필수 기능 요구 5건 검토). - 실제 고객 RFP(저장소 밖 fixture·템플릿 2종): 전략 4건이 
- (이전) 단계 2 완료(2026-10-16) — 상세 `docs/DIRECTIVE_STAGE2_REPORT.md`
- 단계 2 결과: PPTX·이미지(OCR) 입력, 회의록 문서 종류, 요구사항 품질 규칙 8종(+QA-RFP-09, 총 53항목), 사업성 평가 13항목·권고·비용 산정(단가 없으면 불가)·평가서·파이프라인 단계 bid_assessment·bid_reviewer 에이전트·참여 결정(Decision). - pytest 303 passed, 1 skipped(전체, llm 제외; 단계 1 대비 +8: 신규 tests/unit/test_stage2_rfp_feasibility.py 8건 — PPTX 리더·형식 판별, 이미지 OCR 리더(엔진 없음·불가 시 실패 기록), 업로드 규칙(PPTX RFP 추출·회의록·이미지 첨부), 품질 규칙 8종, 금액 파싱·권고 규칙(사용자 판정 우선), 데이터 평가(미확인·비용 산정 불가 표시), 서비스 평가→재평가→결정 기록(근거 필수·권한 미확인은 제안), 파이프라인 순서). 기존 테스트 2건은 기대값만 갱신(역할 14종, 구축 모드 문서 종류에 회의록). ruff·mypy(139 파일) 통과. 민감 용어 검사 통과. - 계산기 샘플(모의 에이전트, 렌더링): 사업성 평가 
- (이전) 단계 1 완료(2026-10-16) — 상세 `docs/DIRECTIVE_STAGE1_REPORT.md`
- 단계 1 결과: 프로젝트 설정(기술 선택 모드 5종·단가), 신규 엔티티 9종+마이그레이션 8·`next_code`, StepRun 진행률·중단·재개·백그라운드(JobManager), 실행 계획 미리보기·단계 디스패처·실패만 재실행, 로그 비밀값 마스킹, QA·shapes 패키지 분할(동작 불변). - pytest 295 passed, 1 skipped(전체, llm 제외; 단계 0 대비 +6: 신규 tests/unit/test_stage1_foundation.py 6건 — 설정 왕복·사유 규칙, 엔티티 저장·프로젝트 내 코드 유일·다른 프로젝트 허용, 결정/협상 구속 규칙, 진행률·중단·백그라운드·끊긴 작업 정리, 실행 계획·디스패처·실패만 재실행, 로그 마스킹). ruff·mypy(132 파일) 통과. 민감 용어 검사 통과. - 실샘플 회귀(모의 에이전트, 렌더링 켬): 계산기 QA 52항목 중 49 실행·43 통과·0 실패·6 검토, 실제 RFP(저장소 밖 fixture·템플릿 2종) 52 실행·47 통과·0 실패·5 검토 — 단계 0 기준선(QUALITY_BASELINE §3) 과 동일. 모듈 
- (이전) 단계 0 완료, 단계 1 착수 조건이던 승인 A-1~A-7 은 2026-10-16 전부 승인 — 승인 항목 A-1(데이터 모델 확장·마이그레이션)·A-4(백그라운드 실행) 결정 필요, 나머지 단계 1 작업(설정 확장·대형 모듈 분할·보안 확인·실행 계획 미리보기) 은 승인 없이 진행 가능
- 진단 문서: `workspace/PROJECT_ANALYSIS.md`(구조·스택·실동작·재사용 판단), `FEATURE_GAP_ANALYSIS.md`(업무 20단계·횡단 요구 상태), `QUALITY_BASELINE.md`(실샘플 지표·샘플 제안서 차이·회귀 기준), `TECHNICAL_RISKS.md`(R-31~R-41, 승인 항목 A-1~A-7), `IMPLEMENTATION_PLAN.md`(단계 1~8 계획·테스트 기준), `DECISIONS.md`(D-11~D-19), `TEST_RESULTS.md`(최신 결과)
- 기능 상태 집계: 완료·검증 5 / 품질 개선 3 / LLM 미검증 2 / 일부 구현 7 / 미구현 8(사업성 평가·참여 결정·협상/계약·회의/의사결정·코드 개발/리뷰·테스트/결함·운영 이관·비용)
- 코드 수정 없음(진단만). 마지막 검증: pytest 289 passed·1 skipped, ruff·mypy 통과, 실샘플 QA 실패 0

## 분석 완료
- 기존 프로젝트(Phase 1~15) 구조·에이전트·MCP·산출물·테스트 분석, 요청 19개 절 ↔ 구현 차이표(계획 문서 §1·§2)
- 라이브러리 지원 범위 검토(`docs/LIBRARY_REVIEW.md`): python-pptx 유지, PowerPoint COM 렌더링 가능, SVG 미지원

## 구현 완료
- **23단계** (이번): 새 역할 `design_writer`(`agents/prompts/design_writer.md`, `requirements/design.py`, 스키마 `ImplementationDesign`/`DesignReport`), 파이프라인 단계 `impl_design`(아키텍처 뒤, 총 16단계), `GenerationContext.designs`, 묶음 결정에 설계 최우선(`req_groups.group_requirements(use_designs)`), 묶음 소절 블록(구현 구조 계층 띠·처리 절차 레인/세로 도식+상세 표·적용 기술 표·데이터/인터페이스·정의서 구현방안 표)과 장 배분(`decks._paginate_blocks`, 유실 방지 이월), 템플릿 '(계속)' 소절 번호 유지, QA-CON-13(총 52항목), 대행 스크립트 `DESIGNS`·단계 호출, 문안·구현방안 프롬프트 보강
- **22단계**: `generators/pptx/req_groups.py` 요구사항 묶음(에이전트 `requirement_groups` 우선, 코드 RFP 번호·분류), 목차 필수 키 `req_groups`, 묶음 장표(결론형 제목·요점·기능 블록 도식·정의서 구현방안 전문 표·(계속)·※ 전제), `composite_slide`·`draw_blocks`(밴드 배치·고정/가변 블록·최소 높이·장 분할), `draw_text_table`, 카드·2열·띠 높이 상한, 도식 소절 요점+도식+기술 상세 표 1장, QA-CON-12(51항목), QA-CON-01 RFP 번호 제외 → `docs/PHASE22_REPORT.md`
- **21단계**: `validation/render.py` PowerPoint COM 렌더링·재열기(QA-FILE-14, 설정 `qa_render_check`·화면 체크), QA-FILE-13 페이지 제한, `QaCategory.EDITABILITY` QA-EDIT-01~10, `QaService.run(categories, render_check)` 범주 분리·보고서 범주별 집계, 발표용 노트 초안, 장 라벨 줄바꿈 수정, `run_regression.py --render` → `docs/PHASE21_REPORT.md`
- **20단계**: `generators/pptx/charts.py` 네이티브 차트(역할별 공수·요구사항 통계·제출용 간트·VisualSpec `chart`), `draw_screen` 컴포넌트(`VisualItem.kind`: input/button/menu/tab/message/table/list/chart)와 그룹화(`shapes.group`: 목업·카드·수치 카드·엔티티), 도식 14종, `DocumentKind.PICTURE`(참고 그림, `<태그>__<설명>.png|jpg`) → `GenerationContext.pictures` → 소절 `picture` 참조·부록 태그 그림, 프로젝트 화면 그림 종류·설명 입력, QA `check_pptx` 그룹 평탄화, 명세 chart 집계 → `docs/PHASE20_REPORT.md`
- **19단계**: `ProposalSection` 슬라이드 명세(key_message·purpose·audience·evidence·links·layout_type·tech_detail·terms)·`glossary`, 슬라이드 명세 JSON(`슬라이드명세_제출용/발표용_vX.Y.json`, manifest extra_files), 도식 13종(raci·data_model·procedure·security_layers·layers), 기술 상세 카드·대안 비교(상용/공개/자체) 표·용어 설명 표, `proposal_writer` 규칙 12~16, QA-CON-10(추상 표현·근거 없는 수치)·QA-CON-11(약어 미설명) → 총 38항목, 산출물 화면 '슬라이드 명세' 패널 → `docs/PHASE19_REPORT.md`
- **18단계**: `strategy_planner` 브리프(RFP 요약·요구사항 대응 방향·목차 초안·전략 3~5·차별화·핵심 기술·위험·제출/발표 차이·확인 필요), Gate P(사람 승인) 평가·승인·반려·재작성, 승인 전 제안 문안 작성·최종 확정 차단(시안 생성은 허용), QA-RFP-08, 산출물 화면 승인 패널, 브리프 목차 → 제출용 덱 뼈대 → `docs/PHASE18_REPORT.md`
- **17단계**: RFP 분석 항목 확장(현행 문제·보안/개인정보·이관/운영·개발 환경·산출물·시험/검수/교육·작성 지침·페이지 제한·규격·필수 제출), 페이지 제한 파싱, `Requirement.evidence_class/response_strategy`, 덱→Excel 순서·제안서 페이지 역산, 추적표 29열·정의서 33열 → `docs/PHASE17_REPORT.md`
- **16단계**: `Output/<프로젝트>/manifest.json`(생성 run 누적·QA 첨부·category·sha256), 그림 정책(허용 태그 photo/illustration/decoration/reference, 태그 없는 그림만 QA-FILE-12 실패, 예외 기록), `scripts/record_test_status.py` → `docs/PHASE16_REPORT.md`
- 이전: Phase 14(정의서·추적표·구현 방안), Phase 15(WBS·투입계획)

## 변경 파일 (22단계)
- 신규: `generators/pptx/req_groups.py`, `docs/PHASE22_REPORT.md`, `tests/unit/test_phase22_req_groups.py`
- 수정: `generators/pptx/shapes.py`, `generators/pptx/decks.py`, `generators/pptx/outline.py`, `generators/pptx/builder.py`, `generators/pptx/template.py`, `agents/schemas.py`, `agents/prompts/proposal_writer.md`, `validation/independent_qa.py`, `scripts/run_manual_agents.py`, 테스트 2건, `docs/USER_GUIDE.md`, `docs/AGENT_DESIGN.md`, `docs/LIMITATIONS.md`, `docs/TEST_RESULTS.md`, `README.md`

## 변경 파일 (21단계)
- 신규: `validation/render.py`, `docs/PHASE21_REPORT.md`, `docs/FINAL_REPORT_IMPROVEMENT_2026-10.md`, `tests/unit/test_phase21_render_qa.py`
- 수정: `validation/independent_qa.py`, `validation/qa_service.py`, `validation/__init__.py`, `models/qa.py`, `config/settings.py`, `orchestrator/runner.py`, `generators/pptx/decks.py`, `generators/pptx/template.py`, `ui/app_pages/deliverables.py`, `scripts/run_manual_agents.py`, `scripts/run_regression.py`, `tests/integration/test_phase7_qa.py`, `docs/USER_GUIDE.md`, `docs/OUTPUT_STRUCTURE.md`, `docs/LIMITATIONS.md`, `docs/LIBRARY_REVIEW.md`, `docs/TEST_RESULTS.md`, `README.md`

## 변경 파일 (20단계)
- 신규: `generators/pptx/charts.py`, `docs/PHASE20_REPORT.md`, `tests/unit/test_phase20_editable_objects.py`
- 수정: `agents/schemas.py`, `agents/prompts/proposal_writer.md`, `models/enums.py`, `services/document_service.py`, `ingest/service.py`, `generators/base.py`, `generators/service.py`, `generators/pptx/shapes.py`, `generators/pptx/decks.py`, `generators/pptx/slide_spec.py`, `validation/deliverables.py`, `ui/app_pages/project.py`, `scripts/run_manual_agents.py`, 테스트 2건(그룹 평탄화), `docs/USER_GUIDE.md`, `docs/AGENT_DESIGN.md`, `docs/LIBRARY_REVIEW.md`, `docs/LIMITATIONS.md`, `docs/OUTPUT_STRUCTURE.md`, `docs/TEST_RESULTS.md`, `README.md`

## 변경 파일 (19단계)
- 신규: `generators/pptx/slide_spec.py`, `docs/PHASE19_REPORT.md`, `tests/unit/test_phase19_slide_spec.py`
- 수정: `agents/schemas.py`, `agents/prompts/proposal_writer.md`, `generators/base.py`, `generators/pptx/shapes.py`, `generators/pptx/decks.py`, `generators/service.py`, `validation/independent_qa.py`, `ui/app_pages/deliverables.py`, `scripts/run_manual_agents.py`, `tests/integration/test_phase7_qa.py`, `docs/AGENT_DESIGN.md`, `docs/USER_GUIDE.md`, `docs/OUTPUT_STRUCTURE.md`, `docs/TEST_RESULTS.md`, `docs/LIMITATIONS.md`, `README.md`

## 변경 파일 (18단계)
- 신규: `services/strategy_service.py`, `agents/prompts/strategy_planner.md`, `docs/PHASE18_REPORT.md`, `tests/unit/test_phase18_strategy_gate.py`
- 수정: `agents/schemas.py`, `agents/roles.py`, `orchestrator/gates.py`, `orchestrator/runner.py`, `services/pipeline_service.py`, `services/__init__.py`, `generators/service.py`, `generators/pptx/outline.py`, `generators/pptx/template.py`, `validation/independent_qa.py`, `validation/qa_service.py`, `ui/app_pages/deliverables.py`, `scripts/run_manual_agents.py`, 테스트 7건, `docs/AGENT_DESIGN.md`, `docs/USER_GUIDE.md`, `docs/OUTPUT_STRUCTURE.md`, `docs/TEST_RESULTS.md`

## 변경 파일 (17단계)
- 신규: `requirements/evidence.py`, `generators/pptx/pagemap.py`, `docs/PHASE17_REPORT.md`, `tests/unit/test_phase17_rfp_trace.py`
- 수정: `agents/schemas.py`, `agents/prompts/rfp_analyst.md`, `ingest/rfp_profile.py`, `ingest/excel_reader.py`, `models/requirement.py`, `requirements/service.py`, `requirements/approach.py`, `changes/baseline_service.py`, `changes/service.py`, `generators/base.py`, `generators/service.py`, `generators/excel/trace_matrix.py`, `generators/excel/requirement_spec.py`, `docs/AGENT_DESIGN.md`, `docs/OUTPUT_STRUCTURE.md`, `docs/TEST_RESULTS.md`, 테스트 2건

## 변경 파일 (16단계)
- 신규: `src/proposal_agent/storage/manifest.py`, `docs/LIBRARY_REVIEW.md`, `docs/PHASE16_REPORT.md`, `scripts/record_test_status.py`, `tests/unit/test_phase16_manifest_pictures.py`
- 수정: `generators/base.py`, `generators/service.py`, `generators/pptx/builder.py`, `generators/pptx/template.py`, `validation/deliverables.py`, `validation/independent_qa.py`, `validation/qa_service.py`, `changes/service.py`, `docs/OUTPUT_STRUCTURE.md`, `docs/USER_GUIDE.md`, `docs/TEST_RESULTS.md`, `README.md`, `.gitignore`

## 테스트 실행 결과
- 2026-10-16 `pytest -q -p no:cacheprovider`: **284 passed, 1 skipped, 2 deselected, 0 failed**. `ruff`·`mypy src`(116 파일) 통과
- 실제 고객 RFP PDF(저장소 밖) 재실행(22단계): 요구사항 42건·묶음 7개, 제출용 58장·발표용 44장, QA 51항목 중 47 통과·0 실패·4 검토, gate3·gate4 PASS, QA-CON-12 통과
- 실샘플 재검증(21단계, 렌더링 켬): QA 50항목 중 48 실행·44 통과·0 실패·4 검토(QA-TECH-01/02/05/07)·2 미실행, gate3·gate4 PASS, QA-FILE-14 PASS(제출용 30/30·발표용 22/22 PNG, 재열기 성공), QA-EDIT 10항목 통과. 재실행(21b): 장 라벨 수정(줄바꿈 끔·여백 반영·덮개 30% 확장) 후 재실행 (렌더링 21b)·(렌더링 21c) 모두 QA 50항목 중 48 실행·44 통과·0 실패·4 검토·2 미실행, gate3·gate4 PASS, QA-FILE-14 PASS(제출용 30/30·발표용 22/22 PNG, 재열기 성공, 9.4s·3.8s). 21c PNG에서 장 라벨이 한 줄로 들어가고 레이아웃 잔여 글자가 사라진 것을 육안 확인
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답·Gate P 대행 승인, 20단계): QA 38항목 중 37 실행·33 통과·0 실패·4 검토(QA-TECH-01/02/05/07)·1 미실행, gate3·gate4 PASS, QA-FILE-12 통과(사진 예외 2), 제출용 네이티브 차트 3·그룹 8·사진 1, 발표용 차트 1·그룹 10·사진 1

## 해결한 문제
- (22) 정의서 구현방안이 제안서에 60자 표 셀로만 들어가던 구조 → 묶음별 구현 방안 소절(전문 표)과 QA-CON-12
- (22) 세로로 늘어진 빈 상자·장표당 낮은 밀도 → 복합 장표(밴드), 블록 높이 상한·배분, 도식+기술 상세 한 장
- (22) QA-CON-01이 RFP 고유번호를 미등록 요구 ID로 오인, QA-CON-10 'FR-013'+줄바꿈 오탐, QA-CON-11 'UI/UX' 오탐
- (21) 렌더링 PNG에서 템플릿 장 라벨('사업 관리 방안')이 두 줄로 꺾임 → 줄바꿈 끔·여백 반영 글꼴 맞춤
- (21) 대행 흐름의 발표용 슬라이드에 발표자 노트 0건(QA-EDIT-08 검토) → 코드가 '[발표 노트 초안]' 채움
- (21) 렌더링 꺼짐이 gate4를 검토 필요로 만들던 문제 → 꺼짐은 '해당 없음', 켰는데 엔진 없음만 검토
- (20) 카드·목업이 그룹이 되면서 도식 테스트의 최상위 도형 수 검사가 깨짐 → 테스트 도우미 그룹 평탄화, QA `check_pptx`도 평탄화
- (19) QA-CON-10이 범위별 건수("부가 제안 2건")를 근거 없는 수치로 판정 → 범위·유형·수용 상태별 건수를 기준 숫자에 포함
- (19) 발표용 대안 비교 슬라이드의 ※ 주석 2줄 넘침(QA-FILE-03) → 발표용은 근거 주석 1줄·대안 표 축약
- (19) 슬라이드 명세 제목이 템플릿 장 라벨·장 머리글을 집음 → 소절 제목 상자 우선
- (19) 대행 스크립트가 cp949 콘솔에서 '—' 출력 시 예외 → UTF-8 재설정
- (18) 브리프 프롬프트의 build_context 호출이 계획·구성 요소 기본값을 먼저 저장해 에이전트 아키텍처 결과를 무시하던 문제 → 저장소 직접 읽기
- (18) 템플릿 장 라벨 상자보다 긴 장 제목의 넘침(QA-FILE-03) → 한글 글자 폭 기준 글꼴 맞춤
- 그림 삽입 시 잘못된 태그면 그림을 넣은 뒤 거부하던 문제 → 삽입 전 검증
- 통합 QA가 허용 그림(사진)을 실패로 처리하던 정책 → 예외 기록으로 변경

## 미해결 문제
- 실제 Claude 모델 호출 미검증(크레딧 없음)
- 브리프 목차를 화면에서 직접 편집하는 기능 없음(반려 의견으로 재작성). 데이터 없는 브리프 절은 자리표시로 남음(제안 문안 에이전트가 채움)
- 렌더링 QA는 PowerPoint가 있는 PC에서만 실행되며 모양 품질(글자 깨짐·겹침)은 PNG 육안 확인. 네이티브 간트 값 축은 경과 일수(날짜 축 아님), 차트 색·글꼴은 코드 값, 참고 그림은 파일명 태그 규칙 의존
- 슬라이드 명세 필드(key_message·evidence·tech_detail·glossary)는 실제 모델 실행 미검증. QA-CON-10 수치 대조는 숫자 토큰 일치·QA-CON-11은 영문 약어만(검토만 냄)
- manifest에 최종본 확정 기록 없음(21단계)

## 외부 API·MCP 연결 상태
- Claude API: 키 미설정(연결 안 됨). MCP `pwa`: 연결 확인(2026-10-15). `claude-code-docs`: 연결 확인(2026-10-15). WebSearch/WebFetch: 도구 노출 확인, 실제 검색 미실행. PowerPoint COM: 등록 확인(미사용)

## 편집 가능성 QA 결과
- 실샘플 덱: 태그 없는 그림 0, 허용 그림 0(예외 없음). 표·도식은 도형·연결선·표 객체. 차트는 도형 막대(네이티브 아님), UI 목업은 영역 수준 → 20단계

## 다음 작업
- 사용자 확인: 브리프 10항목 형식·승인 화면·차단 범위(PHASE18_REPORT §3)
- 19단계: 슬라이드별 명세(결론형 제목·핵심 메시지·독자·근거·연결·레이아웃)·기술 구체성 템플릿·비전문가 표현·QA-CON-10/11
- (완료) 17단계: RFP 분석 항목 확장(현행 문제·보안/개인정보·이관/운영·시험/검수/교육·페이지 제한/규격·필수 제출), 추적표 대응 전략·대응 제안서 페이지·근거 구분, `Requirement.evidence_class`
