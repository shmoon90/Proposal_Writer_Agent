"""요구사항 관리: ID 정책(Phase 1), registry/diff/trace(Phase 2~)."""

from proposal_agent.requirements.id_policy import (
    LegacyIdScheme,
    RequirementIdPolicy,
    find_match,
    normalize_text,
)

__all__ = ["LegacyIdScheme", "RequirementIdPolicy", "find_match", "normalize_text"]
