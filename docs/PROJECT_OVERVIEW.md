# PROJECT_OVERVIEW — SI 제안서 자동 생성 및 구축 단계 변경관리 시스템

| 항목 | 내용 |
|---|---|
| 문서 버전 | 0.1 (설계 단계) |
| 작성일 | 2026-10-15 |
| 프로젝트 루트 | `C:\DEV\Claude_Work\Proposal_Writer_Agent` |
| 산출물 루트 | `C:\DEV\Claude_Work\Proposal_Writer_Agent\Output` |
| 상태 | 설계 완료, 구현 착수 전 |

관련 문서: [ARCHITECTURE.md](ARCHITECTURE.md) · [DATA_MODEL.md](DATA_MODEL.md) · [AGENT_DESIGN.md](AGENT_DESIGN.md) · [WORKFLOW_DESIGN.md](WORKFLOW_DESIGN.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [TEST_STRATEGY.md](TEST_STRATEGY.md) · [RISK_REGISTER.md](RISK_REGISTER.md)

---

## 1. 목적

SI 프로젝트의 **제안 단계**와 **구축 단계**를 지원하는 멀티 에이전트 애플리케이션을 만든다.

- **제안 단계**: RFP를 분석해 요구사항을 추출·검증하고, 기술 조사와 구현 가능성 검토를 거쳐 제출용/발표용 PPT, 요구사항 정의서, 추적표, WBS, 인력 투입계획, 구성도를 생성한다.
- **구축 단계**: 기존 산출물(요구사항 정의서, 추적표, WBS, 인력계획)을 업로드해 기준 데이터로 삼고, 요구사항 추가·변경·삭제 요청에 대해 영향 분석을 수행한 뒤 사람의 승인 하에 관련 문서를 새 버전으로 갱신한다.

AI(LLM)는 **의미 해석·조사·작성·영향 분석**을 담당하고, **ID 발급·날짜·공수 합계·선후행 검증·파일 무결성·버전 관리**는 결정적 Python 코드가 담당한다.

## 2. 실제 확인한 개발 환경 (2026-10-15)

| 항목 | 확인 결과 | 비고 |
|---|---|---|
| OS | Windows 11 Pro 10.0.26200 | 경로는 `pathlib.Path`로만 관리 |
| Python | 3.12.10 (`C:\dev\python312`) | 3.15 런처 항목도 있으나 pip 실행 불가 → **3.12 고정** |
| pip | 25.0.1 | 26.2.1 업그레이드 가능 |
| Git | 2.56.0.windows.2 | 전역 설정 없음 → 이번 단계에서 설정함 (3절) |
| Node.js / npm | v24.21.0 / 11.19.0 | npx 기반 MCP 서버 실행 가능 |
| `claude` CLI | PATH에 없음 | Agent SDK가 `claude.exe`를 번들(256 MB)하므로 **별도 설치 불필요** |
| uv | 없음 | pip + venv 사용 |
| Tesseract | 없음 | OCR 방식 미확정 (RISK R-07) |
| `ANTHROPIC_API_KEY` | `.env`에 설정됨 (2026-10-15, 값은 기록하지 않음) | Git 제외 확인. 런타임 에이전트 실행에 필수 (RISK R-01) |
| 가상환경 | `.venv` (Python 3.12.10), `pip install -e .[dev]` 완료 | 설치 버전은 `requirements.lock.txt` |

### 설치된 패키지 (`.venv`, 2026-10-15)

| 패키지 | 설치 버전 | 비고 |
|---|---|---|
| claude-agent-sdk | 0.2.167 | 전역에는 0.2.165 |
| mcp / mcp-types | 2.3.0 | |
| pydantic | 2.14.1 | |
| streamlit | 1.66.0 | |
| pandas | 2.3.3 | D-03: 2.x 고정 결정 (`pandas>=2.2,<3`) |
| openpyxl / python-pptx / python-docx | 3.1.5 / 1.0.2 / 1.2.0 | |
| pdfplumber / pypdf / pypdfium2 | 0.11.10 / 6.20.1 / 5.14.0 | PyMuPDF 1.28.2는 이 PC의 앱 제어 정책이 DLL을 차단해 제거 (RISK R-19) |
| rapidocr / onnxruntime | 3.10.0 / 1.31.0 | 한국어 OCR 확정 (D-02) |
| matplotlib | 3.11.2 | |
| reportlab (dev) | 5.0.1 | 테스트용 텍스트 PDF 픽스처 생성 |
| pytest / pytest-asyncio / ruff / mypy | 9.1.1 / 1.4.0 / 0.17.0 / 2.4.0 | |
| python-dotenv | 1.2.4 | .env 로드 |

### PyPI에서 확인한 설치 가능 버전 (미설치)

| 패키지 | 최신 버전 | 메모 |
|---|---|---|
| streamlit | 1.66.0 | Requires-Python ≥3.11, pandas <4 |
| pandas | 3.0.6 | pandas 3.x는 Copy-on-Write 기본, 문자열 dtype 변경 → **2.x 계열 고정 권장** (RISK R-09) |
| openpyxl | 3.1.5 | |
| python-pptx | 1.0.2 | |
| python-docx | 1.2.0 | |
| pymupdf | 1.28.2 | |
| matplotlib | 3.11.2 | |
| pytest | 9.1.1 | |
| ruff | 0.17.0 | |
| mypy | 2.4.0 | |
| anthropic | 1.14.0 | Agent SDK 외 직접 API 호출이 필요할 때만 |
| pytesseract | 0.3.13 | Tesseract 바이너리 필요 |
| rapidocr-onnxruntime | 1.4.4 | 순수 pip, 한국어 모델 확인 필요 |

## 3. 이번 단계에서 수행한 환경 설정

- `git init` (브랜치 `main`)
- 전역: `init.defaultBranch=main`, `core.autocrlf=true`, `core.quotepath=false`
- 저장소 로컬: `user.name=shmoon90`, `user.email=awasoftlab@gmail.com` (필요 시 변경)
- `.gitignore`: `Output/`, `workspace/`, `.env`, `.venv/`, DB 파일 제외

## 4. 확정된 기술 / 확인이 필요한 기술

### 확정 (공식 문서·설치 패키지로 API 확인 완료)

| 기술 | 확인 내용 |
|---|---|
| **Claude Agent SDK (Python) 0.2.165** | `query()`, `ClaudeSDKClient`, `ClaudeAgentOptions`, `AgentDefinition`(서브에이전트, camelCase 필드), `create_sdk_mcp_server`/`@tool`(인프로세스 MCP), `hooks`/`HookMatcher`, `can_use_tool`, `output_format={"type":"json_schema","schema":...}` + `ResultMessage.structured_output`, `max_budget_usd`, `max_turns`, `effort`, `cwd`, `add_dirs` — 설치된 패키지에서 시그니처 직접 확인 |
| **내장 도구** | `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Agent`, `Skill` 등. **WebSearch는 Claude API 기본 제공 서버 도구** → 별도 MCP 서버 없이 기술 조사 가능 (Bedrock 미지원) |
| **MCP Python SDK 2.3.0** | v2에서 `FastMCP`→`MCPServer` 개명, `from mcp.server.mcpserver import MCPServer, Context`. 외부 프로세스 MCP 서버 작성 시 사용. 1차 구현은 인프로세스 SDK MCP 서버(`create_sdk_mcp_server`)로 충분 |
| **인증** | `ANTHROPIC_API_KEY` 환경변수 필수. SDK는 `.env`를 자동 로드하지 않음 → `python-dotenv`로 직접 로드. **claude.ai 구독 로그인은 서드파티 제품에 허용되지 않음** (공식 문서 명시) |
| Pydantic v2, pandas, openpyxl, python-pptx, python-docx, PyMuPDF, matplotlib, SQLite(표준 `sqlite3`), pytest, Ruff | 표준적이며 PyPI 버전 확인 완료 |

### 확인·결정이 필요한 기술

| 항목 | 상태 | 조치 |
|---|---|---|
| OCR 엔진 | 미확정 | `rapidocr-onnxruntime`(한국어 모델 확인) vs `pytesseract`(바이너리 설치) → Phase 2 스파이크 |
| pandas 메이저 버전 | 미확정 | 2.x 고정 vs 3.x 수용 → Phase 1에서 streamlit 호환 검증 후 결정 |
| 모델 선택 | 미확정 | 기본 `claude-opus-5-5`, 보조 `claude-sonnet-5-5`/`claude-haiku-5-5` 권장. 비용 측정 후 역할별 조정 |
| 다이어그램 생성 방식 | 미확정 | matplotlib 직접 렌더링 vs Mermaid→이미지(외부 도구 필요) vs python-pptx 도형 → Phase 4 |
| 구축 단계 기존 문서 파싱 | 미확정 | 고객사별 Excel 양식이 다름 → 컬럼 매핑 UI + 템플릿 프로파일로 대응 |
| Agent SDK 세션 영속화 | 미확정 | `session_store` 옵션 활용 여부 → Phase 2 |

## 5. 전체 구현 단계 요약

세부 내용은 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

| Phase | 범위 | 완료 조건(요약) |
|---|---|---|
| 0 | 설계 (이번 단계) | docs 8종 작성, 일관성 검토, 첫 커밋 |
| 1 | 기반: 환경·데이터 모델·저장소·설정·로깅 | venv 구성, 모델/DB CRUD 단위 테스트 통과, Streamlit 모드 선택 화면 기동 |
| 2 | 문서 입력 + 요구사항 추출/검증 (제안 단계 핵심) | PDF/DOCX 텍스트 추출, 요구사항 추출 에이전트 + 독립 검증 에이전트, 출처 추적 |
| 3 | 기술 조사 + WBS/공수/인력 계산 | WebSearch 기반 조사, 출처 관리, 결정적 일정·공수 엔진 |
| 4 | 문서 생성: Excel 4종, PPT 2종, 구성도 | 공통 데이터→파일 생성, 무결성 검사 |
| 5 | QA·승인·버전 관리 | 산출물 QA 에이전트, 승인 흐름, Revision 기록 |
| 6 | 구축 단계: 업로드·비교·영향 분석·갱신 | 기존 문서 파싱, 변경 요청 UI, 영향 분석, 새 버전 생성 |
| 7 | 안정화·운영 | E2E 테스트, 비용 모니터링, 사용자 매뉴얼 |

## 6. 핵심 품질 원칙 (요약)

1. RFP 원문과 출처 추적 가능 (`SourceDocument` → `Requirement.source_refs`)
2. 추출 후 **독립 검증 에이전트**가 재검토 (추출 에이전트와 분리된 컨텍스트)
3. 제안서 작성 전 기술 구현 가능성 검토 (공식 문서 우선, 출처 저장)
4. 필수 / 선택 제안 / 과잉 범위 구분 (`Requirement.scope_class`)
5. 일정·공수 산정 근거 필드 필수 (`WBSItem.estimate_basis`)
6. 생성 파일 무결성 검사 (다시 열어 필수 시트·컬럼 확인)
7. 승인되지 않은 변경은 기준 데이터에 반영하지 않음 (`Approval` 게이트)
8. 기존 파일은 사용자 승인 없이 덮어쓰지 않음 (항상 새 버전 파일명)
9. 실행하지 않은 테스트를 통과로 보고하지 않음
10. 오류는 원인·해결 방안과 함께 `AuditEvent`/로그에 기록

## 7. 이번 단계에서 생성한 것

```
Proposal_Writer_Agent/
├── .gitignore
├── pyproject.toml            # 의존성·도구 설정 초안 (설치는 Phase 1)
├── docs/                     # 설계 문서 8종
├── src/proposal_agent/       # 패키지 골격 (빈 디렉터리, 코드 없음)
├── tests/{unit,integration,fixtures}/
├── Output/.gitkeep           # 업무 산출물 루트 (git 제외)
├── workspace/.gitkeep        # 임시 파일 (git 제외)
└── scripts/
```

설계 문서에 없는 기능은 구현된 것이 없으며, 이번 단계에서 실행한 테스트는 없다.
