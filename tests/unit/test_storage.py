"""storage: 마이그레이션 멱등성, CRUD, 격리, 감사 이벤트 추가 전용, 시퀀스, 파일 저장."""

from __future__ import annotations

from pathlib import Path

import pytest

from proposal_agent.config import (
    FileExistsConflict,
    NotFoundError,
    PathSecurityError,
    ProjectPaths,
    StorageError,
)
from proposal_agent.models import (
    AuditEvent,
    Project,
    ProjectMode,
    Requirement,
    RequirementStatus,
    RequirementType,
)
from proposal_agent.storage import MIGRATIONS, Database, FileStore, Repositories, versioned_name
from proposal_agent.storage.files import next_minor_version, parse_version


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "t.sqlite3")
    database.migrate()
    return database


@pytest.fixture
def repos(db: Database) -> Repositories:
    return Repositories(db)


def _project(name: str = "P", output_dir: str = "Project_P") -> Project:
    return Project(name=name, mode=ProjectMode.PROPOSAL, output_dir=output_dir, workspace_dir="w")


def test_migrate_is_idempotent_and_records_version(tmp_path: Path) -> None:
    db = Database(tmp_path / "m.sqlite3")
    assert db.migrate() == [m.version for m in MIGRATIONS]
    assert db.migrate() == []
    assert db.schema_version == MIGRATIONS[-1].version
    tables = {
        r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"projects", "requirements", "audit_events", "sequences", "schema_migrations"} <= tables


def test_project_insert_get_update(repos: Repositories) -> None:
    p = repos.projects.insert(_project())
    loaded = repos.projects.get(p.id)
    assert loaded.name == "P" and loaded.mode == ProjectMode.PROPOSAL
    loaded.name = "P2"
    repos.projects.update(loaded)
    assert repos.projects.get(p.id).name == "P2"
    assert repos.projects.get(p.id).updated_at >= loaded.created_at


def test_duplicate_output_dir_rejected(repos: Repositories) -> None:
    repos.projects.insert(_project(output_dir="same"))
    with pytest.raises(StorageError):
        repos.projects.insert(_project(name="other", output_dir="same"))


def test_get_missing_raises_not_found(repos: Repositories) -> None:
    with pytest.raises(NotFoundError):
        repos.projects.get("prj_missing")


def test_requirements_are_isolated_per_project(repos: Repositories) -> None:
    a = repos.projects.insert(_project("A", "Project_A"))
    b = repos.projects.insert(_project("B", "Project_B"))
    repos.requirements.insert(
        Requirement(id="REQ-F-001", project_id=a.id, name="a1", type=RequirementType.FUNCTIONAL)
    )
    repos.requirements.insert(
        Requirement(id="REQ-F-001", project_id=b.id, name="b1", type=RequirementType.FUNCTIONAL)
    )
    assert [r.name for r in repos.requirements.find(a.id)] == ["a1"]
    assert [r.name for r in repos.requirements.find(b.id)] == ["b1"]
    assert repos.requirements.get("REQ-F-001", a.id).name == "a1"
    with pytest.raises(StorageError):
        repos.requirements.get("REQ-F-001")  # 복합 키는 project_id 필수


def test_requirement_has_no_physical_delete(repos: Repositories) -> None:
    p = repos.projects.insert(_project())
    r = repos.requirements.insert(
        Requirement(id="REQ-F-001", project_id=p.id, name="x", type=RequirementType.FUNCTIONAL)
    )
    assert not hasattr(repos.requirements, "delete")
    r.status = RequirementStatus.DELETED
    repos.requirements.update(r)
    assert repos.requirements.get("REQ-F-001", p.id).status == RequirementStatus.DELETED
    assert repos.requirements.count(p.id) == 1


def test_find_rejects_unknown_filter_column(repos: Repositories) -> None:
    with pytest.raises(StorageError):
        repos.projects.find(nonexistent="x")
    with pytest.raises(StorageError):
        repos.projects.find(order_by="data; DROP TABLE projects")


