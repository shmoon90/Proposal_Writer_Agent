"""PowerPoint 생성기."""

from proposal_agent.generators.pptx.builder import DeckBuilder
from proposal_agent.generators.pptx.decks import (
    build_presentation_deck,
    build_submission_deck,
    key_figures,
)
from proposal_agent.generators.pptx.outline import (
    ChapterPlan,
    OutlineSection,
    decide_outline,
    plan_chapters,
    rfp_toc_from_blocks,
)
from proposal_agent.generators.pptx.template import (
    TemplateDeckBuilder,
    TemplateProfile,
    profile_template,
)

__all__ = [
    "ChapterPlan",
    "DeckBuilder",
    "OutlineSection",
    "TemplateDeckBuilder",
    "TemplateProfile",
    "plan_chapters",
    "profile_template",
    "build_presentation_deck",
    "build_submission_deck",
    "decide_outline",
    "key_figures",
    "rfp_toc_from_blocks",
]
