"""Phase 21: PowerPoint COM 실제 렌더링·재열기(없으면 skip=미실행), QA-EDIT-01~10 편집 가능성 체크리스트,
QA-FILE-13 페이지 제한, 범주 선택 실행(미선택 범주는 미실행)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from proposal_agent.config import ProjectPaths
from proposal_agent.generators.base import GenerationContext
from proposal_agent.generators.pptx.builder import DeckBuilder
from proposal_agent.generators.pptx.decks import build_presentation_deck, build_submission_deck
from proposal_agent.generators.pptx.outline import decide_outline
from proposal_agent.models import (
    AcceptanceStatus,
    DeliverableKind,
    Project,
    ProjectMode,
    QaCategory,
    QaResult,
    Requirement,
    RequirementType,
)
from proposal_agent.validation.independent_qa import (
    CheckArtifacts,
    _page_limit_issues,
    check_editability,
)
from proposal_agent.validation.qa_service import QaService
from proposal_agent.validation.render import com_available, render_pptx


def _small_deck() -> bytes:
    b = DeckBuilder()
    b.title_slide("렌더링 테스트", "부제", "")
    b.bullet_slides("본문", ["첫째 줄", "둘째 줄"], "footer")
    b.table_slides("표", ("A", "B"), [["1", "2"]], "footer")
    return b.to_bytes()


def test_render_pptx_exports_png_and_reopens(tmp_path: Path) -> None:
    ok, why = com_available()
    if not ok:
        pytest.skip(f"PowerPoint COM 없음 — 렌더링 검증 미실행 ({why})")
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(_small_deck())
    res = render_pptx(deck, tmp_path / "render")
    assert res.available and res.engine == "PowerPoint COM"
    assert res.ok, res.errors
    assert res.slides_pptx == 3 and res.slides_rendered == 3 and res.reopened
    assert all(Path(p).exists() and Path(p).stat().st_size > 0 for p in res.png_paths)
    with Image.open(res.png_paths[0]) as im:
        assert im.size[0] == 1280
    assert "성공" in res.summary


def test_render_result_without_engine_is_not_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import proposal_agent.validation.render as mod

    monkeypatch.setattr(mod, "com_available", lambda: (False, "테스트: 엔진 없음"))
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(_small_deck())
    res = mod.render_pptx(deck, tmp_path / "r")
    assert not res.available and not res.ok and res.errors == ["테스트: 엔진 없음"]
    assert "엔진 없음" in res.summary


def _project() -> Project:
    return Project(
        name="편집성",
        mode=ProjectMode.PROPOSAL,
        output_dir="Project_e",
        workspace_dir="ws_e",
        start_date=date(2026, 11, 2),
        end_date=date(2027, 4, 30),
        created_by="t",
    )


def _inputs(tmp_path: Path, *, with_photo: bool, page_limit: int | None = None) -> Any:
    p = _project()
    paths = ProjectPaths(root=tmp_path)
    out_dir = tmp_path / "Output" / p.output_dir
    (out_dir / "07_Submission_Proposal_PPT").mkdir(parents=True)
    (out_dir / "08_Presentation_PPT").mkdir(parents=True)
    pictures: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = [
        {"slide_group": "understanding", "title": "사업 이해", "bullets": ["배경", "목적"]}
    ]
    if with_photo:
        img = tmp_path / "photo__현장.png"
        Image.new("RGB", (120, 60), (90, 90, 90)).save(img)
        pictures.append(
            {"file_name": img.name, "path": str(img), "tag": "photo", "caption": "현장"}
        )
        sections[0]["picture"] = "현장"
    ctx = GenerationContext(
        project=p,
        requirements=[
            Requirement(
                id="FR-001",
                project_id=p.id,
                name="사건 접수",
                description="사건을 접수한다",
                type=RequirementType.FUNCTIONAL,
                created_by="t",
                acceptance_status=AcceptanceStatus.ACCEPTED,
                implementation_approach="웹 화면",
            )
        ],
        proposal_content={"profile": "submission", "sections": sections},
        period_start=date(2026, 11, 2),
        period_end=date(2027, 4, 30),
        pictures=pictures,
    )
    outline = decide_outline(ctx, [])
    sub = out_dir / "07_Submission_Proposal_PPT" / "제안서_제출용_v1.0.pptx"
    pres = out_dir / "08_Presentation_PPT" / "제안서_발표용_v1.0.pptx"
    sub.write_bytes(build_submission_deck(ctx, outline))
    pres.write_bytes(build_presentation_deck(ctx, outline))
    rel = lambda path: paths.relative_output(path)  # noqa: E731
    return SimpleNamespace(
        project=p,
        mode=ProjectMode.PROPOSAL,
        paths=paths,
        deliverables={
            DeliverableKind.SUBMISSION_PPTX: SimpleNamespace(file_path=rel(sub)),
            DeliverableKind.PRESENTATION_PPTX: SimpleNamespace(file_path=rel(pres)),
        },
        template_profiles={},
        page_limit=page_limit,
        render_check=False,
        render_dir=None,
    )


def test_editability_checklist_on_generated_decks(tmp_path: Path) -> None:
    inp = _inputs(tmp_path, with_photo=True)
    checks = check_editability(inp, CheckArtifacts())
    assert [c.check_id for c in checks] == [f"QA-EDIT-{i:02d}" for i in range(1, 11)]
    assert all(
        c.executed and c.category == QaCategory.EDITABILITY and c.gate == "gate4" for c in checks
    )
    by_id = {c.check_id: c for c in checks}
    for cid in ("QA-EDIT-01", "QA-EDIT-02", "QA-EDIT-04", "QA-EDIT-06", "QA-EDIT-10"):
        assert by_id[cid].mandatory and by_id[cid].result == QaResult.PASS, (cid, by_id[cid].issues)
    assert any(x.startswith("예외:") and "photo:" in x for x in by_id["QA-EDIT-06"].issues)
    assert by_id["QA-EDIT-09"].result == QaResult.PASS
    assert all(c.files for c in checks)
    # 구축 단계는 전부 미실행
    inp.mode = ProjectMode.BUILD
    build_checks = check_editability(inp, CheckArtifacts())
    assert all(not c.executed and not c.applicable for c in build_checks)


def test_page_limit_check(tmp_path: Path) -> None:
    inp = _inputs(tmp_path, with_photo=False, page_limit=2)
    fails, revs = _page_limit_issues(inp, CheckArtifacts())
    assert fails and "초과" in fails[0] and "제한 2쪽" in fails[0]
    inp.page_limit = 500
    assert _page_limit_issues(inp, CheckArtifacts()) == ([], [])


def test_category_filter_marks_unselected_as_not_run() -> None:
    from proposal_agent.validation.independent_qa import _check

    checks = [
        _check("QA-RFP-01", QaCategory.RFP_FIT, "a", "b", gate="gate5"),
        _check("QA-EDIT-01", QaCategory.EDITABILITY, "c", "d", gate="gate4"),
    ]
    for c in checks:
        c.result = QaResult.PASS
    out = QaService._apply_category_filter(checks, {QaCategory.EDITABILITY})
    rfp, edit = out
    assert not rfp.executed and rfp.applicable and "범주 선택" in rfp.not_run_reason
    assert edit.executed and edit.result == QaResult.PASS
    assert QaService._apply_category_filter(checks, None) is checks
