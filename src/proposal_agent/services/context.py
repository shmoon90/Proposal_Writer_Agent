"""애플리케이션 컨텍스트: 설정·경로·DB·리포지토리·파일 저장소를 한 번에 조립한다.

UI는 ``AppContext``만 받아 서비스 객체를 얻고, 리포지토리에 직접 접근하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from proposal_agent.config.logging import get_logger, setup_logging
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings, load_settings
from proposal_agent.storage.db import Database
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

log = get_logger("services.context")


@dataclass
class AppContext:
    settings: Settings
    paths: ProjectPaths
    db: Database
    repos: Repositories = field(init=False)
    files: FileStore = field(init=False)

    def __post_init__(self) -> None:
        self.repos = Repositories(self.db)
        self.files = FileStore(self.paths)

    @classmethod
    def create(
        cls,
        settings: Settings | None = None,
        *,
        paths: ProjectPaths | None = None,
        env_file: Path | str | None = None,
        configure_logging: bool = True,
    ) -> AppContext:
        """설정 로드 → 루트 폴더 생성 → 로깅 → DB 마이그레이션 순으로 초기화한다."""
        settings = settings or load_settings(env_file)
        paths = paths or settings.paths()
        paths.ensure_roots()
        if configure_logging:
            setup_logging(paths.log_file, settings.log_level)
        db = Database(paths.db_path)
        applied = db.migrate()
        if applied:
            log.info("DB 마이그레이션 적용: %s", applied)
        log.info(
            "컨텍스트 초기화 (env=%s, api_key=%s, db=%s)",
            settings.app_env,
            "set" if settings.has_api_key else "missing",
            paths.db_path,
        )
        return cls(settings=settings, paths=paths, db=db)

    def close(self) -> None:
        self.db.close()
