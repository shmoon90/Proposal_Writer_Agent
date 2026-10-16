# WORK_LOG

작업 순서 기록. 상태 요약은 `workspace/DEVELOPMENT_STATUS.md`, 단계별 상세는 `docs/PHASE*_REPORT.md`.

## 2026-10-16
- Phase 23: 사용자 검토 의견('장표 밀도가 아니라 내용 — 어떻게 구현할지·어떤 기술·어떤 구조를 웹 검색 근거나 자체 설계로 구체적으로')을 반영. 구현 설계 에이전트 `design_writer`(묶음별 구조·절차·적용 기술·근거) 신설, 파이프라인 `impl_design` 단계, 묶음 소절에 구조/절차 도식·적용 기술 표, QA-CON-13(52항목). 실제 RFP 는 세션의 Claude 가 웹 검색(전자정부 프레임워크 4.3·JEUS 7·sticky·알림톡·POI SXSSF·Chart.js·KWCAG 2.2·Rocky Linux·ojdbc·TOTP·ShedLock)으로 확인한 사실에 근거해 설계 7묶음을 대행 작성(저장소 밖 fixture)
- Phase 22: 사용자 검토 의견(구현 방안 부실·정의서 미반영·시각화 단조·빈칸)과 같은 RFP 제안서 샘플(Ⅲ장) 분석을 반영 — 요구사항 묶음별 구현 방안 소절(`req_groups.py`, requirement_groups 스키마·규칙 18), 복합 장표(밴드·블록 높이 배분·장 분할), 기능 블록 도식, 여러 줄 셀 표, 카드·2열·띠 높이 상한, QA-CON-12(51항목). 실제 RFP 재실행 QA 0 실패·gate4 PASS·QA-CON-12 통과. pytest 284 passed. → `docs/PHASE22_REPORT.md`
- 실제 고객 RFP PDF(48쪽, 저장소 밖)로 제안 단계 전체 흐름을 대행 응답(API 없음)으로 실행: `run_manual_agents.py --fixture <저장소 밖 .py>` 옵션과 '@별칭' → 요구사항 ID 해결을 추가하고, 실행에서 드러난 생성기·QA 결함(데이터 흐름 라벨 겹침·양방향 화살표, 구성도 라벨 폭, 일정·인력·요구사항 소절 도식+데이터 슬라이드 병행, 발표용 필요성 리드 축약, QA-CON-10 줄바꿈 오탐, QA-CON-11 슬래시 약어)을 고쳤다. 결과: 요구사항 42건, 제출용 45장·발표용 37장, QA 50항목 46 통과·0 실패·4 검토, gate3·gate4 PASS, 렌더링 45/45·37/37.
- Phase 21 완료(개선 계획 마지막 단계): PowerPoint COM 실제 렌더링·재열기(validation/render.py, QA-FILE-14), 페이지 제한(QA-FILE-13), 편집 가능성 체크리스트 QA-EDIT-01~10(새 범주), QA 범주 분리 실행·범주별 집계, 발표자 노트 초안, 렌더링으로 찾은 장 라벨 줄바꿈 수정. pytest 279 passed, 실샘플 QA 50항목 0 실패·gate4 PASS·렌더링 30/30·22/22. → `docs/PHASE21_REPORT.md`, 최종 완료 보고 `docs/FINAL_REPORT_IMPROVEMENT_2026-10.md`
- Phase 20 완료: 네이티브 차트(charts.py: 공수·요구사항 통계·제출용 간트·VisualSpec chart), 화면 목업 컴포넌트(입력·버튼·메뉴·탭·메시지·표·목록·차트 영역)·그룹화(목업·카드·수치 카드·엔티티), 참고 그림 문서 종류(PICTURE)와 태그 삽입 경로, QA 그룹 평탄화. pytest 274 passed, 실샘플 QA 0 실패·gate4 PASS·QA-FILE-12 사진 예외 통과. → `docs/PHASE20_REPORT.md`
- Phase 19 완료: ProposalSection 슬라이드 명세(결론형 제목·목적·독자·근거·연결·레이아웃·tech_detail·terms)·glossary, 슬라이드 명세 JSON 산출(07_/08_, manifest), 도식 13종(raci·data_model·procedure·security_layers·layers), 기술 상세·대안 비교(상용/공개/자체)·용어 설명 슬라이드, 프롬프트 규칙 12~16, QA-CON-10/11(총 38항목), 산출물 화면 명세 패널. pytest 270 passed, 실샘플 QA 0 실패·gate4 PASS. → `docs/PHASE19_REPORT.md`
- Phase 18 완료: strategy_planner 브리프(10항목)·Gate P(목차·전략 승인) 게이트·승인 전 문안 작성/최종 확정 차단·반려 재작성·QA-RFP-08·산출물 화면 승인 패널. 브리프 프롬프트 부작용(기본 계획 선저장)과 장 라벨 넘침 수정. pytest 265 passed, 실샘플 QA 0 실패·gate4 PASS. → `docs/PHASE18_REPORT.md` (브리프 형식·승인 화면 사용자 확인 대기)
- Phase 17 완료: RfpAnalysis 항목 확장·프롬프트, 페이지 제한/규격 파싱, 근거 구분·대응 전략, 덱→Excel 순서와 제안서 페이지 역산(추적표 29열·정의서 33열). pytest 262 passed, 실샘플 QA 0 실패. → `docs/PHASE17_REPORT.md`
- Phase 16 완료: manifest.json(생성 run 누적·QA 첨부), 그림 정책(허용 태그·QA-FILE-12 개정), 라이브러리 검토 문서, 상태 기록 스크립트. pytest 257 passed, 실샘플 재검증 QA 0 실패. → `docs/PHASE16_REPORT.md`
- Phase 15 완료·main 병합·origin push (`ab75fba`): WBS 상세/약식·주 간트·마일스톤, 투입계획 구성원별 월별 공수, planner team/milestones, ID 없는 고객 WBS 재적재. pytest 253 passed.
- 품질 고도화·편집 가능 산출물 요청 분석: 요청 19개 절 ↔ 현재 구현 차이 정리, 6단계(16~21) 계획 작성 → `docs/IMPROVEMENT_PLAN_2026-10.md`. 환경 점검(PowerPoint COM 가능, LibreOffice 없음). 진행 기록 파일 신설. **사용자 승인 대기** — 코드 변경 없음.

## 2026-10-15
- Phase 14 완료·main 병합·push (`6c649f3`): 정의서 31열·추적표 25열, approach_writer 구현 방안 자동 작성, 문맥 기반 변경 비교·난이도 가중, QA-CON-09. pytest 249 passed.
- Phase 11~13 이력 익명화(고객 샘플 식별 정보 제거), 민감 용어 검사 훅 도입.
