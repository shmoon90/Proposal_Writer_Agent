# Phase 12 보고서 — 제출용 제안서 템플릿 입력·적용 (2026-10-15)

요청: 제출용 제안서 샘플 3종에서 작성 방법·구조·형식을 파악하고, 제안서 작성·검토 에이전트와 모듈이 이를 쓰도록 수정. 템플릿은 제안마다 바뀌므로 **제안서 작성 전에 템플릿을 입력받아 사용**. 다음 작업(발표용 제안서 샘플)도 고려.

샘플 분석 결과는 [PROPOSAL_TEMPLATE_ANALYSIS.md](PROPOSAL_TEMPLATE_ANALYSIS.md)에 있다.

## 1. 무엇을 바꿨나

| 영역 | 변경 | 위치 |
|---|---|---|
| 입력 문서 | `DocumentKind.PROPOSAL_TEMPLATE`("제안서 템플릿(PPT)", `.pptx`, 제안 단계 선택 문서). 업로드 시 용도(`template_purpose`: submission/presentation, 미지정이면 용지 방향으로 추정)를 받는다. 추출 대상이 아니므로 `extract_all`에서 건너뛰고 Gate 0에 영향 없음 | `models/enums.py`, `models/project.py`, `services/document_service.py`, `ingest/service.py` |
| 템플릿 프로파일(신규) | `profile_template()`: 용지·레이아웃, 반복 좌표의 머리글 상자(2단), 리드 상자, 본문 영역, ※ 주석 위치, 장 표지 요소(제목·로마숫자·절 목록 상자), 레이아웃 고정 장 라벨·띠 색, 쪽번호 패턴, 글꼴·크기·색, 표 머리글 색·표 유형, 장/절/소절 구성, 작성 관행 문장(`conventions`). `TemplateService`가 등록 문서를 읽어 용도별 최신 템플릿을 돌려준다 | `generators/pptx/template.py`, `services/template_service.py` |
| 템플릿 기반 빌더(신규) | `TemplateDeckBuilder`: 템플릿 파일의 마스터·레이아웃을 그대로 쓰고 기존 슬라이드만 제거. `begin_chapter`(장 표지) → `begin_section`(절 번호) → `bullet_slides/table_slides/image_slide`(소절 번호 자동, "(계속)" 분할, 리드 메시지, ※ 주석). 장 전용 레이아웃이 있으면 그 레이아웃(쪽번호 `Ⅲ - N`), 없으면 장 라벨 덮어쓰기. 글머리 수·글자 수·표 행 수는 본문 영역과 글꼴 크기에서 계산 | `generators/pptx/template.py` |
| RFP 지정 목차 트리 | Phase 11 프로파일에 `proposal_toc_tree`(장 → 절 → 작성방법). 표가 행 단위로 쪼개져 장 행이 절 줄 뒤에 오는 PDF, 한 셀에 "1. … 2. …"가 이어지는 경우, RFP 자체 장 제목(Ⅴ. 제안서 작성요령) 제외, 쪽번호 줄 제외를 처리 | `ingest/rfp_profile.py`, `ingest/service.py` |
| 장 계획 | `plan_chapters()`: 장·절 뼈대 = RFP 목차 트리 → 템플릿 샘플 장·절 → 단일 장. 목차 항목(에이전트 소절/기본 섹션)을 에이전트 지정 장·절 번호 → 절 제목 키워드 → 장 제목 힌트 순으로 배치하고, 내용 없는 RFP 절은 "RFP 작성방법 … / 사람 작성 필요" 자리표시 소절로 채운다 | `generators/pptx/outline.py` |
| 제출용·발표용 PPT | `build_submission_deck(template_profile, template_data, toc_tree, chapters)`: 표지 → 목차(장/절) → 장마다 표지·절·소절. 템플릿 없으면 기존 16:9 기본 빌더(장/절 API 호환). 발표용도 발표용 템플릿이 등록되면 같은 빌더 사용(다음 작업에서 발표 관행 반영 예정) | `generators/pptx/decks.py`, `builder.py`, `generators/service.py` |
| 제안 문안 에이전트 | `ProposalSection`에 `chapter/section/number/lead_message/table_headers/table_rows/requirement_ids/footnotes` 추가(모두 선택). `GenerationService.proposal_brief()`가 `<proposal_template>`·`<rfp_toc>`·`<data>`(요구사항 ID+RFP ID, 구성 요소, 조사, WBS 상위, 인력)를 조립하고 `StepRunner.run_proposal_writing()`이 proposal_writer를 실행(Gate 1 필요). 프롬프트 규칙 9개로 재작성 | `agents/schemas.py`, `agents/prompts/proposal_writer.md`, `orchestrator/runner.py` |
| 검토 | 통합 QA **QA-FILE-11 "제안서 템플릿 준수"**(용지 크기, 본문 슬라이드 머리글 2단 위치, 장 표지 로마숫자 순서 = RFP 목차, 템플릿 글꼴 비율; 템플릿 미등록이면 해당 없음). QA-FILE-02는 템플릿 용지 크기와 대조(16:9 가정 제거). PPT 넘침 추정에 글꼴 크기 반영. `qa_reviewer` 입력에 템플릿 요약·목차 트리, 프롬프트 항목 7 | `validation/independent_qa.py`, `validation/deliverables.py`, `validation/qa_service.py`, `agents/prompts/qa_reviewer.md` |
| UI | 프로젝트 화면: 템플릿 업로드 시 용도 선택. 산출물 화면: "제안서 템플릿" 패널(프로파일 요약·경고·RFP 지정 목차), "제안 문안 작성(에이전트)" 버튼, 저장된 문안 표시 | `ui/app_pages/project.py`, `ui/app_pages/deliverables.py` |
| 수동 실행 스크립트 | `--template <pptx>`(여러 개 가능), `--name <프로젝트명>`(기존 프로젝트 보존) | `scripts/run_manual_agents.py` |
| 저장소 결함 수정 | `architecture_components` PK가 전역 `id`라 두 번째 프로젝트에서 구성 요소 코드(CLI01)가 UNIQUE 위반 → 마이그레이션 7로 `(project_id, id)` 복합 키 | `storage/migrations.py`, `storage/repositories.py` |

