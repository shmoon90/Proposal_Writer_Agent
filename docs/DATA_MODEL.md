# DATA_MODEL — 공통 데이터 모델 및 데이터 흐름

문서 버전 0.1 · 2026-10-15 · 관련: [ARCHITECTURE.md](ARCHITECTURE.md), [WORKFLOW_DESIGN.md](WORKFLOW_DESIGN.md)

---

## 1. 모델링 원칙

- Pydantic v2 `BaseModel`로 정의하고, 동일 모델을 (a) SQLite 저장, (b) 에이전트 구조화 출력 스키마(`model_json_schema()`), (c) 문서 생성 입력에 공용으로 사용한다. 에이전트 출력용은 `*Draft` 서브셋 모델로 분리해 ID·상태·감사 필드를 LLM이 채우지 못하게 한다.
- 모든 엔티티의 PK는 애플리케이션이 발급하는 문자열 ID. 요구사항처럼 사람이 읽는 ID는 `id_policy.py`가 결정적으로 발급하고 재발급하지 않는다.
- 삭제는 물리 삭제 없이 `status` 변경 + `AuditEvent`.
- 시각은 UTC ISO-8601 문자열로 저장, UI에서 로컬 변환.
- 모든 엔티티에 `created_at`, `updated_at`, `created_by`(사용자 또는 에이전트 이름)를 둔다.

## 2. 엔티티 관계도

```mermaid
erDiagram
    Project ||--o{ SourceDocument : has
    Project ||--o{ Requirement : has
    Project ||--o{ WBSItem : has
    Project ||--o{ StaffRole : defines
    Project ||--o{ TechnologyResearch : has
    Project ||--o{ ArchitectureComponent : has
    Project ||--o{ Deliverable : produces
    Project ||--o{ Revision : versions
    Project ||--o{ AuditEvent : logs
    Project ||--o{ Screen : has
    Project ||--o{ Approval : has

    SourceDocument ||--o{ Requirement : "source_refs"
    Requirement ||--o{ RequirementChange : history
    Requirement ||--o{ RequirementTrace : traced_by
    RequirementTrace }o--o| Screen : to
    RequirementTrace }o--o| WBSItem : to
    RequirementTrace }o--o| UnitTest : to
    RequirementTrace }o--o| IntegrationTest : to
    RequirementTrace }o--o| ArchitectureComponent : to
    Requirement }o--o{ TechnologyResearch : evaluated_by
    Requirement ||--o{ ValidationResult : validated_by

    WBSItem ||--o{ Dependency : predecessor
    WBSItem ||--o{ Dependency : successor
    WBSItem ||--o{ StaffingAllocation : staffed_by
    StaffRole ||--o{ StaffingAllocation : role

    Deliverable ||--o{ ValidationResult : checked_by
    Deliverable }o--|| Revision : belongs_to
    Revision ||--o{ RequirementChange : includes
    Revision ||--o| Approval : approved_by
    RequirementChange }o--o| Approval : approved_by
```

## 3. 공통 enum

| enum | 값 |
|---|---|
| `ProjectMode` | `proposal`, `build` |
| `ProjectStatus` | `created`, `analyzing`, `requirements_review`, `researching`, `planning`, `generating`, `qa`, `approved`, `archived` |
| `DocumentKind` | `rfp`, `rfp_attachment`, `requirement_spec`, `trace_matrix`, `wbs`, `staffing_plan`, `other` |
| `RequirementType` | `functional`, `non_functional` |
| `RequirementCategory` | 기능: `ui`, `business`, `data`, `interface`, `report`, `admin` / 비기능: `performance`, `security`, `availability`, `compatibility`, `operability`, `constraint`, `other` |
| `ScopeClass` | `mandatory`(RFP 필수), `optional_proposal`(선택 제안), `out_of_scope`(과잉 범위) |
| `AcceptanceStatus` | `proposed`, `accepted`, `partially_accepted`, `rejected`, `deferred` |
| `RequirementStatus` | `draft`, `verified`, `baseline`, `changed`, `deleted` |
| `VerificationStatus` | `unverified`, `verified`, `needs_revision`, `rejected` |
| `ChangeType` | `add`, `modify`, `delete`, `restore` |
| `ChangeStatus` | `requested`, `analyzed`, `approved`, `rejected`, `applied`, `withdrawn` |
| `TraceTargetType` | `screen`, `wbs_item`, `unit_test`, `integration_test`, `component`, `deliverable` |
| `WBSLevel` | `phase`, `activity`, `task` |
| `DependencyType` | `FS`, `SS`, `FF`, `SF` |
| `DeliverableKind` | `requirement_spec_xlsx`, `trace_matrix_xlsx`, `wbs_gantt_xlsx`, `staffing_plan_xlsx`, `submission_pptx`, `presentation_pptx`, `system_diagram_png`, `sw_diagram_png`, `service_diagram_png`, `qa_report_md`, `project_summary_md` |
| `ValidationLevel` | `error`, `warning`, `info` |
| `ApprovalDecision` | `approved`, `rejected`, `approved_with_comments` |
| `ApprovalTarget` | `requirement_set`, `research`, `plan`, `deliverable`, `change_request`, `revision` |
| `FeasibilityVerdict` | `feasible`, `feasible_with_risk`, `infeasible`, `unknown` |
| `SourceTrust` | `official_doc`(공식 문서), `vendor_guide`, `standard`, `community`, `unknown` |

