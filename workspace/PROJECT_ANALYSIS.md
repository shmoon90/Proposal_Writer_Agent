# PROJECT_ANALYSIS — 기존 프로젝트 자체 진단 (단계 0)

작성: 2026-10-16 · 기준 커밋: `62ed4d5` (branch `feature/major-revision`, main 과 동일) · 상위 지시문: "AI 기반 SI 사업 전 과정 지원 시스템 — 통합 개발 지시문" §1
근거는 모두 이 저장소의 실제 파일·명령 실행 결과다. 파일명만 보고 추정한 항목은 "확인 필요"로 표시했다.

## 1. 구조와 기술 스택

| 항목 | 실제 상태 (근거) |
|---|---|
| 언어·런타임 | Python 3.12 고정(`pyproject.toml` `requires-python = ">=3.12,<3.13"`), `.venv` 사용. 테스트·린트 도구: pytest 9, ruff, mypy |
| 핵심 라이브러리 | claude-agent-sdk 0.2.x, mcp 2.x, pydantic 2, pandas 2.x(고정), openpyxl, python-pptx 1.0.2, python-docx, pdfplumber·pypdf·pypdfium2(PDF), rapidocr+onnxruntime(OCR), Pillow(도식·차트 PNG), streamlit 1.6x, python-dotenv. PyMuPDF·matplotlib 는 이 PC 의 앱 제어 정책으로 차단되어 대체됨(`pyproject.toml` 주석, RISK R-19·R-25) |
| 진입점 | `streamlit run src\proposal_agent\app.py` (README·INSTALLATION). 대행 실행: `scripts/run_manual_agents.py`(FakeAgentRunner, `--fixture`·`--template`), 회귀: `scripts/run_regression.py`, 연결 점검: `scripts/check_mcp.py`, 민감 용어 훅: `scripts/check_sensitive_terms.py` |
| 소스 규모 | `src/proposal_agent` 35,088줄(2026-10-16 `wc -l`), 테스트 9,402줄·테스트 함수 274개(`tests/unit` 30파일, `tests/integration` 6파일 + `llm/` 1파일은 `-m llm` 으로 기본 제외). 커밋 31개 |
| 패키지 구성 | `ingest/`(PDF·DOCX·TXT·Excel 읽기, OCR, 청크, RFP 프로파일) · `requirements/`(추출·검증·ID 정책·근거·난이도·구현방안·구현설계) · `research/`(기술 조사·출처 분류) · `agents/`(역할 13종, 프롬프트 `.md` 13개, SDK 러너, 통제·훅, 인프로세스 MCP 도구) · `orchestrator/`(단계 실행·게이트) · `planning/`(공수·달력·일정·인력) · `generators/`(Excel 4종, PPT 2종+템플릿 빌더, 도식 PNG, 슬라이드 명세, manifest) · `changes/`(기준선 적재·의미 비교·영향 분석·반영) · `validation/`(독립 QA 52항목·렌더링·산출물 검사) · `services/`(프로젝트·문서·파이프라인·에이전트 단계·전략·템플릿·감사) · `storage/`(SQLite·마이그레이션·저장소 29종·파일·manifest) · `ui/`(Streamlit 8 페이지) · `config/`(설정·경로·오류·로그) · `models/`(pydantic 엔티티 15 모듈) |
| 데이터 저장 | SQLite `workspace/pwa.sqlite3`(마이그레이션 `storage/migrations.py`, 저장소 29종: 프로젝트·문서·요구사항·변경·추적·단계 실행·게이트·산출물·검증·승인·Revision·감사·시퀀스·추출 실행·블록·게이트 평가·기술 조사·구현 가능성·에이전트 출력·WBS·의존·역할·배정·구성 요소·화면·단위/통합 테스트·변경 요청·QA 실행) + 파일(`Output/<프로젝트>/00_~13_` 폴더, `manifest.json`) + 프로젝트 작업 폴더(`workspace/prj_*`) |
| 설정·비밀 | `.env`(`ANTHROPIC_API_KEY`, `PWA_*`), `config/settings.py` 23개 필드(모델·예산·턴·청크·OCR·휴일·글꼴·QA 옵션). 키는 코드에 없고 `.env` 는 git 무시. **현재 API 키 미설정, 크레딧 부족** — 모든 에이전트 기능은 FakeAgentRunner(모의 응답)로만 검증됨 |
| 에이전트 | 역할 13종(`agents/roles.py`): rfp_analyst, requirement_extractor, requirement_verifier, tech_researcher(WebSearch/WebFetch), approach_writer(Web), design_writer(Web), strategy_planner, architect, planner, proposal_writer, document_generator, qa_reviewer, semantic_differ. 출력은 pydantic 스키마(`agents/schemas.py`)로 강제, 예산·턴·시간·재시도·도구 허용 목록을 역할마다 선언. 인프로세스 MCP `pwa`(프로젝트 조회 도구 10종, `agents/tools/project_tools.py`), 외부 MCP 는 설정으로 추가 |
| 실행 흐름 | 제안 모드 16단계(`services/pipeline_service.py` PROPOSAL_STEPS: 업로드 → 추출 → RFP 분석 → 요구사항 추출 → 독립 검증(Gate 1) → 기술 조사(Gate 2) → 구현 방안 → 전략 브리프(Gate P) → 아키텍처 → 구현 설계 → WBS → 인력(Gate 3) → 문서 생성 → 제안 문안·PPT → 통합 QA(Gate 5) → 확정), 구축 모드 10단계(업로드 → 구조 분석 → 기준 적재 → 변경 요청 → 비교 → 영향 분석(승인) → 적용 → 재생성 → QA → Revision 확정). 게이트 0/1/P/2/3/4/5 는 코드 판정 + 사람 승인 |
| UI | Streamlit 8 페이지(`ui/app_pages`: home·project·extraction·requirements·agents·deliverables·build_baseline·changes). 긴 작업은 `st.status` 로 **동기 실행**(백그라운드 작업 큐 없음 — `jobs.py` 부재, RISK R-06 미해결). 단계별 버튼·승인/반려·재생성·QA 범주 선택·렌더링 체크 제공 |
| 산출물 | 제출용 PPT(A4 세로 템플릿 또는 16:9), 발표용 PPT, 요구사항 정의서(33열)·추적표(29열)·WBS/간트·인력투입계획 Excel, 구성도 PNG 3종, 슬라이드 명세 JSON, 전략 브리프 MD, 통합 QA 보고서 MD, manifest. 버전 파일명(`_vX.Y`)으로 덮어쓰기 방지 |
| 품질 장치 | 독립 QA 52항목(RFP 8·TECH 7·CON 13·FILE 14·EDIT 10), 재생성으로만 자동 수정(기본 2회), PowerPoint COM 렌더링·재열기(QA-FILE-14, 이 PC 에 PowerPoint 있음), 민감 용어 pre-commit 훅, ruff·mypy 통과(117 파일) |
| 문서 | `docs/` 46개(아키텍처·데이터 모델·워크플로·에이전트 설계·사용자/관리자 안내·단계 보고서 PHASE1~23·위험 대장 R-01~30·제한 사항·테스트 전략/결과), `WORK_LOG.md`, `workspace/DEVELOPMENT_STATUS.md/.json` |

