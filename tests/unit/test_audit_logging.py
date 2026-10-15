"""감사 이벤트·기술 로그: 오류 기록, 비밀값 마스킹, 로그 파일 생성."""

from __future__ import annotations

import logging
from pathlib import Path

from proposal_agent.config import ConfigError, ProjectPaths, Settings
from proposal_agent.config.logging import ROOT_LOGGER_NAME, get_logger, setup_logging
from proposal_agent.models import Project
from proposal_agent.services import AppContext, Services
from proposal_agent.services.audit import mask_secrets


def test_record_error_stores_cause_and_resolution(
    services: Services, proposal_project: Project
) -> None:
    exc = ConfigError("키 없음", cause="환경변수 미설정", resolution="키를 설정하십시오.")
    ev = services.audit.record_error(
        proposal_project.id, "agent.run", exc, payload={"api_key": "sk-1", "step": "x"}
    )
    stored = services.ctx.repos.audit.get(ev.id)
    assert stored.is_error and stored.error == exc.to_dict()
    assert (
        stored.error["cause"] == "환경변수 미설정"
        and stored.error["resolution"] == "키를 설정하십시오."
    )
    assert stored.payload == {"api_key": "***", "step": "x"}


def test_record_error_for_plain_exception(services: Services, proposal_project: Project) -> None:
    ev = services.audit.record_error(proposal_project.id, "x", ValueError("bad"))
    assert (
        ev.error["type"] == "ValueError" and ev.error["message"] == "bad" and ev.error["resolution"]
    )


def test_mask_secrets_is_recursive() -> None:
    assert mask_secrets({"a": 1, "nested": {"token": "t", "ok": "v"}, "API_KEY": ""}) == {
        "a": 1,
        "nested": {"token": "***", "ok": "v"},
        "API_KEY": "",
    }


def test_error_is_written_to_log_file(tmp_path: Path, caplog) -> None:
    paths = ProjectPaths(root=tmp_path)
    ctx = AppContext.create(Settings(), paths=paths, configure_logging=True)
    try:
        services = Services.from_context(ctx)
        project = services.projects.create(name="로그", mode="proposal")  # type: ignore[arg-type]
        with caplog.at_level(logging.ERROR, logger=ROOT_LOGGER_NAME):
            services.audit.record_error(project.id, "boom.action", RuntimeError("폭발"))
        for h in logging.getLogger(ROOT_LOGGER_NAME).handlers:
            h.flush()
        text = paths.log_file.read_text(encoding="utf-8")
        assert "boom.action" in text and "폭발" in text and "RuntimeError" in text
    finally:
        ctx.close()


def test_get_logger_namespacing() -> None:
    assert get_logger("x").name == f"{ROOT_LOGGER_NAME}.x"
    assert setup_logging(None, "DEBUG").name == ROOT_LOGGER_NAME
