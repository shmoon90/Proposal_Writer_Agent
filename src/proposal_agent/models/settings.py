"""프로젝트 설정 값 객체 (통합 개발 지시문 §3, 단계 1).

``Project.settings``(dict) 에 JSON 으로 저장한다 — 스키마 변경 없이 되돌릴 수 있다. 기술 선택 모드 5종과
기술 스택, 일정·예산·공수 제약, 기존 시스템, 보안·개인정보 요구, 외부 솔루션·연계 시스템, 산출물 종류를 담는다.
RFP 가 기술을 명시하면 ``tech_selection_mode`` 는 ``rfp_specified`` 가 기본이며, 다른 모드로 바꾸는 것은
사람의 결정(변경 사유 기록) 이다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from proposal_agent.models.enums import TechSelectionMode

SETTINGS_KEY = "project_settings"  # Project.settings 안의 키
TECH_AREAS: tuple[tuple[str, str], ...] = (
    ("language", "개발 언어"),
    ("frontend", "프론트엔드 프레임워크"),
    ("backend", "백엔드 프레임워크"),
    ("database", "데이터베이스"),
    ("web_server", "웹 서버"),
    ("was", "WAS"),
    ("ui_framework", "UI/UX 프레임워크"),
    ("deploy_platform", "배포 플랫폼·인프라"),
)


class TechStack(BaseModel):
    """영역별 기술 선택. 값은 사람이 적은 문자열(제품·버전)이며 빈값은 미정."""

    model_config = ConfigDict(extra="forbid")

    language: str = ""
    frontend: str = ""
    backend: str = ""
    database: str = ""
    web_server: str = ""
    was: str = ""
    ui_framework: str = ""
    deploy_platform: str = ""

    def filled(self) -> dict[str, str]:
        return {k: v for k, v in self.model_dump().items() if str(v).strip()}

    def labeled(self) -> list[tuple[str, str]]:
        labels = dict(TECH_AREAS)
        return [(labels[k], v) for k, v in self.filled().items()]


class ProjectSettings(BaseModel):
    """프로젝트 착수 설정. 모든 필드는 선택이며 비어 있으면 '미정' 으로 다룬다."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(default="", description="사업 설명")
    schedule_constraints: list[str] = Field(
        default_factory=list, description="일정 제약 (예: 10월 오픈)"
    )
    budget_amount: Decimal | None = Field(default=None, description="예산 (원). 없으면 None")
    budget_note: str = Field(default="", description="예산 근거·부가세 포함 여부 등")
    effort_limit_mm: Decimal | None = Field(default=None, description="투입 공수 상한 (M/M)")
    has_existing_system: bool | None = Field(
        default=None, description="기존 시스템 유무 (None=미확인)"
    )
    existing_system_note: str = ""
    tech_selection_mode: TechSelectionMode = TechSelectionMode.RFP_SPECIFIED
    tech_selection_reason: str = Field(
        default="", description="모드 선택·변경 사유 (RFP 명시 기술을 바꿀 때 필수)"
    )
    tech_stack: TechStack = Field(default_factory=TechStack)
    rfp_specified_tech: list[str] = Field(
        default_factory=list, description="RFP 가 명시한 기술 (조사·분석에서 채움)"
    )
    security_privacy_requirements: list[str] = Field(default_factory=list)
    external_solutions: list[str] = Field(default_factory=list, description="외부 솔루션 (제품명)")
    integration_systems: list[str] = Field(default_factory=list, description="연계 시스템")
    deliverable_kinds: list[str] = Field(
        default_factory=list, description="요구 산출물 종류 (DeliverableKind 값 또는 자유 문자열)"
    )
    deliverable_formats: list[str] = Field(
        default_factory=list, description="제출 형식 (예: A4 세로 PPT, xlsx)"
    )
    cost_rates: dict[str, Decimal] = Field(
        default_factory=dict,
        description="역할별 단가 (원/M/M). 사업성 평가·비용 산정에 사용, 없으면 산정 불가",
    )
    overhead_ratio: Decimal | None = Field(default=None, description="간접비율 (0.2 = 20%)")
    notes: str = ""

    @field_validator("budget_amount", "effort_limit_mm", "overhead_ratio")
    @classmethod
    def _non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("음수는 허용되지 않습니다.")
        return v

    @field_validator(
        "schedule_constraints",
        "security_privacy_requirements",
        "external_solutions",
        "integration_systems",
        "deliverable_kinds",
        "deliverable_formats",
        "rfp_specified_tech",
    )
    @classmethod
    def _strip_items(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in v if str(x).strip()]

    # --- 직렬화 ---------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_project_settings(cls, settings: dict[str, Any] | None) -> ProjectSettings:
        raw = (settings or {}).get(SETTINGS_KEY)
        if not isinstance(raw, dict):
            return cls()
        return cls.model_validate(raw)

    def requires_change_reason(self, rfp_specified: bool) -> bool:
        """RFP 명시 기술이 있는데 모드가 rfp_specified 가 아니면 사유가 필요하다."""
        return rfp_specified and self.tech_selection_mode != TechSelectionMode.RFP_SPECIFIED

    def summary_lines(self) -> list[str]:
        out: list[str] = []
        if self.description:
            out.append(f"사업 설명: {self.description[:120]}")
        if self.schedule_constraints:
            out.append("일정 제약: " + "; ".join(self.schedule_constraints[:4]))
        if self.budget_amount is not None:
            out.append(
                f"예산: {self.budget_amount:,} 원"
                + (f" ({self.budget_note})" if self.budget_note else "")
            )
        if self.effort_limit_mm is not None:
            out.append(f"공수 상한: {self.effort_limit_mm} M/M")
        if self.has_existing_system is not None:
            out.append(
                "기존 시스템: "
                + ("있음" if self.has_existing_system else "없음")
                + (f" — {self.existing_system_note}" if self.existing_system_note else "")
            )
        out.append(
            f"기술 선택 모드: {self.tech_selection_mode.label}"
            + (f" ({self.tech_selection_reason})" if self.tech_selection_reason else "")
        )
        for k, v in self.tech_stack.labeled():
            out.append(f"{k}: {v}")
        if self.rfp_specified_tech:
            out.append("RFP 명시 기술: " + ", ".join(self.rfp_specified_tech[:8]))
        if self.security_privacy_requirements:
            out.append("보안·개인정보: " + "; ".join(self.security_privacy_requirements[:4]))
        if self.external_solutions:
            out.append("외부 솔루션: " + ", ".join(self.external_solutions[:6]))
        if self.integration_systems:
            out.append("연계 시스템: " + ", ".join(self.integration_systems[:6]))
        if self.deliverable_kinds:
            out.append("산출물: " + ", ".join(self.deliverable_kinds[:10]))
        if self.cost_rates:
            out.append(
                "단가 입력: "
                + ", ".join(f"{k} {v:,}" for k, v in list(self.cost_rates.items())[:5])
            )
        return out


__all__ = ["SETTINGS_KEY", "TECH_AREAS", "ProjectSettings", "TechStack"]