## 2. 실제 확인 결과

- pytest **238 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_proposal_template.py` 7건, 픽스처 `build_template_pptx()`(A4 세로 가상 양식: 장 표지 + 본문 6장, 머리글 2단·리드·표·※)와 구조화 RFP 목차 표에 절 항목 추가. 기존 E2E는 미실행 2건(QA-RFP-07, QA-FILE-11)으로 기대값 조정. `ruff check/format`, `mypy src` 통과.
- 실샘플 템플릿(저장소 밖): 고객 제공 샘플(Ⅰ·Ⅲ장) 프로파일 인식 결과와 계산기 RFP 전체 흐름(제출용 PPT 17장 A4, QA 28 통과/0 실패/3 검토(기술 조사 미확인)/1 미실행, QA-FILE-11 통과, gate4 PASS)은 [TEST_RESULTS.md](TEST_RESULTS.md) §1 참조. 생성 파일: `Output/Project_20261015_공학용_계산기_웹_개발_(템플릿_적용)/07_Submission_Proposal_PPT/제안서_제출용_v1.0.pptx`.
- 실제 Claude 모델로 proposal_writer를 실행한 결과는 없다(크레딧 부족). 템플릿 관행을 담은 프롬프트와 브리프는 FakeAgentRunner로만 검증했다.

## 3. 한계·다음 작업

- 한계는 [LIMITATIONS.md](LIMITATIONS.md) §3 "제안서 템플릿 인식" 참조(머리글 미검출 시 기본 배치, 장 전용 레이아웃 없는 장의 라벨 덮어쓰기, A3 별지 미지원, 도식 미재현).
- RFP 목차가 없고 템플릿이 한 장(Ⅰ장)만 담고 있으면 다른 장을 알 수 없어 모든 절이 그 장 아래에 들어간다. 장마다 템플릿 파일이 있으면 각각 등록하거나(현재는 용도별 최신 1개만 사용), RFP를 등록해 목차 트리를 얻는 것이 낫다. 장별 템플릿 병합은 발표용 작업 뒤 후속 과제.
- 다음 작업(발표용 제안서 샘플): 같은 `PROPOSAL_TEMPLATE`(용도 presentation)로 등록 → `profile_template`이 가로 용지·발표 관행을 읽도록 보강하고, `build_presentation_deck`에 핵심 메시지·발표자 노트 관행을 반영할 예정.
