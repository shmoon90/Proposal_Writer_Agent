"""PowerPoint·Excel·다이어그램 생성."""

from proposal_agent.generators.base import GenerationContext, acceptance_label, requirement_note
from proposal_agent.generators.service import (
    FINAL_SUBDIR,
    KIND_TARGETS,
    GenerationResult,
    GenerationService,
)

__all__ = [
    "FINAL_SUBDIR",
    "KIND_TARGETS",
    "GenerationContext",
    "GenerationResult",
    "GenerationService",
    "acceptance_label",
    "requirement_note",
]
