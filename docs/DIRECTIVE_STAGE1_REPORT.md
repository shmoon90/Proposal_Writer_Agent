# 통합 개발 지시문 단계 1 보고서 — 공통 기반·실행 구조 (2026-10-16)

범위: `workspace/IMPLEMENTATION_PLAN.md` 단계 1(①~⑥). 승인: A-1(데이터 모델 확장·마이그레이션)·A-4(백그라운드 실행 선택 기능) 포함 A-1~A-7 전부 승인(2026-10-16, `workspace/DECISIONS.md` D-13~D-20). 브랜치 `feature/major-revision`.

## 1. 무엇을 만들었나

| 항목 | 구현 | 위치 |
|---|---|---|
| ① 프로젝트 설정(지시문 §3) | `ProjectSettings`(사업 설명·일정 제약·예산·공수 상한·기존 시스템·**기술 선택 모드 5종**·기술 스택 8영역·RFP 명시 기술·보안/개인정보·외부 솔루션·연계 시스템·산출물 종류/형식·역할별 단가·간접비율). `Project.settings` JSON 에 저장(스키마 변경 없음). `ProjectService.settings_of/update_settings`: **RFP 명시 기술이 있는데 모드를 바꾸면 사유 필수**, 변경 항목을 감사 기록. 프로젝트 화면 '설정' 탭(폼 + 요약) | `models/settings.py`, `models/enums.py`(`TechSelectionMode`), `services/project_service.py`, `ui/app_pages/project.py` |
| ② 공통 객체 ID·엔티티(§17) | 신규 엔티티 9종 + 내장 1종: 제안 전략 `ProposalStrategy`(STR), DB 테이블 `DbTable`(TBL)·컬럼 `DbColumn`(COL, 내장), API `ApiSpec`(API), 설계 항목 `DesignItem`(DSG), 코드 모듈 `CodeModule`(MOD), 테스트 케이스 `TestCase`(TC), 결함 `Defect`(DEF), 의사결정 `Decision`(DEC), 협상 `Negotiation`(NEG). 모두 프로젝트 범위·버전·상태·관련 ID 보유. **마이그레이션 8**(테이블 9개, `(project_id, code)` 유일), 저장소 9종(`get_by_code`), `Repositories.next_code(project_id, prefix)` 로 프로젝트 안 단조 증가 코드 발급. `TraceTargetType` 에 strategy/api/db_table/design_item/code_module/test_case/acceptance 추가. 결정은 `kind=official_decision` + 승인 + 권한 확인일 때만 구속력(`is_binding`), 협상은 합의+승인일 때만 기준선 반영 가능(`can_apply_to_baseline`) | `models/strategy.py`, `models/design.py`, `models/testing.py`, `models/decision.py`, `models/enums.py`, `storage/migrations.py`, `storage/repositories.py` |
| ③ 작업 실행 레코드·백그라운드(§15·§16) | `StepRun` 에 진행률·현재 일·중단 요청·재개 지점·생존 신호·백그라운드 여부. `PipelineService.update_progress/plan_preview/failed_steps`. `JobManager`(스레드 실행, 생존 신호, 중단 요청, 끊긴 작업 탐지·정리). **항상 DB 최신본을 읽고 갱신**해 작업 스레드의 옛 복사본이 화면의 중단 요청을 지우지 않게 했다(테스트로 재현·수정). 동기 경로는 그대로(결정 D-16) | `models/pipeline.py`, `services/pipeline_service.py`, `services/jobs.py`, `services/__init__.py` |
| ⑥ 공통 UI·실행 범위(§16) | `StepRunner.run_step(key)` 디스패처(13단계; 업로드·인력 기간·최종 확정은 사람 입력이라 거부), `run_steps`(정의 순서·실패/게이트 대기에서 멈춤), `rerun_failed`. 프로젝트 화면 '실행 계획' 탭: 단계 선택 → 미리보기 표(상태·실행 가능·차단 사유·에이전트/코드·게이트·진행률) → 선택 실행(동기 또는 백그라운드) · 실패한 단계만 재실행 · 끊긴 작업 정리 · 백그라운드 작업 목록·중단 요청 | `orchestrator/runner.py`, `ui/components.py`(`plan_table`·`jobs_panel`), `ui/app_pages/project.py` |
| ⑤ 보안 확인·보강(§15.3) | 확인: 업로드는 빈 파일·200MB 상한·종류별 확장자 허용 목록(`document_service._validate_upload`), 파일 저장은 경로 조작 차단(`FileStore`, 기존 테스트), 키는 `.env` 만. 보강: **로그 비밀값 마스킹 필터**(`sk-ant-…`, `api_key/token/secret/password/authorization=…` → `***`, 메시지·인자 모두) 를 루트 로거에 부착 | `config/logging.py` |
| ④ 대형 모듈 분할(동작 불변, D-19) | `validation/independent_qa.py`(2,204줄) → 패키지 `validation/qa_checks/`(common·rfp·tech·consistency·files·editability·`__init__`(run_all_checks·gate_status)), 원래 경로는 facade 로 전부 재수출. `generators/pptx/shapes.py`(2,073줄) → 패키지 `shapes/`(base·diagrams·blocks, `__init__` 재수출, `shapes.Box` 호환). AST 기반 분할기(이름 → 모듈 배정, 모듈 간 참조는 import, 순환은 공용으로 이동)로 수행하고 import 정리는 ruff 가 했다. `decks.py`·`changes/service.py` 는 단계 4·5 에서 구조를 바꿀 때 분할 | `validation/qa_checks/*`, `generators/pptx/shapes/*`, 분할기 `scratchpad/split_module.py`(저장소 밖) |

