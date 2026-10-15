"""로깅 설정: 파일 핸들러(workspace/logs/app.log) + 콘솔. 멱등."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_LOGGER_NAME = "proposal_agent"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_CONFIGURED_KEY = "_pwa_configured"


def setup_logging(log_file: Path | None = None, level: str | int = "INFO") -> logging.Logger:
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    if getattr(logger, _CONFIGURED_KEY, False):
        logger.setLevel(level)
        return logger
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    setattr(logger, _CONFIGURED_KEY, True)
    return logger


def get_logger(name: str) -> logging.Logger:
    """``proposal_agent.<name>`` 하위 로거."""
    if name.startswith(ROOT_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
