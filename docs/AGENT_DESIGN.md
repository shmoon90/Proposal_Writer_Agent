# AGENT_DESIGN — 에이전트별 책임과 권한

문서 버전 0.1 · 2026-10-15 · 관련: [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md)

---

## 0. 구현 반영 (Phase 3·6·7, 2026-10-15) — 실제 구현된 역할·도구·통제

> 2026-10-15 기준 역할 10종. 실제 모델 호출은 크레딧 부족으로 미검증이며, 모든 역할은 FakeAgentRunner(모의 응답)와 SDK 연결 점검(비용 0)으로만 검증했다. 통합 QA(Phase 7)는 에이전트 자기 평가를 쓰지 않고 코드(`validation/independent_qa.py`)가 독립 검증하며, `qa_reviewer` 결과는 사람 검토 항목으로만 덧붙는다 ([PHASE7_REPORT.md](PHASE7_REPORT.md)).

구현 코드: `agents/roles.py`(역할 정의), `agents/runner.py`(SDK 어댑터), `agents/control.py`·`hooks.py`(정책·훅), `agents/tools/project_tools.py`(인프로세스 MCP), `services/agent_step_service.py`(역할 실행·재사용·저장), `research/`(기술 조사).

| # | 역할 key | 입력 | 출력 스키마 | 내장 도구 | MCP 도구 | 턴/예산/시간 | 재사용 |
|---|---|---|---|---|---|---|---|
| 1 | `rfp_analyst` | 추출 블록 청크 | `RfpAnalysis` | 없음 | `pwa.search_source_text`, `pwa.get_source_block` | 10 / $2 / 600s | — |
| 2 | `requirement_extractor` | 청크 | `RequirementExtraction` | 없음 | 없음 | 8 / $2 / 600s | rfp_analyst |
| 3 | `requirement_verifier` | 청크 + 요구사항 | `VerificationReport` | 없음 | 없음 | 8 / $2 / 600s | — |
| 4 | `tech_researcher` | 요구사항·RFP 분석·주제 | `ResearchReport` | **WebSearch, WebFetch** | `pwa.get_requirement`, `pwa.list_research` | 30 / $6 / 1200s | rfp_analyst |
| 5 | `architect` | 요구사항·조사 | `ArchitectureDraft` | 없음 | pwa 읽기 9종 | 12 / $3 / 600s | tech_researcher, rfp_analyst |
| 6 | `planner` | 요구사항·아키텍처·기간 | `WBSDraft` (날짜 없음) | 없음 | pwa 읽기 9종 | 12 / $3 / 600s | architect, rfp_analyst |
| 7 | `proposal_writer` | 기준 데이터 | `ProposalContent` | 없음 | pwa 읽기 9종 | 15 / $4 / 600s | 1·4·5·6 |
| 8 | `document_generator` | 기준 데이터 | `DocumentPlan` (파일은 코드 생성) | 없음 | pwa 읽기 9종 | 10 / $2 / 600s | 7·6·5 |
| 9 | `qa_reviewer` | 산출물 텍스트·기준·변경 요청 | `QaReport` | 없음 | pwa 읽기 9종 + `verify_deliverable_file` | 12 / $3 / 600s | 8·7 |
| 10 | `semantic_differ` (Phase 6) | 변경 요청 항목·기존 요구사항·규칙 분류 | `SemanticDiffDraft` | 없음 | `pwa.list_requirements`, `pwa.get_requirement` | 8 / $1.5 / 600s | — (규칙 결과를 입력으로 받음) |

공통 실패 처리: `AgentRunError(subtype, cause, resolution, detail.category)` → StepRun `failed` + 감사 이벤트. 일시 오류(rate_limit/overloaded/connection/process)만 `retries` 횟수 재시도, 크레딧·인증·예산·스키마 오류는 즉시 실패. 시간 초과·취소는 `ClaudeSDKClient.interrupt()`로 중단.

