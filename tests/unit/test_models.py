"""models: ID 자동 발급, 직렬화 왕복, 검증 규칙, 상태 전이, 에이전트 출력 스키마."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError as PydanticValidationError

from proposal_agent.models import (
    Project,
    ProjectMode,
    Requirement,
    RequirementDraft,
    RequirementStatus,
    RequirementType,
    SourceRef,
    can_transition,
)


def test_entity_gets_prefixed_id_and_timestamps() -> None:
    p = Project(name="n", mode=ProjectMode.BUILD, output_dir="o", workspace_dir="w")
    assert p.id.startswith("prj_") and len(p.id) == 4 + 32
    assert p.created_at.tzinfo is not None


def test_project_rejects_blank_name_and_bad_dates() -> None:
    with pytest.raises(PydanticValidationError):
        Project(name="   ", mode=ProjectMode.BUILD, output_dir="o", workspace_dir="w")
    with pytest.raises(PydanticValidationError):
        Project(
            name="n",
            mode=ProjectMode.BUILD,
            output_dir="o",
            workspace_dir="w",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 4, 1),
        )


def test_requirement_json_roundtrip() -> None:
    r = Requirement(
        id="REQ-N-001",
        project_id="prj_x",
        name="성능",
        type=RequirementType.NON_FUNCTIONAL,
        source_refs=[SourceRef(document_id="doc_1", page=3, quote="응답 2초 이내")],
    )
    data = r.model_dump(mode="json")
    again = Requirement.model_validate(data)
    assert again == r
    assert data["type"] == "non_functional"


def test_requirement_from_draft_sets_id_and_status() -> None:
    draft = RequirementDraft(
        name="로그인", description="SSO 로그인", type=RequirementType.FUNCTIONAL
    )
    r = Requirement.from_draft(
        draft, id="REQ-F-001", project_id="prj_x", created_by="agent:extractor"
    )
    assert (
        r.id == "REQ-F-001"
        and r.status == RequirementStatus.DRAFT
        and r.created_by == "agent:extractor"
    )


def test_draft_schema_excludes_id_and_status_and_is_draft07_compatible() -> None:
    schema = RequirementDraft.model_json_schema()
    assert "id" not in schema["properties"] and "status" not in schema["properties"]
    assert "$schema" not in schema  # Agent SDK는 draft-07로 검증
    with pytest.raises(PydanticValidationError):
        RequirementDraft(name="x", description="y", type="functional", id="REQ-F-999")  # type: ignore[call-arg]


def test_requirement_state_transitions() -> None:
    assert can_transition(RequirementStatus.DRAFT, RequirementStatus.VERIFIED)
    assert not can_transition(RequirementStatus.DRAFT, RequirementStatus.BASELINE)
    assert can_transition(RequirementStatus.BASELINE, RequirementStatus.DELETED)
    assert can_transition(RequirementStatus.DELETED, RequirementStatus.BASELINE)
    assert not can_transition(RequirementStatus.DELETED, RequirementStatus.DRAFT)
