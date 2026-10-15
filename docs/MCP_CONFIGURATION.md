# MCP_CONFIGURATION — MCP 서버 구성과 연결 점검

문서 버전 1.0 · 2026-10-15 · 구현: `src/proposal_agent/agents/tools/project_tools.py`, `agents/roles.py`, `services/agent_step_service.py`, `scripts/check_mcp.py`

---

## 1. 구성 요약

| 서버 | 종류 | 용도 | 사용 역할 | 설정 |
|---|---|---|---|---|
| `pwa` | 인프로세스 SDK MCP (`create_sdk_mcp_server`) | 프로젝트 데이터 **읽기 전용** 조회·파일 검증 | 대부분의 역할 | 설정 없음. 역할 실행 시 프로젝트별로 자동 조립 |
| 내장 `WebSearch` / `WebFetch` | Claude Code 내장 도구 | 기술 조사(공식 문서 우선) | `tech_researcher`만 | 설정 없음 |
| 외부 MCP (예: `claude-code-docs`) | HTTP/stdio | 선택. 문서 서버 등 | 역할 선언에 따라 | `.env`의 `PWA_MCP_EXTERNAL` JSON |

에이전트는 SQLite 파일·`Output` 폴더를 직접 읽지 않는다. 데이터는 `pwa` 도구로만 보고, 파일 쓰기 도구(Bash/Write/Edit/NotebookEdit)는 어떤 역할에도 없다.

## 2. 인프로세스 `pwa` 서버 도구 (10종)

도구 이름 규칙은 `mcp__pwa__<tool>`이며 모두 읽기 전용이다.

| 도구 | 입력 | 반환 |
|---|---|---|
| `get_project` | — | 프로젝트 요약(이름·모드·기간·상태) |
| `list_requirements` | `status?`, `type?` | 요구사항 목록(요약) |
| `get_requirement` | `id` | 요구사항 상세(출처·이력 포함) |
| `search_source_text` | `query`, `limit?` | 추출 블록 전문 검색 |
| `get_source_block` | `block_id` | 블록 원문·위치 |
| `list_research` | — | 기술 조사 기록 요약 |
| `list_findings` | `requirement_id?` | 검증 지적 사항 |
| `list_gates` | — | 게이트 상태 |
| `get_prior_output` | `role` | 이전 역할의 구조화 출력(JSON) |
| `verify_deliverable_file` | `path`(프로젝트 폴더 안 상대 경로) | 파일 열기·구조 검사 결과 |

경로 인자는 `ensure_within`으로 프로젝트 `Output` 폴더 안으로 제한된다.

## 3. 역할별 허용 도구

역할은 `roles.py`에서 `builtin_tools`, `mcp_servers`, `mcp_tool_patterns`를 선언하고, 실행 시 `allowed_tools`로 그 목록만 넘긴다. 선언되지 않은 서버·도구는 PreToolUse 훅과 `can_use_tool` 폴백이 거부한다.

| 역할 | 내장 도구 | pwa 도구 |
|---|---|---|
| rfp_analyst | — | search_source_text, get_source_block |
| requirement_extractor / requirement_verifier | — | — (프롬프트에 청크 포함) |
| tech_researcher | WebSearch, WebFetch | get_requirement, list_research |
| architect / planner / proposal_writer / document_generator | — | 읽기 9종 |
| qa_reviewer | — | 읽기 9종 + verify_deliverable_file |
| semantic_differ (구축 단계) | — | list_requirements, get_requirement |

## 4. 외부 MCP 서버 추가

1. `.env`에 서버를 선언한다 (JSON 한 줄).

```
PWA_MCP_EXTERNAL={"claude-code-docs": {"type": "http", "url": "https://code.claude.com/docs/mcp"}, "my-stdio": {"command": "C:\\tools\\server.exe", "args": ["--port", "0"]}}
```

2. 사용할 역할의 `mcp_servers`에 서버 이름을, `mcp_tool_patterns`에 `mcp__<server>__<tool>`을 추가한다 (`src/proposal_agent/agents/roles.py`). 선언하지 않으면 `agent_step_service`가 경고를 남기고 연결하지 않는다.
3. `python scripts\check_mcp.py`로 연결 상태를 확인한다.

지원 형식은 Claude Agent SDK가 받는 `mcp_servers` 설정(`type: http | sse | stdio`, `url` 또는 `command/args/env`)이다. 인증 헤더가 필요한 서버는 `headers`를 함께 넣되 값은 `.env`에만 둔다.

## 5. 연결 점검 (모델 호출 없음)

```powershell
python scripts\check_mcp.py
```

번들 Claude Code 프로세스를 띄워 `init` 메시지의 서버 상태와 노출 도구 목록을 읽는다(비용 0, API 키 필요). 2026-10-15 실행 결과:

- `pwa`: `connected`, 도구 10종 노출
- `claude-code-docs`(HTTP): `connected`, 도구 3종
- 일부러 깨뜨린 stdio 서버: `failed`로 정상 보고
- 내장 `WebSearch`/`WebFetch`: 세션 도구 목록에 노출됨

결과 파일: `workspace\mcp_check.json`. 같은 검사는 pytest의 `sdk` 마커(`tests/integration/test_sdk_connection.py`)와 에이전트 화면의 **연결 점검** 버튼으로도 실행된다.

## 6. 한계

- 실제 웹 검색·문서 열람 실행은 크레딧 부족으로 검증하지 못했다(도구 노출만 확인).
- Brave/Tavily 등 별도 검색 MCP는 연결하지 않았다. 필요하면 4절 절차로 추가하고 `tech_researcher`의 허용 목록에 넣는다.
