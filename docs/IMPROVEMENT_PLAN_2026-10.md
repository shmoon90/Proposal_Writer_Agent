# 품질 고도화·편집 가능 산출물 개선 계획 (2026-10-16, 승인 대기)

요청 문서("Claude Code 통합 개발 지시문")의 19개 절을 기존 구현(Phase 1~15, main `ab75fba`)과 대조해 차이를 정리하고, 기존 동작을 보존하면서 단계적으로 반영하는 계획이다. **이 문서는 계획이며, 사용자 승인 후 단계별로 구현한다.** 실제로 구현·검증한 것은 각 단계 보고서(PHASE16~)에 적는다.

## 1. 기존 프로젝트 분석 요약 (현재 상태)

| 영역 | 현재 구현 | 근거 |
|---|---|---|
| 실행 엔진·UI | Claude Agent SDK(Python) 어댑터 + FakeAgentRunner, Streamlit 6화면, 인프로세스 MCP `pwa`(10 도구) | `agents/runner.py`, `ui/`, `agents/tools/project_tools.py` |
| 에이전트 | 11역할(rfp_analyst, requirement_extractor/verifier, tech_researcher(WebSearch/WebFetch), approach_writer, architect, planner, proposal_writer, document_generator, qa_reviewer, semantic_differ), 역할별 프롬프트·스키마·도구 화이트리스트 | `agents/roles.py`, `agents/prompts/*.md` |
| RFP 분석 | 절·자체 ID·목차·평가·제출 조건 프로파일(`rfp_profile`), 블록 단위 추출·출처 좌표·독립 검증, Gate 0·1 | Phase 2·11 |
| 요구사항 데이터 | ID·출처·원문 인용·분류·난이도·검사 기준·구현 방안(에이전트+규칙 초안)·변경 상태; 정의서 31열·추적표 25열(묶음 머리글·색) | Phase 14 |
| 기술 조사·근거 | 출처 URL·신뢰도·확인 시점·미확인 항목, 조사 선행 강제, 구현 가능성 비교 | Phase 3·13 |
| 계획 | WBS 상세/약식·주 간트·마일스톤·투입계획(구성원별 월별 MM) 코드 계산 | Phase 4·15 |
| PPT | python-pptx, 템플릿(고객 양식) 마스터 위 장/절/소절, 도형·연결선·표 10종 도식(`shapes.py`), 그림 삽입 0(QA-FILE-12), 제출용·발표용 별도 빌더 | Phase 12·13 |
| QA | 독립 검증 35항목(RFP 7·기술 7·일관성 9·파일 12), Gate 2~5, 재생성 자동 수정, QA 보고서 md | Phase 7·13·14 |
| 저장 | `Output/<프로젝트>/00_~13_` 폴더, `_vX.Y` 버전 파일명, Revision 스냅샷, 감사 로그 | `OUTPUT_STRUCTURE.md` |
| 테스트 | pytest 253 passed(단위·통합·UI), 실샘플 재검증 명령, 민감 용어 검사 | `TEST_RESULTS.md` |
| 환경 확인(2026-10-16) | PowerPoint COM 등록됨 + pywin32 설치됨(렌더링·재열기 검증에 사용 가능), LibreOffice 없음, API 크레딧 없음(실제 모델 호출 미검증) | 이 세션 점검 |

## 2. 요구사항 ↔ 현재 구현 차이

판정: **충족** / **부분**(구조는 있으나 요구 범위에 못 미침) / **미충족**.

