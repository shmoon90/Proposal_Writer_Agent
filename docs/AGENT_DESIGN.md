# AGENT_DESIGN — 에이전트별 책임과 권한

문서 버전 0.1 · 2026-10-15 · 관련: [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md)

---

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

## 4. 에이전트 역할 정의

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
