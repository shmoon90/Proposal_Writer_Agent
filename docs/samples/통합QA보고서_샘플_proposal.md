# 통합 QA 보고서 — 회귀_제안

- 실행 시각: 2026-10-15T03:12:57+00:00 · 모드: proposal · 판정 기준: 코드(validation.independent_qa)
- **최종 판정: NEEDS_HUMAN_REVIEW** — 사람 승인이 필요합니다.

## 1. 전체 검증 범위
- RFP 적합성
- 기술 타당성
- 문서 간 일관성
- 파일 품질
- 게이트: gate2=NEEDS_HUMAN_REVIEW, gate3=PASS, gate4=PASS, gate5=NEEDS_HUMAN_REVIEW

## 2. 실제 실행한 테스트
- 자동 검증 항목 30건 실행 / 0건 미실행 (미실행은 통과로 세지 않음)
- pytest (unit·integration·sdk, llm 제외): exit_code=0, summary=215 passed, 1 skipped, 2 deselected in 57.63s, duration_s=59.8, passed=215, skipped=1, deselected=2

## 3. 건수
- 통과 25 · 실패 0 · 검토 필요 5 · 미실행 0 · 자동 수정 후 통과 0

## 4. 검증 항목별 결과

| 검증 ID | 대상 | 기준 | 결과 | 발견 문제 | 관련 요구사항 | 영향 파일 | 수정 제안 | 수정 여부 | 재검증 |
|---|---|---|---|---|---|---|---|---|---|
| QA-RFP-01 | RFP 원문 ↔ 요구사항 목록 | 의무 표현('하여야 한다' 등)이 있는 원문 블록이 모두 요구사항 출처로 연결되어 있는가 | NEEDS_HUMAN_REVIEW | 출처로 연결되지 않은 의무 표현 블록 1건; -p/blk_fe59a6cc: 다음 기능 요구사항은 모두 필수 구현 대상이다. | - | rfp.docx | 누락 블록을 검토해 요구사항을 추가(요구사항 화면 수동 추가)하거나 '해당 없음' 사유를 기록 | - | - |
| QA-RFP-02 | 요구사항 범위 분류 | RFP 필수가 아닌 항목(부가 제안·범위 외)이 필수로 표시되지 않았는가, 필수 요구사항에 원문 출처가 있는가 | PASS | 없음 | - | - | - | - | - |
| QA-RFP-03 | 요구사항 인용문 ↔ 원문 | 요구사항의 원문 인용(rfp_quote)이 실제 원문 블록에 존재하는가 | PASS | 없음 | - | - | - | - | - |
| QA-RFP-04 | 제출 조건 | RFP가 제출 조건을 요구하면 제출 조건 요구사항이 있고 제출용 제안서에 반영되었는가 | PASS | 없음 | SUB-001, SUB-002 | - | - | - | - |
| QA-RFP-05 | 평가 기준 대응 | RFP 평가 기준이 요구사항(EVA-)과 제출용 제안서에 대응되는가 | NEEDS_HUMAN_REVIEW | RFP에 평가 기준 표현이 있으나 평가 기준 요구사항(EVA-)이 없음 | - | - | 평가 항목별 대응 섹션을 제안서에 추가 | - | - |
| QA-RFP-06 | 원본 출처 참조 | 요구사항 출처(document_id·block_id)가 실제 등록 문서·추출 블록을 가리키는가 | PASS | 없음 | - | - | - | - | - |
| QA-TECH-01 | 기술 조사 구현 가능성 ↔ 수용 요구사항 | 구현 불가(infeasible)로 조사된 요구사항이 수용으로 표시되지 않았는가, 미확인(unknown)인 필수 요구사항이 없는가 | NEEDS_HUMAN_REVIEW | 기술 조사 기록이 없어 구현 가능성을 확인하지 못함 (tech_researcher 미실행) | - | - | 해당 요구사항의 수용 여부를 '조건부 수용/미수용'으로 바꾸거나 추가 조사를 수행 | - | - |
| QA-TECH-02 | 조사 미확인 사항 | 확인되지 않은 솔루션 기능·주장이 남아 있지 않은가 | PASS | 없음 | - | - | - | - | - |
| QA-TECH-03 | 버전 호환성 | 같은 제품이 서로 다른 버전으로 조사·명시되지 않았는가 | PASS | 없음 | - | - | - | - | - |
| QA-TECH-04 | 기술 간 연계 | 구성 요소 연결이 존재하는 구성 요소를 가리키고, RFP 연계 대상마다 연계 구성 요소가 있는가 | PASS | 없음 | - | - | - | - | - |
| QA-TECH-05 | 보안·성능·운영 위험 | 조사에서 식별된 위험과 보안·성능 요구사항에 대응 구성 요소가 있는가 | PASS | 없음 | - | - | - | - | - |
| QA-TECH-06 | 기술 주장 근거 | 구성 요소·제안서가 언급한 기술이 출처 있는 조사 기록으로 뒷받침되는가 | NEEDS_HUMAN_REVIEW | 근거 조사 없는 기술: HTML5 브라우저 | - | - | 기술 조사를 실행하거나 근거 없는 기술명을 '검토 필요'로 바꿈 | - | - |
| QA-CON-01 | PPT ↔ 요구사항 정의서 | 제출용 PPT가 모든 필수 요구사항 ID를 다루고 없는 ID를 언급하지 않으며, PPT 핵심 수치가 Excel과 같은가 | PASS | 없음 | - | Project_20261015_회귀_제안/07_Submission_Proposal_PPT/제안서_제출용_v1.0.pptx, Project_20261015_회귀_제안/08_Presentation_PPT/제안서_발표용_v1.0.pptx | - | - | - |
| QA-CON-02 | 요구사항 정의서 ↔ 추적표 | 두 파일의 요구사항 ID 집합이 같고 기준 데이터와 일치하는가 | PASS | 없음 | - | Project_20261015_회귀_제안/09_Excel_Deliverables/요구사항정의서_v1.0.xlsx, Project_20261015_회귀_제안/09_Excel_Deliverables/요구사항추적표_v1.0.xlsx | - | - | - |
| QA-CON-03 | 요구사항 ↔ WBS | 수용된 필수 요구사항마다 WBS Task가 있고, WBS가 없는 요구사항을 참조하지 않는가 | PASS | 없음 | - | - | - | - | - |
| QA-CON-04 | WBS ↔ 일정 | 선후행(FS) 관계·상위 항목 범위·기간(영업일)이 날짜와 맞는가 | PASS | 없음 | - | Project_20261015_회귀_제안/06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx | - | - | - |
| QA-CON-05 | WBS ↔ 인력 투입계획 | WBS 총 공수 = 인력 계획 합계 = 배정 합계인가 | PASS | 없음 | - | Project_20261015_회귀_제안/06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx, Project_20261015_회귀_제안/06_WBS_Effort_Schedule/인력투입계획_v1.0.xlsx | - | - | - |
| QA-CON-06 | 기술 조사 ↔ 아키텍처 | 구성 요소 기술이 조사 권고 스택과 모순되지 않는가 | PASS | 없음 | - | - | - | - | - |
| QA-CON-07 | 변경 이력 ↔ 현재 기준 데이터 | 반영된 변경 요청의 요구사항 상태·Revision·변경 후 파일이 현재 데이터와 맞는가 | PASS | 없음 | - | - | - | - | - |
| QA-CON-08 | 발표용 PPT 미확정 표기 | '검토 필요/미정' 표기가 과다하지 않은가 | NEEDS_HUMAN_REVIEW | 발표용 PPT에 '미정' 표기 13회 — 확정 후 재생성 권장 | - | - | 기술·수용 여부를 확정한 뒤 재생성 | - | - |
| QA-FILE-01 | 산출물 파일 열기 | PPT·Excel·PNG 파일이 정상적으로 열리는가 | PASS | 없음 | - | Project_20261015_회귀_제안/06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx, Project_20261015_회귀_제안/06_WBS_Effort_Schedule/인력투입계획_v1.0.xlsx, Project_20261015_회귀_제안/07_Submission_Proposal_PPT/제안서_제출용_v1.0.pptx | - | - | - |
| QA-FILE-02 | 슬라이드 방향·규격 | 가로 16:9, 슬라이드 3장 이상 | PASS | 없음 | - | Project_20261015_회귀_제안/07_Submission_Proposal_PPT/제안서_제출용_v1.0.pptx, Project_20261015_회귀_제안/08_Presentation_PPT/제안서_발표용_v1.0.pptx | - | - | - |
| QA-FILE-03 | 텍스트·도형 잘림 | 도형이 슬라이드 안에 있고 텍스트가 넘치지 않는가 | PASS | 없음 | - | Project_20261015_회귀_제안/07_Submission_Proposal_PPT/제안서_제출용_v1.0.pptx, Project_20261015_회귀_제안/08_Presentation_PPT/제안서_발표용_v1.0.pptx | - | - | - |
| QA-FILE-04 | 표·차트 겹침 | 텍스트 도형끼리 크게 겹치지 않는가 | PASS | 없음 | - | - | - | - | - |
| QA-FILE-05 | Excel 시트·컬럼 | 필수 시트와 컬럼이 모두 있는가 | PASS | 없음 | - | Project_20261015_회귀_제안/06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx, Project_20261015_회귀_제안/06_WBS_Effort_Schedule/인력투입계획_v1.0.xlsx, Project_20261015_회귀_제안/09_Excel_Deliverables/요구사항정의서_v1.0.xlsx | - | - | - |
| QA-FILE-06 | 날짜·수식 | 종료일 ≥ 시작일, 수식 형식 오류 없음, 산정 근거 있음 | PASS | 없음 | - | Project_20261015_회귀_제안/06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx, Project_20261015_회귀_제안/06_WBS_Effort_Schedule/인력투입계획_v1.0.xlsx | - | - | - |
| QA-FILE-07 | 요구사항 ID | Excel의 요구사항 ID가 기준 데이터와 같고 형식이 올바른가, 미실행 테스트가 '성공'으로 표시되지 않았는가 | PASS | 없음 | - | - | - | - | - |
| QA-FILE-08 | 간트 차트 ↔ 일정 데이터 | 간트 시트의 시작·종료와 채움 구간이 WBS 시트 날짜와 같은가 | PASS | 없음 | - | Project_20261015_회귀_제안/06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx | - | - | - |
| QA-FILE-09 | 파일 경로 | 산출물 경로가 프로젝트 Output 폴더 안에 있고 실제로 존재하는가 | PASS | 없음 | - | Project_20261015_회귀_제안/06_WBS_Effort_Schedule/WBS_간트_v1.0.xlsx, Project_20261015_회귀_제안/06_WBS_Effort_Schedule/인력투입계획_v1.0.xlsx, Project_20261015_회귀_제안/07_Submission_Proposal_PPT/제안서_제출용_v1.0.pptx | - | - | - |
| QA-FILE-10 | 산출물 누락 | 모드별 필수 산출물이 모두 생성되었는가 | PASS | 없음 | - | - | - | - | - |

