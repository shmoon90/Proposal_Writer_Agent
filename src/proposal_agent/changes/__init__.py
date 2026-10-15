"""구축 단계 변경관리 (Phase 6).

- ``baseline_service``: 기존 산출물(Excel) 적재 → 기준 데이터(요구사항·추적·WBS·인력) + Revision v1.0
- ``semantic``: 결정적 의미 비교 (ADD/MODIFY/DELETE_REQUEST/NO_CHANGE/AMBIGUOUS)
- ``impact``: WBS·일정·공수·인력 영향 시뮬레이션 (코드 계산, 순환 시 중단)
- ``service``: 변경 요청 생애주기 (접수 → 분석 → 승인/반려 → 반영 → 문서 재생성)
"""

from proposal_agent.changes.baseline_service import BaselineLoadResult, BaselineService
from proposal_agent.changes.impact import analyze_impact, simulate
from proposal_agent.changes.semantic import classify_request, similarity
from proposal_agent.changes.service import ApplyResult, ChangeService

__all__ = [
    "ApplyResult",
    "BaselineLoadResult",
    "BaselineService",
    "ChangeService",
    "analyze_impact",
    "classify_request",
    "similarity",
    "simulate",
]
