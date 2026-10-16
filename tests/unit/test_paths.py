"""config.paths: 폴더 생성, 중복 식별자, 잘못된 경로 차단."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from proposal_agent.config import OUTPUT_SUBDIRS, PathSecurityError, ProjectPaths, ensure_within
from proposal_agent.config.paths import WORKSPACE_SUBDIRS, project_dir_name, safe_filename, slugify


def test_slugify_preserves_korean_and_replaces_invalid_chars() -> None:
    assert slugify("차세대 시스템: 구축/운영?") == "차세대_시스템_구축_운영"
    assert slugify("   ") == "project"
    assert slugify("CON") == "project"
    assert len(slugify("a" * 200)) == 60


def test_project_dir_name_format() -> None:
    assert project_dir_name("테스트 사업", date(2026, 10, 15)) == "Project_20261015_테스트_사업"


def test_create_project_output_dir_creates_all_subdirs(paths: ProjectPaths) -> None:
    created = paths.create_project_output_dir("사업", date(2026, 10, 15))
    assert created.name == "Project_20261015_사업"
    assert sorted(p.name for p in created.iterdir()) == sorted(OUTPUT_SUBDIRS)
    assert len(OUTPUT_SUBDIRS) == 15  # 단계 7: 14_Generated_App 추가


def test_duplicate_project_name_gets_unique_suffix(paths: ProjectPaths) -> None:
    first = paths.create_project_output_dir("사업", date(2026, 10, 15))
    second = paths.create_project_output_dir("사업", date(2026, 10, 15))
    assert first != second
    assert second.name.startswith("Project_20261015_사업_")
    assert len(second.name.rsplit("_", 1)[1]) == 6


def test_ensure_output_subdirs_preserves_existing_files(paths: ProjectPaths) -> None:
    project_dir = paths.create_project_output_dir("사업")
    keep = project_dir / "03_Requirements" / "keep.txt"
    keep.write_text("원본", encoding="utf-8")
    (project_dir / "05_Architecture_Design").rmdir()
    created = ProjectPaths.ensure_output_subdirs(project_dir)
    assert created == ["05_Architecture_Design"]
    assert keep.read_text(encoding="utf-8") == "원본"
    assert paths.missing_output_subdirs(project_dir.name) == []


def test_ensure_workspace_creates_subdirs(paths: ProjectPaths) -> None:
    ws = paths.ensure_workspace("prj_x")
    assert ws == paths.workspace_root / "prj_x"
    for sub in WORKSPACE_SUBDIRS:
        assert (ws / sub).is_dir()


@pytest.mark.parametrize("bad", ["../escape", "../../etc/passwd", "sub/../../x"])
def test_ensure_within_blocks_parent_traversal(tmp_path: Path, bad: str) -> None:
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(PathSecurityError):
        ensure_within(base, base / bad)


def test_ensure_within_blocks_absolute_outside(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside" / "file.txt"
    with pytest.raises(PathSecurityError):
        ensure_within(base, outside)


def test_ensure_within_allows_inside(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    assert ensure_within(base, Path("a/b.txt")) == (base / "a" / "b.txt").resolve()


def test_ensure_within_blocks_symlink_escape(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = base / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # Windows: 개발자 모드/권한 없으면 생성 불가
        pytest.skip(f"심볼릭 링크를 만들 수 없는 환경: {exc}")
    with pytest.raises(PathSecurityError):
        ensure_within(base, link / "x.txt")


def test_project_output_dir_rejects_escape(paths: ProjectPaths) -> None:
    with pytest.raises(PathSecurityError):
        paths.project_output_dir("../outside")
    with pytest.raises(PathSecurityError):
        paths.resolve_output("../x")


def test_subdir_rejects_unknown_name(paths: ProjectPaths) -> None:
    with pytest.raises(ValueError):
        paths.subdir("Project_x", "99_Unknown")


def test_safe_filename_strips_directories() -> None:
    assert safe_filename("../../evil.pdf") == "evil.pdf"
    assert safe_filename("C:\\temp\\제안요청서 v1.pdf") == "제안요청서_v1.pdf"
    assert safe_filename("a?b*c.xlsx") == "a_b_c.xlsx"
