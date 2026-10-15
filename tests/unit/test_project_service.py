"""services.project_service: 생성·조회·열기·폴더·격리·감사."""

from __future__ import annotations

from datetime import date

import pytest

from proposal_agent.config import OUTPUT_SUBDIRS, NotFoundError, PWAError, ValidationError
from proposal_agent.models import Project, ProjectMode, ProjectStatus
from proposal_agent.services import Services


def test_create_project_builds_folders_db_and_audit(
    services: Services, proposal_project: Project
) -> None:
    p = proposal_project
    assert p.output_dir.startswith("Project_") and p.workspace_dir == p.id
    loc = services.projects.locations(p)
    assert loc.missing_subdirs == ()
    out = services.ctx.paths.project_output_dir(p.output_dir)
    assert sorted(x.name for x in out.iterdir()) == sorted(OUTPUT_SUBDIRS)
    assert (services.ctx.paths.workspace_for(p.id) / "uploads").is_dir()
    assert services.projects.get(p.id).name == "제안 테스트 사업"
    assert services.projects.get(p.id).duration_days == 181
    actions = [e.action for e in services.ctx.repos.audit.recent(p.id)]
    assert "project.created" in actions


def test_create_rejects_blank_name_and_bad_dates(services: Services) -> None:
    with pytest.raises(ValidationError):
        services.projects.create(name="  ", mode=ProjectMode.PROPOSAL)
    with pytest.raises(ValidationError):
        services.projects.create(
            name="x",
            mode=ProjectMode.PROPOSAL,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
        )
    assert services.projects.list_projects() == []


def test_same_name_projects_get_distinct_folders(services: Services) -> None:
    a = services.projects.create(name="중복", mode=ProjectMode.PROPOSAL)
    b = services.projects.create(name="중복", mode=ProjectMode.PROPOSAL)
    assert a.output_dir != b.output_dir
    assert b.output_dir.startswith(a.output_dir + "_")


def test_list_and_filter_by_mode(
    services: Services, proposal_project: Project, build_project: Project
) -> None:
    all_ids = {p.id for p in services.projects.list_projects()}
    assert all_ids == {proposal_project.id, build_project.id}
    assert [p.id for p in services.projects.list_projects(ProjectMode.BUILD)] == [build_project.id]


def test_open_missing_raises_and_restores_subdirs(
    services: Services, proposal_project: Project
) -> None:
    with pytest.raises(NotFoundError):
        services.projects.open("prj_nope")
    out = services.ctx.paths.project_output_dir(proposal_project.output_dir)
    (out / "11_QA_Validation_Reports").rmdir()
    opened = services.projects.open(proposal_project.id, actor="tester")
    assert (out / "11_QA_Validation_Reports").is_dir()
    assert opened.id == proposal_project.id
    assert "project.subdirs_restored" in [
        e.action for e in services.ctx.repos.audit.recent(opened.id)
    ]


def test_open_fails_clearly_when_folder_removed(
    services: Services, proposal_project: Project
) -> None:
    out = services.ctx.paths.project_output_dir(proposal_project.output_dir)
    for sub in out.iterdir():
        sub.rmdir()
    out.rmdir()
    with pytest.raises(PWAError) as info:
        services.projects.open(proposal_project.id)
    assert "산출물 폴더" in info.value.message and info.value.resolution


def test_update_status_records_audit(services: Services, proposal_project: Project) -> None:
    services.projects.update_status(proposal_project, ProjectStatus.ANALYZING, actor="tester")
    assert services.projects.get(proposal_project.id).status == ProjectStatus.ANALYZING
    ev = [
        e
        for e in services.ctx.repos.audit.recent(proposal_project.id)
        if e.action == "project.status_changed"
    ]
    assert ev and ev[0].payload == {"from": "created", "to": "analyzing"}


def test_data_isolation_between_projects(
    services: Services, proposal_project: Project, build_project: Project
) -> None:
    services.documents.register_upload(
        proposal_project, kind="rfp", file_name="a.pdf", data=b"%PDF a"
    )  # type: ignore[arg-type]
    assert services.documents.list_documents(build_project.id) == []
    assert len(services.documents.list_documents(proposal_project.id)) == 1
    assert services.ctx.repos.audit.recent(build_project.id, errors_only=True) == []
    assert all(
        e.project_id == build_project.id for e in services.ctx.repos.audit.recent(build_project.id)
    )
