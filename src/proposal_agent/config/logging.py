"""로깅 설정: 파일 핸들러(workspace/logs/app.log) + 콘솔. 멱등."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_LOGGER_NAME = "proposal_agent"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_CONFIGURED_KEY = "_pwa_configured"

# 단계 1 (지시문 §15.3): 비밀값이 로그에 남지 않도록 메시지·인자를 마스킹한다.
_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),  # Anthropic API 키
    re.compile(
        r"(?i)(api[_-]?key|token|secret|password|authorization)(\s*[=:]\s*)([^\s,;'\"]{4,})"
    ),
)
_MASK = "***"


def mask_secrets(text: str) -> str:
    out = _SECRET_PATTERNS[0].sub("sk-ant-" + _MASK, text)
    return _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}{_MASK}", out)


class SecretMaskingFilter(logging.Filter):
    """로그 레코드의 메시지와 포맷 인자에서 비밀값을 가린다. 예외 텍스트도 대상이다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: mask_secrets(v) if isinstance(v, str) else v for k, v in record.args.items()
                }
            else:
                record.args = tuple(
                    mask_secrets(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def setup_logging(log_file: Path | None = None, level: str | int = "INFO") -> logging.Logger:
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    if getattr(logger, _CONFIGURED_KEY, False):
        logger.setLevel(level)
        return logger
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(_FORMAT)

    logger.addFilter(SecretMaskingFilter())
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
