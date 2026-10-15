"""예외 계층.

모든 오류는 원인(cause)과 권장 조치(resolution) 메시지를 가진다 (ARCHITECTURE.md 7절).
"""

from __future__ import annotations

from typing import Any


class PWAError(Exception):
    """프로젝트 공통 최상위 예외."""

    default_resolution = "로그를 확인하고 다시 시도하십시오."

    def __init__(
        self,
        message: str,
        *,
        cause: str | None = None,
        resolution: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause or message
        self.resolution = resolution or self.default_resolution
        self.detail: dict[str, Any] = detail or {}

    def to_dict(self) -> dict[str, Any]:
        """AuditEvent.error 에 저장하기 위한 직렬화."""
        return {
            "type": type(self).__name__,
            "message": self.message,
            "cause": self.cause,
            "resolution": self.resolution,
            "detail": self.detail,
        }

    def __str__(self) -> str:
        return f"{self.message} (원인: {self.cause}; 조치: {self.resolution})"


class ConfigError(PWAError):
    """설정·환경변수 오류."""

    default_resolution = ".env 또는 환경변수를 확인하십시오."


class IngestError(PWAError):
    """문서 입력·추출 오류."""

    default_resolution = "입력 문서 형식과 내용을 확인하십시오."


class AgentRunError(PWAError):
    """에이전트 실행 실패 (예산·턴 초과, 구조화 출력 실패 등)."""

    default_resolution = "입력을 줄이거나 예산·턴 상한을 조정한 뒤 재실행하십시오."

    def __init__(
        self,
        message: str,
        *,
        subtype: str | None = None,
        cause: str | None = None,
        resolution: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, cause=cause, resolution=resolution, detail=detail)
        self.subtype = subtype
        if subtype:
            self.detail.setdefault("subtype", subtype)


class ValidationError(PWAError):
    """도메인 검증 오류 (상태 전이 위반, 규칙 위반 등)."""

    default_resolution = "검증 메시지에 따라 데이터를 수정하십시오."


class StorageError(PWAError):
    """DB·파일 저장소 오류."""

    default_resolution = "DB 파일 경로와 권한을 확인하십시오."


class NotFoundError(StorageError):
    """조회 대상 없음."""

    default_resolution = "ID가 올바른지 확인하십시오."


class PathSecurityError(StorageError):
    """허용 범위(프로젝트 루트) 밖 경로 접근 시도."""

    default_resolution = "프로젝트 폴더 내부 경로만 사용하십시오."


class FileExistsConflict(StorageError):  # noqa: N818 - 설계 문서(ARCHITECTURE.md 7절)의 이름을 유지
    """덮어쓰기 금지 정책 위반: 대상 경로에 이미 파일이 존재."""

    default_resolution = "새 버전 파일명을 사용하십시오. 기존 파일은 덮어쓰지 않습니다."

    def __init__(self, path: Any, **kwargs: Any) -> None:
        super().__init__(f"파일이 이미 존재합니다: {path}", cause="덮어쓰기 금지", **kwargs)
        self.path = path
