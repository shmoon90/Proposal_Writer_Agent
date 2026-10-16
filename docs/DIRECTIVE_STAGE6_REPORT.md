# 통합 개발 지시문 단계 6 보고서 — 화면·DB·API·아키텍처 설계 (2026-10-16)

범위: `workspace/IMPLEMENTATION_PLAN.md` 단계 6(①~⑥, ⑥-0), 결정 D-21(발주처 문맥 주입·구현 방안 구체성 검사)·D-22(설계 객체를 코드 생성 입력 규격으로). A-6(실제 모델 1회 검증) 은 크레딧이 없어 수행하지 못했다(미검증으로 기록). 브랜치 `feature/major-revision`.

## 1. 무엇을 만들었나

| 항목 | 구현 | 위치 |
|---|---|---|
| ①·⑥-0 상세 설계 객체·에이전트(§12.1~12.3, D-22) | 새 역할 **`detail_designer`**(스키마 `DetailDesignReport`): 화면(유형·목적·사용자 역할·배치 영역·**항목(형식·필수·검증 규칙·오류 메시지)**·동작(기대 결과·호출 API)·상태 메시지·기능 정의), 테이블(물리/논리명·**컬럼(자료형·길이·NULL·PK·FK·제약·개인정보)**·인덱스·관계·보존 정책·이관·DB 종류), API(메서드·경로·**요청 필드·응답·인증·오류 코드**·검증·멱등성·타임아웃·페이징·로깅·버전·화면/테이블/모듈 연결), **코드 모듈(경로·계층·책임·의존)**, 업무 규칙, 가정. 결과는 `Screen`(확장: purpose/user_roles/layout/fields/actions/states/functions/related_requirement_ids/source)·`DbTable`·`ApiSpec`·`CodeModule`(+`depends_on`)·`DesignItem`(business_rule) 로 저장(같은 이름은 갱신·버전 ↑, 빠진 것은 dropped, RFP 고유번호는 내부 ID 로 변환), 요구 ↔ 화면 추적(`RequirementTrace`) 연결. 파이프라인 단계 **`detail_design`**(impl_design 뒤, Gate 1 필요) | `agents/schemas.py`, `agents/prompts/detail_designer.md`, `agents/roles.py`, `models/design.py`, `design/service.py`(`DetailDesignService.brief/persist/consistency/codegen_package`), `orchestrator/runner.py`(`run_detail_design`), `services/pipeline_service.py` |
| ⑤ 발주처 문맥 주입(D-21) | `design/context.py` `client_context_block`: RFP 분석(사업 목적·발주처 목표·**현행 문제점**·연계 대상·명시 솔루션·개발 환경·보안 규정·이관/운영·제약) + 프로젝트 설정(기존 시스템 유무·설명·연계 시스템·외부 솔루션·RFP 지정 기술)을 `<client_context>` 블록으로. 없는 항목은 "(없음)" 으로 명시해 추정을 막는다. **approach_writer·design_writer·detail_designer** 프롬프트에 주입하고 프롬프트 규칙에 "왜 이 방식인가를 현행 문제·연계·제약과 연결" 추가 | `design/context.py`, `requirements/approach.py`(`_prompt(project=)`), `requirements/design.py`(`brief`), `agents/prompts/*.md` |
| ② 추적·누락·모순 검사 | `design/consistency.py` `design_consistency_issues`: 실패 = 필수 기능 요구에 화면·API·테이블 연결 없음, API 가 가리키는 화면·테이블 없음, FK 참조 테이블 없음, 모듈 의존 없음·순환, 존재하지 않는 요구 ID 참조. 검토 = 비필수 연결 없음·비기능 미연결, 개인정보 테이블 API 인증 누락, 오류 코드 없음, 상태 메시지 없음. **QA-CON-15**(설계 객체 있을 때만 실행) | `design/consistency.py`, `validation/qa_checks/consistency.py` |
| ③ DB 호환성 검토 | 테이블 `db_engine` 을 아키텍처 구성 요소 기술·조사 권고 스택·RFP 지정 기술과 대조 — 미지정·불일치·식별 불가는 검토 | `design/consistency.py` |
| ④ 변경 영향 반영 | 단계 5의 영향 확장(`_extend_impact`)이 이제 실제 API·테이블·설계 항목을 찾아 채움(추적표 '미정' 열도 설계 후 값이 들어감) | (단계 5 코드 그대로) |
| ⑥ 구현 방안 구체성 검사(D-21) | **QA-TECH-09 구현 방안 구체성(내용 수준)**: 설계 객체가 있을 때 기능 요구의 구현 방안·분석·설계가 실제 화면·테이블·API 이름을 언급하는지(필수 요구에 없으면 실패), 요구사항 수치 조건(초·건·명·%·개월·일…)이 구현 방안·설계에 그대로 있는지(검토), 필수 기능 요구에 예외·실패 처리 문장이 있는지(검토). 설계 객체가 전혀 없으면 검토 1건. 두 모드 공통. 총 **57항목** | `validation/qa_checks/tech.py`(`_approach_concreteness_issues`) |
| 산출물 | **설계서** Excel(`05_Architecture_Design/설계서_vX.Y.xlsx`: 화면목록·화면항목·화면기능·DB테이블·DB컬럼·API목록·API상세·모듈·업무규칙·요구-설계추적) + Markdown(같은 내용 + 추적·모순 검사 결과). 산출물 생성 시 설계가 있으면 자동 포함, 설계 화면에서 따로 생성 가능. **코드 생성 입력 패키지**(D-22) `codegen_package_vX.json`: RFP_JAVA Developer 입력 모양(requirements 명세·ui_design 화면·architecture 모듈/데이터/API/규칙/test_plan(단계 7)) | `generators/excel/design_docs.py`, `generators/service.py`(`_design_doc_deliverables`·`generate_design_docs`), `design/service.py`(`codegen_package`·`export_codegen_package`) |
| 화면·스크립트 | 새 화면 '설계': 상세 설계 실행, 화면/테이블/API/모듈/규칙 탭, 추적·모순·DB 호환성 검사, 설계서·패키지 생성. 대행 스크립트: 계산기 상세 설계 대행 응답(화면 2·테이블 1·API 3·모듈 5·규칙 2) + 실제 RFP fixture(저장소 밖: 화면 4·테이블 4·API 6·모듈 11·규칙 5) → 설계 단계 실행·패키지 내보내기 | `ui/app_pages/design.py`, `app.py`, `scripts/run_manual_agents.py` |