| 절 | 요구 | 판정 | 차이·필요한 변경 |
|---|---|---|---|
| 2 환경 원칙 | SDK·Streamlit·MCP 유지, 하드코딩 금지, 미연결 기능을 완료로 보고 금지 | 충족 | 유지. 상태 기록에 연결 상태를 항상 명시 |
| 3 RFP 분석 항목 | 배경·범위·현행 문제·기능/비기능·보안/개인정보·연계·이관/운영·개발환경·일정/산출물·시험/검수/교육/안정화/유지관리·목차/지침·페이지 제한/규격·평가·필수 제출/별첨 | 부분 | `RfpAnalysis`에 현행 문제점·보안/개인정보 규정·데이터 이관/운영·시험/검수/교육/유지관리·페이지 제한/문서 규격·필수 제출/별첨 필드 추가, `rfp_profile`에 페이지 제한·제출 형식 파싱, 프롬프트 갱신 |
| 3 추적표 항목 | 대응 전략·**대응 제안서 페이지**·근거 자료·검토 상태 | 부분 | 추적표에 '대응 전략'·'대응 제안서 페이지(제출용/발표용 슬라이드 번호)'·'근거 구분' 추가. 덱 생성 후 소절의 `requirement_ids` ↔ 슬라이드 번호를 역산해 채움 |
| 3 근거 구분 | RFP 명시 / 참고 문서 / 외부 조사 / 설계 제안 구분, 근거 없는 수치 금지 | 부분 | `Requirement.evidence_class`·`ProposalSection.evidence[]`(종류·출처) 추가, QA에 '근거 없는 수치·실적·효과' 검사(QA-CON-10) |
| 3 입력 자료 부재 처리 | 파일이 없으면 가정하지 않고 안내 | 충족 | 문서 등록·추출 실패 시 오류 안내 존재(IngestError). 유지 |
| 4 목차·전략 승인 | RFP 요약·요구사항·대응 방향·목차 초안·전략 3~5·차별화·핵심 기술·위험·제출/발표 차이·확인 필요 사항을 **승인 후** 작성 | 미충족 | 새 단계 **전략·목차 브리프**(`strategy_planner` 역할 또는 proposal_writer 1단계)와 **Gate P(목차·전략 승인)** 추가. 승인 전 `run_proposal_writing` 차단(샘플 슬라이드만 허용), UI 승인 화면 |
| 5 슬라이드별 메시지 설계 | 번호·제목(결론형)·핵심 메시지·목적·독자·근거·시각화·RFP 연결·앞뒤 연결 | 부분 | `ProposalSection`에 `key_message`(결론형 제목)·`purpose`·`audience`·`evidence`·`links_prev/next`·`layout_type` 추가. 소절 → 슬라이드 명세(`source/slide_spec_vX.json`) 산출. 프롬프트: 긴 글머리 나열 금지·결론형 제목 |
| 6 기술 제안 구체성 | 문제·입력·절차·규칙·구성요소·데이터 흐름·연계·예외·보안·성능·검증·한계; 상용/공개/자체 비교 | 부분 | 조사 `comparisons`·구현 방안·구성도는 있음. 기술 소절 구조 템플릿(`tech_detail` 필드)과 추상 표현 금지 목록, 대안 비교 표(상용/공개/자체) 소절 생성, QA-CON-10 추상 표현 검사 |
| 7 기술 조사·근거 관리 | 공식 문서 우선·버전·확인 시점·미확인 명시 | 충족 | 유지(`ResearchSource.accessed_at`·`trust`·`unverified_items`). 주장↔근거 연결은 §5 evidence로 보강 |
| 8 제출용/발표용 별도 설계 | 규격·페이지 제한 준수, 발표용 압축·발표자 노트 | 부분 | 빌더는 별도. 페이지 제한(QA) 미구현 → RFP 페이지 제한 파싱 + QA-FILE-13. 발표용 `speaker_notes` 활용 확대 |
| 9 비전문가 표현 | 용어 설명·약어 풀이·문제 먼저 | 미충족 | 프롬프트 규칙 + 용어집(`glossary`) 소절 자동 생성 + QA 약어 미설명 검사(QA-CON-11) |
| 10 편집 가능 산출물 | 텍스트 상자·실제 표·개별 도형/연결선·**편집 가능 차트**·UI 목업 개별 객체·그룹 해제 가능·사진/일러스트는 이미지 허용 | 부분 | 도형·표·연결선은 충족. **차트는 도형 막대**(python-pptx 네이티브 차트 미사용) → `add_chart` 네이티브 차트 도입. UI 목업은 영역 수준(`draw_screen`) → 입력 필드·버튼·메뉴·탭·메시지 개별 객체로 확장. **그림 정책 변경**: 현재 QA-FILE-12는 그림 1장이라도 실패 → 사진/일러스트(태그 `photo:`)는 허용, 정보성 자료(표·구조도·차트·목업)의 이미지화만 금지. 그룹화 지원(`group_shapes`) |
| 11 디자인 명세 | 슬라이드별 레이아웃·배치·시각화 유형·데이터 출처·편집 객체 계획·이미지 사유·글꼴/색 규칙 | 부분 | 목차 결정 JSON·템플릿 프로파일에 일부 있음 → **슬라이드 디자인 명세** 산출물(`source/design_spec`)로 통합, 시각화 유형 13종 매핑(현재 10종 + RACI·데이터 모델·운영/장애 절차·보안 통제) |
| 12 라이브러리 검토 | python-pptx 지원 범위 확인 | 부분 | python-pptx: 텍스트·도형·연결선·표·차트·그림·그룹(`shapes.add_group_shape`) 지원 확인됨. SVG 아이콘·렌더링은 미지원 → 렌더링은 PowerPoint COM(설치 확인됨) 보조, SVG는 도형으로 대체. 검토 결과를 문서화 |
| 13 QA 분리·실제 검증 | 내용·디자인·편집 가능성·파일 안정성 분리, 객체 구조 검사 + **실제 렌더링** 둘 다, 체크리스트 10항목, 이미지 예외 기록 | 부분 | 객체 구조 검사(잘림·겹침·그림·템플릿)는 있음. **렌더링 검증 없음** → PowerPoint COM으로 PNG 내보내기·재열기 검증(QA-FILE-14, 없으면 '미실행'). 편집 가능성 체크리스트 10항목을 QA-EDIT-01~10으로 분리, 그림 예외 보고. 검토 범주를 내용/기술/디자인/편집 4개 독립 실행으로 재편 |
| 14 회귀 테스트 | 추출·목차·PPT 2종·Excel·편집 가능성(텍스트/도형/표/도식/목업/사진)·재열기·잘림/겹침·근거·오류·외부 연결 실패 | 부분 | 대부분 존재(253건). 추가: 목업 편집 요소, 사진 삽입 허용, 네이티브 차트, 렌더링(COM 없으면 skip=미실행), 목차·전략 승인 흐름, 추상 표현/근거 QA |
| 15 저장·버전 | `Output/<project>/`에 submission/presentation/excel/qa/source + manifest.json | 부분 | 기존 `00_~13_` 구조 유지(요청서도 기존 구조 통합 허용). **manifest.json**(산출물·생성 시각·버전·검증 결과·해시) 추가, `source/` 역할은 `02_~06_`·목차 결정·슬라이드 명세로 대응 |
| 16 진행 기록 | `workspace/DEVELOPMENT_STATUS.md/.json`, `WORK_LOG.md` | 미충족 | 이번 계획과 함께 생성(이 세션), 이후 단계마다 갱신. 테스트 결과와 일치 검사 스크립트 |
| 17 진행 순서 | 1~14 | — | 아래 3절의 단계 순서가 이를 따른다 |
| 18·19 완료 보고 기준 | 생성하지 않은 산출물·미실행 테스트를 완료로 보고 금지, 4기준 모두 충족 | 충족(원칙) | 각 단계 보고서에 실제 경로·실행 결과·미실행 명시(기존 관행 유지) |