def test_audit_events_are_append_only(repos: Repositories) -> None:
    p = repos.projects.insert(_project())
    e = repos.audit.insert(AuditEvent(project_id=p.id, action="x", error={"cause": "c"}))
    with pytest.raises(StorageError):
        repos.audit.update(e)
    assert [x.action for x in repos.audit.recent(p.id, errors_only=True)] == ["x"]


def test_sequences_monotonic_and_isolated(repos: Repositories) -> None:
    a = repos.projects.insert(_project("A", "Project_A"))
    b = repos.projects.insert(_project("B", "Project_B"))
    assert [repos.sequences.next(a.id, "k") for _ in range(3)] == [1, 2, 3]
    assert repos.sequences.next(b.id, "k") == 1
    assert repos.sequences.peek(a.id, "k") == 4
    assert repos.sequences.ensure_at_least(a.id, "k", 2) == 4  # 낮추지 않음
    assert repos.sequences.ensure_at_least(a.id, "k", 10) == 10
    assert repos.sequences.next(a.id, "k") == 10


def test_transaction_rollback_on_error(db: Database, repos: Repositories) -> None:
    p = _project()
    with pytest.raises(RuntimeError):
        with db.transaction():
            repos.projects.insert(p)
            raise RuntimeError("abort")
    assert not repos.projects.exists(p.id)


# --- 파일 저장소 -----------------------------------------------------------------------


@pytest.fixture
def store(paths: ProjectPaths) -> tuple[FileStore, str]:
    out = paths.create_project_output_dir("파일테스트")
    return FileStore(paths), out.name


def test_save_bytes_refuses_overwrite(store: tuple[FileStore, str]) -> None:
    fs, project_dir = store
    saved = fs.save_bytes(project_dir, "01_RFP_Original", "rfp.pdf", b"one")
    assert saved.path.read_bytes() == b"one"
    assert saved.relative_path == f"{project_dir}/01_RFP_Original/rfp.pdf"
    assert len(saved.sha256) == 64
    with pytest.raises(FileExistsConflict):
        fs.save_bytes(project_dir, "01_RFP_Original", "rfp.pdf", b"two")
    assert saved.path.read_bytes() == b"one"


def test_store_unique_appends_suffix(store: tuple[FileStore, str]) -> None:
    fs, project_dir = store
    names = [
        fs.store_unique(project_dir, "01_RFP_Original", "rfp.pdf", b"x").path.name for _ in range(3)
    ]
    assert names == ["rfp.pdf", "rfp_1.pdf", "rfp_2.pdf"]


def test_store_blocks_path_traversal_in_filename(store: tuple[FileStore, str]) -> None:
    fs, project_dir = store
    saved = fs.store_unique(project_dir, "01_RFP_Original", "..\\..\\evil.pdf", b"x")
    assert saved.path.parent.name == "01_RFP_Original" and saved.path.name == "evil.pdf"
    with pytest.raises(PathSecurityError):
        fs.save_bytes("../outside", "01_RFP_Original", "x.pdf", b"x")


def test_version_helpers(store: tuple[FileStore, str]) -> None:
    fs, project_dir = store
    assert versioned_name("요구사항정의서", "v1.0", ".xlsx") == "요구사항정의서_v1.0.xlsx"
    assert parse_version("요구사항정의서_v1.2.xlsx") == ("요구사항정의서", 1, 2)
    assert parse_version("plain.xlsx") is None
    assert next_minor_version("v1.9") == "v1.10"
    assert (
        fs.next_version_name(project_dir, "09_Excel_Deliverables", "요구사항정의서", ".xlsx")
        == "요구사항정의서_v1.0.xlsx"
    )
    fs.save_bytes(project_dir, "09_Excel_Deliverables", "요구사항정의서_v1.0.xlsx", b"a")
    fs.save_bytes(project_dir, "09_Excel_Deliverables", "요구사항정의서_v1.3.xlsx", b"b")
    assert (
        fs.latest_version(project_dir, "09_Excel_Deliverables", "요구사항정의서", ".xlsx") == "v1.3"
    )
    assert (
        fs.next_version_name(project_dir, "09_Excel_Deliverables", "요구사항정의서", ".xlsx")
        == "요구사항정의서_v1.4.xlsx"
    )
