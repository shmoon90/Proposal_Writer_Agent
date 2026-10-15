"""config.settings: .env/환경변수 로드, 설정 누락 처리, 비밀값 마스킹."""

from __future__ import annotations

from pathlib import Path

import pytest

from proposal_agent.config import ConfigError, load_settings


def test_missing_api_key_is_allowed_in_dev_but_require_raises(tmp_path: Path) -> None:
    s = load_settings(env_file=tmp_path / "none.env", environ={})
    assert s.anthropic_api_key is None
    assert s.has_api_key is False
    with pytest.raises(ConfigError) as info:
        s.require_api_key()
    assert "ANTHROPIC_API_KEY" in info.value.message
    assert ".env" in info.value.resolution


def test_prod_env_requires_api_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(env_file=tmp_path / "none.env", environ={"PWA_APP_ENV": "prod"})
    s = load_settings(
        env_file=tmp_path / "none.env",
        environ={"PWA_APP_ENV": "prod", "ANTHROPIC_API_KEY": "sk-test"},
    )
    assert s.app_env == "prod" and s.has_api_key


def test_invalid_app_env_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(env_file=tmp_path / "none.env", environ={"PWA_APP_ENV": "staging"})


def test_env_file_loaded_and_real_env_wins(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=from-file\nANTHROPIC_MODEL=claude-sonnet-5-5\nPWA_MAX_TURNS_DEFAULT=7\n",
        encoding="utf-8",
    )
    s = load_settings(env_file=env_file, environ={"PWA_MAX_TURNS_DEFAULT": "9"})
    assert s.anthropic_api_key == "from-file"
    assert s.model_primary == "claude-sonnet-5-5"
    assert s.max_turns_default == 9  # 실제 환경변수 우선


def test_bad_numeric_value_reports_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=tmp_path / "none.env", environ={"PWA_MAX_TURNS_DEFAULT": "many"})
    assert "PWA_MAX_TURNS_DEFAULT" in info.value.message


def test_safe_dict_masks_api_key(tmp_path: Path) -> None:
    s = load_settings(env_file=tmp_path / "none.env", environ={"ANTHROPIC_API_KEY": "sk-secret"})
    d = s.safe_dict()
    assert d["anthropic_api_key"] == "***"
    assert "sk-secret" not in repr(d)
    assert "env_file" not in d


def test_path_settings_coerced(tmp_path: Path) -> None:
    s = load_settings(
        env_file=tmp_path / "none.env", environ={"PWA_OUTPUT_ROOT": str(tmp_path / "out")}
    )
    assert s.output_root == tmp_path / "out"
    assert s.paths().output_root == tmp_path / "out"
