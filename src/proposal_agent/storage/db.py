"""SQLite 연결과 마이그레이션 적용.

- 표준 ``sqlite3`` 사용 (의존성 최소화, DATA_MODEL.md 6절).
- Streamlit은 요청마다 스레드가 바뀔 수 있으므로 ``check_same_thread=False`` + 잠금으로 보호한다.
- 외래 키 활성화, WAL 저널.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from proposal_agent.config.errors import StorageError
from proposal_agent.config.logging import get_logger
from proposal_agent.storage.migrations import MIGRATIONS, Migration

log = get_logger("storage.db")

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class Database:
    """단일 SQLite 파일에 대한 연결 관리자."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    # --- 연결 ----------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                if str(self.path) != ":memory:":
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    conn = sqlite3.connect(
                        str(self.path), check_same_thread=False, isolation_level=None
                    )
                except sqlite3.Error as exc:
                    raise StorageError(f"DB 연결 실패: {self.path}", cause=str(exc)) from exc
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                if str(self.path) != ":memory:":
                    conn.execute("PRAGMA journal_mode = WAL")
                self._conn = conn
            return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        return self.connect()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """재진입 가능한 트랜잭션. 바깥 트랜잭션이 있으면 그에 합류한다."""
        conn = self.connect()
        with self._lock:
            if conn.in_transaction:
                yield conn
                return
            conn.execute("BEGIN")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    # --- 마이그레이션 ------------------------------------------------------------------
    def applied_versions(self) -> list[int]:
        conn = self.connect()
        conn.execute(_MIGRATIONS_TABLE)
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return [int(r["version"]) for r in rows]

    def pending_migrations(self, migrations: tuple[Migration, ...] = MIGRATIONS) -> list[Migration]:
        applied = set(self.applied_versions())
        return [m for m in sorted(migrations, key=lambda m: m.version) if m.version not in applied]

    def migrate(self, migrations: tuple[Migration, ...] = MIGRATIONS) -> list[int]:
        """미적용 마이그레이션을 순서대로 적용하고 적용한 버전 목록을 돌려준다. 멱등."""
        applied: list[int] = []
        conn = self.connect()
        for m in self.pending_migrations(migrations):
            # executescript는 실행 전 보류 중인 트랜잭션을 커밋하므로, 스크립트 안에서 BEGIN/COMMIT을
            # 직접 감싸 스키마 변경과 버전 기록을 원자적으로 적용한다.
            name = m.name.replace("'", "''")
            script = (
                "BEGIN;\n"
                f"{m.sql}\n"
                "INSERT INTO schema_migrations(version, name, applied_at) "
                f"VALUES ({int(m.version)}, '{name}', '{datetime.now(UTC).isoformat()}');\n"
                "COMMIT;"
            )
            with self._lock:
                try:
                    conn.executescript(script)
                except sqlite3.Error as exc:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise StorageError(
                        f"마이그레이션 {m.version} ({m.name}) 적용 실패",
                        cause=str(exc),
                        resolution="DB 파일을 백업한 뒤 마이그레이션 SQL을 확인하십시오.",
                    ) from exc
            applied.append(m.version)
            log.info("migration applied: %s_%s", m.version, m.name)
        return applied

    @property
    def schema_version(self) -> int:
        versions = self.applied_versions()
        return versions[-1] if versions else 0