## 4. 엔티티 정의

필드 표기: `이름: 타입 (제약)`. 공통 필드(`created_at`, `updated_at`, `created_by`)는 생략.

### 4.1 Project

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str (PK, `prj_<uuid7>`) | |
| `name` | str | 프로젝트명 |
| `mode` | ProjectMode | 서비스 시작 시 선택 |
| `status` | ProjectStatus | |
| `client_name` | str \| None | 발주처 |
| `output_dir` | str | `Output/Project_YYYYMMDD_<slug>[_<short>]` (상대 경로) |
| `workspace_dir` | str | `workspace/<id>` |
| `baseline_revision_id` | str \| None | 현재 기준선 |
| `settings` | dict | 영업일 규칙, 기본 M/M 단가 등 |

### 4.2 SourceDocument

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str (PK, `doc_…`) | |
| `project_id` | FK | |
| `kind` | DocumentKind | |
| `file_name`, `stored_path` | str | 원본은 `01_RFP_Original`에 복사 |
| `sha256` | str | 무결성·중복 검사 |
| `page_count` | int \| None | |
| `extraction_method` | `text` \| `ocr` \| `mixed` | |
| `extracted_text_path` | str \| None | workspace 내 청크 JSON |
| `column_mapping` | dict \| None | 구축 단계 Excel 업로드 시 컬럼 매핑 |

### 4.3 Requirement

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str (PK) | `REQ-F-001` / `REQ-N-001`. `id_policy.py` 발급, 재발급 금지 |
| `project_id` | FK | |
| `name` | str | 요구사항명 |
| `description` | str | 상세 내용 |
| `type` | RequirementType | 기능/비기능 |
| `category` | RequirementCategory | |
| `scope_class` | ScopeClass | 필수/선택 제안/과잉 범위 |
| `implementation_approach` | str \| None | 구현 방안 |
| `acceptance_status` | AcceptanceStatus | 수용 상태 |
| `status` | RequirementStatus | 수명주기 (삭제=`deleted`) |
| `verification_status` | VerificationStatus | 독립 검증 결과 |
| `priority` | `high`/`medium`/`low` | |
| `source_refs` | list[SourceRef] | 원본 출처 |
| `rfp_quote` | str \| None | RFP 원문 인용 |
| `rationale` | str \| None | 추출·분류 근거 |
| `tags` | list[str] | |
| `version` | int | 변경마다 +1 |

`SourceRef`: `{document_id, page: int|None, section: str|None, char_start: int|None, char_end: int|None, quote: str}`.

**에이전트 출력용 `RequirementDraft`**: `name, description, type, category, scope_class, priority, rfp_quote, source_refs, rationale, implementation_approach`만 포함. ID·상태는 코드가 부여.

### 4.4 RequirementChange

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str (PK, `chg_…`) | |
| `project_id`, `requirement_id` | FK | 신규 추가 시 `requirement_id`는 발급 후 채움 |
| `change_type` | ChangeType | |
| `status` | ChangeStatus | |
| `before` | dict \| None | 변경 전 스냅샷 (Requirement dump) |
| `after` | dict \| None | 변경 후 |
| `diff_summary` | str | 결정적 필드 diff |
| `semantic_summary` | str \| None | 에이전트의 의미 비교 요약 |
| `impact` | ImpactAnalysis \| None | 4.14 참조 |
| `requested_by`, `reason` | str | |
| `approval_id` | FK \| None | |
| `revision_id` | FK \| None | 적용된 리비전 |

