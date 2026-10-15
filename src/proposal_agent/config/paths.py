"""경로 중앙 관리.

모든 경로는 이 모듈의 ``ProjectPaths``(pathlib 기반)에서만 생성한다 (ARCHITECTURE.md 1절 6항).
프로젝트 루트 밖을 가리키는 경로, 심볼릭 링크를 통한 탈출, ``..`` 조작은 ``ensure_within``이 거부한다.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from proposal_agent.config.errors import PathSecurityError

# ARCHITECTURE.md 4절 — 산출물 폴더 규칙 (단일 정의)
OUTPUT_SUBDIRS: tuple[str, ...] = (
    "00_Project_Summary",
    "01_RFP_Original",
    "02_RFP_Analysis",
    "03_Requirements",
    "04_Technology_Research",
    "05_Architecture_Design",
    "06_WBS_Effort_Schedule",
    "07_Submission_Proposal_PPT",
    "08_Presentation_PPT",
    "09_Excel_Deliverables",
    "10_Diagrams_Charts_Images",
    "11_QA_Validation_Reports",
    "12_Revision_History",
    "13_Final_Deliverables",
)

# 프로젝트 workspace 하위 폴더 (임시 파일)
WORKSPACE_SUBDIRS: tuple[str, ...] = ("uploads", "chunks", "tmp")

PROJECT_DIR_PREFIX = "Project"
SHORT_ID_LENGTH = 6
MAX_SLUG_LENGTH = 60

# 파일명으로 쓸 수 없는 문자(Windows 예약 문자 포함)와 공백 → "_"
_INVALID_CHARS = re.compile(r"[\\/:*?\"<>|\s\x00-\x1f]+")
_MULTI_UNDERSCORE = re.compile(r"_{2,}")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}  # fmt: skip


def repo_root() -> Path:
    """패키지 위치에서 역산한 저장소 루트 (src/proposal_agent/config/paths.py 기준)."""
    return Path(__file__).resolve().parents[3]


def slugify(name: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    """프로젝트명을 폴더명 조각으로 변환. 한글·영숫자는 보존하고 공백·금지 문자는 ``_``."""
    slug = _INVALID_CHARS.sub("_", name.strip())
    slug = _MULTI_UNDERSCORE.sub("_", slug).strip("_.")
    if not slug or slug.upper() in _WINDOWS_RESERVED:
        slug = "project"
    return slug[:max_length].rstrip("_.") or "project"


def safe_filename(name: str, max_length: int = 120) -> str:
    """업로드 파일명을 저장용으로 정규화. 디렉터리 구성 요소는 제거한다."""
    base = Path(name).name  # 경로 조작 제거 (../, 절대 경로)
    stem, suffix = Path(base).stem, Path(base).suffix
    stem = slugify(stem, max_length=max_length)
    suffix = _INVALID_CHARS.sub("", suffix)[:16]
    return f"{stem}{suffix}"


def project_dir_name(name: str, on: date | None = None) -> str:
    """``Project_YYYYMMDD_<slug>`` 형식 폴더명 (중복 식별자 없음)."""
    on = on or date.today()
    return f"{PROJECT_DIR_PREFIX}_{on.strftime('%Y%m%d')}_{slugify(name)}"


def short_id(length: int = SHORT_ID_LENGTH) -> str:
    """중복 폴더 식별자용 소문자 16진수 문자열."""
    return secrets.token_hex((length + 1) // 2)[:length]


def ensure_within(base: Path, target: Path) -> Path:
    """``target``이 ``base`` 안에 있음을 보장하고 정규화된 절대 경로를 돌려준다.

    - ``..``·절대 경로 조작: ``resolve()`` 후 공통 경로 비교로 차단
    - 심볼릭 링크: 존재하는 가장 가까운 조상까지 실제 경로를 따라가 비교하므로,
      링크가 base 밖을 가리키면 거부된다.
    """
    base_r = base.resolve()
    target_r = (target if target.is_absolute() else base_r / target).resolve()
    try:
        common = os.path.commonpath([str(base_r), str(target_r)])
    except ValueError:  # 드라이브가 다름 (Windows)
        common = ""
    if Path(common) != base_r:
        raise PathSecurityError(
            f"허용 범위 밖 경로: {target}",
            cause=f"기준 폴더 {base_r} 밖을 가리킴 (해석 결과 {target_r})",
            resolution="프로젝트 폴더 내부의 상대 경로만 사용하십시오.",
            detail={"base": str(base_r), "target": str(target_r)},
        )
    return target_r


@dataclass(frozen=True)
class ProjectPaths:
    """프로젝트 수준 경로 집합.

    - ``root``: 저장소(또는 설치) 루트
    - ``output_root``: 업무 산출물 루트 (기본 ``<root>/Output``)
    - ``workspace_root``: 임시 파일 루트 (기본 ``<root>/workspace``)
    - ``db_path``: SQLite 파일 (기본 ``<workspace_root>/pwa.sqlite3``)
    """

    root: Path
    output_root: Path
    workspace_root: Path
    db_path: Path

    def __init__(
        self,
        root: Path | str | None = None,
        output_root: Path | str | None = None,
        workspace_root: Path | str | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        root_path = Path(root) if root is not None else repo_root()
        out = Path(output_root) if output_root is not None else root_path / "Output"
        ws = Path(workspace_root) if workspace_root is not None else root_path / "workspace"
        db = Path(db_path) if db_path is not None else ws / "pwa.sqlite3"
        object.__setattr__(self, "root", root_path)
        object.__setattr__(self, "output_root", out)
        object.__setattr__(self, "workspace_root", ws)
        object.__setattr__(self, "db_path", db)

    # --- 루트 수준 -----------------------------------------------------------------
    @property
    def logs_dir(self) -> Path:
        return self.workspace_root / "logs"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "app.log"

    def ensure_roots(self) -> None:
        """루트 폴더들을 생성한다. 이미 있으면 그대로 둔다."""
        for p in (self.output_root, self.workspace_root, self.logs_dir, self.db_path.parent):
            p.mkdir(parents=True, exist_ok=True)

    # --- 프로젝트 수준 -------------------------------------------------------------
    def workspace_for(self, project_id: str) -> Path:
        return self.workspace_root / project_id

    def ensure_workspace(self, project_id: str) -> Path:
        ws = self.workspace_for(project_id)
        ws.mkdir(parents=True, exist_ok=True)
        for sub in WORKSPACE_SUBDIRS:
            (ws / sub).mkdir(exist_ok=True)
        return ws

    def project_output_dir(self, output_dir_name: str) -> Path:
        """``Project.output_dir``(Output 기준 상대 폴더명)를 절대 경로로."""
        return ensure_within(self.output_root, self.output_root / output_dir_name)

    def subdir(self, output_dir_name: str, subdir: str) -> Path:
        if subdir not in OUTPUT_SUBDIRS:
            raise ValueError(f"알 수 없는 산출물 하위 폴더: {subdir}")
        return self.project_output_dir(output_dir_name) / subdir

    def allocate_project_dir_name(self, project_name: str, on: date | None = None) -> str:
        """중복되지 않는 프로젝트 폴더명을 결정한다.

        동일 이름 폴더가 이미 있으면 ``_<6자리 short id>``를 덧붙인다 (ARCHITECTURE.md 4절).
        """
        base = project_dir_name(project_name, on)
        candidate = base
        while (self.output_root / candidate).exists():
            candidate = f"{base}_{short_id()}"
        return candidate

    def create_project_output_dir(self, project_name: str, on: date | None = None) -> Path:
        """프로젝트 산출물 폴더와 하위 폴더 14종을 생성하고 절대 경로를 돌려준다."""
        self.output_root.mkdir(parents=True, exist_ok=True)
        name = self.allocate_project_dir_name(project_name, on)
        path = self.output_root / name
        path.mkdir(parents=True, exist_ok=False)
        self.ensure_output_subdirs(path)
        return path

    @staticmethod
    def ensure_output_subdirs(project_dir: Path) -> list[str]:
        """누락된 하위 폴더만 생성하고 생성한 이름 목록을 돌려준다. 기존 파일은 건드리지 않는다."""
        created: list[str] = []
        for sub in OUTPUT_SUBDIRS:
            p = project_dir / sub
            if not p.exists():
                p.mkdir()
                created.append(sub)
        return created

    def missing_output_subdirs(self, output_dir_name: str) -> list[str]:
        base = self.project_output_dir(output_dir_name)
        return [s for s in OUTPUT_SUBDIRS if not (base / s).is_dir()]

    def relative_output(self, path: Path | str) -> str:
        """Output 루트 기준 상대 경로 문자열 (DB 저장용, POSIX 구분자). 범위 밖이면 오류."""
        resolved = ensure_within(self.output_root, Path(path))
        return resolved.relative_to(self.output_root.resolve()).as_posix()

    def resolve_output(self, relative: str) -> Path:
        """DB에 저장된 상대 경로를 절대 경로로. 범위 밖이면 오류."""
        return ensure_within(self.output_root, self.output_root / relative)

    def resolve_in_project(self, output_dir_name: str, relative: str | Path) -> Path:
        """프로젝트 산출물 폴더 기준 상대 경로를 검증된 절대 경로로."""
        base = self.project_output_dir(output_dir_name)
        return ensure_within(base, base / relative)
