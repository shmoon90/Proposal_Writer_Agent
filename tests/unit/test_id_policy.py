"""requirements.id_policy: 발급 형식·단조성·격리·재발급 금지·레거시 체계."""

from __future__ import annotations

import pytest

from proposal_agent.config import ValidationError
from proposal_agent.models import Project, Requirement, RequirementType
from proposal_agent.requirements import (
    LegacyIdScheme,
    RequirementIdPolicy,
    find_match,
    normalize_text,
)
from proposal_agent.services import Services


def test_allocate_sequential_per_type_and_project(
    services: Services, proposal_project: Project, build_project: Project
) -> None:
    policy = RequirementIdPolicy(services.ctx.repos.sequences)
    a = proposal_project.id
    assert policy.allocate(a, RequirementType.FUNCTIONAL) == "FR-001"
    assert policy.allocate(a, RequirementType.NON_FUNCTIONAL) == "NFR-001"
    assert policy.allocate(a, RequirementType.FUNCTIONAL) == "FR-002"
    assert policy.allocate(build_project.id, RequirementType.FUNCTIONAL) == "FR-001"
    assert policy.peek(a, RequirementType.FUNCTIONAL) == "FR-003"


def test_ids_never_reissued_after_delete(services: Services, proposal_project: Project) -> None:
    policy = RequirementIdPolicy(services.ctx.repos.sequences)
    first = policy.allocate(proposal_project.id, RequirementType.FUNCTIONAL)
    # 삭제는 상태 변경일 뿐 시퀀스를 되돌리지 않는다
    assert policy.allocate(proposal_project.id, RequirementType.FUNCTIONAL) != first
    assert policy.allocate(proposal_project.id, RequirementType.FUNCTIONAL) == "FR-003"


def test_resolve_keeps_existing_id_on_match(services: Services, proposal_project: Project) -> None:
    policy = RequirementIdPolicy(services.ctx.repos.sequences)
    existing = [
        Requirement(
            id="FR-001",
            project_id=proposal_project.id,
            name="사용자 로그인",
            type=RequirementType.FUNCTIONAL,
            rfp_quote="SSO 기반 로그인",
        )
    ]
    assert policy.resolve(
        proposal_project.id,
        RequirementType.FUNCTIONAL,
        name="사용자  로그인!",
        rfp_quote=None,
        existing=existing,
    ) == ("FR-001", True)
    assert policy.resolve(
        proposal_project.id,
        RequirementType.FUNCTIONAL,
        name="다른 이름",
        rfp_quote="sso 기반 로그인",
        existing=existing,
    ) == ("FR-001", True)
    new_id, matched = policy.resolve(
        proposal_project.id,
        RequirementType.FUNCTIONAL,
        name="권한 관리",
        rfp_quote=None,
        existing=existing,
    )
    assert new_id == "FR-001" and not matched  # 시퀀스는 이 프로젝트에서 처음 발급


def test_normalize_and_find_match() -> None:
    assert normalize_text(" 응답 시간, 2초 이내 ") == normalize_text("응답시간2초이내")
    assert find_match("없음", None, []) is None


def test_legacy_scheme_infer_and_continue(services: Services, build_project: Project) -> None:
    scheme = LegacyIdScheme.infer(["SFR-001", "SFR-012", "SFR-007", "NFR-003"])
    assert scheme == LegacyIdScheme(prefix="SFR-", width=3)
    policy = RequirementIdPolicy(services.ctx.repos.sequences)
    assert policy.allocate_legacy(build_project.id, scheme, ["SFR-001", "SFR-012"]) == "SFR-013"
    assert (
        policy.allocate_legacy(build_project.id, scheme, ["SFR-001"]) == "SFR-014"
    )  # 낮아지지 않음
    assert LegacyIdScheme.infer(["없음"]) is None


def test_validate_format(services: Services) -> None:
    policy = RequirementIdPolicy(services.ctx.repos.sequences)
    assert policy.validate_format("FR-001") == RequirementType.FUNCTIONAL
    assert policy.validate_format("CON-010") == RequirementType.CONSTRAINT
    with pytest.raises(ValidationError):
        policy.validate_format("ZZ-1")
