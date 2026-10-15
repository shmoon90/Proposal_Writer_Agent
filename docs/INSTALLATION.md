# INSTALLATION — 설치와 실행 (Windows)

문서 버전 1.0 · 2026-10-15 · 대상: 처음 설치하는 사용자

검증된 환경은 다음 하나뿐이다. 그 밖의 OS·Python 버전에서는 동작을 확인하지 않았다.

| 항목 | 검증된 값 |
|---|---|
| OS | Windows 11 Pro 10.0.26200 (x64) |
| Python | 3.12.10 (`py -3.12`) — `pyproject.toml`은 `>=3.12,<3.13`을 요구 |
| 셸 | PowerShell 5.1 (Windows 기본) |
| 프로젝트 루트 | `C:\DEV\Claude_Work\Proposal_Writer_Agent` |

---

## 1. Python과 가상환경

```powershell
py -3.12 --version                      # Python 3.12.x 확인 (없으면 python.org에서 3.12 설치)
cd C:\DEV\Claude_Work\Proposal_Writer_Agent
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python --version                        # 3.12.x
```

PowerShell에서 `Activate.ps1` 실행이 막히면 현재 사용자 범위로 실행 정책을 바꾼다.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

이후 모든 명령은 가상환경이 활성화된 상태(프롬프트 앞 `(.venv)`)에서 실행한다. 가상환경을 켜지 않으려면 `python` 대신 `.venv\Scripts\python`을 쓴다.

## 2. 의존성 설치

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

- `-e`(editable)로 설치해야 `src/proposal_agent`가 패키지로 임포트된다. `[dev]`는 pytest·ruff·mypy·reportlab(테스트 PDF 생성)을 포함한다.
- 실제 설치되어 검증된 버전은 [FINAL_REPORT.md 4절](FINAL_REPORT.md)에 있다 (claude-agent-sdk 0.2.167, mcp 2.3.0, streamlit 1.66.0, pydantic 2.14.1, openpyxl 3.1.5, python-pptx 1.0.2, python-docx 1.2.0, pdfplumber 0.11.10, pypdf 6.20.1, pypdfium2 5.14.0, rapidocr 3.10.0, onnxruntime 1.31.0, pillow 12.3.0, pandas 2.3.3). `requirements.lock.txt`에 전체 고정 목록이 있다.
- OCR 한국어 인식 모델(`korean_PP-OCRv5_rec_mobile`, 약 12.9MB)은 스캔 PDF를 처음 처리할 때 rapidocr가 내려받는다. 인터넷이 막힌 PC에서는 스캔 PDF 처리가 실패하며, 텍스트 PDF·DOCX·TXT는 영향이 없다.
- 이 개발 PC에서는 Windows 앱 제어 정책이 PyMuPDF·matplotlib의 네이티브 DLL을 차단해 이 두 패키지를 쓰지 않는다. 의존성에 포함되어 있지 않으므로 별도 조치는 필요 없다.

설치 확인:

```powershell
python -c "import proposal_agent, claude_agent_sdk, mcp, streamlit; print('ok')"
```

## 3. 환경변수와 API 키

`.env.example`을 복사해 `.env`를 만들고 값을 채운다. `.env`는 `.gitignore`에 포함되어 저장소에 올라가지 않는다.

```powershell
Copy-Item .env.example .env
notepad .env
```

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 에이전트 실행 시 필수 | Anthropic Console에서 발급한 API 키. **구독(claude.ai) 로그인은 사용할 수 없다** (Agent SDK는 서드파티 앱의 OAuth 로그인을 허용하지 않음). 키가 없어도 프로젝트 생성·문서 추출·Excel/PPT 생성·QA·변경관리 규칙 분석은 동작하고, 에이전트 단계만 `ConfigError`로 막힌다 |
| `PWA_APP_ENV` | 선택 | `dev`(기본) / `prod`. prod는 기동 시 API 키가 없으면 실패한다 |
| `PWA_MODEL_PRIMARY` / `PWA_MODEL_WORKER` | 선택 | 기본 `claude-opus-5-5` / `claude-sonnet-5-5` |
| `PWA_MAX_BUDGET_USD_PER_STEP` | 선택 | 단계당 비용 상한 기본 2.0 (역할별 상한은 이 값의 3배를 넘지 않음) |
| `PWA_OUTPUT_ROOT` / `PWA_WORKSPACE_ROOT` / `PWA_DB_PATH` | 선택 | 기본 `<루트>\Output`, `<루트>\workspace`, `<루트>\workspace\pwa.sqlite3` |
| `PWA_LOG_LEVEL` | 선택 | 기본 `INFO` |
| `PWA_HOLIDAYS` | 선택 | 영업일 계산에서 제외할 공휴일, 쉼표 구분 ISO 날짜 (`2026-12-25,2027-01-01`) |
| `PWA_FONT_PATH` | 선택 | 구성도·차트 한글 폰트, 기본 `C:\Windows\Fonts\malgun.ttf` |
| `PWA_ID_PREFIXES` | 선택 | 요구사항 ID 접두사 JSON, 기본 `{"functional":"FR","non_functional":"NFR","constraint":"CON","evaluation":"EVA","submission":"SUB"}` |
| `PWA_MCP_EXTERNAL` | 선택 | 외부 MCP 서버 JSON ([MCP_CONFIGURATION.md](MCP_CONFIGURATION.md)) |
| `PWA_QA_MAX_FIX_ROUNDS` / `PWA_QA_USE_AGENT` | 선택 | 통합 QA 자동 수정 횟수(기본 2) / qa_reviewer 에이전트 검토 사용(기본 false) |

