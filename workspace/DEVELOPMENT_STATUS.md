# 개발 진행 상태 (DEVELOPMENT_STATUS)

갱신: 2026-10-16 (Phase 17 완료) · 기계 판독용은 `DEVELOPMENT_STATUS.json`, 작업 순서 기록은 `../WORK_LOG.md`, 계획은 `../docs/IMPROVEMENT_PLAN_2026-10.md`.

## 분석 완료
- 기존 프로젝트(Phase 1~15) 구조·에이전트·MCP·산출물·테스트 분석, 요청 19개 절 ↔ 구현 차이표(계획 문서 §1·§2)
- 라이브러리 지원 범위 검토(`docs/LIBRARY_REVIEW.md`): python-pptx 유지, PowerPoint COM 렌더링 가능, SVG 미지원

## 구현 완료
- **17단계** (이번): RFP 분석 항목 확장(현행 문제·보안/개인정보·이관/운영·개발 환경·산출물·시험/검수/교육·작성 지침·페이지 제한·규격·필수 제출), 페이지 제한 파싱, `Requirement.evidence_class/response_strategy`, 덱→Excel 순서·제안서 페이지 역산, 추적표 29열·정의서 33열 → `docs/PHASE17_REPORT.md`
- **16단계**: `Output/<프로젝트>/manifest.json`(생성 run 누적·QA 첨부·category·sha256), 그림 정책(허용 태그 photo/illustration/decoration/reference, 태그 없는 그림만 QA-FILE-12 실패, 예외 기록), `scripts/record_test_status.py` → `docs/PHASE16_REPORT.md`
- 이전: Phase 14(정의서·추적표·구현 방안), Phase 15(WBS·투입계획)

## 변경 파일 (17단계)
- 신규: `requirements/evidence.py`, `generators/pptx/pagemap.py`, `docs/PHASE17_REPORT.md`, `tests/unit/test_phase17_rfp_trace.py`
- 수정: `agents/schemas.py`, `agents/prompts/rfp_analyst.md`, `ingest/rfp_profile.py`, `ingest/excel_reader.py`, `models/requirement.py`, `requirements/service.py`, `requirements/approach.py`, `changes/baseline_service.py`, `changes/service.py`, `generators/base.py`, `generators/service.py`, `generators/excel/trace_matrix.py`, `generators/excel/requirement_spec.py`, `docs/AGENT_DESIGN.md`, `docs/OUTPUT_STRUCTURE.md`, `docs/TEST_RESULTS.md`, 테스트 2건

## 변경 파일 (16단계)
- 신규: `src/proposal_agent/storage/manifest.py`, `docs/LIBRARY_REVIEW.md`, `docs/PHASE16_REPORT.md`, `scripts/record_test_status.py`, `tests/unit/test_phase16_manifest_pictures.py`
- 수정: `generators/base.py`, `generators/service.py`, `generators/pptx/builder.py`, `generators/pptx/template.py`, `validation/deliverables.py`, `validation/independent_qa.py`, `validation/qa_service.py`, `changes/service.py`, `docs/OUTPUT_STRUCTURE.md`, `docs/USER_GUIDE.md`, `docs/TEST_RESULTS.md`, `README.md`, `.gitignore`

## 테스트 실행 결과
- 2026-10-16 `pytest -q -p no:cacheprovider`: **262 passed, 1 skipped, 2 deselected, 0 failed** (86.7s). `ruff`·`mypy src` 통과
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답): QA 35항목 중 34 실행·30 통과·0 실패·4 검토·1 미실행, manifest run 1건 확인

## 해결한 문제
- 그림 삽입 시 잘못된 태그면 그림을 넣은 뒤 거부하던 문제 → 삽입 전 검증
- 통합 QA가 허용 그림(사진)을 실패로 처리하던 정책 → 예외 기록으로 변경

## 미해결 문제
- 실제 Claude 모델 호출 미검증(크레딧 없음)
- 슬라이드 렌더링·재열기 검증 미구현(21단계), 목차·전략 승인 게이트 미구현(18단계), 네이티브 차트·UI 목업 컴포넌트 미구현(20단계), 허용 그림을 덱 생성에서 쓰는 경로 없음(19단계)
- manifest에 최종본 확정 기록 없음(21단계)

## 외부 API·MCP 연결 상태
- Claude API: 키 미설정(연결 안 됨). MCP `pwa`: 연결 확인(2026-10-15). `claude-code-docs`: 연결 확인(2026-10-15). WebSearch/WebFetch: 도구 노출 확인, 실제 검색 미실행. PowerPoint COM: 등록 확인(미사용)

## 편집 가능성 QA 결과
- 실샘플 덱: 태그 없는 그림 0, 허용 그림 0(예외 없음). 표·도식은 도형·연결선·표 객체. 차트는 도형 막대(네이티브 아님), UI 목업은 영역 수준 → 20단계

## 다음 작업
- 18단계: 목차·전략 브리프(10항목) 생성 역할, Gate P(목차·전략 승인) 게이트·UI, 승인 전 전체 작성 차단 — 구현 후 사용자 확인
- (완료) 17단계: RFP 분석 항목 확장(현행 문제·보안/개인정보·이관/운영·시험/검수/교육·페이지 제한/규격·필수 제출), 추적표 대응 전략·대응 제안서 페이지·근거 구분, `Requirement.evidence_class`
