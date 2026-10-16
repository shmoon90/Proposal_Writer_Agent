# 통합 개발 지시문 최종 보고서 (§20) — AI 기반 SI 사업 전 과정 지원 시스템

작성일 2026-10-16 · 프로젝트 루트 `C:\dev\Claude_Work\Proposal_Writer_Agent` · 브랜치 `feature/major-revision`(main 병합 전) · 단계별 상세: `docs/DIRECTIVE_STAGE1~8_REPORT.md`, 진단: `workspace/PROJECT_ANALYSIS.md`·`FEATURE_GAP_ANALYSIS.md`·`QUALITY_BASELINE.md`·`TECHNICAL_RISKS.md`, 결정: `workspace/DECISIONS.md`(A-1~A-7, D-11~D-23), 테스트: `workspace/TEST_RESULTS.md`, 성능: `workspace/PERFORMANCE.md`.

**판정 요약**: 지시문 단계 0~8 을 모두 구현했고 코드·자동 테스트·샘플 실행으로 검증했다(pytest 342 passed, 독립 QA 58항목, 실제 RFP 1건·계산기 샘플 1건 재실행, Docker 격리 JUnit 실행 성공). 그러나 **실제 Claude 모델은 한 번도 호출하지 못했다**(A-6, 크레딧 없음). 따라서 에이전트가 만드는 내용(요구사항·전략·설계·코드)의 품질은 미검증이며, 이 보고서의 "완료"는 **구조·검증 장치·흐름이 동작한다**는 뜻이지 산출물 내용이 제안·설계·개발 실무 수준이라는 뜻이 아니다.

## 1. 구현 완료 기능 (업무 영역 20종 ↔ 단계)

| 영역(지시문 §2) | 상태 | 핵심 구현 | 단계 |
|---|---|---|---|
| 1 RFP·관련 자료 접수 | 완료 | PDF·DOCX·TXT·PPTX·이미지(OCR), 회의록, 템플릿·그림 | 2 |
| 2 RFP 분석 | 완료 | rfp_analyst(개요·목표·현행 문제점·제약·연계·보안·일정·예산·지침), 프로파일·목차 트리 | 기존+2 |
| 3 요구사항 추출·정제 | 완료 | 추출·독립 검증(Gate 1)·품질 규칙 8종(QA-RFP-09)·14항목 기술 검토 | 기존+2·3 |
| 4 사업 참여 의사결정 | 완료 | 13항목 사업성 평가(코드)+검토 에이전트, 비용은 단가 입력 시만, 결정(DEC) 기록(권한 미확인 시 제안) | 2·4 |
| 5 제안 전략 | 완료 | STR 엔티티(발주처 문제·방법·기술·효과·미확인 주장), Gate P | 3 |
| 6 상세 기술 검토 | 완료 | 묶음별 구현 설계(구조·절차·기술·대안 비교·비기능), 출처 확인 날짜, QA-TECH-08 | 3 |
| 7 제안서·제출 산출물 | 완료 | 제출용·발표용 PPT(편집 가능 도형 16종·분량 모드·장 수 상한·배포 구조), 정의서·추적표·WBS·투입계획·비용산정 Excel, 렌더링 미리보기 | 4 |
| 8 제안 품질 검증 | 완료 | 독립 QA 58항목(RFP 9·TECH 9·CON 16·FILE 14·EDIT 10), 게이트 2~5, 재생성 자동 수정 | 기존+2~7 |
| 9 요구사항 기준선 | 완료 | 구축 모드 Excel 적재·Revision·승인 전 불변 | 기존 |
| 10 기술 협상·계약 변경 | 완료 | NEG(고객 합의·승인자 없이는 합의·반영 불가) → 변경 요청 전환 | 5 |
| 11 변경 관리 | 완료 | 수정 문서 비교(Excel ID 기준 6종, PPT/Word 불확실), 상태 8종, 영향 확장, 선택 재생성·회귀 비교 | 5 |
| 12 회의·인터뷰·결정 관리 | 완료 | 회의록 구조화(규칙+meeting_analyzer), 권한 미확인 승인 금지, 미결·조치 기한 | 5 |
| 13 화면·DB·API 설계 | 완료 | detail_designer → SCR/TBL/API/MOD/DSG, 추적·모순·DB 호환성 검사, 설계서 Excel/MD, 코드 생성 입력 패키지 | 6 |
| 14 WBS·공수·비용 | 완료 | WBS 설계 모듈 분해(계층×난이도), 투입 배정 재계산, 비용산정 | 4·7 |
| 15 개발·코드 리뷰 | 범위 축소 완료 | RFP_JAVA 발췌: Spring Boot 프로토타입 생성(구조화 출력)·정적 검사·구현 위치(implementation_map)·리뷰 메모. **납품 코드 생성은 범위 밖(A-2)** | 7 |
| 16 테스트·결함 | 완료 | TC 계획(API·화면·인수), Docker 격리 JUnit → TC/DEF, QA 분석·수정 루프, 미검증은 완료 아님 | 7 |
| 17 사용자 검수 | 완료 | 인수 TC 합격/불합격 사람 기록, 검수 결과서 | 7 |
| 18 운영 이관 | 완료 | 운영 이관 체크리스트(배포·백업·모니터링·미결) | 7 |
| 19 변경 영향 분석·산출물 갱신 | 완료 | 영향 대상 확장(화면·테스트·API·DB·설계·보안), 선택 재생성 | 5 |
| 20 전체 추적성·이력 | 완료 | 요구 → 전략·설계·모듈·TC·DEF 열(추적표), QA-CON-15·16, 감사·Revision·복원 | 4·6·7·8 |

