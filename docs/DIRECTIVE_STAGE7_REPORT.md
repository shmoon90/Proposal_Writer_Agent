# 통합 개발 지시문 단계 7 보고서 — WBS·개발·테스트·검수·운영 이관 + RFP_JAVA 발췌 이식 (2026-10-16)

범위: `workspace/IMPLEMENTATION_PLAN.md` 단계 7(①~⑤, ⑦), 결정 A-2·D-22(RFP_JAVA 에서 코드 생성 이후 부분만 발췌 이식, 중복 기능 제외, 생성물은 Spring Boot 프로토타입이며 납품 코드가 아님). A-6(실제 모델 1회 검증) 은 크레딧이 없어 수행하지 못했다(미검증으로 기록). 브랜치 `feature/major-revision`.

## 1. 무엇을 만들었나

| 항목 | 구현 | 위치 |
|---|---|---|
| ⑦ RFP_JAVA 발췌 이식 — `development/` | **constants**(생성 앱 고정 경로·base package `com.app`·허용 확장자·요구사항 ID 패턴), **inspector**(정적 검사: 중괄호·package·파일명=타입·허용/금지 import·금지 호출·정의 이름·테스트 @DisplayName 요구 ID·내부 import 존재), **test_runner**(Docker 격리: `--network none --read-only`, 읽기 전용 /app 마운트, 오프라인 Maven·JUnit, surefire 해석·컴파일 오류 추출·타임아웃 강제 종료), **workspace**(경로 탈출·링크·예약 이름 거부, 허용 확장자·200KB 제한, 원자적 쓰기, 스냅샷·복원), **plan**(의존 순서 위상 정렬 배치, 테스트 마지막, 생성 규칙 밖 모듈 제외), **templates**(pom 3.4.5·Java 21·web/validation/test 고정, Application, properties, README), `docker/`(test-runner Dockerfile·run-tests.sh·seed). RFP_JAVA 의 러너·오케스트레이터·화면·설계 에이전트·문서 생성기는 가져오지 않음 | `development/*.py`, `docker/` |
| 설계 변경(이 프로젝트 보안 모델 유지) | RFP_JAVA 는 에이전트가 Write/Edit 도구로 파일을 직접 썼지만, 이 프로젝트는 파일 도구를 금지하므로 **Developer 가 파일 내용을 구조화 출력(`CodeBatchReport.files[].content`)으로 돌려주고 코드가 안전 쓰기·검사·테스트**를 한다. MCP `inspect_code/run_tests/get_test_result` 는 이식하지 않고 오케스트레이터 루프가 검사·테스트 결과를 `<errors>`·`<test_result>` 로 다시 넣는다 (D-23) | `agents/prompts/developer.md`·`code_qa.md`·`code_fixer.md`, `agents/roles.py`(developer·code_qa·code_fixer), `agents/schemas.py` |
| 코드 생성·테스트·수정 루프 | `DevelopmentService`: 템플릿 준비 → 배치 계획 → 배치별 developer 호출(대상 밖 파일·빈 내용·없는 요구 ID·정적 검사 오류·implementation_map 미정의 이름은 거부, 1회 재요청, 실패 배치는 스냅샷 복원) → 모듈 상태(generated/failed)·구현 위치 저장 → Docker JUnit 실행(정적 오류 있으면 실행 금지) → 결과 JSON(`14_Generated_App/test_results/testing-N.json`) → TC·DEF 반입 → `code_qa`(원인 분류·수정 지시) → `code_fixer`(기존 파일만 전체 내용) → 재검사(실패 시 복원) → 재테스트. 설정 `PWA_DOCKER_TEST_IMAGE`·`PWA_TEST_TIMEOUT_SECONDS`·`PWA_CODEGEN_MAX_FILES`·`PWA_CODE_FIX_ROUNDS` | `development/service.py`, `config/settings.py`, `config/paths.py`(`14_Generated_App`) |
| ① WBS 설계 분해 | 코드 모듈마다 '구현: <모듈>' Task 를 요구사항 겹침이 가장 큰 Task 의 상위 Activity 아래에 추가(코드 3단계 유지), 공수 = 계층 기준 MD × 난이도 가중(상 1.5·중 1.0·하 0.7), 산정 근거 기록, 상위 공수 자식 합계로 재계산 | `planning/decompose.py` |
| ②·③ 코드 모듈·테스트 케이스·결함 | `CodeModule.implementation_map`(요구 → 타입/메서드, 정적 검사로 확인). `TestingService.plan_from_design`: API → 통합 TC(정상 + 오류 코드별), 화면 기능 → 화면 TC, 요구 인수 기준 → 인수 TC(모두 draft). `record_junit`: JUnit 케이스 → TC(passed/failed/**unverified** — 실행 못한 것은 완료로 보지 않음), 실패 → DEF(open, 재현), 통과 → DEF closed·재테스트 기록. QA 분석 → DEF 원인·수정 계획, 수정 → DEF 수정 메모·회귀 메모 | `testing/service.py`, `models/design.py` |
| ④ 검수·인수 판정 | 인수 TC 에 사람이 합격/불합격(불합격 사유 필수·검수자 필수) 기록 → `검수결과서_vX.md`(요구사항별 판정·검수자·일시, 미검수는 완료 아님) | `testing/service.py`(`record_acceptance`·`acceptance_markdown`), 화면 |
| ⑤ 운영 이관 | `운영이관체크리스트_vX.md`: 모듈 배포·테이블 백업/파기(개인정보 컬럼)·API 모니터링(로깅·타임아웃)·미해결 결함·미검증 테스트·미결 결정·교육/문서 [ ] 항목 | `testing/service.py`(`handover_checklist_markdown`) |
| 문서 | `테스트계획서_vX.md`(수준별 TC 표), `테스트결과서_vX.md`(실행 이력·TC 현황·결함) | `testing/service.py`(`write_documents`) |
| 실행 단계·QA·화면 | 보조 단계 `wbs_decompose`·`test_plan`·`code_generation`·`code_test`·`code_fix`(두 모드 공통, 진행률 분모 제외, 디스패처 포함). **QA-CON-16 추적 사슬**(총 **58항목**): TC·DEF 의 존재하지 않는 요구/TC 참조·실행 기록 없는 통과는 실패, 필수 기능 요구 TC 없음·미실행 TC·미해결 DEF·생성 모듈 테스트 없음은 검토(TC·DEF 있을 때만). 새 화면 '개발·테스트'(Docker 상태·이미지 빌드·분해·계획·생성·테스트·수정 루프·TC/DEF 표·검수 기록·문서). 대행 스크립트: 계산기 설계 모듈을 Spring Boot 경로로, developer 대행(실제 컴파일 가능한 Java 6파일) → Docker JUnit 실행 | `orchestrator/runner.py`, `services/pipeline_service.py`(`EXTRA_STEPS`), `validation/qa_checks/consistency.py`, `ui/app_pages/development.py`, `scripts/run_manual_agents.py` |

## 2. 확인 결과

- pytest 337 passed, 2 skipped(전체, llm 제외; 단계 6 대비 +8: 신규 tests/unit/test_stage7_development.py — 정적 검사 규칙(package·금지 import·금지 호출·중괄호·테스트 ID·내부 import·JS 금지 패턴·중첩 제네릭 메서드), 배치 계획(의존 순서·테스트 마지막·규칙 밖 모듈 제외), 작업 폴더 안전성(경로 탈출·절대 경로·패키지 밖·확장자·배치 밖·새 파일 금지·크기·복원)·템플릿, 생성→검사→모듈 상태→실행기 스텁 테스트→TC 실패·DEF 생성→QA 수정 루프(스텁)→DEF 종료·정적 오류 시 테스트 금지, surefire 해석·결과 판정, 테스트 계획(중복 없음)·검수 규칙·추적 사슬 판정·문서 4종, WBS 모듈 분해(상위 공수 재계산·재실행 중복 없음)·보조 단계 디스패처; Docker 실제 실행 테스트는 PWA_RUN_DOCKER_TESTS=1 일 때만(이 PC 에서 1회 실행: JUnit 1건 통과, 5.9초). 기존 테스트 3곳 갱신(역할 목록 +3, E2E not_run 5, 산출물 폴더 15). ruff·mypy(163 파일) 통과. 민감 용어 검사 통과.
- 계산기 샘플(모의 에이전트, 렌더링, Docker 이미지 rfp-java-test-runner:jdk21-1): WBS 분해 모듈 Task 6건 추가(투입 배정 재계산), 테스트 계획 통합 9·화면 4·인수 11건, 코드 생성 배치 3/3·파일 6개(developer 대행: Spring Boot 계산 엔진·컨트롤러·이력 저장소·정적 화면·JUnit) → 정적 검사 오류 0 → **Docker 격리 JUnit 4건 통과(4.9초)** → TC 4건 passed 반입, 결함 0. 테스트 계획서·결과서·검수 결과서·운영 이관 체크리스트 생성. QA 58항목 중 55 실행·45 통과·0 실패·10 검토(단계 6 대비 검토 +1 = QA-CON-16: 계획만 세운 통합·화면·인수 TC 가 draft 라 '완료로 볼 수 없음' — 의도된 판정). 첫 실행에서는 (가) 정적 검사가 중첩 제네릭 메서드(List<Map<String, Object>> list) 이름을 못 잡아 배치 1 이 거부되고 컴파일 실패, (나) 분해 단계가 산출물 생성 뒤에 있어 WBS 공수와 투입 배정이 어긋나 QA-CON-05 실패 → 검사기 보강·배정 재계산·단계 순서(planner 직후)로 고쳐 통과.
- 실제 고객 RFP(저장소 밖 fixture·템플릿 2종): WBS 분해 모듈 Task 14건, 테스트 계획 통합 20·화면 9·인수 31건, 코드 생성은 모듈 경로가 생성 규칙(com.app) 밖이라 제외(경고 11건, 대행 파일 없음 — 실모델 실행 필요), 문서 4종 생성. QA 58 전부 실행·47 통과·0 실패·11 검토(단계 6 대비 검토 +2: QA-CON-16 draft TC, QA-CON-08 발표용 '미정' 표기 19회 — 분해로 추가된 Task 의 담당·조직이 비어 있어 생긴 것).
- 미검증: 실제 developer·code_qa·code_fixer 에이전트(A-6). 샘플 Java 코드는 대행 응답이라 모델이 이 수준의 코드를 내는지는 알 수 없음. 개발·테스트 화면은 Streamlit 을 띄워 보지 않고 코드·타입 검사만 했다.

## 3. 남은 것·다음 단계

- 실제 developer·code_qa·code_fixer 에이전트는 미실행(A-6). 샘플의 Java 코드는 제가 쓴 대행 응답이라 "모델이 이 코드를 내는지"는 알 수 없다. Docker 격리 실행·검사·반입 경로만 검증했다.
- 생성 대상은 Spring Boot 3.4(Java 21) 고정 템플릿이다. 발주처 환경(전자정부 프레임워크·JEUS·Oracle)으로 템플릿을 바꾸는 것은 별도 과제. 실제 RFP 샘플의 모듈 경로는 `com.knia` 패키지라 생성 규칙(`com.app`) 밖으로 제외되었다(경고로 표시).
- 코드 생성은 배치당 파일 수·출력 토큰 한도에 묶인다(기본 3파일). 큰 파일은 모델 출력 한도에 걸릴 수 있어 수정 루프가 전체 내용을 다시 받는 설계의 비용이 크다.
- 성능·보안·회귀 테스트 수준(TestLevel) 은 계획만 가능하고 실행기는 JUnit(단위·통합) 뿐이다.
- 다음: 단계 8(통합 품질·성능·안정성 — 전체 흐름 통합 테스트, 회귀, 대용량 RFP 측정, 복원, 최종 보고서 §20), 그 뒤 main 병합.
