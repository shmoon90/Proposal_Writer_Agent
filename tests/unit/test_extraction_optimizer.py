"""추출·검증 최적화: 신호 없는 청크 건너뛰기, 청크 캐시, 검증 창 병합, 호출 수·누적 예산 상한, 프롬프트 압축."""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures import builders as bld
from proposal_agent.agents import FakeAgentRunner
from proposal_agent.config import ProjectPaths, Settings, ValidationError
from proposal_agent.ingest.chunker import Chunk, build_chunks
from proposal_agent.models import (
    BlockType,
    DocumentKind,
    ExtractedBlock,
    FileFormat,
    Project,
    ProjectMode,
)
from proposal_agent.orchestrator import StepRunner
from proposal_agent.requirements.optimizer import (
    ChunkCache,
    RunPlan,
    build_windows,
    chunk_key,
    compact_items,
    has_signal,
)
from proposal_agent.services import AppContext, Services
from unit.test_requirements_phase2 import extractor_from_text, verifier_all_ok


def _block(i: int, text: str, kind: BlockType = BlockType.PARAGRAPH) -> ExtractedBlock:
    return ExtractedBlock(
        project_id="p",
        source_document_id="d",
        file_name="rfp.docx",
        file_format=FileFormat.DOCX,
        order=i,
        block_type=kind,
        text=text,
    )


def test_has_signal_skips_headings_and_short_or_plain_text() -> None:
    blocks = [
        _block(1, "제1장 사업 개요", BlockType.HEADING),
        _block(2, "안녕하세요. 이 문서는 참고용입니다. " * 10),
        _block(3, "시스템은 3초 이내에 응답하여야 한다. " * 10),
        _block(4, "| 항목 | 값 |", BlockType.TABLE),
    ]
    by_id = {b.id: b for b in blocks}
    heading_only = Chunk(
        index=0,
        block_ids=[blocks[0].id],
        text=f'<block id="{blocks[0].id}">제1장 사업 개요</block>',
    )
    assert not has_signal(heading_only, by_id)
    plain = Chunk(index=1, block_ids=[blocks[1].id], text=blocks[1].text)
    assert not has_signal(plain, by_id)
    req = Chunk(index=2, block_ids=[blocks[2].id], text=blocks[2].text)
    assert has_signal(req, by_id)
    table = Chunk(index=3, block_ids=[blocks[3].id], text=blocks[3].text)
    assert has_signal(table, by_id)


def test_build_windows_merges_chunks_without_splitting_blocks() -> None:
    blocks = [_block(i, f"요구사항 {i}: 시스템은 기능을 제공하여야 한다. " * 20) for i in range(8)]
    chunks = build_chunks(blocks, 1200)
    assert len(chunks) >= 4
    windows = build_windows(chunks, 1200 * 3)
    assert 1 < len(windows) < len(chunks)
    assert [b for w in windows for b in w.block_ids] == [b for c in chunks for b in c.block_ids]
    assert all(w.index == i for i, w in enumerate(windows))


def test_chunk_cache_roundtrip_and_key_sensitivity(tmp_path: Path) -> None:
    cache = ChunkCache(tmp_path / "cache")
    k1 = chunk_key("requirement_extractor", "sys", "text A", "model")
    k2 = chunk_key("requirement_extractor", "sys", "text B", "model")
    k3 = chunk_key("requirement_verifier", "sys", "text A", "model")
    assert len({k1, k2, k3}) == 3
    assert cache.get(k1) is None
    cache.put(k1, {"requirements": []}, cost_usd=0.5, turns=2)
    assert cache.get(k1) == {"output": {"requirements": []}, "cost_usd": 0.5, "turns": 2}
    assert ChunkCache(tmp_path / "x", enabled=False).get(k1) is None


def test_compact_items_truncates_and_drops_fields() -> None:
    from proposal_agent.models import Requirement, RequirementType

    r = Requirement(
        id="FR-001",
        project_id="p",
        name="n",
        description="가" * 1000,
        type=RequirementType.FUNCTIONAL,
        rfp_quote="나" * 500,
        rationale="근거",
    )
    full = compact_items([r], with_sources=True)[0]
    assert (
        len(full["description"]) == 400
        and len(full["rfp_quote"]) == 200
        and "rationale" not in full
    )
    short = compact_items([r], with_sources=False)[0]
    assert "rfp_quote" not in short and "source_block_ids" not in short


def test_run_plan_limits() -> None:
    plan = RunPlan(
        kind="extract",
        chunks_total=5,
        to_call=[0, 1, 2],
        max_cost_per_call=2.0,
        max_calls=2,
        project_cost_so_far=1.0,
        project_budget=10.0,
    )
    assert (
        plan.calls == 3
        and plan.est_max_cost == 6.0
        and plan.over_call_limit
        and not plan.over_budget
    )
    with pytest.raises(ValidationError, match="호출 수가 상한"):
        plan.require_within_limits()
    plan.max_calls = 0
    plan.project_budget = 5.0
    assert plan.over_budget
    with pytest.raises(ValidationError, match="누적 비용 상한"):
        plan.require_within_limits()
    assert "호출 3개" in plan.summary()


