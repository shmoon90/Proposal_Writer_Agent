"""프로젝트 생성·조회·열기 서비스.

생성 순서: 입력 검증 → Output 폴더(14종 하위) 생성 → workspace 생성 → DB 저장 → 감사 이벤트.
폴더를 만든 뒤 DB 저장에 실패하면 폴더는 그대로 두고(기존 파일 보존 원칙) 오류를 보고한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from proposal_agent.config.errors import NotFoundError, PWAError, StorageError, ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import OUTPUT_SUBDIRS, ProjectPaths
from proposal_agent.models import ActorKind, Project, ProjectMode, ProjectStatus
from proposal_agent.services.audit import AuditService
from proposal_agent.storage.repositories import Repositories

log = get_logger("services.project")


@dataclass(frozen=True)
class ProjectLocations:
    """UI '저장 위치 확인'용 경로 요약."""

    output_dir: str
    workspace_dir: str
    subdirs: tuple[str, ...]
    missing_subdirs: tuple[str, ...]
    db_path: str
    log_file: str


class ProjectService:
    def __init__(self, repos: Repositories, paths: ProjectPaths, audit: AuditService) -> None:
        self._repos = repos
        self._paths = paths
        self._audit = audit

    # --- 생성 ------------------------------------------------------------------------
    def create(
        self,
        *,
        name: str,
        mode: ProjectMode,
        start_date: date | None = None,
        end_date: date | None = None,
        client_name: str | None = None,
        created_by: str = "user",
    ) -> Project:
        name = (name or "").strip()
        if not name:
            raise ValidationError("프로젝트명을 입력하십시오.", cause="빈 프로젝트명")
        if start_date and end_date and end_date < start_date:
            raise ValidationError(
                "종료일은 시작일보다 빠를 수 없습니다.",
                cause=f"start={start_date}, end={end_date}",
                resolution="과제 기간을 다시 입력하십시오.",
            )

        output_path = self._paths.create_project_output_dir(name)
        output_dir = output_path.name
        project = Project(
            name=name,
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            client_name=client_name or None,
            output_dir=output_dir,
            workspace_dir="",
            created_by=created_by,
        )
        project.workspace_dir = project.id
        self._paths.ensure_workspace(project.id)
        try:
            self._repos.projects.insert(project)
        except StorageError as exc:
            log.error("프로젝트 DB 저장 실패, 폴더는 보존됨: %s", output_path, exc_info=exc)
            raise StorageError(
                "프로젝트 저장에 실패했습니다.",
                cause=exc.cause,
                resolution=f"생성된 폴더 {output_path} 는 보존되었습니다. DB 상태를 확인한 뒤 다시 시도하십시오.",
            ) from exc
        self._audit.record(
            project.id,
            "project.created",
            actor=created_by,
            actor_kind=ActorKind.USER,
            entity_type="Project",
            entity_id=project.id,
            payload={"name": name, "mode": str(mode), "output_dir": output_dir},
        )
        log.info("프로젝트 생성 %s (%s) → %s", project.id, mode, output_dir)
        return project

    # --- 조회 ------------------------------------------------------------------------
    def list_projects(self, mode: ProjectMode | None = None) -> list[Project]:
        if mode is None:
            return self._repos.projects.list_all()
        return self._repos.projects.find(mode=str(mode), order_by="created_at", descending=True)

    def get(self, project_id: str) -> Project:
        try:
            return self._repos.projects.get(project_id)
        except NotFoundError as exc:
            raise NotFoundError(
                "프로젝트를 찾을 수 없습니다.",
                cause=f"id={project_id}",
                resolution="프로젝트 목록에서 다시 선택하십시오.",
            ) from exc

    def open(self, project_id: str, *, actor: str = "user") -> Project:
        """기존 프로젝트를 연다. 누락된 폴더는 보충 생성하되 기존 파일은 건드리지 않는다."""
        project = self.get(project_id)
        base = self._paths.project_output_dir(project.output_dir)
        if not base.exists():
            raise PWAError(
                "프로젝트 산출물 폴더가 없습니다.",
                cause=str(base),
                resolution="폴더가 이동·삭제되었는지 확인하십시오. 복구 후 다시 여십시오.",
            )
        created = self._paths.ensure_output_subdirs(base)
        self._paths.ensure_workspace(project.workspace_dir or project.id)
        if created:
            self._audit.record(
                project.id,
                "project.subdirs_restored",
                actor=actor,
                actor_kind=ActorKind.USER,
                entity_type="Project",
                entity_id=project.id,
                payload={"created": created},
            )
        return project

    def update_status(
        self, project: Project, status: ProjectStatus, *, actor: str = "system"
    ) -> Project:
        before = project.status
        project.status = status
        self._repos.projects.update(project)
        self._audit.record(
            project.id,
            "project.status_changed",
            actor=actor,
            entity_type="Project",
            entity_id=project.id,
            payload={"from": str(before), "to": str(status)},
        )
        return project

    def locations(self, project: Project) -> ProjectLocations:
        base = self._paths.project_output_dir(project.output_dir)
        return ProjectLocations(
            output_dir=str(base),
            workspace_dir=str(self._paths.workspace_for(project.workspace_dir or project.id)),
            subdirs=OUTPUT_SUBDIRS,
            missing_subdirs=tuple(self._paths.missing_output_subdirs(project.output_dir)),
            db_path=str(self._paths.db_path),
            log_file=str(self._paths.log_file),
        )
