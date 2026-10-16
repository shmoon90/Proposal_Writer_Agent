"""사업 참여 타당성 평가 (지시문 §6, 단계 2).

평가 항목 13개를 코드가 프로젝트 데이터(RFP 분석·요구사항·조사·설정·계획) 로 채우고, 데이터가 없는 항목은
``unknown`` + ``needs_input`` 으로 남긴다. 사용자는 항목별 판정을 덮어쓸 수 있고(``user_rating``), 최종 참여 결정은
``Decision`` 엔티티(공식 결정) 로 따로 기록한다 — 점수만으로 자동 결정하지 않는다.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped
from proposal_agent.models.enums import BidRecommendation, FeasibilityRating

ITEM_KEYS: tuple[tuple[str, str], ...] = (
    ("strategic_fit", "사업 목적·전략적 적합성"),
    ("win_probability", "수주 가능성·평가 기준"),
    ("tech_capability", "요구 기술의 확보 가능성"),
    ("staffing", "인력·협력사 확보 가능성"),
    ("schedule", "일정·납기 위험"),
    ("effort", "예상 투입 공수"),
    ("profitability", "예상 매출·원가·수익성"),
    ("external_solutions", "외부 솔루션 비용·라이선스"),
    ("contract", "계약 조건·책임 범위"),
    ("security_legal", "보안·개인정보·법적 위험"),
    ("ambiguity", "요구사항의 모호성"),
    ("legacy", "기존 시스템 연계·기술 부채"),
    ("failure_factors", "주요 실패 요인·대응 방안"),
)
CRITICAL_ITEMS = ("tech_capability", "schedule", "profitability", "security_legal", "contract")


class FeasibilityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    rating: FeasibilityRating = FeasibilityRating.UNKNOWN
    code_basis: list[str] = Field(default_factory=list, description="코드가 데이터에서 찾은 근거")
    assumptions: list[str] = Field(default_factory=list, description="산정에 쓴 가정")
    needs_input: bool = Field(default=False, description="데이터가 없어 사용자 판단·입력 필요")
    user_rating: FeasibilityRating | None = None
    user_note: str = ""
    agent_comment: str = ""

    @property
    def final_rating(self) -> FeasibilityRating:
        return self.user_rating or self.rating


class FeasibilityAssessment(ProjectScoped):
    id_prefix: ClassVar[str] = "bida"

    version: int = 1
    status: str = Field(default="draft", description="draft | reviewed | decided")
    items: list[FeasibilityItem] = Field(default_factory=list)
    recommendation: BidRecommendation = BidRecommendation.NEEDS_REVIEW
    recommendation_basis: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list, description="추가 확인 사항")
    effort_estimate: dict[str, Any] = Field(default_factory=dict)
    cost_estimate: dict[str, Any] = Field(
        default_factory=dict,
        description="revenue/cost/margin/status/assumptions — 단가·예산 없으면 status=unavailable",
    )
    inputs_snapshot: dict[str, Any] = Field(
        default_factory=dict, description="평가에 쓴 데이터 요약"
    )
    agent_review: dict[str, Any] | None = Field(default=None, description="에이전트 검토(선택)")
    report_path: str = Field(default="", description="평가서 파일 (Output 루트 기준)")
    decision_id: str | None = Field(default=None, description="참여 결정 Decision ID")
    decision_choice: str = Field(default="", description="사용자 최종 결정 (BidRecommendation 값)")

    def item(self, key: str) -> FeasibilityItem | None:
        return next((i for i in self.items if i.key == key), None)

    def counts(self) -> dict[str, int]:
        out = {r.value: 0 for r in FeasibilityRating}
        for i in self.items:
            out[i.final_rating.value] += 1
        return out


__all__ = ["CRITICAL_ITEMS", "ITEM_KEYS", "FeasibilityAssessment", "FeasibilityItem"]