## 3. 단계별 구현 계획

각 단계는 "구현 → ruff/mypy/pytest 전체 → 실샘플(계산기 RFP + 고객 템플릿, API 키 없이 대행 응답) 재검증 → 보고서·진행 기록 갱신 → main 병합" 순서를 지킨다. 실제 모델 호출은 크레딧이 생기면 별도로 검증한다.

| 단계 | 내용 | 주요 파일 | 검증 | 승인 필요 |
|---|---|---|---|---|
| **16. 진행 기록·manifest·그림 정책** | `workspace/DEVELOPMENT_STATUS.md/.json`·`WORK_LOG.md` 생성과 갱신 규칙, 산출물 `manifest.json`(목록·시각·버전·해시·QA 결과), 그림 정책(사진/일러스트 허용 태그, 정보성 자료 이미지 금지) + QA-FILE-12 개정, python-pptx 지원 범위 검토 문서 | `generators/service.py`, `validation/`, `docs/LIBRARY_REVIEW.md`, `workspace/` | 단위 테스트, manifest 생성 확인 | 아니오 |
| **17. RFP 분석·추적표 확장** | `RfpAnalysis`·프롬프트에 §3 항목 추가, 페이지 제한·제출 형식 파싱, `Requirement.evidence_class`, 추적표 '대응 전략·대응 제안서 페이지·근거 구분', 덱 생성 후 슬라이드 번호 역산 | `agents/schemas.py`, `prompts/rfp_analyst.md`, `ingest/rfp_profile.py`, `generators/excel/trace_matrix.py`, `generators/service.py` | 픽스처 RFP·실샘플 RFP로 파싱 확인, 추적표 페이지 열 검증 | 아니오 |
| **18. 목차·전략 승인(Gate P)** | 전략·목차 브리프(10항목) 생성 역할, 저장(`07_…/전략브리프_vX.json`+md), UI 승인 화면(수정 후 승인), 승인 전 전체 작성 차단·샘플 슬라이드 허용, 승인 기록(Approval) | `agents/roles.py`, `prompts/strategy_planner.md`, `orchestrator/gates.py`·`runner.py`, `ui/app_pages/deliverables.py` | 게이트 테스트, UI 흐름 테스트 | **예 — 브리프 형식·승인 화면은 구현 후 사용자 확인** |
| **19. 슬라이드 명세·기술 구체성·비전문가 표현** | `ProposalSection` 확장(key_message·purpose·audience·evidence·links·layout_type·tech_detail), 슬라이드 디자인 명세 산출(`source/slide_spec`), 시각화 유형 13종, 기술 소절 템플릿·대안 비교(상용/공개/자체), 용어집 소절, 프롬프트(결론형 제목·글머리 제한·용어 설명), QA-CON-10(추상 표현·근거 없는 수치)·QA-CON-11(약어 미설명) | `agents/schemas.py`, `prompts/proposal_writer.md`, `generators/pptx/outline.py`·`decks.py`, `validation/independent_qa.py` | 단위·통합 테스트, 실샘플 덱 검토 | 아니오 (프롬프트 결과는 실제 모델 실행 후 보정) |
| **20. 편집 가능 객체 강화** | 네이티브 차트(`add_chart`: 공수·일정·통계·비교), UI 목업 컴포넌트(입력 필드·버튼·메뉴·탭·메시지·구획), 그룹화(`add_group_shape`, 해제 가능), RACI·데이터 모델·운영/장애 절차·보안 통제 도식, 사진/일러스트 삽입 API(태그) | `generators/pptx/shapes.py`·`builder.py`·`template.py`·`decks.py` | 객체 구조 테스트(도형 수·차트 타입·그룹), 실샘플 덱 | 아니오 |
| **21. 렌더링·편집 가능성 QA·회귀 테스트** | PowerPoint COM 렌더링(PNG 내보내기·재열기, 없으면 미실행), QA-EDIT-01~10 체크리스트, QA 범주 4분리 실행, QA-FILE-13(페이지 제한), 회귀 테스트 추가(목업·사진·차트·렌더링·승인 흐름), 최종 보고서(§18 13항목) | `validation/render.py`(신규), `validation/independent_qa.py`, `tests/` | 전체 테스트, 실샘플 생성·렌더링 결과 | 아니오 |

