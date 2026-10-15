"""PowerPoint 생성기."""

from proposal_agent.generators.pptx.builder import DeckBuilder
from proposal_agent.generators.pptx.decks import (
    build_presentation_deck,
    build_submission_deck,
    key_figures,
)
from proposal_agent.generators.pptx.outline import (
    OutlineSection,
    decide_outline,
    rfp_toc_from_blocks,
)

__all__ = [
    "DeckBuilder",
    "OutlineSection",
    "build_presentation_deck",
    "build_submission_deck",
    "decide_outline",
    "key_figures",
    "rfp_toc_from_blocks",
]