## 2. 확인 결과

- pytest 295 passed, 1 skipped(전체, llm 제외; 단계 0 대비 +6: 신규 tests/unit/test_stage1_foundation.py 6건 — 설정 왕복·사유 규칙, 엔티티 저장·프로젝트 내 코드 유일·다른 프로젝트 허용, 결정/협상 구속 규칙, 진행률·중단·백그라운드·끊긴 작업 정리, 실행 계획·디스패처·실패만 재실행, 로그 마스킹). ruff·mypy(132 파일) 통과. 민감 용어 검사 통과.
- 실샘플 회귀(모의 에이전트, 렌더링 켬): 계산기 QA 52항목 중 49 실행·43 통과·0 실패·6 검토, 실제 RFP(저장소 밖 fixture·템플릿 2종) 52 실행·47 통과·0 실패·5 검토 — 단계 0 기준선(QUALITY_BASELINE §3) 과 동일. 모듈 분할·설정·작업 레코드 확장이 산출물에 영향을 주지 않았다.
- 미검증: 실제 Claude 모델, Streamlit 화면의 새 탭은 AppTest 스모크(기존 4건) 로 예외 없이 그려지는 것만 확인(사람의 화면 조작 시험은 안 함), 백그라운드 실행은 단위 테스트(스레드) 로만 확인.

## 3. 남은 것·다음 단계

- 설정의 기술 스택·단가는 저장·표시까지이며, 조사·전략·사업성 평가가 이를 읽는 연결은 단계 2·3 에서 한다.
- 신규 엔티티는 저장소·ID·규칙까지이고 생성 화면·산출물은 단계 5~7 에서 만든다. 추적표 열 확장은 단계 4.
- 백그라운드 실행은 프로세스 안 스레드다(프로세스 재시작 시 끊긴 작업은 '끊긴 작업 정리' 로 실패 처리 후 재실행). 재개 지점(`resume_point`) 은 레코드만 있고 단계별 이어가기 로직은 단계 2(추출 청크) 부터 쓴다.
- `decks.py`(1,367줄)·`changes/service.py`(1,249줄) 분할은 보류(단계 4·5).
- 다음: 단계 2(RFP 분석·사업성 평가) — 입력 형식 확장(PPTX·이미지), 요구사항 품질 검사 확장, 사업성 평가 서비스·화면·평가서, 참여 의사결정 기록.
