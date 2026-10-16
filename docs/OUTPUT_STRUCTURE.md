# OUTPUT_STRUCTURE — 산출물 폴더와 파일 규칙

문서 버전 1.0 · 2026-10-15 · 구현: `config/paths.py`, `storage/files.py`, `generators/service.py`, `changes/service.py`

---

## 1. 루트

| 경로 | 내용 | 설정 |
|---|---|---|
| `Output\` | 업무 산출물. 프로젝트별 폴더 | `PWA_OUTPUT_ROOT` |
| `workspace\` | 임시 파일: `logs\app.log`, `pwa.sqlite3`, `<project_id>\`(추출 텍스트·청크, 에이전트 cwd), `mcp_check.json`, `final_inspection.*` | `PWA_WORKSPACE_ROOT`, `PWA_DB_PATH` |

두 루트는 git에서 제외된다. DB에는 파일의 **상대 경로**(Output 루트 기준)와 sha256이 기록된다.

## 2. 프로젝트 폴더

프로젝트 생성 시 `Output\Project_<YYYYMMDD>_<안전한 이름>\`이 만들어지고(같은 이름이면 `_1`), 아래 14개 하위 폴더가 항상 생성된다.

| 폴더 | 내용 | 파일명 |
|---|---|---|
| `00_Project_Summary` | (예약) 프로젝트 요약 | — |
| `manifest.json` (프로젝트 폴더 루트, Phase 16) | 생성 실행(run)마다 산출물 목록(종류·category(submission/presentation/excel/qa/source)·경로·버전·sha256·크기)·보조 파일·오류·시각을 **누적**하고, 통합 QA 완료 시 그 run에 판정·건수·게이트·보고서 경로·그림 예외를 첨부. 과거 run은 지우지 않음 | 덮어쓰되 run 누적 |
| `01_RFP_Original` | 업로드 원본(제안: RFP·첨부·**제안서 템플릿 PPTX**·**참고 그림**(Phase 20, `<태그>__<설명>.png|jpg`), 구축: 정의서·추적표·WBS·투입계획·기타, 변경 요청 첨부). **수정하지 않음** | 원본 파일명, 충돌 시 `name_1.ext` |
| `02_RFP_Analysis` (단계 2: `사업성평가_vX.Y.md/.json`, `bid_review_vX.Y.json` 추가) | RFP 분석 에이전트 결과 | `rfp_analysis_vX.Y.json` |
| `03_Requirements` | 요구사항 추출·검증 에이전트 결과 | `requirement_extraction_vX.Y.json`, `verification_vX.Y.json` |
| `04_Technology_Research` | 기술 조사 결과, 요구사항별 구현 방안(approach_writer), 요구사항 묶음별 구현 설계(design_writer, Phase 23: 구조·절차·적용 기술·근거) | `research_vX.Y.json`, `approach_report_vX.Y.json`, `implementation_design_vX.Y.json` |
| `05_Architecture_Design` | 아키텍처 에이전트 결과 | `architecture_vX.Y.json` |
| `06_WBS_Effort_Schedule` | WBS·간트, 인력 투입계획 Excel | 제안: `WBS_간트_vX.Y.xlsx`, `인력투입계획_vX.Y.xlsx` · 구축: `WBS_Gantt_YYYYMMDDHHMM.xlsx`, `Staffing_Plan_YYYYMMDDHHMM.xlsx` |
| `07_Submission_Proposal_PPT` | 제출용 PPT(템플릿이 있으면 그 용지·마스터), 목차 결정 기록(`sections`·`chapters`(장/절/소절 계획)·`templates`(사용 템플릿 파일명)), **목차·전략 브리프**(Phase 18: 에이전트 JSON `strategy_brief_vX.Y.json` + 검토용 Markdown `전략브리프_vX.Y.md`, Gate P 승인 대상), **슬라이드 명세**(Phase 19: 슬라이드별 제목·소절·결론형 제목·목적·독자·계획/실제 레이아웃·도식·근거·요구사항 ID·연결·도형 수와 요약) | `제안서_제출용_vX.Y.pptx`, `목차결정_vX.Y.json`, `전략브리프_vX.Y.md`, `슬라이드명세_제출용_vX.Y.json` |
| `08_Presentation_PPT` | 발표용 PPT, 슬라이드 명세(Phase 19) | `제안서_발표용_vX.Y.pptx`, `슬라이드명세_발표용_vX.Y.json` |
| `09_Excel_Deliverables` | 요구사항 정의서·추적표 | 제안: `요구사항정의서_vX.Y.xlsx`, `요구사항추적표_vX.Y.xlsx` · 구축: `Requirements_Definition_YYYYMMDDHHMM.xlsx`, `Traceability_Matrix_YYYYMMDDHHMM.xlsx` |
| `10_Diagrams_Charts_Images` | 구성도 3종·차트 PNG | `시스템구성도_vX.Y.png`, `SW구성도_vX.Y.png`, `서비스구성도_vX.Y.png`, `일정차트_vX.Y.png`, `공수차트_vX.Y.png` |
| `11_QA_Validation_Reports` | 통합 QA 보고서, 에이전트 QA 결과, **실제 렌더링 PNG**(Phase 21: `render/<덱 파일명>/slide_NN.png`, PowerPoint COM 내보내기, QA-FILE-14) | `통합QA보고서_vX.Y.md` + `.json`, `qa_report_vX.Y.json`, `render/…/slide_NN.png` |
| `12_Revision_History` | 기준선·변경 반영 스냅샷, 의미 비교 결과 | `baseline_snapshot_vX.Y.json`, `revision_CR-nnn_vX.Y.json`, `semantic_diff_vX.Y.json` |
| `13_Final_Deliverables` | Gate 5 승인 후 확정한 최종본 복사본 | 원 파일명 그대로 (같은 버전 재확정 거부) |

## 3. 버전과 덮어쓰기 규칙

- 제안 단계 산출물은 `stem_vX.Y.ext`로 저장하며, 폴더에 있는 최신 버전의 다음 minor(`v1.0 → v1.1 → …`)를 코드가 정한다.
- 구축 단계 변경 반영 문서는 `Stem_YYYYMMDDHHMM.ext`(분 단위 타임스탬프)이며, 같은 이름이 있으면 `_1`, `_2`를 붙인다.
- `FileStore.save_bytes`는 같은 이름이 있으면 `FileExistsConflict`로 거부한다(`open("xb")`). 업로드 원본·보존 저장은 `store_unique`로 `_n` 접미사를 붙인다. **기존 파일을 덮어쓰는 경로는 없다.**
- 모든 경로는 `ensure_within`으로 프로젝트 폴더 안으로 제한되며, 벗어나면 `PathSecurityError`.
- 최종본(`13_`)은 복사본이다. 임시본은 원 폴더에 그대로 남는다.

## 4. DB 레코드와 파일의 관계

| 레코드 | 파일 |
|---|---|
| `source_documents.stored_path`, `sha256` | `01_RFP_Original\…` |
| `agent_outputs.file_path`, `sha256` | `02_~05_`, `11_`, `12_`의 JSON |
| `deliverables.file_path`, `version`, `sha256`, `revision_id`, `integrity_status`, `qa_status` | `06_~10_` 파일 |
| `revisions.snapshot_path`, `change_ids`, `approval_id`, `parent_revision_id` | `12_Revision_History\…json` |
| `qa_runs.report_path`, `json_path` | `11_QA_Validation_Reports\…` |
| `change_requests.before_files`, `after_files` | 변경 전후 파일 경로 목록 |

불일치(파일 없음·해시 다름·프로젝트 폴더 밖)는 통합 QA `QA-FILE-09`·`QA-CON-07`과 `scripts\final_inspection.py`가 검출한다.

## 5. Excel 시트 구성 (생성 파일)

| 파일 | 시트 |
|---|---|
| 요구사항 정의서 (Phase 14 양식) | 표지 · 개정이력 · 요구사항목록 · 기능요구사항 · 비기능요구사항 · 제약·평가·제출조건 · 변경이력 · (구축) 변경관리대장 · 작성가이드. 본문은 **1행 묶음 머리글(묶음별 색) + 2행 컬럼 머리글 + 3행부터 데이터**, 33열: 식별(No·요구사항 ID·RFP 고유번호·대분류·중분류·요구사항 명) · 요구사항 내용(상세 내용·유형·원본 출처·RFP 원문 근거·**근거 구분**) · 구현 방안(구현방안·구현 난이도·난이도 근거·구현 근거(조사·출처)·검증 방법·검사 기준) · 수용·우선순위(수용여부·**대응 전략**·중요도·필수 여부·범위 분류·검토 상태·검증 상태) · 변경 정보(요구사항 변경여부·변경 내용·변경 일자·변경 근거·추가 요청자·추가일) · 협의·비고(검토 및 협의 내용·연결 산출물·비고). 필수 컬럼명(요구사항 ID·요구사항 명·요구사항 상세 내용·구현방안·수용여부·비고)은 유지. 행 색: 추가=연녹, 변경=연노랑, 삭제 요청=연주황, 삭제=회색+취소선, 같은 RFP 번호 묶음=연회색 띠 |
| 요구사항 추적표 (Phase 14 양식) | 표지 · 개정이력 · 추적표 · 검사기준(비기능) · 테스트상세 · 미추적 · 작성가이드. 추적표 29열: 요구사항(No·대분류·중분류·ID·명·유형) → 수용·대응(수용여부·**대응 전략·근거 구분(RFP 명시/참고 문서/외부 조사/설계 제안)·제안서 페이지(제출용/발표용, 생성된 덱에서 ID가 나타난 슬라이드 번호를 역산)**·생성/변경일자) → 설계(화면 ID·화면명·구성 요소 ID·구성 요소명·담당 역할) → 구현(WBS·Task 명·단위테스트 ID·결과) → 테스트(통합테스트 ID·명·결과) → 검사 기준(판정 기준·완료여부) → 검토(검토 상태·변경 사유·비고). 검사기준(비기능): 요구 내용·구현 내용·검사 기준·수행 결과 |
| WBS (Phase 15 양식) | **WBS(상세)** 25열: 식별(WBS ID·상위·구분·단계) · 개발 항목(Task 명·상세·수량·요구사항 ID·산출물) · 담당(개발 조직·담당 역할·개발자) · 일정(계획/실제 시작·종료일·기간·진척율·진행 상태) · 공수(M/D·산정 근거) · 관계(선행·후행·업무 유형) · 비고 + 오른쪽 **주 단위 간트**(1행 월 YYYY-MM 병합, 2행 월 내 주차; 단계 진한 파랑·활동 파랑·작업 연파랑·진척 녹색·마일스톤 주황 ◆) · **약식WBS(보고용)**: 구분·단계·항목·시작일·종료일 + 같은 간트, 첫 행 사업관리 마일스톤 라벨(착수·착수보고·중간보고·완료보고·종료), 구분·단계 세로 병합 · 의존관계(FS/SS/FF/SF·lag) · 산정근거. 마일스톤은 WBS 코드 `0`(사업관리) 아래 공수 0 항목 |
| 인력 투입계획 (Phase 15 양식) | **투입계획**(구성원별): 조직·역할·구성원·기술 등급·담당 업무·투입 시작/종료월·월별 공수(MM)·계(MM, SUM 수식)·비고 + 하단 합계 행(월별 SUM·총계). 구성원 이름 없으면 `역할N` 자리표시 · **역할요약**(역할·등급·기술·인원·담당·기간·MM·M/D·월별·근거·단가 입력란·비용 수식) · 공수요약 · 월별투입 · **비용산정**(단계 4: 역할·MM·단가·금액·비고 + 직접비·간접비·원가·매출·마진, 단가·예산 없으면 '산정 불가') |

구축 단계에서 업로드하는 기존 문서는 이 구조가 아니어도 되며, 컬럼 매핑 제안·확정을 거쳐 적재된다 ([USER_GUIDE.md 3.1](USER_GUIDE.md)).
