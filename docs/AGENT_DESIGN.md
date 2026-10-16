# AGENT_DESIGN — 에이전트별 책임과 권한

문서 버전 0.1 · 2026-10-15 · 관련: [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md)

---

## 0. 구현 반영 (Phase 3·6·7, 2026-10-15) — 실제 구현된 역할·도구·통제

> 2026-10-16 기준 역할 13종(Phase 23 `design_writer` 포함). 실제 모델 호출은 크레딧 부족으로 미검증이며, 모든 역할은 FakeAgentRunner(모의 응답)와 SDK 연결 점검(비용 0)으로만 검증했다. 통합 QA(Phase 7)는 에이전트 자기 평가를 쓰지 않고 코드(`validation/independent_qa.py`)가 독립 검증하며, `qa_reviewer` 결과는 사람 검토 항목으로만 덧붙는다 ([PHASE7_REPORT.md](PHASE7_REPORT.md)).

구현 코드: `agents/roles.py`(역할 정의), `agents/runner.py`(SDK 어댑터), `agents/control.py`·`hooks.py`(정책·훅), `agents/tools/project_tools.py`(인프로세스 MCP), `services/agent_step_service.py`(역할 실행·재사용·저장), `research/`(기술 조사).

| # | 역할 key | 입력 | 출력 스키마 | 내장 도구 | MCP 도구 | 턴/예산/시간 | 재사용 |
|---|---|---|---|---|---|---|---|
| 1 | `rfp_analyst` | 추출 블록 청크 + `<rfp_profile>`(절·ID·목차·평가·제출·페이지 제한) | `RfpAnalysis` (Phase 17: 현행 문제점·보안/개인정보·데이터 이관/운영·개발 환경·단계별 산출물·시험/검수/교육/유지관리·제안서 작성 지침·페이지 제한·문서 규격·필수 제출 자료 추가) | 없음 | `pwa.search_source_text`, `pwa.get_source_block` | 10 / $2 / 600s | — |
| 2 | `requirement_extractor` | 청크 | `RequirementExtraction` | 없음 | 없음 | 8 / $2 / 600s | rfp_analyst |
| 3 | `requirement_verifier` | 청크 + 요구사항 | `VerificationReport` | 없음 | 없음 | 8 / $2 / 600s | — |
| 4 | `tech_researcher` | 요구사항·RFP 분석·주제 | `ResearchReport` | **WebSearch, WebFetch** | `pwa.get_requirement`, `pwa.list_research` | 30 / $6 / 1200s | rfp_analyst |
| 5 | `architect` | 요구사항·조사 | `ArchitectureDraft` | 없음 | pwa 읽기 9종 | 12 / $3 / 600s | tech_researcher, rfp_analyst |
| 6 | `planner` | 요구사항·아키텍처·기간 | `WBSDraft` (날짜 없음; Phase 15: items[].category/organization/assignee/quantity, `team[]`(조직·역할·등급·인원·이름), `milestones[]`(name·timing)) | 없음 | pwa 읽기 9종 | 12 / $3 / 600s | architect, rfp_analyst |
| 7 | `proposal_writer` | 기준 데이터 + `<proposal_template>`(템플릿 관행) + `<rfp_toc>`(RFP 지정 목차, Phase 12) | `ProposalContent` (섹션에 chapter/section/number/lead_message/table/requirement_ids/footnotes; Phase 19: key_message·purpose·audience·evidence·links·layout_type·tech_detail·terms, 문서 glossary) | 없음 | pwa 읽기 9종 | 15 / $4 / 600s | 1·4·5·6 |
| 8 | `document_generator` | 기준 데이터 | `DocumentPlan` (파일은 코드 생성) | 없음 | pwa 읽기 9종 | 10 / $2 / 600s | 7·6·5 |
| 9 | `qa_reviewer` | 산출물 텍스트·기준·변경 요청 | `QaReport` | 없음 | pwa 읽기 9종 + `verify_deliverable_file` | 12 / $3 / 600s | 8·7 |
| 10 | `semantic_differ` (Phase 6) | 변경 요청 항목·기존 요구사항(설명+구현 방안)·규칙 분류 | `SemanticDiffDraft` (Phase 14: `change_aspects`·`difficulty`·`difficulty_basis`·`effort_hint`) | 없음 | `pwa.list_requirements`, `pwa.get_requirement` | 8 / $1.5 / 600s | — (규칙 결과를 입력으로 받음) |
| 12 | `strategy_planner` (Phase 18) | `<rfp_profile>`(목차·평가·제출·페이지 제한) + `<prior role="rfp_analyst">` + `<requirements>`(구현 방안·난이도) + `<research>` + `<reviewer_comments>`(반려 시) | `StrategyBrief{rfp_summary, requirement_directions[], toc[{numeral,title,sections,rfp_mandatory,note}], toc_change_requests[], strategies[3~5: title,description,differentiator,evidence[]], key_technologies[], risks[], submission_vs_presentation, open_questions[]}` | 없음 | pwa 읽기 9종 | 12 / $3 / 600s | rfp_analyst |
| 11 | `approach_writer` (Phase 14) | 요구사항 묶음(≤20) + `<research>` 조사 기록 + `<architecture>` 구성 요소 + `<comparisons>` 기술 선택 | `ApproachReport{items[{requirement_id, approach(글머리 2~5줄), difficulty(상/중/하), difficulty_basis, verification_method, acceptance_criteria, research_refs, sources[], feasibility, notes}], research_needed[]}` | **WebSearch, WebFetch** | `pwa.get_requirement`, `pwa.list_research` | 20 / $4 / 900s | rfp_analyst |
| 13 | `design_writer` (Phase 23) | `<groups>`(코드 제안 묶음: 요구사항·RFP ID·정의서 구현방안·난이도) + `<research>`(조사 사실·출처) + `<architecture>` + `<comparisons>` | `DesignReport{designs[{title, requirement_ids, key_message, overview, structure[{name, layer, technology, role}], flows[{title, actor, action, decision}], tech_choices[{area, choice, reason, alternatives, source, verified}], data_interfaces, premises, risks, sources}], research_needed}` | **WebSearch, WebFetch** | `pwa.get_requirement`, `pwa.list_research` | 30 / $6 / 1200s | approach_writer, architect |

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
- (Phase 19) `proposal_writer`는 소절마다 **슬라이드 명세**를 쓴다: `key_message`(결론형 제목 → 코드가 리드 상자에), `purpose`·`audience`·`links_prev/next`(발표자 노트), `evidence[]`(근거 → 하단 ※ 주석; 단위 붙은 수치는 데이터에 있는 값만), `layout_type`(계획값), 기술 소절의 `tech_detail`(구성·연계·데이터·운영·보안 + 상용/공개/자체 `alternatives` → 기술 상세 카드·대안 비교 표), `terms`와 문서 `glossary`(→ 부록 '용어 설명'). 도식은 14종(`shapes.AGENT_VISUAL_KINDS`: raci·data_model·procedure·security_layers·layers·chart 추가; Phase 20: `chart`는 `charts.chart_from_spec`이 네이티브 차트로, `screen`의 items `kind`(input/button/menu/tab/message/table/list/chart)는 개별 컴포넌트 도형으로 그리고 목업 전체를 그룹으로 묶는다). 소절 `picture`는 `<data>.pictures`(등록된 참고 그림 파일명·태그·설명)에 있는 그림만 참조한다(규칙 17). (Phase 22) `requirement_groups[]`(RequirementGroupSpec: title·requirement_ids(내부 ID 또는 RFP 고유번호)·key_message·summary·notes)로 **내용상 함께 설명할 요구사항을 묶으면** 코드가 묶음마다 '요구사항별 구현 방안' 소절(기능 블록 도식 + 정의서 구현방안 전문 표)을 만든다(규칙 18, `generators/pptx/req_groups.py`). 소절 본문은 구현 방안을 반복하지 않고 설계 판단·구조·근거를 쓴다. QA-CON-12가 정의서 구현방안의 제안서 반영을 대조한다. 생성 후 `generators/pptx/slide_spec.py`가 슬라이드별 명세 JSON(계획 레이아웃 ↔ 실제 렌더링, 근거, 요구사항 ID)을 남기고, QA-CON-10(추상 표현·근거 없는 수치)·QA-CON-11(약어 미설명)이 문안을 검사한다(규칙 12~16).
- (Phase 18) `strategy_planner`가 쓴 브리프는 **Gate P(목차·전략 승인)** 대상이다(`services/strategy_service.py`). 코드는 RFP 지정 목차 장 보존 여부·전략 수·확인 필요 사항을 평가 사유로 적고 항상 사람 승인(NEEDS_HUMAN_REVIEW)을 요구한다. 승인 전에는 `run_proposal_writing`(전체 문안)과 `run_finalize`(최종 확정)가 막히고, `run_generation`은 '시안'으로만 만들어진다. 반려 사유는 `<reviewer_comments>`로 다시 넘긴다. RFP 지정 목차가 없으면 브리프 목차가 덱 뼈대가 된다(`outline.brief_toc_tree`).
- (Phase 15) `planner`는 WBS 항목에 구분·개발 조직·개발자·수량을 붙이고, 수행 조직(`team`: 조직·역할·등급·인원·이름)과 보고용 마일스톤(`milestones`: 착수·보고·오픈·종료, timing = start/mid/end/after:<code>/±Nw)을 제안한다. 코드(`planning/service.py`)가 team을 `StaffRole`(조직·등급·인원·구성원)로, 마일스톤을 WBS 코드 `0` 아래 공수 0 항목으로 만들고 날짜를 계산한다. 투입계획의 구성원별 월별 공수는 코드가 역할 배분을 인원 수로 나눠 산출한다.
- (Phase 23) `design_writer`는 요구사항 **묶음**마다 구현 설계(구현 구조·처리 절차·적용 기술과 선정 이유·대안·근거·데이터/인터페이스·전제·위험)를 쓴다. 코드는 설계 묶음을 묶음 소절로 삼아 계층 띠 도식·절차 도식(+상세 표)·적용 기술 표·정의서 구현방안 표를 그리고, QA-CON-13 이 깊이(구조 2·절차 3·기술 1·데이터 1)와 덱 반영·출처 확인 여부를 검사한다. `proposal_writer` 는 `<data>.designs` 가 있으면 그 묶음을 그대로 따른다.
- (Phase 14) `approach_writer`는 요구사항 정의서의 **구현방안·구현 난이도·검증 방법·검사 기준**을 요구사항마다 짧게 쓴다(`requirements/approach.py`, 단계 `impl_approach`). 조사·구성 요소·기술 선택에 근거가 있는 내용만 구체화하고, 새로 열람한 출처는 조사 기록(`TechnologyResearch`)으로 저장해 QA-TECH-07의 근거 연결에 쓰인다. 빠뜨린 항목은 코드가 프로젝트 데이터만으로 규칙 초안을 만들어 `[자동 초안]`(`approach_source=rule`)으로 표시하고, 사람이 쓴 방안(`user`)은 덮어쓰지 않는다. `semantic_differ`는 변경 항목마다 문맥 관점(범위·대상 사용자·입출력·업무 규칙·수치 조건·화면·연계·성능/보안·데이터)과 난이도를 내고, 코드는 이를 공수 추정 가중치(`changes/impact.py`)에 반영한다.
- (Phase 13) `proposal_writer`는 `<feasibility>`(필수 요구사항별 구현 방안·근거 조사·구현 가능성·출처 수)를 받아 **구현 가능(feasible/with_risk) 조사 근거가 있는 것만** 구체적 구현 방안으로 쓰고, 조사가 없으면 "조사 후 확정"으로 쓰며 소절마다 `feasibility_basis`를 적는다(규칙 9). 작성 단계는 기술 조사 기록이 없으면 실행되지 않는다(`StepRunner.run_proposal_writing`). 소절 도식은 `visual`(VisualSpec: cards/flow/process/two_column/dataflow/screen/kpis/compare)로 지정하고 코드가 편집 가능한 도형으로 그린다(규칙 10, `generators/pptx/shapes.py`). 조사 결과는 `ResearchService._fill_implementation_approach`가 관련 요구사항의 구현 방안을 채운다.
- (Phase 12) 제안서 작성(`proposal_writer`)은 `GenerationService.proposal_brief()`가 만든 `<proposal_template>`(템플릿 PPTX에서 읽은 관행: 용지·머리글 2단·리드·번호 체계·RFP ID 카드·표 유형·글꼴)과 `<rfp_toc>`(RFP 지정 목차 장/절·작성방법)를 받아 소절 단위 문안을 쓴다. 장·절 배치와 번호 매기기, 슬라이드 분할, 표 그리기는 코드(`outline.plan_chapters`, `TemplateDeckBuilder`)가 한다. `qa_reviewer`에도 같은 요약이 들어가고 코드 검사 QA-FILE-11이 용지·머리글·장 순서·글꼴을 대조한다.
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
