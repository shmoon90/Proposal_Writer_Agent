# Proposal Writer Agent

SI 제안서 자동 생성(제안 단계)과 구축 단계 요구사항 변경관리를 위한 멀티 에이전트 시스템.
Claude Agent SDK(Python) 위에서 에이전트가 분석·문안·판단을 데이터로 돌려주고, 문서 생성·ID 발급·일정 계산·QA·승인 게이트는 Python 코드가 결정적으로 수행한다.

- 검증된 실행 환경: **Windows 11 (10.0.26200) · Python 3.12.10 · PowerShell**. 다른 OS·Python 버전은 검증하지 않았다 ([docs/LIMITATIONS.md](docs/LIMITATIONS.md)).
- 상태 (2026-10-15): Phase 1~7 구현·병합 완료. 자동 테스트 215건 통과, 최종 기능 검수 42항목 통과(이 중 에이전트 호출 4항목은 모의 LLM). **실제 Claude 모델 호출은 API 크레딧 부족으로 검증하지 못했다** ([docs/TEST_RESULTS.md](docs/TEST_RESULTS.md), [docs/FINAL_REPORT.md](docs/FINAL_REPORT.md)).

## 빠른 시작 (Windows PowerShell)

```powershell
cd C:\DEV\Claude_Work\Proposal_Writer_Agent
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env        # ANTHROPIC_API_KEY=... 입력 (에이전트 실행 시 필수)
python -m pytest -q                 # 설치 검증 (모델 호출 없음)
streamlit run src\proposal_agent\app.py
```

브라우저에서 `http://localhost:8501`이 열린다. 자세한 절차는 [docs/INSTALLATION.md](docs/INSTALLATION.md), 사용 방법은 [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## 문서

| 문서 | 내용 |
|---|---|
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Python·가상환경·의존성·.env·SDK·MCP·DB·Streamlit·로그 (처음 설치하는 사용자용) |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | 제안 단계·구축 단계 화면 사용법, 승인 게이트, 산출물 확인 |
| [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) | 운영 절차: 설정·백업·로그·비용 통제·장애 대응·회귀 테스트 |
| [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) | 에이전트 10역할·권한·도구·실패 처리 (구현 반영) |
| [docs/FLOW_DIAGRAM.md](docs/FLOW_DIAGRAM.md) | 에이전트·MCP·도구·코드 간 호출 흐름 다이어그램(Mermaid) |
| [docs/MCP_CONFIGURATION.md](docs/MCP_CONFIGURATION.md) | 인프로세스 `pwa` MCP 서버, 외부 MCP 추가 방법, 연결 점검 |
| [docs/OUTPUT_STRUCTURE.md](docs/OUTPUT_STRUCTURE.md) | `Output/<프로젝트>/00_~13_` 폴더·파일명·버전 규칙 |
| [docs/ERROR_HANDLING.md](docs/ERROR_HANDLING.md) | 오류 종류·메시지 형식·원인·조치 |
| [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) | 실제 실행한 테스트와 결과 |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | 미구현·부분 구현·검증되지 않은 사항 |
| [docs/FINAL_REPORT.md](docs/FINAL_REPORT.md) | 최종 검수 보고서 |
| 설계 | [PROJECT_OVERVIEW](docs/PROJECT_OVERVIEW.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATA_MODEL](docs/DATA_MODEL.md) · [WORKFLOW_DESIGN](docs/WORKFLOW_DESIGN.md) · [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md) · [TEST_STRATEGY](docs/TEST_STRATEGY.md) · [RISK_REGISTER](docs/RISK_REGISTER.md) |
| 단계 보고 | [PHASE1](docs/PHASE1_REPORT.md) · [PHASE2](docs/PHASE2_REPORT.md) · [PHASE3](docs/PHASE3_REPORT.md) · [PHASE4](docs/PHASE4_REPORT.md) · [PHASE6](docs/PHASE6_REPORT.md) · [PHASE7](docs/PHASE7_REPORT.md) |

## 폴더

```
src/proposal_agent/   소스 (config, models, storage, ingest, requirements, agents, research,
                      orchestrator, planning, generators, validation, changes, services, ui)
tests/                pytest (unit · integration · integration/llm[수동])
scripts/              check_mcp.py · run_phase2_llm.py · run_regression.py · final_inspection.py
docs/                 설계·운영 문서, 단계 보고서, samples/
Output/               업무 산출물 (프로젝트별, git 제외)
workspace/            임시 파일·로그·SQLite DB (git 제외)
```

## 핵심 원칙

- 에이전트는 파일을 만들지 않고 JSON(구조화 출력)만 돌려준다. 파일·ID·일정·QA·게이트는 코드가 만든다.
- 기존 파일은 덮어쓰지 않는다(버전 파일명, 충돌 시 `_1` 접미사). 요구사항은 물리 삭제하지 않는다.
- 승인 게이트(Gate 0~5)는 코드가 판정하고, 최종 확정·변경 반영은 사람 승인이 있어야 한다.
- API 키는 `.env` 또는 OS 환경변수로만 읽고 로그·DB·감사 기록에 남기지 않는다.