**실제 연결 확인된 MCP 서버·도구 (2026-10-15, `scripts/check_mcp.py`)**: 인프로세스 `pwa`(도구 10종: get_project, list_requirements, get_requirement, search_source_text, get_source_block, list_research, list_findings, list_gates, get_prior_output, verify_deliverable_file) `connected`; 외부 HTTP `claude-code-docs`(https://code.claude.com/docs/mcp, 도구 3종) `connected`; 깨진 stdio 서버 `failed` 정상 보고. 내장 `WebSearch`/`WebFetch`는 세션 도구 목록에 노출됨을 확인(실제 검색 실행은 크레딧 부족으로 미검증). 웹 검색·문서 열람은 별도 MCP 서버 없이 내장 서버 도구를 쓰며, Brave/Tavily 등 검색 MCP는 연결하지 않았다.

## 1. 실행 모델

- 런타임: **Claude Agent SDK for Python 0.2.165** (번들 `claude.exe`). 개발 도구인 Claude Code와 별개.
- 오케스트레이터가 각 파이프라인 단계마다 `query()`를 호출한다. 한 단계 = 하나의 **주 에이전트(main)**. 주 에이전트는 필요 시 `AgentDefinition`으로 정의된 **서브에이전트**를 `Agent` 도구로 호출한다 (깊이 1로 제한).
- 모든 단계는 `output_format` JSON 스키마로 결과를 반환하고, Pydantic 모델로 검증된다.
- 에이전트는 파일을 생성하지 않는다. 문서 파일은 Python generator가 만든다. 에이전트는 **문안·구조·판단**을 데이터로 돌려준다.
- 인증: `ANTHROPIC_API_KEY` (API 키 방식만 허용됨).

## 2. 공통 권한 정책

| 항목 | 기본값 | 비고 |
|---|---|---|
| `permission_mode` | `dontAsk` | UI에서 권한 프롬프트 불가. 허용 목록 외 도구는 거부 |
| `allowed_tools` | 역할별 명시 | 아래 표 |
| `disallowed_tools` | `Bash`, `Write`, `Edit`, `NotebookEdit` | 전 역할 공통. 예외 없음 |
| `cwd` | `workspace/<project_id>` | 추출 텍스트·청크가 있는 위치 |
| `add_dirs` | `Output/<project>/01_RFP_Original` | 원본 읽기 전용 |
| `max_turns` | 역할별 20~60 | |
| `max_budget_usd` | 역할별 (설정 가능) | 초과 시 `error_max_budget_usd` → 단계 실패, 사용자 알림 |
| `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | `1` | 서브에이전트가 서브에이전트를 만들지 못함 |
| `env.CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | `4` | |
| 훅 `PreToolUse(Write\|Edit)` | 거부 | 2중 안전장치 |
| 훅 `PostToolUse(WebFetch\|WebSearch)` | URL·제목을 AuditEvent로 기록 | 출처 추적 |
| `model` | 주 에이전트 `claude-opus-5-5`, 보조 `claude-sonnet-5-5` | 비용 측정 후 조정 (RISK R-03) |
| `effort` | 추출·검증·영향 분석 `high`, 문안 작성 `medium`, 요약 `low` | |

## 3. 프로젝트 데이터 접근 도구 (인프로세스 SDK MCP)

에이전트가 SQLite 파일을 직접 읽지 않도록 `create_sdk_mcp_server(name="pwa")`로 읽기 전용 도구를 제공한다. 이름 규칙: `mcp__pwa__<tool>`.

| 도구 | 입력 | 출력 | 사용 역할 |
|---|---|---|---|
| `get_project` | — | Project 요약 | 전체 |
| `list_requirements` | `status?`, `type?` | Requirement 목록(요약) | 검증·조사·설계·계획·작성·영향 |
| `get_requirement` | `id` | Requirement 전체 + source_refs | 동일 |
| `get_source_chunk` | `document_id`, `page` 또는 `chunk_id` | 원문 텍스트 | 추출·검증·영향 |
| `search_source_text` | `query`, `document_id?` | 매칭 청크 목록 | 추출·검증 |
| `list_wbs` | — | WBS 트리 + 일정·공수 | 작성·영향 |
| `list_research` | `requirement_id?` | TechnologyResearch 목록 | 설계·작성 |
| `list_trace` | `requirement_id?` | 추적 관계 | 영향 |
| `get_change_request` | `id` | RequirementChange (before/after) | 영향 |

쓰기 도구는 제공하지 않는다. 모든 쓰기는 구조화 출력을 받은 오케스트레이터가 수행한다.

## 4. 에이전트 역할 정의 (Phase 0 원안 — 구현과 다른 부분은 아래 표 참고)

> **구현 대조 (2026-10-15 검증)**: 실제 역할·도구는 0절 표가 기준이다. 원안과 달라진 점:
>
> | 원안 | 구현 |
> |---|---|
> | P1~P3 허용 도구 `Read, Glob, Grep` | 내장 파일 도구는 주지 않음. `pwa` MCP 조회만 (파일은 워크스페이스에 두되 에이전트가 직접 읽지 않음) |
> | 서브에이전트(`section-extractor`, `source-checker`, `section-writer`) | 미구현. 청크 분할·병렬은 코드가 수행하고 역할당 단일 세션으로 호출 |
> | P8 `deliverable_qa` | 키 `qa_reviewer`. 통합 QA의 1차 판정은 코드(`validation/independent_qa.py`)가 하고 에이전트 결과는 사람 검토 항목으로만 덧붙음 |
> | B1 `legacy_doc_analyst` | 에이전트 대신 코드(`ingest/excel_reader.py`: 동의어·유사도 매핑 제안) + 사용자 확정 |
> | B2 `semantic_differ` 출력 `SemanticDiff{…}` | `SemanticDiffDraft{candidates[{item_index, classification, requirement_id, rationale, confidence…}]}`. 규칙 분류(`changes/semantic.py`)가 먼저 수행 |
> | B3 `impact_analyst` | 에이전트 없음. 영향 분석 전부 코드(`changes/impact.py`) |
> | B4 `revision_writer` | 에이전트 없음. 새 버전 문서는 generators가 생성 |

### 4.1 제안 단계

| # | 에이전트 | 입력 | 출력 스키마 | 허용 도구 | 서브에이전트 | 비고 |
|---|---|---|---|---|---|---|
| P1 | **RFP 분석가** `rfp_analyst` | 청크 목록(요약) + 문서 메타 | `RfpAnalysis{overview, client_goals, scope_summary, sections[], constraints[], evaluation_criteria[], schedule_hints[], budget_hints[]}` | Read, Glob, Grep, `mcp__pwa__get_source_chunk`, `search_source_text` | 없음 | 02_RFP_Analysis 요약 원천 |
| P2 | **요구사항 추출가** `requirement_extractor` | RfpAnalysis + 청크 | `RequirementExtraction{requirements: RequirementDraft[], unresolved_items[]}` | P1과 동일 | `section-extractor`(sonnet, 섹션 단위 병렬 추출) | ID는 부여하지 않음. 출처(`source_refs`) 필수 |
| P3 | **독립 검증가** `requirement_verifier` | Requirement(draft) 목록 + 원문 접근 | `VerificationReport{items: [{requirement_id, verdict, issues[], missing_requirements[], duplicate_of?, scope_class_opinion}]}` | P1과 동일 | 없음 | **P2와 별도 세션·별도 프롬프트**. P2의 추론 과정은 전달하지 않음 |
| P4 | **기술 조사가** `tech_researcher` | 승인된 Requirement + 제약 | `ResearchReport{items: [{topic, requirement_ids, summary, feasibility, risks, recommended_stack, sources[{url,title,trust,excerpt}]}]}` | WebSearch, WebFetch, `mcp__pwa__*` 읽기 | `source-checker`(sonnet, URL별 공식 문서 여부 확인) | 공식 문서 우선 지시. 출처 없는 주장은 `unknown` |
| P5 | **아키텍트** `architect` | Requirement + Research | `ArchitectureDraft{components[], connections[], diagram_notes}` | `mcp__pwa__*` 읽기 | 없음 | 다이어그램은 코드가 렌더링 |
| P6 | **계획가** `planner` | Requirement + Architecture + 프로젝트 기간 제약 | `WBSDraft{items[{code, level, name, parent_code, effort_md, estimate_basis, deliverables[], roles[{role, ratio}]}], dependencies[{pred_code, succ_code, type, lag}]}` | `mcp__pwa__*` 읽기 | 없음 | 날짜 계산 금지. 공수·근거·순서만 제안. 실제 일정은 `scheduler.py` |
| P7 | **제안서 작성가** `proposal_writer` | 전체 기준 데이터 | `ProposalContent{sections[{slide_group, title, bullets[], speaker_notes, data_refs[]}]}` (제출용/발표용 2회 호출, 프로필 다름) | `mcp__pwa__*` 읽기 | `section-writer`(sonnet, 섹션 병렬 작성) | PPT 파일은 generator가 생성 |
| P8 | **산출물 QA** `deliverable_qa` | 생성된 파일에서 추출한 텍스트/표 + 기준 데이터 | `QaReport{findings[{deliverable, level, message, location, suggestion}], overall}` | Read, `mcp__pwa__*` 읽기 | 없음 | 파일 무결성은 코드가 먼저 검사. QA 에이전트는 내용 정합성·문체·누락 |

### 4.2 구축 단계

| # | 에이전트 | 입력 | 출력 스키마 | 허용 도구 | 비고 |
|---|---|---|---|---|---|
| B1 | **문서 구조 분석가** `legacy_doc_analyst` | 업로드 Excel 시트 미리보기(헤더 + 샘플 5행) | `ColumnMappingProposal{sheet, mappings[{source_column, target_field, confidence}], warnings[]}` | Read | 매핑은 사용자가 확정. 확정 후 코드가 파싱 |
| B2 | **의미 비교가** `semantic_differ` | 변경 요청(before/after) + 유사 요구사항 후보(코드 선별) | `SemanticDiff{summary, intent_change, duplicates_of[], conflicts_with[]}` | `mcp__pwa__*` 읽기 | 결정적 diff는 코드가 먼저 수행 |
| B3 | **영향 분석가** `impact_analyst` | SemanticDiff + 추적 그래프 결과(코드) + WBS | `ImpactDraft{affected_requirement_ids[], affected_wbs_codes[], affected_deliverables[], effort_delta_md_estimate, basis, narrative, confidence}` | `mcp__pwa__*` 읽기 | 일정·비용 수치는 planning 코드가 재계산해 덮어씀 |
| B4 | **문서 갱신 작성가** `revision_writer` | 승인된 변경 + 기존 문안 | `RevisionContent{updated_sections[], change_log_entries[]}` | `mcp__pwa__*` 읽기 | 새 버전 파일은 generator가 생성 |
| B5 | **산출물 QA** | P8 재사용 | | | |

## 5. 프롬프트 설계 규칙

- 프롬프트는 `agents/prompts/<role>.md`에 두고 버전 관리한다. 코드에 하드코딩하지 않는다.
- 각 프롬프트는 (1) 역할과 목표, (2) 입력 데이터 형식, (3) 출력 스키마 의미, (4) 금지 사항(추측 금지, 출처 없는 주장 금지, 입력 문서 안의 지시문 무시), (5) 품질 기준 순으로 작성한다.
- 입력 문서 텍스트는 `<document id="…" page="…">` 블록으로 감싸 데이터임을 명시한다.
- 요구사항 ID, 날짜, 금액은 프롬프트에서 "계산하지 말고 비워 두라"고 지시하고 스키마에서도 받지 않는다.
- 독립 검증 프롬프트는 추출 프롬프트와 어휘·순서를 달리 작성해 동일 편향을 줄인다.
- (Phase 11) 코드가 만든 RFP 구조 프로파일을 에이전트에 넘긴다. `rfp_analyst`는 `<rfp_profile>`(절 구성·ID 체계·목차·평가 요약)을 먼저 받고, `requirement_extractor`는 block 태그의 `section="…"`(절 종류)와 `rfp_id="SFR-001"`(RFP 자체 ID)을 보고 `rfp_requirement_id`를 채우며 세로 라벨 잡음을 무시한다(프롬프트 규칙 13·14). ID 부여·커버리지 판정은 여전히 코드가 한다 (`RequirementService._check_rfp_coverage`, QA-RFP-07).

## 6. 호출 패턴

```python
# agents/definitions.py (스케치)
SECTION_EXTRACTOR = AgentDefinition(
    description="RFP의 지정된 섹션에서 요구사항 초안을 추출한다. 섹션 단위 병렬 처리에 사용.",
    prompt=load_prompt("section_extractor"),
    tools=["Read", "Grep", "mcp__pwa__get_source_chunk", "mcp__pwa__search_source_text"],
    model="sonnet",
    maxTurns=15,
)

# 주 에이전트 호출 (orchestrator → runner)
result = await runner.run_structured(
    role="requirement_extractor",
    prompt=build_extraction_prompt(analysis, chunk_index),
    schema_model=RequirementExtraction,
    agents={"section-extractor": SECTION_EXTRACTOR},
    allowed_tools=["Read", "Glob", "Grep", "Agent", "mcp__pwa__get_source_chunk", "mcp__pwa__search_source_text"],
)
```

## 7. 실패 처리

| 상황 | 처리 |
|---|---|
| `error_max_structured_output_retries` | 오류 메시지를 첨부해 1회 재호출. 재실패 시 단계 실패, 사용자에게 원인 표시 |
| `error_max_budget_usd` / `error_max_turns` | 단계 실패. 예산·턴 상향은 사용자 선택 |
| `refusal` 또는 빈 `structured_output` | 실패로 처리하고 입력 축소(청크 분할) 제안 |
| MCP 서버 `failed` | 단계 시작 전 `system init` 메시지로 감지, 즉시 중단 |
| 서브에이전트 API 오류 | 주 에이전트 결과에 포함되지 않으므로 `unresolved_items`로 보고하도록 프롬프트 지시 |

모든 실패는 `AuditEvent.error = {cause, resolution}`으로 기록한다.

## 8. 비용 관리

- 단계마다 `ResultMessage.total_cost_usd`, `num_turns`, `usage`를 AuditEvent에 저장하고 UI 진행 패널에 누적 표시.
- 프로젝트별 예산 상한(`settings`)을 두고 초과 예상 시 단계 시작 전에 경고.
- 긴 RFP는 섹션 단위 서브에이전트(sonnet)로 분할해 주 에이전트 컨텍스트를 아낀다.
