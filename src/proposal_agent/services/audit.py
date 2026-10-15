"""감사 이벤트 기록 헬퍼. 기술 로그(파일)와 감사 이벤트(DB)를 함께 남긴다.

비밀값은 기록하지 않는다: payload에 ``api_key``/``token``/``secret`` 이 포함된 키는 마스킹한다.
"""

from __future__ import annotations

from typing import Any

from proposal_agent.config.errors import PWAError
from proposal_agent.config.logging import get_logger
from proposal_agent.models import ActorKind, AuditEvent
from proposal_agent.storage.repositories import AuditEventRepository

log = get_logger("services.audit")

_SECRET_MARKERS = ("api_key", "apikey", "token", "secret", "password")


def mask_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if any(marker in k.lower() for marker in _SECRET_MARKERS):
            out[k] = "***" if v else v
        elif isinstance(v, dict):
            out[k] = mask_secrets(v)
        else:
            out[k] = v
    return out


class AuditService:
    def __init__(self, repo: AuditEventRepository) -> None:
        self._repo = repo

    def record(
        self,
        project_id: str,
        action: str,
        *,
        actor: str = "system",
        actor_kind: ActorKind = ActorKind.SYSTEM,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            project_id=project_id,
            action=action,
            actor=actor,
            actor_kind=actor_kind,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=mask_secrets(payload or {}),
        )
        self._repo.insert(event)
        log.info("audit %s %s %s/%s", project_id[:12], action, entity_type, entity_id)
        return event

    def record_error(
        self,
        project_id: str,
        action: str,
        error: BaseException,
        *,
        actor: str = "system",
        actor_kind: ActorKind = ActorKind.SYSTEM,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """오류를 원인·해결 방안과 함께 기록한다. 기술 로그에는 스택을 남긴다."""
        if isinstance(error, PWAError):
            err = error.to_dict()
        else:
            err = {
                "type": type(error).__name__,
                "message": str(error),
                "cause": str(error),
                "resolution": PWAError.default_resolution,
                "detail": {},
            }
        event = AuditEvent(
            project_id=project_id,
            action=action,
            actor=actor,
            actor_kind=actor_kind,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=mask_secrets(payload or {}),
            error=err,
        )
        self._repo.insert(event)
        log.error("audit error %s %s: %s", project_id[:12], action, err["message"], exc_info=error)
        return event
