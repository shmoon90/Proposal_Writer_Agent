"""비용 산정 (지시문 §6·§14·단계 4): 역할별 배정 공수 × 단가 → 원가, 예산 → 매출·마진.

단가는 ``ProjectSettings.cost_rates``(역할명 → 원/M/M) 또는 ``StaffRole.unit_cost_per_mm`` 에서 오고, 예산은 설정
또는 RFP 예산 문구에서 온다. 어느 하나가 없으면 ``status="unavailable"`` 과 이유를 남기고 수치를 만들지 않는다.
사업성 평가·인력투입계획 '비용산정' 시트가 같은 함수를 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from proposal_agent.models import ProjectSettings, StaffingAllocation, StaffRole
from proposal_agent.planning.effort import md_to_mm

_KRW_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(억|천만|백만|만)?\s*원?")


def parse_krw(text: str) -> Decimal | None:
    """'약 4.5억', '450,000,000원', '3천만원' 같은 금액 문구를 원 단위 Decimal 로. 못 찾으면 None."""
    best: Decimal | None = None
    for num, unit in _KRW_RE.findall(text or ""):
        try:
            v = Decimal(num.replace(",", ""))
        except Exception:
            continue
        mult = {
            "억": Decimal(10**8),
            "천만": Decimal(10**7),
            "백만": Decimal(10**6),
            "만": Decimal(10**4),
        }.get(unit)
        if mult is None:
            if "," not in num and v < 10_000:  # 단위 없는 작은 수는 금액이 아님
                continue
            mult = Decimal(1)
        v = (v * mult).quantize(Decimal("1"))
        if best is None or v > best:
            best = v
    return best


@dataclass
class CostLine:
    role: str
    mm: Decimal
    rate: Decimal | None
    cost: Decimal | None

    @property
    def label(self) -> str:
        if self.rate is None or self.cost is None:
            return f"{self.role}: {self.mm} M/M × 단가 없음"
        return f"{self.role}: {self.mm} M/M × {self.rate:,} 원 = {self.cost:,} 원"


@dataclass
class CostEstimate:
    status: str = "unavailable"  # estimated | unavailable
    revenue: Decimal | None = None
    revenue_source: str = ""
    direct_cost: Decimal | None = None
    overhead_ratio: Decimal | None = None
    overhead_cost: Decimal | None = None
    total_cost: Decimal | None = None
    margin: Decimal | None = None
    margin_ratio: Decimal | None = None
    lines: list[CostLine] = field(default_factory=list)
    missing_rates: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "assumptions": list(self.assumptions),
            "lines": [ln.label for ln in self.lines],
            "missing_rates": list(self.missing_rates),
        }
        if self.revenue is not None:
            out["revenue"] = str(self.revenue)
            out["revenue_source"] = self.revenue_source
        if self.status == "estimated":
            out.update(
                {
                    "cost": str(self.total_cost),
                    "direct_cost": str(self.direct_cost),
                    "overhead_cost": str(self.overhead_cost or Decimal(0)),
                    "margin": str(self.margin),
                    "margin_ratio": str(self.margin_ratio),
                }
            )
        return out


def estimate_cost(
    settings: ProjectSettings,
    roles: list[StaffRole],
    allocations: list[StaffingAllocation],
    *,
    budget_hints: list[str] | None = None,
) -> CostEstimate:
    est = CostEstimate()
    # 매출(예산)
    if settings.budget_amount is not None:
        est.revenue, est.revenue_source = settings.budget_amount, "설정 예산"
    else:
        for h in budget_hints or []:
            parsed = parse_krw(str(h))
            if parsed:
                est.revenue, est.revenue_source = parsed, f"RFP 예산 문구 '{str(h)[:40]}'"
                break
    # 역할별 공수
    role_name = {r.id: r.role_name for r in roles}
    by_role: dict[str, Decimal] = {}
    for al in allocations:
        name = role_name.get(al.staff_role_id, al.staff_role_id)
        by_role[name] = by_role.get(name, Decimal("0")) + Decimal(str(al.effort_md))
    rate_of: dict[str, Decimal] = {
        r.role_name: r.unit_cost_per_mm for r in roles if r.unit_cost_per_mm is not None
    }
    rate_of.update(settings.cost_rates)
    direct = Decimal("0")
    for name, md in by_role.items():
        mm = md_to_mm(md)
        rate = rate_of.get(name)
        cost = (mm * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP) if rate else None
        est.lines.append(CostLine(role=name, mm=mm, rate=rate, cost=cost))
        if cost is None:
            est.missing_rates.append(name)
        else:
            direct += cost
    if not by_role:
        est.assumptions.append("배정 공수 없음(WBS·인력 계획 전) — 원가 산정 불가")
    if est.missing_rates:
        est.assumptions.append("단가 없는 역할: " + ", ".join(est.missing_rates[:6]))
    if by_role and not est.missing_rates:
        est.direct_cost = direct
        est.overhead_ratio = settings.overhead_ratio
        est.overhead_cost = (
            (direct * settings.overhead_ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if settings.overhead_ratio is not None
            else Decimal("0")
        )
        est.total_cost = direct + est.overhead_cost
        est.assumptions.append("원가 = 계획 공수 × 단가(+간접비율), 실제 투입과 다를 수 있음")
        if est.revenue is not None:
            est.status = "estimated"
            est.margin = est.revenue - est.total_cost
            est.margin_ratio = (
                (est.margin / est.revenue).quantize(Decimal("0.001")) if est.revenue else Decimal(0)
            )
            est.assumptions.append("부가세·간접비 처리는 단가·예산 입력 기준")
        else:
            est.assumptions.append("예산 정보 없음(설정·RFP 모두) — 마진 산정 불가")
    elif est.revenue is None:
        est.assumptions.append("예산 정보 없음(설정·RFP 모두)")
    return est


__all__ = ["CostEstimate", "CostLine", "estimate_cost", "parse_krw"]
