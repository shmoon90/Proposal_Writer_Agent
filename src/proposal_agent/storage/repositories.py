"""엔티티별 Repository.

패턴: 조회 컬럼 + ``data`` JSON 문서. 모든 저장은 Pydantic 모델을 통해서만 이루어지며,
리포지토리는 비즈니스 규칙을 갖지 않는다 (ARCHITECTURE.md 2절). 예외: 요구사항 삭제는
물리 삭제가 금지되어 있으므로 ``delete`` 메서드를 제공하지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import Any, ClassVar, cast

from proposal_agent.config.errors import NotFoundError, StorageError
from proposal_agent.models import (
    AgentOutput,
    Approval,
    AuditEvent,
    Deliverable,
    Entity,
    ExtractedBlock,
    ExtractionRun,
    FeasibilityStudy,
    GateEvaluation,
    GateResult,
    Project,
    ProjectScoped,
    Requirement,
    RequirementChange,
    RequirementTrace,
    Revision,
    SourceDocument,
    StepRun,
    TechnologyResearch,
    ValidationResult,
)
from proposal_agent.storage.db import Database


def _dumps(entity: Entity) -> str:
    return json.dumps(entity.model_dump(mode="json"), ensure_ascii=False)


def _to_column(value: Any) -> Any:
    if value is None or isinstance(value, int | float):
        return int(value) if isinstance(value, bool) else value
    return str(value)  # enum, datetime, str


class BaseRepository[T: Entity]:
    """공통 CRUD. 서브클래스는 ``table``, ``model``, ``columns``를 지정한다.

    ``columns``: 테이블 컬럼명 → 엔티티 속성명 (조회 컬럼). ``id``, ``data``, 시각 컬럼은 자동.
    """

    table: ClassVar[str]
    model: ClassVar[type[Entity]]
    columns: ClassVar[dict[str, str]] = {}
    scoped: ClassVar[bool] = True  # project_id 컬럼 보유 여부
    composite_key: ClassVar[bool] = False  # (project_id, id) 복합 PK 여부

    def __init__(self, db: Database) -> None:
        self.db = db

    # --- 직렬화 ----------------------------------------------------------------------
    def _row_values(self, entity: T) -> dict[str, Any]:
        values: dict[str, Any] = {"id": entity.id}
        if self.scoped:
            values["project_id"] = cast("ProjectScoped", entity).project_id
        for col, attr in self.columns.items():
            values[col] = _to_column(getattr(entity, attr))
        values["data"] = _dumps(entity)
        values["created_at"] = entity.created_at.isoformat()
        values["updated_at"] = entity.updated_at.isoformat()
        return values

    def _from_row(self, row: sqlite3.Row) -> T:
        return self.model.model_validate(json.loads(row["data"]))  # type: ignore[return-value]

    # --- 쓰기 ------------------------------------------------------------------------
    def insert(self, entity: T) -> T:
        values = self._row_values(entity)
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    f"INSERT INTO {self.table} ({cols}) VALUES ({marks})", tuple(values.values())
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError(
                f"{self.table} 저장 실패 (제약 위반): {entity.id}",
                cause=str(exc),
                resolution="중복 ID·중복 해시 여부를 확인하십시오.",
            ) from exc
        return entity

    def update(self, entity: T) -> T:
        entity.touch()
        values = self._row_values(entity)
        key_cols = ["project_id", "id"] if self.composite_key else ["id"]
        set_cols = [c for c in values if c not in key_cols]
        assignments = ", ".join(f"{c} = ?" for c in set_cols)
        where = " AND ".join(f"{c} = ?" for c in key_cols)
        params = [values[c] for c in set_cols] + [values[c] for c in key_cols]
        with self.db.transaction() as conn:
            cur = conn.execute(f"UPDATE {self.table} SET {assignments} WHERE {where}", params)
        if cur.rowcount == 0:
            raise NotFoundError(f"{self.table}에 {entity.id} 없음")
        return entity

    # --- 읽기 ------------------------------------------------------------------------
    def get(self, id: str, project_id: str | None = None) -> T:
        if self.composite_key and project_id is None:
            raise StorageError(f"{self.table} 조회에는 project_id가 필요합니다.")
        sql = f"SELECT data FROM {self.table} WHERE id = ?"
        params: list[Any] = [id]
        if self.composite_key:
            sql += " AND project_id = ?"
            params.append(project_id)
        row = self.db.conn.execute(sql, params).fetchone()
        if row is None:
            raise NotFoundError(f"{self.table}에 {id} 없음")
        return self._from_row(row)

    def exists(self, id: str, project_id: str | None = None) -> bool:
        try:
            self.get(id, project_id)
            return True
        except NotFoundError:
            return False

    def find(
        self,
        project_id: str | None = None,
        *,
        order_by: str = "created_at",
        descending: bool = False,
        limit: int | None = None,
        **filters: Any,
    ) -> list[T]:
        """조회 컬럼으로 필터링. ``filters``의 키는 ``columns``에 정의된 컬럼이어야 한다."""
        where: list[str] = []
        params: list[Any] = []
        if self.scoped and project_id is not None:
            where.append("project_id = ?")
            params.append(project_id)
        for col, val in filters.items():
            if col not in self.columns and col != "id":
                raise StorageError(f"{self.table}에 조회 컬럼 {col!r} 없음")
            if isinstance(val, Sequence) and not isinstance(val, str):
                marks = ", ".join("?" for _ in val)
                where.append(f"{col} IN ({marks})")
                params.extend(_to_column(v) for v in val)
            else:
                where.append(f"{col} = ?")
                params.append(_to_column(val))
        if order_by not in ("created_at", "updated_at", "id", *self.columns):
            raise StorageError(f"{self.table}에 정렬 컬럼 {order_by!r} 없음")
        sql = f"SELECT data FROM {self.table}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order_by} {'DESC' if descending else 'ASC'}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.conn.execute(sql, params).fetchall()
        return [self._from_row(r) for r in rows]

    def count(self, project_id: str | None = None, **filters: Any) -> int:
        return len(self.find(project_id, **filters))


class ProjectRepository(BaseRepository[Project]):
    table = "projects"
    model = Project
    scoped = False
    columns = {"name": "name", "mode": "mode", "status": "status", "output_dir": "output_dir"}

    def list_all(self) -> list[Project]:
        return self.find(order_by="created_at", descending=True)


class SourceDocumentRepository(BaseRepository[SourceDocument]):
    table = "source_documents"
    model = SourceDocument
    columns = {"kind": "kind", "sha256": "sha256", "stored_path": "stored_path"}


class RequirementRepository(BaseRepository[Requirement]):
    table = "requirements"
    model = Requirement
    composite_key = True
    columns = {
        "type": "type",
        "status": "status",
        "verification_status": "verification_status",
        "scope_class": "scope_class",
    }


class RequirementChangeRepository(BaseRepository[RequirementChange]):
    table = "requirement_changes"
    model = RequirementChange
    columns = {
        "requirement_id": "requirement_id",
        "change_type": "change_type",
        "status": "status",
    }


class RequirementTraceRepository(BaseRepository[RequirementTrace]):
    table = "requirement_traces"
    model = RequirementTrace
    columns = {
        "requirement_id": "requirement_id",
        "target_type": "target_type",
        "target_id": "target_id",
    }


class StepRunRepository(BaseRepository[StepRun]):
    table = "step_runs"
    model = StepRun
    columns = {"step_key": "step_key", "attempt": "attempt", "status": "status"}

    def latest(self, project_id: str, step_key: str) -> StepRun | None:
        runs = self.find(
            project_id, step_key=step_key, order_by="attempt", descending=True, limit=1
        )
        return runs[0] if runs else None

    def latest_by_step(self, project_id: str) -> dict[str, StepRun]:
        out: dict[str, StepRun] = {}
        for run in self.find(project_id, order_by="attempt"):
            out[run.step_key] = run  # attempt 오름차순이므로 마지막이 최신
        return out


class GateResultRepository(BaseRepository[GateResult]):
    table = "gate_results"
    model = GateResult
    columns = {"step_key": "step_key", "step_run_id": "step_run_id", "decision": "decision"}


class DeliverableRepository(BaseRepository[Deliverable]):
    table = "deliverables"
    model = Deliverable
    columns = {"kind": "kind", "version": "version", "file_path": "file_path"}


class ValidationResultRepository(BaseRepository[ValidationResult]):
    table = "validation_results"
    model = ValidationResult
    columns = {
        "target_type": "target_type",
        "target_id": "target_id",
        "level": "level",
        "resolved": "resolved",
    }


class ApprovalRepository(BaseRepository[Approval]):
    table = "approvals"
    model = Approval
    columns = {"target_type": "target_type", "target_id": "target_id", "decision": "decision"}


class RevisionRepository(BaseRepository[Revision]):
    table = "revisions"
    model = Revision
    columns = {"number": "number"}


class AuditEventRepository(BaseRepository[AuditEvent]):
    """추가 전용. ``update``는 금지."""

    table = "audit_events"
    model = AuditEvent
    columns = {"at": "at", "action": "action", "is_error": "is_error"}

    def update(self, entity: AuditEvent) -> AuditEvent:  # noqa: D102
        raise StorageError(
            "감사 이벤트는 수정할 수 없습니다.", resolution="새 이벤트를 추가하십시오."
        )

    def recent(
        self, project_id: str, limit: int = 50, errors_only: bool = False
    ) -> list[AuditEvent]:
        if errors_only:
            return self.find(project_id, is_error=True, order_by="at", descending=True, limit=limit)
        return self.find(project_id, order_by="at", descending=True, limit=limit)


class ExtractionRunRepository(BaseRepository[ExtractionRun]):
    table = "extraction_runs"
    model = ExtractionRun
    columns = {"source_document_id": "source_document_id", "status": "status"}

    def latest_for_document(self, project_id: str, document_id: str) -> ExtractionRun | None:
        runs = self.find(
            project_id,
            source_document_id=document_id,
            order_by="created_at",
            descending=True,
            limit=1,
        )
        return runs[0] if runs else None

    def latest_by_document(self, project_id: str) -> dict[str, ExtractionRun]:
        out: dict[str, ExtractionRun] = {}
        for run in self.find(project_id, order_by="created_at"):
            out[run.source_document_id] = run
        return out


class ExtractedBlockRepository(BaseRepository[ExtractedBlock]):
    table = "extracted_blocks"
    model = ExtractedBlock
    columns = {
        "source_document_id": "source_document_id",
        "extraction_run_id": "extraction_run_id",
        "block_type": "block_type",
        "block_order": "order",
        "needs_review": "needs_review",
    }

    def insert_many(self, blocks: list[ExtractedBlock]) -> None:
        with self.db.transaction():
            for b in blocks:
                self.insert(b)

    def for_run(self, project_id: str, run_id: str) -> list[ExtractedBlock]:
        return self.find(project_id, extraction_run_id=run_id, order_by="block_order")

    def get_many(self, project_id: str, ids: list[str]) -> dict[str, ExtractedBlock]:
        if not ids:
            return {}
        return {b.id: b for b in self.find(project_id, id=list(ids), order_by="block_order")}

    def search(
        self, project_id: str, query: str, run_ids: list[str] | None = None, limit: int = 20
    ) -> list[ExtractedBlock]:
        """단순 부분 문자열 검색 (data JSON LIKE)."""
        sql = f"SELECT data FROM {self.table} WHERE project_id = ? AND data LIKE ?"
        params: list[Any] = [project_id, f"%{query}%"]
        if run_ids:
            sql += " AND extraction_run_id IN (" + ", ".join("?" for _ in run_ids) + ")"
            params.extend(run_ids)
        sql += f" ORDER BY block_order LIMIT {int(limit)}"
        rows = self.db.conn.execute(sql, params).fetchall()
        return [self._from_row(r) for r in rows]


class GateEvaluationRepository(BaseRepository[GateEvaluation]):
    table = "gate_evaluations"
    model = GateEvaluation
    columns = {"gate_key": "gate_key", "status": "status"}

    def latest(self, project_id: str, gate_key: str) -> GateEvaluation | None:
        rows = self.find(
            project_id, gate_key=gate_key, order_by="created_at", descending=True, limit=1
        )
        return rows[0] if rows else None


class TechnologyResearchRepository(BaseRepository[TechnologyResearch]):
    table = "technology_research"
    model = TechnologyResearch
    columns = {"topic": "topic", "feasibility": "feasibility"}


class FeasibilityStudyRepository(BaseRepository[FeasibilityStudy]):
    table = "feasibility_studies"
    model = FeasibilityStudy
    columns = {}


class AgentOutputRepository(BaseRepository[AgentOutput]):
    table = "agent_outputs"
    model = AgentOutput
    columns = {"role": "role", "version": "version", "file_path": "file_path"}

    def latest(self, project_id: str, role: str) -> AgentOutput | None:
        rows = self.find(project_id, role=role, order_by="created_at", descending=True, limit=1)
        return rows[0] if rows else None


class SequenceRepository:
    """프로젝트별 단조 증가 시퀀스 (요구사항 ID 발급 등). 값은 낮아지지 않는다."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def next(self, project_id: str, key: str, start: int = 1) -> int:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT next_value FROM sequences WHERE project_id = ? AND key = ?",
                (project_id, key),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO sequences(project_id, key, next_value) VALUES (?, ?, ?)",
                    (project_id, key, start + 1),
                )
                return start
            value = int(row["next_value"])
            conn.execute(
                "UPDATE sequences SET next_value = ? WHERE project_id = ? AND key = ?",
                (value + 1, project_id, key),
            )
            return value

    def peek(self, project_id: str, key: str, start: int = 1) -> int:
        row = self.db.conn.execute(
            "SELECT next_value FROM sequences WHERE project_id = ? AND key = ?",
            (project_id, key),
        ).fetchone()
        return start if row is None else int(row["next_value"])

    def ensure_at_least(self, project_id: str, key: str, minimum_next: int) -> int:
        """다음 발급값이 ``minimum_next`` 이상이 되도록 끌어올린다 (기존 ID 적재용). 낮추지 않는다."""
        with self.db.transaction() as conn:
            current = self.peek(project_id, key)
            target = max(current, minimum_next)
            conn.execute(
                "INSERT INTO sequences(project_id, key, next_value) VALUES (?, ?, ?) "
                "ON CONFLICT(project_id, key) DO UPDATE SET next_value = excluded.next_value",
                (project_id, key, target),
            )
            return target


class Repositories:
    """모든 리포지토리 묶음."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.documents = SourceDocumentRepository(db)
        self.requirements = RequirementRepository(db)
        self.changes = RequirementChangeRepository(db)
        self.traces = RequirementTraceRepository(db)
        self.step_runs = StepRunRepository(db)
        self.gates = GateResultRepository(db)
        self.deliverables = DeliverableRepository(db)
        self.validations = ValidationResultRepository(db)
        self.approvals = ApprovalRepository(db)
        self.revisions = RevisionRepository(db)
        self.audit = AuditEventRepository(db)
        self.sequences = SequenceRepository(db)
        self.extraction_runs = ExtractionRunRepository(db)
        self.blocks = ExtractedBlockRepository(db)
        self.gate_evaluations = GateEvaluationRepository(db)
        self.research = TechnologyResearchRepository(db)
        self.feasibility = FeasibilityStudyRepository(db)
        self.agent_outputs = AgentOutputRepository(db)
