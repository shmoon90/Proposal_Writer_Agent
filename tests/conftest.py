"""공통 fixture: 임시 루트 폴더에 격리된 AppContext/Services."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/fixtures 임포트

from proposal_agent.config import ProjectPaths, Settings
from proposal_agent.models import Project, ProjectMode
from proposal_agent.services import AppContext, Services


@pytest.fixture
def paths(tmp_path: Path) -> ProjectPaths:
    return ProjectPaths(root=tmp_path)


@pytest.fixture
def ctx(paths: ProjectPaths) -> Iterator[AppContext]:
    context = AppContext.create(Settings(), paths=paths, configure_logging=False)
    yield context
    context.close()


@pytest.fixture
def services(ctx: AppContext) -> Services:
    return Services.from_context(ctx)


@pytest.fixture
def proposal_project(services: Services) -> Project:
    return services.projects.create(
        name="제안 테스트 사업",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 1),
        end_date=date(2027, 4, 30),
        created_by="tester",
    )


@pytest.fixture
def build_project(services: Services) -> Project:
    return services.projects.create(
        name="구축 테스트 사업", mode=ProjectMode.BUILD, created_by="tester"
    )