### 4.5 RequirementTrace

| 필드 | 타입 |
|---|---|
| `id` (PK) | |
| `project_id`, `requirement_id` | FK |
| `target_type` | TraceTargetType |
| `target_id` | str |
| `note` | str \| None |

추적표는 이 테이블의 피벗이다. 영향 분석 시 `requirement_id → target` 그래프 탐색의 기반.

### 4.6 Screen / UnitTest / IntegrationTest

| 엔티티 | 주요 필드 |
|---|---|
| `Screen` | `id`(`SCR-001`), `project_id`, `name`, `description`, `screen_type`(`list`/`detail`/`form`/`dashboard`/`popup`), `status` |
| `UnitTest` | `id`(`UT-001`), `project_id`, `name`, `target_component`, `description`, `status` |
| `IntegrationTest` | `id`(`IT-001`), `project_id`, `name`, `scenario`, `description`, `status` |

제안 단계에서는 추적표 작성 목적의 식별자 수준으로만 생성한다.

### 4.7 WBSItem / Dependency

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str (PK, `WBS-1.2.3` 형식 코드 별도 `code` 필드) | 내부 ID는 `wbs_…`, 표시 코드는 `code` |
| `project_id`, `parent_id` | FK | |
| `level` | WBSLevel | |
| `name`, `description` | str | |
| `planned_start`, `planned_end` | date \| None | `scheduler.py` 계산 결과 |
| `duration_days` | int \| None | 영업일 |
| `effort_md` | Decimal | 공수(M/D) |
| `estimate_basis` | str | **산정 근거(필수)** |
| `deliverable_names` | list[str] | |
| `order` | int | 표시 순서 |

`Dependency`: `id, project_id, predecessor_id, successor_id, type(DependencyType), lag_days`. 순환은 `scheduler.py`가 거부.

### 4.8 StaffRole / StaffingAllocation

| 엔티티 | 주요 필드 |
|---|---|
| `StaffRole` | `id`, `project_id`, `role_name`(PM, PL, 개발자…), `grade`(특급/고급/중급/초급), `unit_cost_per_mm`(Decimal \| None), `headcount_planned` |
| `StaffingAllocation` | `id`, `project_id`, `wbs_item_id`, `staff_role_id`, `person_name`(None 허용), `start`, `end`, `allocation_ratio`(0~1), `effort_md`(계산값) |

월별 M/M 집계와 비용은 `planning/staffing.py`가 계산한다.

### 4.9 TechnologyResearch

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str (PK, `TR-001`) | |
| `project_id` | FK | |
| `topic` | str | 조사 주제 |
| `related_requirement_ids` | list[str] | |
| `summary` | str | |
| `feasibility` | FeasibilityVerdict | |
| `risks` | list[str] | |
| `recommended_stack` | list[str] | |
| `sources` | list[ResearchSource] | `{url, title, trust: SourceTrust, accessed_at, excerpt}` |
| `verified_by_human` | bool | |

`ResearchSource.trust`는 도메인 규칙(`research/sources.py`)이 URL 도메인으로 1차 분류하고, 에이전트 판단을 참고값으로만 저장한다.

### 4.10 ArchitectureComponent

`id`(`ARC-001`), `project_id`, `layer`(`client`/`web`/`app`/`data`/`integration`/`infra`/`security`), `name`, `technology`, `description`, `connections: list[{to_component_id, protocol, note}]`, `diagram_kinds: list[system|sw|service]`.

### 4.11 Deliverable

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str (PK, `dlv_…`) | |
| `project_id`, `revision_id` | FK | |
| `kind` | DeliverableKind | |
| `file_path` | str | Output 내 상대 경로, **버전 포함 파일명** |
| `version` | str | `v1.0` |
| `sha256` | str | |
| `generated_from_snapshot` | str | 생성 당시 데이터 스냅샷 ID(리비전) |
| `integrity_status` | `pending`/`passed`/`failed` | |
| `qa_status` | `pending`/`passed`/`failed`/`waived` | |

### 4.12 ValidationResult

