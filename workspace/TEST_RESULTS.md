# TEST_RESULTS (workspace) — 최신 테스트·검증 결과 요약

상세 이력은 `docs/TEST_RESULTS.md`(Phase 1~23), 단계별 보고서는 `docs/PHASE*_REPORT.md`. 이 파일은 지시문 §19 요구에 따라 최신 상태만 짧게 유지한다.

## 2026-10-16 단계 1 완료 시점

- pytest 295 passed, 1 skipped(전체, llm 제외; 단계 0 대비 +6: 신규 tests/unit/test_stage1_foundation.py 6건 — 설정 왕복·사유 규칙, 엔티티 저장·프로젝트 내 코드 유일·다른 프로젝트 허용, 결정/협상 구속 규칙, 진행률·중단·백그라운드·끊긴 작업 정리, 실행 계획·디스패처·실패만 재실행, 로그 마스킹). ruff·mypy(132 파일) 통과. 민감 용어 검사 통과.
- 실샘플 회귀(모의 에이전트, 렌더링 켬): 계산기 QA 52항목 중 49 실행·43 통과·0 실패·6 검토, 실제 RFP(저장소 밖 fixture·템플릿 2종) 52 실행·47 통과·0 실패·5 검토 — 단계 0 기준선(QUALITY_BASELINE §3) 과 동일. 모듈 분할·설정·작업 레코드 확장이 산출물에 영향을 주지 않았다.
- 미검증: 실제 Claude 모델, Streamlit 화면의 새 탭은 AppTest 스모크(기존 4건) 로 예외 없이 그려지는 것만 확인(사람의 화면 조작 시험은 안 함), 백그라운드 실행은 단위 테스트(스레드) 로만 확인.

## 2026-10-16 (단계 0 진단 시점, 커밋 62ed4d5)

| 항목 | 결과 | 근거 |
|---|---|---|
| `pytest -q`(llm 제외) | 289 passed, 1 skipped (149s) | 세션 실행 로그 |
| `ruff check src tests scripts` | 통과 | 세션 실행 |
| `mypy src` | 통과(117 파일) | 세션 실행 |
| 민감 용어 검사(`scripts/check_sensitive_terms.py`) | 통과(43개 용어) | pre-commit 훅 |
| 계산기 샘플 전체 흐름(모의 에이전트, 렌더링) | QA 52항목 중 49 실행·43 통과·0 실패·6 검토 | `Output/Project_20261016_공학용_계산기_웹_개발_(구현_설계_23)/11_QA_Validation_Reports` |
| 실제 고객 RFP 전체 흐름(저장소 밖 fixture·템플릿 2종, 렌더링) | QA 52 실행·47 통과·0 실패·5 검토, gate3·4 PASS, 제출용 80장·발표용 60장 | 실제 RFP 프로젝트 폴더 `11_QA_Validation_Reports`(폴더명은 고객 식별 정보라 생략) |
| 실제 Claude 모델 호출 | 미실행(크레딧 부족) | RISK R-21 |
| 웹 검색(에이전트) | 미실행. 세션의 Claude 가 검색한 사실만 fixture 에 반영 | PHASE23_REPORT §4 |

미검증: 실제 모델 품질, 수백 쪽 RFP 성능, 다른 OS·Python 버전, 동시 사용자.
