"""파일 저장소: Output 폴더 내 저장, 덮어쓰기 금지, 중복 파일명 처리, 해시.

규칙 (ARCHITECTURE.md 4절):
- 같은 경로에 파일이 있으면 저장하지 않고 ``FileExistsConflict``를 던진다.
- 업로드 원본 보관은 ``store_unique``로 이름 뒤에 ``_1``, ``_2`` … 를 붙여 보존한다.
- 모든 대상 경로는 프로젝트 산출물 폴더 내부여야 한다 (``ensure_within``).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from proposal_agent.config.errors import FileExistsConflict, StorageError
from proposal_agent.config.paths import ProjectPaths, ensure_within, safe_filename

_VERSION_RE = re.compile(r"^(?P<stem>.+)_v(?P<major>\d+)\.(?P<minor>\d+)$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def versioned_name(stem: str, version: str, suffix: str) -> str:
    """``요구사항정의서`` + ``v1.0`` + ``.xlsx`` → ``요구사항정의서_v1.0.xlsx``."""
    if not version.startswith("v"):
        version = f"v{version}"
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    return f"{stem}_{version}{suffix}"


def parse_version(file_name: str) -> tuple[str, int, int] | None:
    """``stem_v1.2.ext`` → ``("stem", 1, 2)``. 형식이 아니면 None."""
    m = _VERSION_RE.match(Path(file_name).stem)
    if not m:
        return None
    return m.group("stem"), int(m.group("major")), int(m.group("minor"))


def next_minor_version(version: str) -> str:
    major, minor = version.lstrip("v").split(".")
    return f"v{major}.{int(minor) + 1}"


@dataclass(frozen=True)
class StoredFile:
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int


class FileStore:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def _target(self, output_dir_name: str, subdir: str, file_name: str) -> Path:
        base = self.paths.subdir(output_dir_name, subdir)
        return ensure_within(base, base / safe_filename(file_name))

    def save_bytes(
        self, output_dir_name: str, subdir: str, file_name: str, data: bytes
    ) -> StoredFile:
        """정확한 이름으로 저장. 이미 있으면 ``FileExistsConflict``."""
        target = self._target(output_dir_name, subdir, file_name)
        if target.exists():
            raise FileExistsConflict(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as f:  # 'x': 경쟁 상태에서도 덮어쓰기 방지
                f.write(data)
        except FileExistsError as exc:
            raise FileExistsConflict(target) from exc
        except OSError as exc:
            raise StorageError(f"파일 저장 실패: {target}", cause=str(exc)) from exc
        return StoredFile(target, self.paths.relative_output(target), sha256_bytes(data), len(data))

    def store_unique(
        self, output_dir_name: str, subdir: str, file_name: str, data: bytes
    ) -> StoredFile:
        """같은 이름이 있으면 ``name_1.ext``, ``name_2.ext`` … 로 저장한다 (원본 보존)."""
        target = self._target(output_dir_name, subdir, file_name)
        candidate = target
        n = 0
        while candidate.exists():
            n += 1
            candidate = target.with_name(f"{target.stem}_{n}{target.suffix}")
            if n > 1000:
                raise StorageError(f"중복 파일명이 너무 많습니다: {target.name}")
        return self.save_bytes(output_dir_name, subdir, candidate.name, data)

    def exists(self, output_dir_name: str, subdir: str, file_name: str) -> bool:
        return self._target(output_dir_name, subdir, file_name).exists()

    def latest_version(
        self, output_dir_name: str, subdir: str, stem: str, suffix: str
    ) -> str | None:
        """폴더 안에서 ``stem_vX.Y<suffix>`` 중 가장 높은 버전 문자열."""
        folder = self.paths.subdir(output_dir_name, subdir)
        if not folder.exists():
            return None
        best: tuple[int, int] | None = None
        for p in folder.iterdir():
            if p.suffix != suffix:
                continue
            parsed = parse_version(p.name)
            if parsed and parsed[0] == stem and (best is None or parsed[1:] > best):
                best = (parsed[1], parsed[2])
        return f"v{best[0]}.{best[1]}" if best else None

    def next_version_name(self, output_dir_name: str, subdir: str, stem: str, suffix: str) -> str:
        """존재하는 최신 버전의 다음 minor 버전 파일명. 없으면 ``v1.0``."""
        latest = self.latest_version(output_dir_name, subdir, stem, suffix)
        version = next_minor_version(latest) if latest else "v1.0"
        return versioned_name(stem, version, suffix)