## 2. 부분 구현·미구현과 이유

- **실제 모델 실행(A-6)**: 미수행. 모든 에이전트 경로는 FakeAgentRunner(대행 응답)로만 검증. 프롬프트 규칙 준수·내용 깊이·웹 조사 정확도는 알 수 없다.
- **코드 생성**: Spring Boot 3.4(Java 21) 고정 템플릿 프로토타입. 발주처 환경(전자정부 프레임워크·JEUS·Oracle) 템플릿 없음. 파일 도구 없이 구조화 출력으로 내용을 받으므로 큰 파일은 출력 한도에 걸릴 수 있음(D-23). 실제 RFP 샘플은 모듈 패키지가 생성 규칙 밖이라 제외.
- **HWP 입력**: 미지원(A-7). **역할별 모델 선택**: 기본 모델 1종(설정으로 교체).
- **복원 범위**: 요구·추적·WBS·의존·역할까지. 설계 객체·TC·DEF 는 Revision 스냅샷에 포함하지 않음.
- **화면(Streamlit) 수동 확인**: 단계 2~8 의 새 화면(사업성·회의/결정·설계·개발/테스트·분량·미리보기·복원)은 코드·타입 검사와 서비스 테스트로만 확인했고 브라우저에서 눌러 보지 않았다.
- **성능**: QA 시간이 요구사항 수에 비례 이상으로 늘어난다(500건 286초). 문서 간 일관성 검사의 PPT 본문 대조가 원인으로 보이며 최적화하지 않았다.

## 3. 실제 사용한 Python 및 주요 라이브러리 버전

Python 3.12.10 · claude-agent-sdk 0.2.167 · pydantic 2.14.1 · streamlit(설치본) · python-pptx 1.0.2 · openpyxl 3.1.5 · python-docx 1.2.0 · pdfplumber 0.11.10 · rapidocr 3.10.0 · Pillow 12.3.0 · pytest 9.1.1 · ruff 0.17.0 · mypy 2.4.0 · Docker 29.8(이미지 `rfp-java-test-runner:jdk21-1`, JDK 21 + Maven 3.9).

## 4. 에이전트·SDK·MCP

역할 20종(rfp_analyst, requirement_extractor, requirement_verifier, tech_researcher, approach_writer, strategy_planner, architect, design_writer, detail_designer, planner, proposal_writer, document_generator, qa_reviewer, semantic_differ, bid_reviewer, meeting_analyzer, developer, code_qa, code_fixer 등). 모두 Claude Agent SDK `query()` 구조화 출력, 내장 도구는 WebSearch·WebFetch 만(Bash/Write/Edit 금지), MCP 는 프로젝트 읽기·검증 도구와 문서 조회. 연결 점검은 비용 0 으로 통과(단계 3 메모), 실제 호출은 미수행.

## 5. 실제 실행한 테스트와 결과 (2026-10-16 최종)

- pytest **342 passed, 3 skipped**(llm 제외; Docker 실제 실행 테스트는 `PWA_RUN_DOCKER_TESTS=1` 일 때만 — 이 PC 에서 1회 통과). ruff·mypy(163 파일) 통과. 민감 용어 검사 통과.
- 단계별 신규 테스트: 1(6)·2(8)·3(4)·4(9)·5(8)·6(5)·7(8+1)·8(보안 5·통합 흐름 1).
- 계산기 샘플(모의 에이전트, 렌더링, Docker): QA 58항목 중 55 실행·45 통과·0 실패·10 검토, 코드 생성 3배치·JUnit 4건 통과, 산출물 전부 생성.
- 실제 고객 RFP(저장소 밖 fixture·고객 템플릿 2종): QA 58 전부 실행·47 통과·0 실패·11 검토, 제출용 83장·발표용 62장, 설계서·테스트 계획·검수·이관 문서 생성.
- 전체 흐름 통합 테스트: 제안 → 기준선(제안 산출물 Excel 적재) → 변경(의미 변경 승인·반영) → 설계 → JUnit 반입 → 구축 QA 실패 0 → 복원.
- 성능(`workspace/PERFORMANCE.md`): 요구 50건 12초, 200건 60초, 500건 353초(생성 61·QA 286), 최대 메모리 121MB. 200·500건의 QA 실패 1건은 분량 초과(QA-FILE-13, 합성 지침 100쪽 대비 116장·261장)로 코드 결함이 아니다.
- 회귀: 같은 상태 QA 재실행 건수 동일, 단계마다 두 샘플 기준선 유지(실패 0).