예상 규모: 단계당 이 세션 기준 1회 작업 분량(코드·테스트·문서). 16→17→18 순서는 고정(18은 17의 분석 항목을 브리프에 씀), 19·20은 병행 가능하나 같은 파일(`decks.py`)을 건드리므로 순차 진행한다.

## 4. 기술 검토 결정(제안)

- **PPT 라이브러리**: python-pptx 유지. 텍스트·도형·연결선·표·네이티브 차트·그림·그룹 생성 지원이 확인되며 기존 템플릿 빌더가 그 위에 있다. 미지원(SVG 아이콘 편집, 렌더링)은 도형 대체·PowerPoint COM으로 보완한다. 교체 시 영향 범위(빌더·템플릿·도식·QA 전부)가 커서 교체하지 않는다.
- **렌더링 검증**: 이 PC에 PowerPoint COM(`PowerPoint.Application`)과 pywin32가 있어 슬라이드 PNG 내보내기·재열기 검증이 가능하다. 설치되지 않은 환경에서는 QA 항목을 '미실행'으로 남긴다(성공으로 표시하지 않음).
- **그림 정책**: 사진·일러스트·장식 배경은 이미지 삽입 허용(선택·이동·교체 가능 객체), 정보성 자료 이미지화는 금지. 구분은 삽입 시 태그(`photo`, `illustration`, `decoration`)와 QA 보고의 예외 목록으로 관리한다.
- **승인 흐름**: 기존 Gate 체계(Approval 엔티티·감사 기록)에 Gate P를 추가하고, Gate 1 → 조사 → **Gate P(목차·전략)** → 작성 → Gate 5 순으로 둔다.

## 5. 위험·제약

- 실제 모델 호출(크레딧)이 없어 프롬프트 변경의 효과(결론형 제목·기술 구체성·비전문가 표현)는 FakeAgentRunner·수동 대행 응답으로만 검증된다. 실제 실행 후 보정 단계가 필요하다.
- PowerPoint COM 렌더링은 Windows+PowerPoint 환경에서만 동작하며 CI에서는 미실행이 된다.
- 고객 샘플 자료(RFP·제안서·정의서·추적표·WBS·투입계획)는 계속 저장소 밖에서만 참고한다(민감 용어 검사 유지).
- 추적표 '대응 제안서 페이지'는 덱을 생성해야 채워지므로 Excel 생성 순서를 덱 생성 뒤로 바꿔야 한다(현재 Excel → PPT 순서).

## 6. 승인 요청

위 3절의 단계 순서(16→21)와 4절의 결정(python-pptx 유지, PowerPoint COM 렌더링, 그림 정책, Gate P 추가)으로 진행해도 되는지 확인을 요청한다. 승인되면 16단계부터 시작하고, 18단계(승인 화면·브리프 형식)는 구현 후 다시 확인을 받는다.
