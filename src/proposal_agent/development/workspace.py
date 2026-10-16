"""생성 앱 작업 폴더 (RFP_JAVA file_manager 발췌): 경로 탈출·링크·예약 이름 거부, 허용 확장자·크기 제한, 원자적 쓰기, 스냅샷·복원."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from proposal_agent.config.errors import PathSecurityError
from proposal_agent.development.constants import (
    GENERATED_EXTENSIONS,
    MAX_GENERATED_FILE_BYTES,
    is_generated_path,
)

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
SKIP_DIRS = frozenset({"target", ".git", ".idea", "node_modules", "data", "test_results"})


def is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or (path.exists() and path.is_junction())
    except OSError:
        return True


def safe_join(base: Path, relative: str | Path) -> Path:
    rel = str(relative)
    if not rel.strip() or "\x00" in rel:
        raise PathSecurityError("빈 경로나 NUL 문자가 포함된 경로는 허용되지 않습니다.")
    win = PureWindowsPath(rel)
    posix = PurePosixPath(rel.replace("\\", "/"))
    if win.drive or win.root or posix.is_absolute():
        raise PathSecurityError(f"절대 경로는 허용되지 않습니다: {rel!r}")
    parts = [p for p in posix.parts if p != "."]
    if not parts:
        raise PathSecurityError(f"파일 경로가 아닙니다: {rel!r}")
    for part in parts:
        if part == "..":
            raise PathSecurityError(f"상위 디렉터리 참조(..)는 허용되지 않습니다: {rel!r}")
        if ":" in part:
            raise PathSecurityError(f"':' 가 포함된 경로는 허용되지 않습니다: {rel!r}")
        if part.split(".")[0].upper() in _WINDOWS_RESERVED:
            raise PathSecurityError(f"Windows 예약 이름은 사용할 수 없습니다: {part!r}")
    if is_link(base):
        raise PathSecurityError("작업 폴더가 심볼릭 링크입니다.")
    base_resolved = base.resolve(strict=True)
    current = base_resolved
    for part in parts:
        current = current / part
        if is_link(current):
            raise PathSecurityError(f"심볼릭 링크를 통한 접근은 허용되지 않습니다: {rel!r}")
    resolved = current.resolve()
    if not resolved.is_relative_to(base_resolved):
        raise PathSecurityError(f"작업 폴더 밖의 경로입니다: {rel!r}")
    return resolved


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        for attempt in range(1, 7):
            try:
                Path(tmp_name).replace(path)
                break
            except PermissionError:
                if attempt == 6:
                    raise
                time.sleep(0.05 * attempt)
    except OSError:
        Path(tmp_name).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class WriteResult:
    path: str
    change_type: str  # CREATED | MODIFIED | UNCHANGED
    lines_added: int
    lines_removed: int
    size_bytes: int
    sha256: str


class GeneratedWorkspace:
    """프로젝트의 ``14_Generated_App`` 폴더. 쓰기는 허용 확장자·크기·경로 규칙을 통과한 파일만."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str) -> Path:
        return safe_join(self.root, relative)

    def write(
        self,
        relative: str,
        content: str,
        *,
        allow_new: bool = True,
        allowed: set[str] | None = None,
    ) -> WriteResult:
        rel = relative.replace("\\", "/")
        if not is_generated_path(rel):
            raise PathSecurityError(
                f"생성 앱에 둘 수 없는 경로·형식입니다: {rel} (허용 확장자 {', '.join(GENERATED_EXTENSIONS)})"
            )
        if allowed is not None and rel not in allowed:
            raise PathSecurityError(
                f"이번 배치에서 쓸 수 없는 파일입니다: {rel} (허용: {', '.join(sorted(allowed))})"
            )
        data = content.encode("utf-8")
        if len(data) > MAX_GENERATED_FILE_BYTES:
            raise PathSecurityError(
                f"파일이 너무 큽니다 ({MAX_GENERATED_FILE_BYTES:,} bytes 초과): {rel}"
            )
        target = self.resolve(rel)
        old = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
        if old is None and not allow_new:
            raise PathSecurityError(f"기존 파일만 수정할 수 있습니다 (새 파일 생성 불가): {rel}")
        if old == content:
            return WriteResult(rel, "UNCHANGED", 0, 0, len(data), hashlib.sha256(data).hexdigest())
        atomic_write_bytes(target, data)
        added, removed = _diff_counts(old or "", content)
        return WriteResult(
            rel,
            "CREATED" if old is None else "MODIFIED",
            added,
            removed,
            len(data),
            hashlib.sha256(data).hexdigest(),
        )

    def read(self, relative: str) -> str | None:
        target = self.resolve(relative)
        return target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None

    def snapshot(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if not self.root.exists():
            return out
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dp = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not is_link(dp / d)]
            for name in filenames:
                p = dp / name
                if is_link(p) or not name.endswith(GENERATED_EXTENSIONS) or name.startswith("."):
                    continue
                rel = p.relative_to(self.root).as_posix()
                if p.stat().st_size <= MAX_GENERATED_FILE_BYTES:
                    out[rel] = p.read_text(encoding="utf-8", errors="replace")
        return out

    def restore(self, snapshot: dict[str, str]) -> list[str]:
        """스냅샷에 없는 파일은 지우고 있는 파일은 되돌린다 (배치 실패 시 롤백)."""
        changed: list[str] = []
        current = self.snapshot()
        for rel in current:
            if rel not in snapshot:
                self.resolve(rel).unlink(missing_ok=True)
                changed.append(rel)
        for rel, content in snapshot.items():
            if current.get(rel) != content:
                atomic_write_bytes(self.resolve(rel), content.encode("utf-8"))
                changed.append(rel)
        return sorted(set(changed))


def _diff_counts(old: str, new: str) -> tuple[int, int]:
    import difflib

    added = removed = 0
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


__all__ = ["GeneratedWorkspace", "WriteResult", "atomic_write_bytes", "safe_join"]
