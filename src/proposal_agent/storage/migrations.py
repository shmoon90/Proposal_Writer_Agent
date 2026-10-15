"""SQLite 스키마 마이그레이션 정의.

방침 (DATA_MODEL.md 6절):
- 테이블 = 엔티티 1:1. 조회·인덱스가 필요한 필드만 컬럼으로 두고, 엔티티 전체는 ``data`` JSON 컬럼에
  저장한다. 새 필드 추가는 Pydantic 모델만 바꾸면 되고(기본값 필요), 조회 컬럼이 필요할 때만 마이그레이션을
  추가한다.
- 마이그레이션은 버전 순서대로 한 번만 적용되며 ``schema_migrations``에 기록된다.
- 기존 마이그레이션은 수정하지 않는다. 변경은 항상 새 버전으로 추가한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


_COMMON = "data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL"
_FK_PROJECT = "project_id TEXT NOT NULL REFERENCES projects(id)"

MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        1,
        "init",
        f"""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            output_dir TEXT NOT NULL UNIQUE,
            {_COMMON}
        );

        CREATE TABLE source_documents (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            kind TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_source_documents_project ON source_documents(project_id);
        CREATE UNIQUE INDEX ux_source_documents_project_sha ON source_documents(project_id, sha256);

        CREATE TABLE requirements (
            id TEXT NOT NULL,
            {_FK_PROJECT},
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            verification_status TEXT NOT NULL,
            scope_class TEXT NOT NULL,
            {_COMMON},
            PRIMARY KEY (project_id, id)
        );

        CREATE TABLE requirement_changes (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            requirement_id TEXT,
            change_type TEXT NOT NULL,
            status TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_requirement_changes_project ON requirement_changes(project_id);

        CREATE TABLE requirement_traces (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            requirement_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_requirement_traces_req ON requirement_traces(project_id, requirement_id);

        CREATE TABLE step_runs (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            step_key TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            status TEXT NOT NULL,
            {_COMMON}
        );
        CREATE UNIQUE INDEX ux_step_runs_attempt ON step_runs(project_id, step_key, attempt);

        CREATE TABLE gate_results (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            step_key TEXT NOT NULL,
            step_run_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_gate_results_project ON gate_results(project_id);

        CREATE TABLE deliverables (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            kind TEXT NOT NULL,
            version TEXT NOT NULL,
            file_path TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_deliverables_project ON deliverables(project_id);

        CREATE TABLE validation_results (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            level TEXT NOT NULL,
            resolved INTEGER NOT NULL DEFAULT 0,
            {_COMMON}
        );
        CREATE INDEX ix_validation_results_project ON validation_results(project_id, resolved);

        CREATE TABLE approvals (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_approvals_project ON approvals(project_id);

        CREATE TABLE revisions (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            number TEXT NOT NULL,
            {_COMMON}
        );
        CREATE UNIQUE INDEX ux_revisions_number ON revisions(project_id, number);

        CREATE TABLE audit_events (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            at TEXT NOT NULL,
            action TEXT NOT NULL,
            is_error INTEGER NOT NULL DEFAULT 0,
            {_COMMON}
        );
        CREATE INDEX ix_audit_events_project ON audit_events(project_id, at);

        CREATE TABLE sequences (
            project_id TEXT NOT NULL REFERENCES projects(id),
            key TEXT NOT NULL,
            next_value INTEGER NOT NULL,
            PRIMARY KEY (project_id, key)
        );
        """,
    ),
    Migration(
        2,
        "extraction_and_gates",
        f"""
        CREATE TABLE extraction_runs (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            source_document_id TEXT NOT NULL,
            status TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_extraction_runs_doc ON extraction_runs(project_id, source_document_id);

        CREATE TABLE extracted_blocks (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            source_document_id TEXT NOT NULL,
            extraction_run_id TEXT NOT NULL,
            block_type TEXT NOT NULL,
            block_order INTEGER NOT NULL,
            needs_review INTEGER NOT NULL DEFAULT 0,
            {_COMMON}
        );
        CREATE INDEX ix_extracted_blocks_run ON extracted_blocks(project_id, extraction_run_id, block_order);

        CREATE TABLE gate_evaluations (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            gate_key TEXT NOT NULL,
            status TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_gate_evaluations_key ON gate_evaluations(project_id, gate_key, created_at);
        """,
    ),
    Migration(
        3,
        "research_and_agent_outputs",
        f"""
        CREATE TABLE technology_research (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            topic TEXT NOT NULL,
            feasibility TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_technology_research_project ON technology_research(project_id);

        CREATE TABLE feasibility_studies (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            {_COMMON}
        );

        CREATE TABLE agent_outputs (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            role TEXT NOT NULL,
            version TEXT NOT NULL,
            file_path TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_agent_outputs_role ON agent_outputs(project_id, role, created_at);
        """,
    ),
    Migration(
        4,
        "planning_and_design",
        f"""
        CREATE TABLE wbs_items (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            code TEXT NOT NULL,
            parent_id TEXT,
            level TEXT NOT NULL,
            {_COMMON}
        );
        CREATE UNIQUE INDEX ux_wbs_items_code ON wbs_items(project_id, code);

        CREATE TABLE dependencies (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            predecessor_id TEXT NOT NULL,
            successor_id TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_dependencies_project ON dependencies(project_id);

        CREATE TABLE staff_roles (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            role_name TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_staff_roles_project ON staff_roles(project_id);

        CREATE TABLE staffing_allocations (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            wbs_item_id TEXT NOT NULL,
            staff_role_id TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_staffing_allocations_project ON staffing_allocations(project_id);

        CREATE TABLE architecture_components (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            layer TEXT NOT NULL,
            name TEXT NOT NULL,
            {_COMMON}
        );
        CREATE INDEX ix_architecture_components_project ON architecture_components(project_id);

        CREATE TABLE screens (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            name TEXT NOT NULL,
            {_COMMON}
        );
        CREATE TABLE unit_tests (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            name TEXT NOT NULL,
            {_COMMON}
        );
        CREATE TABLE integration_tests (
            id TEXT PRIMARY KEY,
            {_FK_PROJECT},
            name TEXT NOT NULL,
            {_COMMON}
        );
        """,
    ),
)
