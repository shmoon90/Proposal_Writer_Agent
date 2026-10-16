# 개발 진행 상태 (DEVELOPMENT_STATUS)

갱신: 2026-10-16 (Phase 20 완료 — 네이티브 차트·UI 목업 컴포넌트·그룹화·참고 그림 삽입; 남은 단계 21) · 기계 판독용은 `DEVELOPMENT_STATUS.json`, 작업 순서 기록은 `../WORK_LOG.md`, 계획은 `../docs/IMPROVEMENT_PLAN_2026-10.md`.

## 분석 완료
- 기존 프로젝트(Phase 1~15) 구조·에이전트·MCP·산출물·테스트 분석, 요청 19개 절 ↔ 구현 차이표(계획 문서 §1·§2)
- 라이브러리 지원 범위 검토(`docs/LIBRARY_REVIEW.md`): python-pptx 유지, PowerPoint COM 렌더링 가능, SVG 미지원

## 구현 완료
- **20단계** (이번): `generators/pptx/charts.py` 네이티브 차트(역할별 공수·요구사항 통계·제출용 간트·VisualSpec `chart`), `draw_screen` 컴포넌트(`VisualItem.kind`: input/button/menu/tab/message/table/list/chart)와 그룹화(`shapes.group`: 목업·카드·수치 카드·엔티티), 도식 14종, `DocumentKind.PICTURE`(참고 그림, `<태그>__<설명>.png|jpg`) → `GenerationContext.pictures` → 소절 `picture` 참조·부록 태그 그림, 프로젝트 화면 그림 종류·설명 입력, QA `check_pptx` 그룹 평탄화, 명세 chart 집계 → `docs/PHASE20_REPORT.md`
- **19단계**: `ProposalSection` 슬라이드 명세(key_message·purpose·audience·evidence·links·layout_type·tech_detail·terms)·`glossary`, 슬라이드 명세 JSON(`슬라이드명세_제출용/발표용_vX.Y.json`, manifest extra_files), 도식 13종(raci·data_model·procedure·security_layers·layers), 기술 상세 카드·대안 비교(상용/공개/자체) 표·용어 설명 표, `proposal_writer` 규칙 12~16, QA-CON-10(추상 표현·근거 없는 수치)·QA-CON-11(약어 미설명) → 총 38항목, 산출물 화면 '슬라이드 명세' 패널 → `docs/PHASE19_REPORT.md`
- **18단계**: `strategy_planner` 브리프(RFP 요약·요구사항 대응 방향·목차 초안·전략 3~5·차별화·핵심 기술·위험·제출/발표 차이·확인 필요), Gate P(사람 승인) 평가·승인·반려·재작성, 승인 전 제안 문안 작성·최종 확정 차단(시안 생성은 허용), QA-RFP-08, 산출물 화면 승인 패널, 브리프 목차 → 제출용 덱 뼈대 → `docs/PHASE18_REPORT.md`
- **17단계**: RFP 분석 항목 확장(현행 문제·보안/개인정보·이관/운영·개발 환경·산출물·시험/검수/교육·작성 지침·페이지 제한·규격·필수 제출), 페이지 제한 파싱, `Requirement.evidence_class/response_strategy`, 덱→Excel 순서·제안서 페이지 역산, 추적표 29열·정의서 33열 → `docs/PHASE17_REPORT.md`
- **16단계**: `Output/<프로젝트>/manifest.json`(생성 run 누적·QA 첨부·category·sha256), 그림 정책(허용 태그 photo/illustration/decoration/reference, 태그 없는 그림만 QA-FILE-12 실패, 예외 기록), `scripts/record_test_status.py` → `docs/PHASE16_REPORT.md`
- 이전: Phase 14(정의서·추적표·구현 방안), Phase 15(WBS·투입계획)

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
- 2026-10-16 `pytest -q -p no:cacheprovider`: **274 passed, 1 skipped, 2 deselected, 0 failed**. `ruff`·`mypy src`(114 파일) 통과
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답·Gate P 대행 승인, 20단계): QA 38항목 중 37 실행·33 통과·0 실패·4 검토(QA-TECH-01/02/05/07)·1 미실행, gate3·gate4 PASS, QA-FILE-12 통과(사진 예외 2), 제출용 네이티브 차트 3·그룹 8·사진 1, 발표용 차트 1·그룹 10·사진 1

## 해결한 문제
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
- 슬라이드 렌더링·재열기 검증 미구현(21단계). 네이티브 간트 값 축은 경과 일수(날짜 축 아님), 차트 색·글꼴은 코드 값, 참고 그림은 파일명 태그 규칙 의존(20단계 한계)
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