## 2. 확인 결과

- pytest 329 passed, 1 skipped(전체, llm 제외; 단계 5 대비 +5: 신규 tests/unit/test_stage6_detail_design.py — 발주처 문맥 블록(분석+설정 병합, 없는 항목 "(없음)"), 상세 설계 스키마·추적/누락/모순/DB 호환성 판정(FK 없음·존재하지 않는 요구·순환·필수 연결 없음·개인정보 API 인증·DB 불일치), 엔티티 저장(코드 발급·RFP 고유번호 변환·갱신 버전·dropped·추적 연결)·코드 생성 패키지·설계서 Excel/MD·추적표 열 채움·generate_design_docs, 파이프라인 단계 순서·FakeAgentRunner 실행, QA-TECH-09 판정). 기존 테스트 4곳 갱신(역할 목록, E2E executed 53·not_run 4, 진행률 분모 18, 기준선 화면 제외). 백그라운드 작업 취소 테스트의 간헐 실패(잃어버린 갱신: set_resume_point 가 옛 복사본으로 덮어씀)를 레코드 락 + DB 최신 레코드 갱신으로 고쳐 5회 연속 통과. ruff·mypy(150 파일) 통과. 민감 용어 검사 통과.
- 계산기 샘플(모의 에이전트, 렌더링): detail_designer 대행 → 화면 2·테이블 1·API 3·모듈 5·규칙 2 저장, 추적 12건 연결, 설계서 Excel(10시트)·MD, codegen_package_v1.0.json. QA 57항목 중 54 실행·45 통과·0 실패·9 검토(단계 5 대비 통과 +1 = QA-CON-15, 검토 +1 = QA-TECH-09: 예외 처리 서술 없는 요구 3건·수치 조건 '21자리' 미기재). 첫 실행에서는 FR-004·007·008·009 가 설계 객체에 연결되지 않아 CON-15·TECH-09 가 실패했고(검사가 의도대로 누락을 잡음), 설계 대행 데이터를 보강해 통과.
- 실제 고객 RFP(저장소 밖 fixture·템플릿 2종): 화면 7·테이블 4(컬럼 28)·API 6·모듈 14·규칙 5 저장, 추적 22건, 설계서 추적 시트 42행 중 연결 25·연결 없음 15(관리성 비기능 요구·평가/제출 조건은 설계 대상 아님). QA 57 전부 실행·48 통과·0 실패·9 검토(단계 5 대비 검토 +2: TECH-09 예외 처리 서술, CON-15 비기능 요구 미연결 8건). 첫 실행에서는 FR-001·004·010~016 미연결로 실패 → 대시보드·정보 조회 표·통계 메뉴 화면과 web 모듈을 설계 데이터에 추가해 통과.
- 미검증: 실제 Claude 모델(A-6) — detail_designer 가 이 깊이(검증 규칙·오류 코드·컬럼·의존)를 실제로 내는지, 발주처 문맥 주입이 구현 방안 문장을 바꾸는지는 알 수 없음. 설계 화면은 Streamlit 을 띄워 보지 않고 코드·타입 검사만 했다.

## 3. 남은 것·다음 단계

- 상세 설계의 깊이는 에이전트 출력에 달려 있고 실모델은 미검증(A-6). 대행 데이터는 제가 쓴 것이라 "모델이 이 깊이를 내는지"는 알 수 없다. 구체성·추적 검사(TECH-09·CON-15)는 모델 출력의 형식적 깊이를 잡지만 업무 적합성은 사람이 봐야 한다.
- 발주처 문맥 주입은 RFP 분석과 설정에서만 가져온다. 회의록·인터뷰에서 확정된 결정(단계 5 DEC)을 문맥에 넣는 것은 단계 8 통합에서 보강.
- 화면 설계의 와이어프레임(시각)은 만들지 않았다. 코드 생성 입력에는 배치(영역·컴포넌트)만 있으면 충분하고, 그림은 단계 8 이후 선택 과제.
- 코드 생성 패키지의 `test_plan` 은 비어 있다 — 단계 7 테스트 케이스(TC) 가 채운다.
- 다음: 단계 7(WBS 분해·개발 관리·테스트·검수·운영 이관 + RFP_JAVA 발췌 이식 `development/`).
