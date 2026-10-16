"""planning: 영업일, 선후행(FS/SS/FF/SF+lag), 순환·참조·3단계 검증, 공수 롤업·배분, 인력 월별 집계, 기본 WBS, 기간 결정."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from proposal_agent.config import ValidationError
from proposal_agent.models import Project, ProjectMode, Requirement, RequirementType
from proposal_agent.planning import (
    BusinessCalendar,
    DepEdge,
    TaskNode,
    aggregate_roles,
    compute_schedule,
    cost_for,
    md_to_mm,
    parse_holidays,
    rollup,
    split_by_ratio,
)
from proposal_agent.services import Services

CAL = BusinessCalendar(holidays=[date(2026, 12, 25)])


def test_business_calendar_skips_weekends_and_holidays() -> None:
    assert not CAL.is_business_day(date(2026, 11, 7))  # 토
    assert not CAL.is_business_day(date(2026, 12, 25))
    assert CAL.add_business_days(date(2026, 11, 6), 1) == date(2026, 11, 6)  # 금
    assert CAL.add_business_days(date(2026, 11, 6), 2) == date(2026, 11, 9)  # 월
    assert CAL.offset(date(2026, 12, 24), 1) == date(2026, 12, 28)
    assert CAL.offset(date(2026, 11, 9), -1) == date(2026, 11, 6)
    assert CAL.business_days_between(date(2026, 11, 2), date(2026, 11, 13)) == 10
    assert CAL.business_days_by_month(date(2026, 11, 30), date(2026, 12, 2)) == {
        "2026-11": 1,
        "2026-12": 2,
    }
    assert parse_holidays("2026-12-25, 2027-01-01") == [date(2026, 12, 25), date(2027, 1, 1)]


def test_schedule_golden_fs_ss_ff_sf_with_lag() -> None:
    nodes = [
        TaskNode("1", None, "A", 5),
        TaskNode("2", None, "B", 3),
        TaskNode("3", None, "C", 2),
        TaskNode("4", None, "D", 4),
    ]
    deps = [DepEdge("1", "2", "FS", 1), DepEdge("1", "3", "SS", 2), DepEdge("2", "4", "FF", 0)]
    r = compute_schedule(
        nodes, deps, project_start=date(2026, 11, 2), project_end=date(2026, 12, 31), calendar=CAL
    )
    assert r.ok and r.order == ["1", "2", "3", "4"]
    assert (r.starts["1"], r.ends["1"]) == (date(2026, 11, 2), date(2026, 11, 6))
    assert (r.starts["2"], r.ends["2"]) == (
        date(2026, 11, 10),
        date(2026, 11, 12),
    )  # FS+1: 11/9 건너뜀
    assert r.starts["3"] == date(2026, 11, 4)  # SS+2
    assert r.ends["4"] == date(2026, 11, 12) and r.starts["4"] == date(2026, 11, 9)  # FF → 역산
    sf = compute_schedule(
        [TaskNode("1", None, "A", 5), TaskNode("2", None, "B", 2)],
        [DepEdge("1", "2", "SF", 0)],
        project_start=date(2026, 11, 2),
        project_end=None,
        calendar=CAL,
    )
    assert sf.ends["2"] >= sf.starts["1"]


def test_schedule_rollup_and_period_exceeded() -> None:
    nodes = [
        TaskNode("1", None, "분석", 1),
        TaskNode("1.1", "1", "a", 5),
        TaskNode("1.2", "1", "b", 10),
    ]
    r = compute_schedule(
        nodes,
        [DepEdge("1.1", "1.2")],
        project_start=date(2026, 11, 2),
        project_end=date(2026, 11, 10),
        calendar=CAL,
    )
    assert r.ok and r.starts["1"] == r.starts["1.1"] and r.ends["1"] == r.ends["1.2"]
    assert r.project_end_exceeded and any("전체 기간 초과" in w for w in r.warnings)


@pytest.mark.parametrize(
    ("nodes", "deps", "fragment"),
    [
        ([TaskNode("1", None, "a", 1), TaskNode("1.1", "9", "b", 1)], [], "상위 코드"),
        ([TaskNode("1.1.1.1", None, "a", 1)], [], "3단계"),
        ([TaskNode("1", None, "a", 0)], [], "1일 이상"),
        ([TaskNode("1", None, "a", 1)], [DepEdge("1", "2")], "참조 오류"),
        ([TaskNode("1", None, "a", 1)], [DepEdge("1", "1")], "자기 참조"),
        (
            [TaskNode("1", None, "a", 1), TaskNode("2", None, "b", 1)],
            [DepEdge("1", "2"), DepEdge("2", "1")],
            "순환",
        ),
    ],
)
def test_schedule_validation_errors(
    nodes: list[TaskNode], deps: list[DepEdge], fragment: str
) -> None:
    r = compute_schedule(
        nodes, deps, project_start=date(2026, 11, 2), project_end=None, calendar=CAL
    )
    assert not r.ok and any(fragment in e for e in r.errors), r.errors


def test_fixed_dates_conflict_warning() -> None:
    nodes = [
        TaskNode("1", None, "a", 5),
        TaskNode("2", None, "b", 2, fixed_start=date(2026, 11, 3)),
    ]
    r = compute_schedule(
        nodes, [DepEdge("1", "2")], project_start=date(2026, 11, 2), project_end=None, calendar=CAL
    )
    assert r.ok and any("충돌" in w for w in r.warnings)


def test_effort_helpers() -> None:
    assert md_to_mm(Decimal("30")) == Decimal("1.50")
    totals = rollup(
        {"1": Decimal("0"), "1.1": Decimal("5"), "1.2": Decimal("7.5"), "2": Decimal("3")},
        {"1": None, "1.1": "1", "1.2": "1", "2": None},
    )
    assert totals["1"] == Decimal("12.5") and totals["2"] == Decimal("3")
    split = split_by_ratio(
        Decimal("10"), [{"role": "백엔드", "ratio": "0.5"}, {"role": "QA", "ratio": "0.5"}]
    )
    assert split == {"백엔드": Decimal("5.00"), "QA": Decimal("5.00")}
    assert sum(
        split_by_ratio(
            Decimal("10"), [{"role": "a", "ratio": "1"}, {"role": "b", "ratio": "2"}]
        ).values()
    ) == Decimal("10")
    assert split_by_ratio(Decimal("4"), []) == {"미정": Decimal("4")}
    assert cost_for(Decimal("2.5"), None) is None and cost_for(
        Decimal("2.5"), Decimal("8000000")
    ) == Decimal("20000000")


def test_staffing_aggregation_by_month() -> None:
    loads = aggregate_roles(
        [
            ("1.1", "백엔드", Decimal("10"), date(2026, 11, 25), date(2026, 12, 8)),
            ("1.2", "백엔드", Decimal("20"), date(2026, 12, 1), date(2026, 12, 28)),
        ],
        CAL,
    )
    load = loads["백엔드"]
    assert load.total_md == Decimal("30") and load.total_mm == Decimal("1.50")
    assert set(load.monthly_md) == {"2026-11", "2026-12"} and sum(
        load.monthly_md.values()
    ) == Decimal("30")
    assert (
        load.headcount >= 1 and load.start == date(2026, 11, 25) and load.end == date(2026, 12, 28)
    )


def test_default_draft_and_build_plan(services: Services) -> None:
    p = services.projects.create(
        name="계획",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 2),
        end_date=date(2027, 4, 30),
    )
    for i, (t, name) in enumerate(
        [
            (RequirementType.FUNCTIONAL, "로그인"),
            (RequirementType.FUNCTIONAL, "조회"),
            (RequirementType.NON_FUNCTIONAL, "성능"),
            (RequirementType.CONSTRAINT, "표준"),
        ],
        start=1,
    ):
        services.ctx.repos.requirements.insert(
            Requirement(id=f"R-{i:03d}", project_id=p.id, name=name, type=t)
        )
    draft = services.planning.default_draft(services.ctx.repos.requirements.find(p.id))
    assert (
        all(i.estimate_basis for i in draft.items)
        and max(i.code.count(".") for i in draft.items) <= 2
    )
    result = services.planning.build_plan(p, None, None)
    assert result.auto_generated and result.period and result.period.source == "ui"
    wbs, deps, roles, allocs = services.planning.current_plan(p)
    milestones = [w for w in wbs if w.milestone]
    assert len(wbs) == len(draft.items) + len(milestones) and len(deps) == 2
    assert [m.code for m in milestones][:2] == ["0", "0.1"] and all(
        m.effort_md == 0 for m in milestones
    )
    assert [m.name for m in milestones if m.parent_id] == [
        "착수",
        "착수보고",
        "중간보고",
        "완료보고",
        "종료",
    ]
    leaf_total = sum((a.effort_md for a in allocs), Decimal("0"))
    assert leaf_total == result.total_effort_md > 0
    assert {r.role_name for r in roles} >= {"백엔드", "QA"}
    tasks = [w for w in wbs if w.related_requirement_ids == ["R-001"]]
    assert (
        tasks
        and tasks[0].planned_start
        and tasks[0].planned_end
        and tasks[0].planned_end >= tasks[0].planned_start
    )
    assert tasks[0].auto_generated and "검토 필요" in tasks[0].estimate_basis
    # 재생성은 이전 계획을 교체한다
    services.planning.build_plan(p, None, None)
    assert len(services.planning.current_plan(p)[0]) == len(wbs)


def test_period_resolution_prefers_ui_then_rfp_then_asks(services: Services) -> None:
    p = services.projects.create(name="기간", mode=ProjectMode.PROPOSAL)
    with pytest.raises(ValidationError) as info:
        services.planning.resolve_period(p, None)
    assert "입력" in info.value.resolution
    p.start_date = date(2026, 11, 2)
    period = services.planning.resolve_period(
        p, {"schedule_hints": ["사업 기간은 계약일로부터 10개월"]}
    )
    assert period.source == "rfp_hint" and period.end == date(2027, 9, 2)
    p.end_date = date(2027, 6, 30)
    assert services.planning.resolve_period(p, {"schedule_hints": ["10개월"]}).source == "ui"


def test_build_plan_rejects_missing_basis_and_cycles(services: Services) -> None:
    from proposal_agent.agents.schemas import WBSDraft

    p = services.projects.create(
        name="검증",
        mode=ProjectMode.PROPOSAL,
        start_date=date(2026, 11, 2),
        end_date=date(2027, 1, 31),
    )
    services.ctx.repos.requirements.insert(
        Requirement(id="R-001", project_id=p.id, name="x", type=RequirementType.FUNCTIONAL)
    )
    bad = WBSDraft.model_validate(
        {
            "items": [
                {
                    "code": "1",
                    "level": "task",
                    "name": "a",
                    "estimate_basis": "",
                    "effort_md_estimate": 2,
                }
            ],
            "dependencies": [],
        }
    )
    with pytest.raises(ValidationError):
        services.planning.build_plan(p, bad, None)
    cyc = WBSDraft.model_validate(
        {
            "items": [
                {
                    "code": "1",
                    "level": "task",
                    "name": "a",
                    "estimate_basis": "x",
                    "effort_md_estimate": 2,
                },
                {
                    "code": "2",
                    "level": "task",
                    "name": "b",
                    "estimate_basis": "y",
                    "effort_md_estimate": 2,
                },
            ],
            "dependencies": [
                {"predecessor_code": "1", "successor_code": "2"},
                {"predecessor_code": "2", "successor_code": "1"},
            ],
        }
    )
    with pytest.raises(ValidationError) as info:
        services.planning.build_plan(p, cyc, None)
    assert "순환" in info.value.cause


def test_project_model_unused_import_guard() -> None:
    assert Project is not None