## 6. 생성된 주요 파일과 경로

`Output/<프로젝트>/` 00 요약 · 01 RFP 원본 · 02 RFP 분석·사업성 평가 · 03 요구사항 · 04 기술 조사·구현 설계 · 05 아키텍처·설계서·코드 생성 패키지 · 06 WBS·투입계획(비용산정) · 07 제출용 PPT · 08 발표용 PPT · 09 정의서·추적표 · 10 도식 · 11 QA 보고서·렌더링 PNG·테스트 계획서/결과서 · 12 Revision·스냅샷 · 13 최종본·검수 결과서·운영 이관 체크리스트 · **14 생성 프로토타입(Spring Boot)·테스트 결과**. 상태 파일: `workspace/DEVELOPMENT_STATUS.md/.json`, `WORK_LOG.md`.

## 7. 남아 있는 버그와 위험 (우선순위)

1. **실모델 미검증(A-6)** — 가장 큰 위험. 크레딧 확보 즉시 실제 RFP 1건으로 전 단계 1회 실행 권장(예산 상한 설정).
2. QA 시간이 요구사항 수에 비례 이상 증가(500건 5분). 대형 RFP 에서는 QA 범주 선택 실행 권장.
3. 수정 PPT/Word 비교는 판독 기반이라 오인 가능(설계상 '불확실' 표시).
4. 생성 코드 템플릿이 발주처 환경과 다를 수 있음(프로토타입 용도 한정).
5. 설계 객체·TC·DEF 가 Revision 복원 범위 밖.
6. 발표용 PPT '미정' 표기 증가(WBS 분해 Task 의 담당 공란) — 담당 지정 후 재생성 필요.
7. 간헐 실패했던 백그라운드 취소 테스트는 레코드 락으로 수정했으나, 멀티 프로세스 동시 쓰기는 지원하지 않음.

## 8. 비용·외부 API 제약

API 키는 `.env` 에만, 로그 마스킹. 역할별 `max_budget_usd`·`max_turns`·프로젝트 예산 상한 설정. 웹 검색은 tech_researcher·design_writer 만. 실제 비용은 미측정(실행 없음). Docker 테스트 컨테이너는 네트워크 없음.

## 9. 실행 방법

```powershell
cd C:\dev\Claude_Work\Proposal_Writer_Agent
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env          # ANTHROPIC_API_KEY 입력
python -m pytest -q                   # 342 passed 기대
streamlit run src\proposal_agent\app.py
```

대행 샘플: `python scripts/run_manual_agents.py <RFP> --name <프로젝트명> [--rate 역할=원/MM]... [--budget 원] [--detail summary] [--group-cap N]`. Docker 이미지: 개발·테스트 화면의 '테스트 이미지 빌드' 또는 `docker build -t rfp-java-test-runner:jdk21-1 -f docker/test-runner.Dockerfile docker`.

## 10. 중단·재개·복원 절차

- 중단: 화면의 중단 버튼(또는 `JobManager.request_cancel`) → StepRun `cancel_requested`·'중단 요청됨' 기록, 작업은 다음 확인 지점에서 멈추고 `resume_point` 를 남긴다.
- 재개: 같은 단계를 다시 실행하면 `resume_point` 부터 이어간다(요구 추출 청크 등). 실패한 단계만 재실행: 실행 계획 탭 '실패만 재실행'.
- 복원: '구축: 기준 문서' 4절에서 Revision 선택·사유 입력 → 복원 전 상태가 먼저 Revision 으로 보존된 뒤 선택 Revision 스냅샷으로 되돌림(요구·추적·WBS·의존·역할). 변경 요청 반영 실패는 자동 롤백(상태 error, 재시도 가능).
- 백업: DB(`workspace/*.sqlite3`)와 `Output/` 을 함께 백업.

## 11. 사용자 확인 또는 수동 작업이 필요한 항목

1. 크레딧 충전 후 **실제 모델 1회 실행**(A-6) 과 결과 검토.
2. 게이트 승인(0·1·P·3·5), 사업 참여 결정·회의 결정·협상 합의의 권한 확인, 검수 판정 — 코드가 대신하지 않는다.
3. 프로젝트 설정: 단가·예산·기존 시스템·연계 시스템·기술 선택 모드·분량 모드.
4. QA '검토 필요' 항목 판단, 제출 전 PowerPoint·Excel 육안 확인.
5. 생성 프로토타입은 설계 검증·개발 착수 자료로만 사용.
6. main 병합(사용자 결정, 단계 8 뒤).

## 12. 결정 기록 요약

A-1~A-7(단계 1 착수), D-11 브랜치 분리, D-14 코드 개발 범위, D-15 비용 단가 입력, D-16 백그라운드 선택, D-17 수정 문서 비교 우선순위, D-18 그림 정책, D-21 단계 6 문맥 주입·구체성 검사, D-22 RFP_JAVA 발췌 이식, D-23 구조화 출력 코드 생성. 전체는 `workspace/DECISIONS.md`.