## 2. 실제 동작 확인 결과 (2026-10-16)

- `pytest`(llm 제외): **289 passed, 1 skipped**. `ruff check`·`mypy src` 통과.
- 계산기 샘플(docx RFP, 모의 에이전트, 렌더링 켬): 제안 단계 16단계 전부 실행, 산출물 9종 생성, QA 52항목 중 49 실행·0 실패·6 검토.
- 실제 고객 RFP PDF(48쪽, 저장소 밖, 템플릿 2종, 모의 에이전트 응답은 세션의 Claude 가 작성): 요구사항 42건, 구현 설계 7묶음, 제출용 80장·발표용 60장, QA 52 실행·47 통과·0 실패·5 검토, 렌더링 PNG 육안 확인.
- 구축 모드: 통합 테스트(`tests/integration/test_phase7_qa.py` 등)와 `workspace/final_inspection.md`(2026-10-15) 기준 기준선 적재·변경 요청·의미 비교(규칙)·영향 분석·승인·재생성·QA 흐름 통과. 의미 비교의 AI 보강(semantic_differ)은 모의 응답.
- 실제 Claude 모델 호출·웹 검색은 **한 번도 실행되지 않았다**(크레딧 부족, RISK R-21). 따라서 "에이전트 품질"에 관한 모든 판단은 미검증이다.

## 3. 재사용 가능한 구성 요소 (판단: 유지)

