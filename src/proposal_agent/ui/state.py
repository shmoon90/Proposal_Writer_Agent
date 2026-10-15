"""Streamlit 세션 상태·서비스 접근 래퍼.

UI 코드는 이 모듈을 통해서만 서비스를 얻는다. ``AppContext``는 프로세스당 하나를 캐시한다.
테스트에서는 ``st.session_state["_pwa_services"]``에 Services를 주입해 임시 DB를 쓸 수 있다.
"""

from __future__ import annotations

import streamlit as st

from proposal_agent.config.errors import ConfigError, PWAError
from proposal_agent.config.logging import get_logger
from proposal_agent.models import Project
from proposal_agent.services import AppContext, Services

log = get_logger("ui.state")

SERVICES_KEY = "_pwa_services"
PROJECT_KEY = "selected_project_id"
ACTOR_KEY = "actor_name"


@st.cache_resource(show_spinner="초기화 중…")
def _build_services() -> Services:
    ctx = AppContext.create()
    return Services.from_context(ctx)


def get_services() -> Services:
    injected = st.session_state.get(SERVICES_KEY)
    if injected is not None:
        return injected
    return _build_services()


def actor_name() -> str:
    return st.session_state.get(ACTOR_KEY) or get_services().ctx.settings.approver_name


def selected_project_id() -> str | None:
    return st.session_state.get(PROJECT_KEY)


def select_project(project_id: str | None) -> None:
    st.session_state[PROJECT_KEY] = project_id


def current_project() -> Project | None:
    pid = selected_project_id()
    if not pid:
        return None
    try:
        return get_services().projects.get(pid)
    except PWAError as exc:
        log.warning("선택된 프로젝트 조회 실패: %s", exc)
        select_project(None)
        return None


def show_error(exc: BaseException, *, context: str = "") -> None:
    """사용자 메시지(원인·조치)와 기술 로그를 분리해 표시·기록한다."""
    if isinstance(exc, PWAError):
        st.error(
            f"{exc.message}\n\n원인: {exc.cause}\n\n조치: {exc.resolution}", icon=":material/error:"
        )
        log.error("%s%s", f"{context}: " if context else "", exc, exc_info=exc)
    else:
        st.error(
            "예상하지 못한 오류가 발생했습니다. 로그 파일을 확인하십시오.",
            icon=":material/error:",
        )
        log.exception("%s예상하지 못한 오류", f"{context}: " if context else "")


def api_key_banner() -> None:
    """API 키가 없을 때 이해 가능한 안내를 표시한다. 키 값은 절대 표시하지 않는다."""
    settings = get_services().ctx.settings
    if not settings.has_api_key:
        try:
            settings.require_api_key()
        except ConfigError as exc:
            st.warning(
                f"{exc.message} 에이전트 실행 단계는 사용할 수 없습니다.\n\n조치: {exc.resolution}",
                icon=":material/key_off:",
            )