## 5. 주요 발견 사항
- 필수 검증 실패 없음

## 6. 수정 내역
- 자동 수정 라운드 0/2
- 자동 수정 없음

## 7. 재검증 결과
- 재검증 항목 없음

## 8. 미해결 위험
- QA-RFP-01 RFP 원문 ↔ 요구사항 목록: 출처로 연결되지 않은 의무 표현 블록 1건
- QA-RFP-05 평가 기준 대응: RFP에 평가 기준 표현이 있으나 평가 기준 요구사항(EVA-)이 없음
- QA-TECH-01 기술 조사 구현 가능성 ↔ 수용 요구사항: 기술 조사 기록이 없어 구현 가능성을 확인하지 못함 (tech_researcher 미실행)
- QA-TECH-06 기술 주장 근거: 근거 조사 없는 기술: HTML5 브라우저
- QA-CON-08 발표용 PPT 미확정 표기: 발표용 PPT에 '미정' 표기 13회 — 확정 후 재생성 권장

## 9. 승인 필요 항목
- QA-RFP-01 RFP 원문 ↔ 요구사항 목록
- QA-RFP-05 평가 기준 대응
- QA-TECH-01 기술 조사 구현 가능성 ↔ 수용 요구사항
- QA-TECH-06 기술 주장 근거
- QA-CON-08 발표용 PPT 미확정 표기
- gate5: 최종 독립 QA 사람 승인

### 생성 단계 사람 검토 항목
- 수용 여부 '검토 필요' 요구사항 11건: CON-001, CON-002, FR-001, FR-002, FR-003, FR-004, NFR-001, NFR-002
- WBS 공수가 기본값입니다 — 산정 근거 검토 필요
- 구성도의 기술 스택이 '미정'입니다 — 아키텍처 확정 필요

## 10. 최종 판정
- NEEDS_HUMAN_REVIEW
- 실제 실행한 검사 결과만 반영했습니다. 미실행 항목은 통과로 표시하지 않았습니다.
