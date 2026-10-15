# Proposal Writer Agent

SI 제안서 자동 생성 및 구축 단계 요구사항 변경관리 멀티 에이전트 시스템.

- 런타임: Python 3.12, Streamlit, Claude Agent SDK (Python)
- 상태: **설계 단계 완료 (Phase 0)**. 소스 코드는 아직 없음.

## 문서

| 문서 | 내용 |
|---|---|
| [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | 목적, 확인된 개발 환경, 확정/미확정 기술, 단계 요약 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 레이어, 디렉터리 구조, Agent SDK 사용 방식, 데이터 흐름 |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | 엔티티 20종, enum, 상태 전이, SQLite 방침 |
| [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) | 에이전트 역할·권한·도구·실패 처리 |
| [docs/WORKFLOW_DESIGN.md](docs/WORKFLOW_DESIGN.md) | 제안 단계 / 구축 단계 업무 흐름, 승인 게이트 |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phase 1~7 작업과 완료 조건 |
| [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) | 테스트 계층, 핵심 케이스, 보고 형식 |
| [docs/RISK_REGISTER.md](docs/RISK_REGISTER.md) | 위험, 외부 의존성, 비용, 미확정 사항 |

## 폴더

```
src/proposal_agent/   소스 (Phase 1부터)
tests/                테스트
docs/                 설계 문서
Output/               업무 산출물 (프로젝트별, git 제외)
workspace/            임시 파일 (git 제외)
```

## 시작 (Phase 1 예정)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # ANTHROPIC_API_KEY 입력
streamlit run src/proposal_agent/app.py
```