| 구성 요소 | 판단 | 이유 |
|---|---|---|
| ingest(PDF·DOCX·TXT·Excel·OCR·청크·RFP 프로파일) | 재사용 | 실 RFP PDF 48쪽 처리 확인. HWP·PPTX·이미지 단독 입력은 미지원(개선 대상) |
| 요구사항 추출·검증·ID 정책·게이트 | 재사용 | 안정적 ID, 원문 근거 연결, 사람 승인 게이트가 지시문 §5 와 일치 |
| 에이전트 러너·역할 선언·스키마·MCP | 재사용 | 역할 추가가 선언 한 곳(`roles.py`)+프롬프트+스키마로 끝남(Phase 23 에서 확인) |
| 기술 조사·구현 방안·구현 설계·전략 브리프 | 재사용·보강 | 지시문 §4·§7·§8 의 골격이 이미 있음. 요구사항별 14개 분석 항목 중 일부(성능·확장, 장애·복구, 감사 로그, 트랜잭션) 는 스키마에 없음 |
| 계획 엔진(WBS·일정·인력·공수) | 재사용 | 영업일 달력, 선후행, 산정 근거 필수. 비용(원가·단가) 은 없음 |
| 생성기(Excel 4종·PPT 2종·템플릿·도식·차트) | 재사용 | 편집 가능 객체, 템플릿 적용, 렌더링 QA 까지 갖춤. 분량 조절·시각 다양성은 개선 |
| 변경관리(기준선·의미 비교·영향·승인·재생성) | 재사용·확장 | 지시문 §11 의 상태 흐름과 거의 일치(상태 7종). "사람이 수정한 PPT/Word 를 다시 입력해 비교" 는 미구현 |
| 독립 QA 52항목·렌더링 | 재사용 | 지시문 §9.3 의 PPT·Excel 검증 항목 대부분 구현 |
| 저장소(SQLite + 파일 + manifest) | 재사용 | 지시문 §17 의 안정적 ID·버전·감사가 이미 있음. 신규 객체(화면·DB·API·테스트·결함·결정·승인 ID) 는 마이그레이션으로 추가 가능 |

## 4. 구조적 문제·개선 필요 (근거)

1. **범위**: 현재 시스템은 20개 업무 영역 중 "제안 단계(1~9, 11, 14 일부)" 와 "구축 단계 변경관리(19, 20 일부)" 를 다룬다. 사업성 평가(3·4), 협상·계약(10), 회의·의사결정(12), 화면·DB·API 설계서(13), 코드 개발·리뷰(15), 테스트 계획·결함(16), 검수(17), 운영 이관(18) 은 **미구현**이다(`FEATURE_GAP_ANALYSIS.md`).
2. **긴 작업의 동기 실행**: Streamlit `st.status` 안에서 에이전트·QA 가 동기로 돈다. 페이지 재실행 시 중복 실행은 `start_step` 이 "실행 중" 단계를 거부해 막지만, 진행률 표시·중단·재개는 없다(`ui/app_pages/*.py`, RISK R-06).
3. **에이전트 품질 미검증**: 13개 역할 모두 모의 응답으로만 검증. 프롬프트 규칙(근거 없는 수치 금지, 열람 URL 만 인용)의 실제 준수 여부는 알 수 없다.
4. **수정 문서 되돌려 넣기 부재**: 구축 모드는 Excel 4종(정의서·추적표·WBS·인력) 만 기준 데이터로 적재하고, 변경 요청은 자연어·선택·첨부(OTHER) 다. 사람이 고친 PPT·Word·설계서의 의미 비교는 없다.
5. **추적성 사슬 불완전**: `RequirementTrace` 대상은 화면·WBS·단위/통합 테스트 4종뿐이고, 화면·테스트 객체는 구축 기준선 적재 때 추적표에서만 생성된다(`changes/baseline_service.py`). 전략·API·DB·코드 모듈·검수 기준 ID 가 없다.
6. **비용 정보 부재**: 공수(M/D·M/M) 까지만 있고 단가·원가·매출은 변경 영향의 `cost_*` 필드(값 없음) 외에 없다. 사업성 평가(§6) 의 전제가 된다.
7. **대형 모듈**: `independent_qa.py` 2,204줄, `shapes.py` 2,073줄, `decks.py` 1,367줄, `changes/service.py` 1,249줄 — 기능 추가 시 분할이 필요하다(동작 변경 없는 리팩터링, 되돌릴 수 있음).
8. **입력 형식**: PPT·이미지·HWP 는 RFP 입력으로 받지 못한다(`FileFormat`: pdf/docx/txt, Excel 은 산출물 적재용). 지시문 §0.1 의 입력 자료 목록과 차이.

## 5. 외부 환경 사실

- Windows 11, Python 3.12.10, PowerPoint 설치(COM 렌더링 가능), PyMuPDF·matplotlib DLL 차단, API 키 없음.
- 고객 자료(RFP·제안서·정의서·추적표·WBS·투입계획 샘플) 는 저장소 밖(외부 드라이브·세션 임시 폴더) 에만 있고 저장소에 두지 않는다(민감 용어 훅 43개 용어).
