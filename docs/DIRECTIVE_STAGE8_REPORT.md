# 통합 개발 지시문 단계 8 보고서 — 통합 품질·성능·안정성 (2026-10-16)

범위: `workspace/IMPLEMENTATION_PLAN.md` 단계 8 — 전체 흐름 통합 테스트, 회귀, 대용량 RFP 측정, 보안 점검, 중단·재개·복원 절차, 최종 보고(§20 은 `docs/DIRECTIVE_FINAL_REPORT.md`). 브랜치 `feature/major-revision`.

## 1. 무엇을 만들었나

| 항목 | 구현 | 위치 |
|---|---|---|
| 전체 흐름 통합 테스트 | 한 테스트에서 **제안 → 기준선 → 변경 → 설계 → 테스트 → 복원** 을 잇는다: RFP docx → 요구 추출·검증(Gate 1) → 상세 설계(모의) → 산출물 생성 → 통합 QA(실패 0) → 같은 상태 QA 재실행 건수 동일(회귀) → **제안이 만든 정의서·추적표·WBS Excel 을 구축 프로젝트 기준선으로 적재**(열 매핑 확인 없이 통과) → 수정 정의서(수치 조건 추가) 변경 요청 → ID 기준 비교(의미 변경) → 승인 대기 → 승인·반영 → 구축 프로젝트 상세 설계 저장·테스트 계획 → JUnit 결과(실행기 스텁) 반입 → 구축 QA(실패 0, QA-CON-16 실행) → 기준선 Revision 으로 복원(변경 전 설명 복귀, '복원 전 상태'·'복원' Revision 기록) | `tests/integration/test_stage8_full_flow.py` |
| 복원 절차 | `BaselineService.restore_revision`: 스냅샷으로 추적·WBS·의존·역할을 교체하고 요구사항은 ID 보존(갱신·삽입, 스냅샷에 없으면 deleted 표시), 배정 초기화, 복원 전 상태를 먼저 Revision 으로 보존한 뒤 '복원' Revision 기록·감사. 화면 '구축: 기준 문서' 4절에서 Revision 선택·사유 입력 후 복원 | `changes/baseline_service.py`, `ui/app_pages/build_baseline.py` |
| 중단·재개 | 단계 1 의 StepRun 진행률·중단 요청·재개 지점·백그라운드(JobManager) 그대로. 단계 6 에서 잃어버린 갱신(옛 복사본 덮어쓰기)을 레코드 락으로 고침. 절차는 최종 보고서 10절 | (기존) |
| 보안 점검 | 테스트로 고정: 업로드(허용 확장자·빈 파일·200MB·모드별 종류·파일명 경로 조작 무력화), 경로(Output 밖 상대/절대 경로·링크 거부, 생성 앱 작업 폴더 탈출·예약 이름·드라이브 거부), 로그(API 키·비밀값 마스킹 필터), 인젝션(**모든 프롬프트가 입력 블록을 '데이터'로 선언** — 누락됐던 requirement_extractor·requirement_verifier·tech_researcher 3종 보강, 에이전트 도구는 허용 내장 도구와 읽기·검증 성격 MCP 만, Bash/Write/Edit 금지), SQL 파라미터 바인딩(테이블·컬럼 이름만 f-string) | `tests/unit/test_stage8_security.py`, `agents/prompts/*.md` |
| 대용량 RFP 측정 | `scripts/measure_large_rfp.py`: 합성 RFP(요구 50·200·500건) 로 추출 → 요구 추출·검증(모의) → 산출물 생성 → QA 시간·메모리 측정 → `workspace/PERFORMANCE.md` | `scripts/measure_large_rfp.py`, `workspace/PERFORMANCE.md` |
| 회귀 | 기존 `scripts/run_regression.py`(pytest + 데모 제안·구축 흐름 + 통합 QA) 유지, 단계 8 통합 테스트가 pytest 에 포함되어 함께 돈다 | `scripts/run_regression.py` |

## 2. 확인 결과

pytest 342 passed, 3 skipped(llm 제외, Docker 실행 테스트는 PWA_RUN_DOCKER_TESTS=1 로 1회 통과) | ruff·mypy 통과 | 단계 8 신규 테스트: 보안 5건(업로드·경로·로그·프롬프트 데이터 선언/읽기 전용 MCP·SQL 바인딩), 전체 흐름 통합 1건(제안→기준선 적재→변경 승인·반영→설계→JUnit 반입→구축 QA 실패 0→복원) | 회귀(run_regression.py --skip-pytest): 회귀_제안 58항목 중 53 실행·실패 0, 회귀_구축 23 실행·실패 0 | 성능(measure_large_rfp.py, 모의 에이전트): 요구 50건 11.8초/11.7MB(QA 53 실행·42 통과·0 실패), 200건 59.6초/32MB(53·41·1), 500건 353.5초(생성 60.6·QA 286)/120.9MB(53·41·1) — 실패 1건은 QA-FILE-13 분량 초과(합성 지침 100쪽 대비 116장·261장), 코드 결함 아님 | 프롬프트 3종(requirement_extractor·requirement_verifier·tech_researcher) 입력 데이터 선언 보강 | 실제 모델 호출 없음(A-6 미검증)

## 3. 남은 것

- 실제 Claude 모델 실행(A-6) 은 끝내 하지 못했다. 모든 에이전트 경로는 대행 응답으로만 검증됐다.
- 성능 측정은 코드 경로(추출·규칙·생성·QA)만 잰다. 실제 모델 호출 시간·비용은 포함되지 않는다.
- 복원은 요구사항·추적·WBS·의존·역할까지이며, 설계 객체(SCR/TBL/API/MOD)·테스트 케이스·결함은 스냅샷에 넣지 않았다(단계 6·7 엔티티는 Revision 범위 밖 — 후속 과제).
- 종합은 `docs/DIRECTIVE_FINAL_REPORT.md`(§20) 참고.