@pytest.fixture
def opt_ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    ctx = AppContext.create(Settings(), paths=ProjectPaths(root=tmp_path), configure_logging=False)
    yield ctx
    ctx.close()


def _ready(ctx: AppContext, runner: FakeAgentRunner) -> tuple[Services, Project]:
    s = Services.from_context(ctx, runner=runner)
    p = s.projects.create(name="최적화", mode=ProjectMode.PROPOSAL)
    s.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name="rfp.docx", data=bld.build_docx()
    )
    StepRunner(s).run_extraction(p)
    return s, p


def test_extraction_skips_low_signal_and_reuses_cache(opt_ctx: AppContext) -> None:
    runner = FakeAgentRunner(
        {"requirement_extractor": extractor_from_text, "requirement_verifier": verifier_all_ok}
    )
    s, p = _ready(opt_ctx, runner)
    plan = s.requirements.plan_extraction(p)
    assert plan.calls >= 1 and plan.calls == len(plan.to_call) and not plan.cached
    first = s.requirements.extract(p)
    calls_after_first = len(runner.calls)
    assert first.calls == calls_after_first == plan.calls
    assert first.chunks == plan.chunks_total and first.skipped_chunks == len(plan.skipped)
    assert len(first.created) == 11
    # 재실행: 같은 청크는 캐시에서 → 에이전트 호출 0, ID 유지
    plan2 = s.requirements.plan_extraction(p)
    assert len(plan2.cached) == plan.calls and plan2.calls == 0 and plan2.est_max_cost == 0
    second = s.requirements.extract(p)
    assert (
        len(runner.calls) == calls_after_first
        and second.cached_chunks == plan.calls
        and second.calls == 0
    )
    assert sorted(r.id for r in s.requirements.list_requirements(p)) == sorted(
        r.id for r in first.created
    )
    assert second.cost_usd == 0


def test_verification_uses_fewer_windows_and_compact_prompt(opt_ctx: AppContext) -> None:
    runner = FakeAgentRunner(
        {"requirement_extractor": extractor_from_text, "requirement_verifier": verifier_all_ok}
    )
    opt_ctx.settings.extraction_chunk_chars = 2500
    opt_ctx.settings.verification_chunk_chars = 10000
    s, p = _ready(opt_ctx, runner)
    s.requirements.extract(p)
    ext_calls = len(runner.calls)
    plan = s.requirements.plan_verification(p)
    assert plan.chunks_total < s.requirements.plan_extraction(p).chunks_total
    v = s.requirements.verify(p)
    verify_calls = [c for c in runner.calls[ext_calls:] if c.role == "requirement_verifier"]
    assert v.calls == len(verify_calls) == plan.calls
    assert v.verdicts == 11 and v.coverage == 1.0
    prompt = verify_calls[0].prompt
    assert '"rationale"' not in prompt and "모드: chunk" in prompt and '"id": "' in prompt
    assert verify_calls[0].max_turns == 8  # 역할 상한 (settings.max_turns_default=30 아님)


def test_call_limit_blocks_before_any_agent_call(opt_ctx: AppContext) -> None:
    runner = FakeAgentRunner({"requirement_extractor": extractor_from_text})
    opt_ctx.settings.extraction_chunk_chars = 1500
    opt_ctx.settings.max_agent_calls_per_step = 2
    s, p = _ready(opt_ctx, runner)
    plan = s.requirements.plan_extraction(p)
    assert plan.over_call_limit
    with pytest.raises(ValidationError, match="호출 수가 상한"):
        s.requirements.extract(p)
    assert runner.calls == [] and s.requirements.list_requirements(p) == []


def test_project_budget_cap_blocks(opt_ctx: AppContext) -> None:
    runner = FakeAgentRunner({"requirement_extractor": extractor_from_text}, cost_per_call=0.4)
    opt_ctx.settings.max_budget_usd_per_project = 0.5
    s, p = _ready(opt_ctx, runner)
    plan = s.requirements.plan_extraction(p)
    assert plan.over_budget  # 최대 비용 추정(호출 수 × 역할 상한)이 상한 초과
    with pytest.raises(ValidationError, match="누적 비용 상한"):
        s.requirements.extract(p)
    assert runner.calls == []
    # 상한 0 = 무제한
    opt_ctx.settings.max_budget_usd_per_project = 0
    assert not s.requirements.plan_extraction(p).over_budget
    s.requirements.extract(p)
    assert len(runner.calls) >= 1


def test_skip_low_signal_can_be_disabled(opt_ctx: AppContext) -> None:
    runner = FakeAgentRunner({"requirement_extractor": extractor_from_text})
    s, p = _ready(opt_ctx, runner)
    with_skip = s.requirements.plan_extraction(p)
    opt_ctx.settings.skip_low_signal_chunks = False
    without = s.requirements.plan_extraction(p)
    assert without.skipped == [] and without.calls >= with_skip.calls
