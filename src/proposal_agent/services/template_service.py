"""제안서 템플릿(PPTX) 조회·프로파일 서비스 (Phase 12).

템플릿은 ``DocumentKind.PROPOSAL_TEMPLATE``로 등록된 입력 문서다. 제안 때마다 바뀌므로 저장하지 않고
요청 시 파일을 읽어 ``TemplateProfile``을 만든다(프로파일링은 1초 미만, 프로세스 내 캐시).
용도(submission/presentation)는 등록 시 지정값을 우선하고, 없으면 용지 방향으로 추정한다(세로 → 제출용).
"""

from __future__ import annotations

from dataclasses import dataclass

from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.generators.pptx.template import TemplateProfile, profile_template
from proposal_agent.models import DocumentKind, Project, SourceDocument
from proposal_agent.storage.repositories import Repositories

log = get_logger("services.template")


@dataclass(frozen=True)
class TemplateHit:
    document: SourceDocument
    profile: TemplateProfile
    data: bytes


class TemplateService:
    def __init__(self, repos: Repositories, paths: ProjectPaths) -> None:
        self._repos = repos
        self._paths = paths
        self._cache: dict[str, TemplateHit] = {}  # sha256 → hit

    def templates(self, project: Project) -> list[SourceDocument]:
        return [
            d
            for d in self._repos.documents.find(project.id, order_by="created_at")
            if d.kind == DocumentKind.PROPOSAL_TEMPLATE
        ]

    def profile_document(self, doc: SourceDocument) -> TemplateHit:
        hit = self._cache.get(doc.sha256)
        if hit is not None and hit.document.id == doc.id:
            return hit
        data = self._paths.resolve_output(doc.stored_path).read_bytes()
        prof = profile_template(
            data, purpose=doc.template_purpose, file_name=doc.file_name, document_id=doc.id
        )
        hit = TemplateHit(document=doc, profile=prof, data=data)
        self._cache[doc.sha256] = hit
        return hit

    def profiles(self, project: Project) -> list[TemplateHit]:
        out: list[TemplateHit] = []
        for doc in self.templates(project):
            try:
                out.append(self.profile_document(doc))
            except Exception as exc:  # noqa: BLE001 - 깨진 템플릿은 건너뛰고 기록
                log.warning("템플릿 프로파일 실패 %s: %s", doc.file_name, exc)
        return out

    def for_purpose(self, project: Project, purpose: str) -> TemplateHit | None:
        """용도에 맞는 최신 템플릿. 없으면 None (코드 기본 양식 사용)."""
        hits = [h for h in self.profiles(project) if h.profile.purpose == purpose]
        return hits[-1] if hits else None


__all__ = ["TemplateHit", "TemplateService"]
