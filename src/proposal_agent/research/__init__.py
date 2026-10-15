"""기술 조사 및 출처 관리."""

from proposal_agent.research.service import (
    COMPARISON_AREAS,
    COMPARISON_CRITERIA,
    ResearchRunResult,
    ResearchService,
    ResearchTopic,
)
from proposal_agent.research.sources import classify_url, effective_trust

__all__ = [
    "COMPARISON_AREAS",
    "COMPARISON_CRITERIA",
    "ResearchRunResult",
    "ResearchService",
    "ResearchTopic",
    "classify_url",
    "effective_trust",
]