`id`, `project_id`, `target_type`(`requirement`/`deliverable`/`plan`/`change`), `target_id`, `rule_id`, `level`(ValidationLevel), `message`, `detail`(dict), `validator`(`code:<rule>` 또는 `agent:<name>`), `resolved`(bool).

### 4.13 Approval / Revision / AuditEvent

| 엔티티 | 주요 필드 |
|---|---|
| `Approval` | `id`, `project_id`, `target_type`(ApprovalTarget), `target_id`, `decision`, `approver`, `comments`, `decided_at` |
| `Revision` | `id`, `project_id`, `number`(`v1.0`), `label`, `reason`, `change_ids: list`, `snapshot_path`(JSON 전체 스냅샷, `12_Revision_History`), `approval_id`, `parent_revision_id` |
| `AuditEvent` | `id`, `project_id`, `at`, `actor`(user/agent/system), `action`, `entity_type`, `entity_id`, `payload`(dict; 비용·모델·턴 수 포함), `error`(dict \| None: `cause`, `resolution`) |

### 4.14 ImpactAnalysis (값 객체)

```
affected_requirement_ids: list[str]        # 결정적: 추적·의존 그래프 + 에이전트 의미 제안(라벨 구분)
affected_deliverables: list[DeliverableKind]
affected_wbs_item_ids: list[str]
schedule_delta_days: int                   # scheduler 재계산 차이
effort_delta_md: Decimal                   # effort 재계산 차이
staffing_delta: list[{role, delta_mm}]
cost_delta: Decimal | None
narrative: str                             # 에이전트 서술
confidence: float
```

## 5. 상태 전이

### Requirement

```mermaid
stateDiagram-v2
    [*] --> draft: 추출/추가
    draft --> verified: 독립 검증 통과
    draft --> draft: 검증 실패 → 재작성
    verified --> baseline: 사람 승인(Approval)
    baseline --> changed: 변경 요청 승인·적용
    changed --> baseline: 새 Revision 기준선 확정
    baseline --> deleted: 삭제 요청 승인
    deleted --> baseline: 복원 승인
```

### RequirementChange

`requested → analyzed → (approved → applied) | rejected | withdrawn`. `applied`는 Revision 생성과 동시에만 가능.

## 6. SQLite 스키마 방침

- 테이블 = 엔티티 1:1. 복합 필드(`source_refs`, `sources`, `impact`, `payload`)는 JSON 텍스트 컬럼.
- 모든 테이블에 `project_id` 인덱스. `requirements(project_id, id)` 고유.
- 마이그레이션: `storage/db.py`에 버전 번호와 순차 SQL 스크립트(`storage/migrations/0001_init.sql` …). 외부 ORM 없이 `sqlite3` 표준 모듈 사용(의존성 최소화). 필요 시 Phase 5에서 SQLAlchemy 검토.
- 리비전 스냅샷은 DB 외에 `12_Revision_History/revision_v1.0.json`으로도 보존(파일 기반 복구 가능).

## 7. 데이터 흐름 요약

| 단계 | 입력 | 처리 주체 | 출력(저장) |
|---|---|---|---|
| 문서 입력 | 파일 | ingest(코드) | SourceDocument, 청크 JSON |
| 요구사항 추출 | 청크 | 에이전트 → `RequirementDraft[]` | Requirement(draft) via id_policy |
| 독립 검증 | Requirement + 청크 | 검증 에이전트 → `VerificationReport` | ValidationResult, verification_status |
| 승인 | — | 사용자 | Approval, status=baseline, Revision v1.0 |
| 기술 조사 | Requirement(baseline) | 조사 에이전트(WebSearch) → `ResearchReport` | TechnologyResearch |
| 구성 설계 | Requirement, Research | 설계 에이전트 → `ArchitectureDraft` | ArchitectureComponent |
| WBS/공수 | Requirement, Architecture | 계획 에이전트 → `WBSDraft`(이름·근거·공수 제안) → planning(코드) 계산 | WBSItem, Dependency, StaffingAllocation |
| 문서 생성 | 전체 기준 데이터 | generators(코드) + 작성 에이전트(문안) | Deliverable + 파일 |
| 검증·QA | Deliverable | validation(코드) + QA 에이전트 | ValidationResult |
| 변경(구축) | ChangeRequest | diff(코드) + 영향 에이전트 + planning 재계산 | RequirementChange, ImpactAnalysis, Revision vN |