우선순위: OS 환경변수 > `.env` > 기본값. 운영 환경에서는 `.env` 대신 OS 환경변수(또는 Windows 자격 증명 관리)를 권장한다.

## 4. Claude Agent SDK 설정

- 패키지 `claude-agent-sdk`에 Claude Code CLI(`claude.exe`)가 번들되어 있어 별도 설치가 없다. 에이전트는 이 CLI 프로세스를 통해 실행되며, 환경변수 `ANTHROPIC_API_KEY`만 전달된다.
- 역할별 모델·턴·예산·시간 제한은 `src/proposal_agent/agents/roles.py`에 정의되어 있고, `.env`의 `PWA_*` 값으로 상한을 조정한다.
- 모델 호출 없이 SDK·MCP 연결만 점검(비용 0):

```powershell
python scripts\check_mcp.py
```

출력의 `pwa`가 `connected`, 도구 10종이 보이면 정상이다. 결과는 `workspace\mcp_check.json`에 남는다. API 키가 없으면 `ConfigError`로 끝난다.

## 5. MCP 서버 연결 설정

기본 구성은 인프로세스 `pwa` 서버(프로젝트 데이터 읽기 전용 10개 도구)와 내장 `WebSearch`/`WebFetch`(기술 조사 역할만)이며 추가 설정이 없다. 외부 MCP 서버를 붙이려면 `.env`에 JSON으로 선언한다.

```
PWA_MCP_EXTERNAL={"claude-code-docs": {"type": "http", "url": "https://code.claude.com/docs/mcp"}}
```

역할이 사용하는 서버 이름은 `roles.py`의 `mcp_servers`에 선언되어야 하며, 선언되지 않은 서버는 연결되지 않는다. 세부는 [MCP_CONFIGURATION.md](MCP_CONFIGURATION.md).

## 6. SQLite DB 초기화

별도 명령이 없다. 앱이나 테스트가 처음 `AppContext`를 만들 때 `workspace\pwa.sqlite3`를 만들고 마이그레이션(0001~0006)을 적용한다. 적용된 버전은 `schema_migrations` 테이블에 기록된다.

- 초기화(모든 데이터 삭제): 앱을 종료한 뒤 `workspace\pwa.sqlite3`를 삭제한다. `Output\`의 산출물 파일은 지워지지 않으므로 같이 정리할지 결정한다.
- 백업: 앱 종료 후 `workspace\pwa.sqlite3`와 `Output\`를 함께 복사한다 ([ADMIN_GUIDE.md](ADMIN_GUIDE.md)).

## 7. Streamlit 실행

```powershell
streamlit run src\proposal_agent\app.py
```

- 기본 주소 `http://localhost:8501`. 포트 변경: `streamlit run src\proposal_agent\app.py --server.port 8600`.
- 좌측 사이드바에 시작 / 프로젝트 / 문서 추출 / 요구사항 / 에이전트·조사 / 산출물 / 구축: 기준 문서 / 구축: 변경 관리 화면이 있다. 사용 순서는 [USER_GUIDE.md](USER_GUIDE.md).
- 종료: 터미널에서 `Ctrl+C`.

## 8. 로그와 오류 확인

| 위치 | 내용 |
|---|---|
| `workspace\logs\app.log` | 애플리케이션 로그(회전 5MB×3). 수준은 `PWA_LOG_LEVEL` |
| 터미널(stderr) | 같은 로그가 콘솔에도 출력된다 |
| 화면의 오류 박스 | 모든 업무 오류는 `메시지 (원인: …; 조치: …)` 형식으로 표시된다 ([ERROR_HANDLING.md](ERROR_HANDLING.md)) |
| DB `audit_events` | 단계 시작·완료·실패, 승인, 변경 반영 등 감사 이벤트(비밀값은 `***`로 마스킹) |
| `Output\<프로젝트>\11_QA_Validation_Reports\` | 통합 QA 보고서(md·json) |

에이전트 단계가 `Credit balance is too low`로 실패하면 Anthropic Console에서 크레딧을 충전해야 한다. 코드 측 설정으로는 해결되지 않는다.

## 9. 설치 검증

```powershell
python -m pytest -q                      # 215 passed 기대 (모델 호출 없음, 약 1분)
python scripts\final_inspection.py       # 제안·구축 전체 기능 검수 (모의 LLM, 약 30초)
python scripts\run_regression.py         # pytest + 데모 프로젝트 통합 QA 보고서
```

실제 모델 호출 검증(비용 발생, API 키·크레딧 필요):

```powershell
python scripts\run_phase2_llm.py         # 추출→요구사항→검증을 실제 Claude로 실행
python -m pytest -m llm -q               # LLM 계약 테스트
```
