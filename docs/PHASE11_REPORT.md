# Phase 11 보고서 — RFP 구조 인식과 요구사항 분석 연동 (2026-10-15)

요청: "각 고객사마다 RFP 형식이 다르기는 하지만 그래도 요구사항 분석 관련된 모듈에서 참고해서 분석, 요구사항을 파악할 수 있도록 프로그램 수정".

## 1. 무엇을 바꿨나

| 영역 | 변경 | 위치 |
|---|---|---|
| 구조 프로파일러(신규) | 추출 블록에서 절 구성(사업 개요·현황·계획·범위·요구사항·작성요령·제출·평가·별첨), RFP 자체 요구사항 ID 체계(`[A-Z]{2,5}-\d{2,4}`, 접두사별 건수·자리수), ID별 명칭·페이지·블록 색인, 지정 제안서 목차, 평가 항목·배점, 제출 서류를 코드로 뽑는다. 표의 세로 병합 라벨("요구/사항/세부/내용" 등 라벨 토큰만 있는 줄·앞 셀)을 제거하고 블록에 `section_kind`·`rfp_requirement_id`를 태그한다 | `src/proposal_agent/ingest/rfp_profile.py` |
| 추출 실행 | RFP·RFP 첨부 추출 시 프로파일을 만들어 `ExtractionRun.rfp_profile`에 저장. `ExtractionService.rfp_profile()`, `rfp_proposal_toc()`(프로파일 목차 우선, 없으면 기존 휴리스틱) | `ingest/service.py`, `models/extraction.py` |
| 청크 | block 태그에 `section="…"`, `rfp_id="…"` 속성 추가. RFP ID가 바뀌는 지점에서 절반 이상 찬 청크를 닫아 한 요구사항 표가 쪼개지지 않게 함 | `ingest/chunker.py` |
| 최적화기 | 요구사항·제출·작성요령 절 블록이나 RFP ID 태그가 있는 청크는 길이와 무관하게 호출 대상(짧은 제출 조건 절이 저신호로 건너뛰어지던 문제 수정) | `requirements/optimizer.py` |
| 요구사항 추출 | 프롬프트에 절·ID 안내, 출처 라벨에 RFP ID 표기, 초안·블록 태그에서 `Requirement.rfp_requirement_id` 채움, 추출 후 **커버리지 검사**: 연결된 요구사항이 없는 RFP ID마다 `ValidationResult(rule=rfp.uncovered_id, WARNING)` 기록, `ExtractionSummary.uncovered_rfp_ids` | `requirements/service.py`, `models/requirement.py` |
| 에이전트 입력 | `rfp_analyst` 프롬프트 앞에 `<rfp_profile>` 요약, `requirement_extractor` 규칙 13·14(rfp_id 전사, 세부 항목 분리, 절 종류별 분류, 라벨 잡음 무시) | `orchestrator/runner.py`, `agents/prompts/*.md` |
| 산출물 | PPT 목차 결정에 프로파일 목차 사용 | `generators/service.py` |
| 통합 QA | QA-RFP-07 "RFP 요구사항 ID 커버리지"(ID 체계가 없으면 해당 없음으로 미실행, 게이트 차단 안 함) | `validation/independent_qa.py`, `qa_service.py` |
| UI | 문서 추출 화면 하단 "RFP 구조 프로파일" 패널 | `ui/app_pages/extraction.py` |

## 2. 실제 확인 결과

- pytest: **231 passed, 1 skipped, 2 deselected** (전체). 신규 `tests/unit/test_rfp_profile.py` 5건(가상 구조화 RFP DOCX 픽스처 `build_structured_rfp_docx`: Ⅰ~Ⅵ 장, 요약·목록·상세 표(세로 라벨), 목차 표, 배점 표, 제출 목록). `ruff check/format`, `mypy src` 통과.
- 기존 테스트 조정 2건: `test_proposal_full_flow_independent_qa_gates_and_finalize`는 항목이 31개가 되어 `not_run == 1`(QA-RFP-07, 픽스처에 ID 체계 없음)로 수정. `test_verification_uses_fewer_windows_and_compact_prompt`는 "제6장 제출 조건" 절이 혼자 짧은 청크가 되어 저신호로 건너뛰어진 것을 최적화기 수정으로 해결(검증 약화 아님).
- 실문서 점검(저장소 밖 샘플 1건, 고객 제공 RFP 샘플 PDF 48쪽 (저장소 밖, 공개 금지)): 절 9종, RFP ID 22건·11 접두사, 요구사항 절 블록 257개 중 225개 태그, 잡음 220줄 제거, 목차 5항목, 평가 19행. 에이전트 호출은 크레딧 부족으로 실행하지 않았다.

## 3. 한계 (LIMITATIONS §3 참조)

절 제목·ID·목차·배점 인식은 정규식·키워드 휴리스틱이다. 제목 번호 체계가 없거나 ID 형식이 다른 RFP는 경고와 함께 문장 단위 추출로 내려간다. 커버리지는 연결 유무만 본다. 실제 모델로의 추출 품질은 미검증.
