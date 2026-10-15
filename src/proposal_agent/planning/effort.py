"""공수 합계와 기간 환산 (결정적, Decimal)."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

MD_PER_MM = Decimal("20")  # 1 M/M = 20 M/D (가정값: 보고서에 명시)


def md_to_mm(md: Decimal | float | str) -> Decimal:
    return (Decimal(str(md)) / MD_PER_MM).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def duration_days_for(effort_md: Decimal | float, concurrent_ratio: float = 1.0) -> int:
    """공수(M/D)를 동시 투입 비율로 나눈 영업일 기간 (최소 1일)."""
    ratio = max(concurrent_ratio, 0.1)
    return max(1, math.ceil(float(effort_md) / ratio))


def rollup(
    code_to_effort: dict[str, Decimal], parent_of: dict[str, str | None]
) -> dict[str, Decimal]:
    """leaf 공수를 상위로 합산한다. 상위 항목의 자체 공수는 자식 합계로 대체된다."""
    children: dict[str, list[str]] = {}
    for code, parent in parent_of.items():
        if parent:
            children.setdefault(parent, []).append(code)
    totals: dict[str, Decimal] = {}

    def total(code: str) -> Decimal:
        if code in totals:
            return totals[code]
        kids = children.get(code, [])
        value = (
            sum((total(k) for k in kids), Decimal("0"))
            if kids
            else Decimal(str(code_to_effort.get(code, 0)))
        )
        totals[code] = value
        return value

    for code in parent_of:
        total(code)
    return totals


def split_by_ratio(effort_md: Decimal, roles: list[dict[str, str]]) -> dict[str, Decimal]:
    """역할별 비율로 공수를 나눈다. 비율 합이 1이 아니면 정규화하고, 역할이 없으면 '미정'에 전부."""
    if not roles:
        return {"미정": Decimal(str(effort_md))}
    weights: dict[str, Decimal] = {}
    for r in roles:
        name = str(r.get("role", "")).strip() or "미정"
        try:
            w = Decimal(str(r.get("ratio", "1")))
        except Exception:  # noqa: BLE001
            w = Decimal("1")
        weights[name] = weights.get(name, Decimal("0")) + max(w, Decimal("0"))
    total = sum(weights.values(), Decimal("0"))
    if total <= 0:
        return {"미정": Decimal(str(effort_md))}
    out = {
        name: (Decimal(str(effort_md)) * w / total).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        for name, w in weights.items()
    }
    diff = Decimal(str(effort_md)) - sum(out.values(), Decimal("0"))
    if diff and out:
        first = next(iter(out))
        out[first] += diff
    return out
