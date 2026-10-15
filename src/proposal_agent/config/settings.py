"""설정 로드 (.env → 환경변수 → Settings).

Agent SDK는 .env를 자동 로드하지 않으므로 python-dotenv로 직접 읽는다 (PROJECT_OVERVIEW.md 4절).
API 키는 로그·AuditEvent에 기록하지 않는다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import dotenv_values

from proposal_agent.config.errors import ConfigError
from proposal_agent.config.paths import ProjectPaths, repo_root

ENV_PREFIX = "PWA_"
API_KEY_ENV = "ANTHROPIC_API_KEY"
MODEL_ENV = "ANTHROPIC_MODEL"  # 설정 시 model_primary 기본값으로 사용 (PWA_MODEL_PRIMARY가 우선)

DEFAULT_MODEL_PRIMARY = "claude-opus-5-5"
DEFAULT_MODEL_WORKER = "claude-sonnet-5-5"

# 요구사항 ID 접두사 기본값 (RequirementType.value → prefix). PWA_ID_PREFIXES=JSON 으로 재정의.
DEFAULT_ID_PREFIXES: dict[str, str] = {
    "functional": "FR",
    "non_functional": "NFR",
    "constraint": "CON",
    "evaluation": "EVA",
    "submission": "SUB",
}

_PATH_FIELDS = {"output_root", "workspace_root", "db_path"}
APP_ENVS = ("dev", "prod")


@dataclass
class Settings:
    """실행 설정.

    ``app_env``: ``dev``(기본, .env 샘플 허용·DEBUG 로그 허용) / ``prod``(API 키 필수, .env 대신
    OS 환경변수 권장). ``load_settings(require_api_key=True)``는 prod에서 자동 적용된다.
    """

    app_env: str = "dev"
    anthropic_api_key: str | None = None
    model_primary: str = DEFAULT_MODEL_PRIMARY
    model_worker: str = DEFAULT_MODEL_WORKER
    max_budget_usd_per_step: float = 2.0
    max_turns_default: int = 30
    output_root: Path | None = None
    workspace_root: Path | None = None
    db_path: Path | None = None
    approver_name: str = "user"
    log_level: str = "INFO"
    id_prefixes: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ID_PREFIXES))
    id_width: int = 3
    ocr_engine: str = "rapidocr"  # rapidocr | none
    ocr_lang: str = "korean"
    ocr_min_chars_per_page: int = 25  # 이보다 적으면 스캔 페이지로 보고 OCR 시도
    ocr_review_threshold: float = 0.80  # OCR 평균 신뢰도가 이보다 낮으면 검토 필요
    extraction_chunk_chars: int = 12000
    env_file: Path | None = field(default=None, repr=False)

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)

    def require_api_key(self) -> str:
        if not self.anthropic_api_key:
            raise ConfigError(
                f"{API_KEY_ENV}가 설정되지 않았습니다.",
                cause="환경변수 또는 .env 파일에 API 키 없음",
                resolution=f".env 파일에 {API_KEY_ENV}=... 를 추가하거나 환경변수를 설정하십시오.",
            )
        return self.anthropic_api_key

    def paths(self) -> ProjectPaths:
        return ProjectPaths(
            root=repo_root(),
            output_root=self.output_root,
            workspace_root=self.workspace_root,
            db_path=self.db_path,
        )

    def safe_dict(self) -> dict[str, object]:
        """API 키를 가린 표시용 사전."""
        out: dict[str, object] = {}
        for f in fields(self):
            if f.name == "env_file":
                continue
            value = getattr(self, f.name)
            if f.name == "anthropic_api_key":
                value = "***" if value else None
            out[f.name] = value
        return out


def _coerce(name: str, raw: str, current: object) -> object:
    try:
        if name in _PATH_FIELDS:
            return Path(raw).expanduser()
        if isinstance(current, dict):
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("JSON 객체가 아님")
            return {str(k): str(v) for k, v in parsed.items()}
        if isinstance(current, bool):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(current, int):
            return int(raw)
        if isinstance(current, float):
            return float(raw)
        return raw
    except (ValueError, json.JSONDecodeError) as exc:
        raise ConfigError(
            f"설정값 형식 오류: {ENV_PREFIX}{name.upper()}={raw!r}",
            cause=str(exc),
            resolution="숫자/경로/JSON 형식을 확인하십시오.",
        ) from exc


def load_settings(
    env_file: Path | str | None = None,
    *,
    environ: dict[str, str] | None = None,
    require_api_key: bool = False,
) -> Settings:
    """설정을 로드한다.

    우선순위: 실제 환경변수 > .env 파일 > 기본값.
    ``environ``을 넘기면 ``os.environ`` 대신 사용한다(테스트용).
    """
    env = dict(os.environ if environ is None else environ)
    if env_file is None:
        candidate = repo_root() / ".env"
        env_file = candidate if candidate.exists() else None
    file_values: dict[str, str] = {}
    if env_file is not None:
        env_file = Path(env_file)
        if env_file.exists():
            file_values = {k: v for k, v in dotenv_values(env_file).items() if v is not None}
    merged = {**file_values, **env}

    settings = Settings(env_file=env_file)
    settings.anthropic_api_key = merged.get(API_KEY_ENV) or None
    if merged.get(MODEL_ENV):
        settings.model_primary = merged[MODEL_ENV]
    for f in fields(settings):
        if f.name in {"anthropic_api_key", "env_file"}:
            continue
        key = f"{ENV_PREFIX}{f.name.upper()}"
        if merged.get(key):
            setattr(settings, f.name, _coerce(f.name, merged[key], getattr(settings, f.name)))
    if settings.app_env not in APP_ENVS:
        raise ConfigError(
            f"PWA_APP_ENV 값이 올바르지 않습니다: {settings.app_env!r}",
            cause=f"허용 값: {', '.join(APP_ENVS)}",
            resolution="PWA_APP_ENV=dev 또는 prod 로 설정하십시오.",
        )
    if require_api_key or settings.app_env == "prod":
        settings.require_api_key()
    return settings
