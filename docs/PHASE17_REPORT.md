# Phase 17 보고서 — RFP 분석 항목 확장·근거 구분·추적표 대응 전략/제안서 페이지 (2026-10-16)

[개선 계획](IMPROVEMENT_PLAN_2026-10.md) 17단계. 요청서 §3(RFP 분석 항목, 추적표 항목, 근거 구분), §8.1(추적표와 제안서 페이지 연결)에 해당한다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| §3 RFP 분석 항목 | `RfpAnalysis`에 현행 시스템 문제점·정보보호/개인정보 규정·데이터 이관/운영·개발 환경/기술 제약·단계별 산출물·시험/검수/교육/안정화/유지관리·제안서 목차/작성 지침·페이지 제한·문서 규격/제출 형식·필수 제출 자료/별첨 필드 추가. 프롬프트는 "원문에 없으면 빈 목록(지어내지 않음)"과 원문 위치 표기를 요구 | `agents/schemas.py`, `agents/prompts/rfp_analyst.md` |
| §3 페이지 제한·규격 | `RfpProfile.page_limit/page_limit_text/format_notes`: 제출·작성요령 절에서 "N쪽 이내" 수치와 용지·글꼴·부수·파일 형식 문구를 파싱(없으면 None/빈 목록). 프로파일 요약에 표시 → 18단계 브리프·21단계 QA-FILE-13(페이지 제한 검사)에서 사용 | `ingest/rfp_profile.py` |
| §3 근거 구분 | `Requirement.evidence_class`(rfp / reference_doc / research / design_proposal). 추출 → `rfp`, 기준 문서 적재 → `reference_doc`(정의서 '근거 구분' 열이 있으면 그 값), 수동 추가 → RFP 인용이 있는 필수 항목만 `rfp` 그 외 `design_proposal`, 변경 반영 추가 → `design_proposal`. 비어 있으면 출처·범위 분류로 추정 | `models/requirement.py`, `requirements/evidence.py`, `requirements/service.py`, `changes/baseline_service.py`, `changes/service.py` |
| §3 대응 전략 | `Requirement.response_strategy`(approach_writer가 `response_strategy`를 주면 저장) 없으면 "수용 상태 — 구현 방안 첫 줄"로 기본값. 미수용은 사유 | `agents/schemas.py`(`ApproachItem.response_strategy`), `requirements/approach.py`, `requirements/evidence.py` |
| §3·§8.1 대응 제안서 페이지 | 덱을 먼저 만들고 생성된 PPTX를 다시 열어 슬라이드별 텍스트·표·그룹에서 내부 ID와 RFP ID를 찾아 요구사항 ↔ 슬라이드 번호 대응(`page_map`)을 만든 뒤 Excel을 생성(생성 순서 변경: 덱 → Excel). 추적표 '제안서 페이지(제출용)/(발표용)' 열은 "3-5, 9" 형식, 미언급은 '—' | `generators/pptx/pagemap.py`, `generators/service.py`, `generators/base.py`(`GenerationContext.page_map`) |
| 추적표·정의서 컬럼 | 추적표 수용·대응 묶음: 수용여부·대응 전략·근거 구분·제안서 페이지(제출용)·제안서 페이지(발표용)·생성/변경일자(29열). 정의서: '근거 구분'(요구사항 내용 묶음)·'대응 전략'(수용·우선순위 묶음) 추가(33열). 작성가이드 행 추가. 재적재 동의어(근거 구분·대응 전략) | `generators/excel/trace_matrix.py`, `requirement_spec.py`, `ingest/excel_reader.py` |

## 2. 실제 확인 결과

- pytest **262 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase17_rfp_trace.py` 5건: 스키마 필드·프롬프트 문구, 페이지 제한·규격 파싱(있음/없음), 근거 구분·대응 전략 기본값, 슬라이드 번호 역산(텍스트·표·그룹, RFP ID 매핑, 범위 표기), 생성 흐름(추출 요구는 `rfp`, 덱이 추적표보다 먼저 생성, 추적표·정의서 새 열, 수동 추가 부가 제안은 `design_proposal`). 기존 테스트 2건은 묶음 제목('수용·대응')으로 조정. `ruff check/format`, `mypy src` 통과.
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답): 통합 QA 35항목 중 34 실행·30 통과·0 실패·4 검토·1 미실행(변화 없음). 추적표 '대응 전략'은 수용 상태 + 에이전트 구현 방안 첫 줄, '근거 구분'은 전부 RFP 명시, '제안서 페이지'는 제출용 5·발표용 7(요구사항 대응표 슬라이드) — 대행 응답의 소절에 `requirement_ids`가 없어 대응표 슬라이드만 ID를 담았다. 실제 에이전트가 소절마다 `requirement_ids`를 적으면(프롬프트 규칙) 해당 소절 슬라이드가 함께 표시된다.
- RFP 분석 새 필드는 FakeAgentRunner·대행 응답에서 비어 있다(실제 모델 호출 미검증). 파싱(페이지 제한)은 픽스처로만 확인했고 고객 RFP 샘플(PDF)에서는 페이지 제한 문구가 없어 None이다.

## 3. 한계·다음 작업

- '제안서 페이지'는 생성 파일에 ID 문자열이 있어야 잡힌다. 소절 본문이 ID 없이 요구를 설명하면 '—'로 남는다 → 19단계 슬라이드 명세에서 `requirement_ids`를 필수로 다루고 QA에서 미언급 필수 요구를 검토 항목으로 올린다.
- 근거 구분은 요구사항 단위다. 제안 문안의 주장별 근거(§5 evidence)는 19단계에서 `ProposalSection.evidence`로 다룬다.
- 다음: 18단계(목차·전략 브리프와 Gate P 승인 흐름). 구현 후 브리프 형식·승인 화면을 사용자에게 확인받는다.
