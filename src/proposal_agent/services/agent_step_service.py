"""역할별 에이전트 실행 서비스.

- 역할 정의(``agents/roles.py``)에서 도구·MCP·예산·시간 제한을 읽어 ``AgentRequest``를 만든다.
- 인프로세스 MCP 서버 ``pwa``는 프로젝트별 ``ToolContext``로 매번 조립한다 (읽기 전용).
- 이전 역할의 결과(``AgentOutput``)를 프롬프트에 재사용해 같은 작업을 반복하지 않는다.
- 결과 JSON은 ``Output/<subdir>/<stem>_vX.Y.json``으로 저장하고 ``AgentOutput``·감사 이벤트를 남긴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from proposal_agent.agents import load_prompt
from proposal_agent.agents.control import CancellationToken
from proposal_agent.agents.roles import MCP_PROJECT, AgentRole, get_role
from proposal_agent.agents.runner import AgentRequest, AgentResponse, AgentRunner
from proposal_agent.agents.tools import ToolContext, build_project_server
from proposal_agent.config.errors import AgentRunError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.models import ActorKind, AgentOutput, Project, RequirementStatus
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.audit import AuditService

log = get_logger("services.agent_step")

PRIOR_OUTPUT_MAX_CHARS = 12000


@dataclass
class RoleRunResult:
    response: AgentResponse
    output_record: AgentOutput
    output: BaseModel


class AgentStepService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        settings: Settings,
        audit: AuditService,
        runner: AgentRunner,
        files: FileStore,
        *,
        external_mcp: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._settings = settings
        self._audit = audit
        self._runner = runner
        self._files = files
        self._external_mcp = dict(external_mcp or settings.mcp_external)

    # --- 요청 조립 ----------------------------------------------------------------------
    def mcp_servers_for(self, project: Project, role: AgentRole) -> dict[str, Any]:
        servers: dict[str, Any] = {}
        for name in role.mcp_servers:
            if name == MCP_PROJECT:
                servers[name] = build_project_server(
                    ToolContext(self._repos, self._paths, project), name=name
                )
            elif name in self._external_mcp:
                servers[name] = dict(self._external_mcp[name])
            else:
                log.warning(
                    "역할 %s가 선언한 MCP 서버 %s 설정이 없어 연결하지 않음", role.key, name
                )
        return servers

    def build_request(
        self,
        project: Project,
        role: AgentRole,
        prompt: str,
        *,
        cancel: CancellationToken | None = None,
    ) -> AgentRequest:
        model = (
            self._settings.model_worker
            if role.model_key == "worker"
            else self._settings.model_primary
        )
        workspace = self._paths.ensure_workspace(project.workspace_dir or project.id)
        return AgentRequest(
            role=role.key,
            system_prompt=load_prompt(role.prompt_name),
            prompt=prompt,
            max_turns=role.max_turns,
            max_budget_usd=min(role.max_budget_usd, self._settings.max_budget_usd_per_step * 3),
            model=model,
            effort=role.effort,
            cwd=workspace,
            add_dirs=(),
            builtin_tools=role.builtin_tools,
            mcp_servers=self.mcp_servers_for(project, role),
            allowed_tools=tuple(role.allowed_tool_names()),
            timeout_s=role.timeout_s,
            retries=role.retries,
            cancel=cancel,
        )

    # --- 재사용 ----------------------------------------------------------------------------
    def prior_output(self, project: Project, role_key: str) -> dict[str, Any] | None:
        rec = self._repos.agent_outputs.latest(project.id, role_key)
        if rec is None:
            return None
        try:
            return json.loads(self._paths.resolve_output(rec.file_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("이전 출력 읽기 실패 %s: %s", rec.file_path, exc)
            return None

    def prior_outputs_block(self, project: Project, role: AgentRole) -> tuple[str, list[str]]:
        parts: list[str] = []
        used: list[str] = []
        for key in role.reuses:
            data = self.prior_output(project, key)
            if data is None:
                continue
            text = json.dumps(data, ensure_ascii=False)
            if len(text) > PRIOR_OUTPUT_MAX_CHARS:
                text = (
                    text[:PRIOR_OUTPUT_MAX_CHARS]
                    + " …(truncated; 전체는 mcp__pwa__get_prior_output 사용)"
                )
            parts.append(f'<prior role="{key}">\n{text}\n</prior>')
            used.append(key)
        return ("\n\n".join(parts), used)

    def requirements_summary(self, project: Project, limit: int = 150) -> list[dict[str, Any]]:
        reqs = self._repos.requirements.find(project.id, order_by="id")
        return [
            {
                "id": r.id,
                "type": str(r.type),
                "name": r.name,
                "scope_class": str(r.scope_class),
                "is_mandatory": r.is_mandatory,
                "description": r.description[:300],
            }
            for r in reqs
            if r.status != RequirementStatus.DELETED
        ][:limit]

    # --- 실행 ------------------------------------------------------------------------------
    def run_role(
        self,
        project: Project,
        role_key: str,
        prompt: str,
        *,
        actor: str = "user",
        step_run_id: str | None = None,
        cancel: CancellationToken | None = None,
        include_prior: bool = True,
    ) -> RoleRunResult:
        role = get_role(role_key)
        prior_block, used = self.prior_outputs_block(project, role) if include_prior else ("", [])
        full_prompt = f"{prior_block}\n\n{prompt}" if prior_block else prompt
        request = self.build_request(project, role, full_prompt, cancel=cancel)
        try:
            response = self._runner.run_structured(request, role.output_schema)
        except AgentRunError as exc:
            self._audit.record_error(
                project.id,
                f"agent.{role.key}.failed",
                exc,
                actor=actor,
                actor_kind=ActorKind.AGENT,
                payload={
                    "role": role.key,
                    "step_run_id": step_run_id,
                    "attempt": exc.detail.get("attempt"),
                    "category": exc.detail.get("category"),
                },
            )
            raise
        record = self._save_output(project, role, response, step_run_id, used)
        self._audit.record(
            project.id,
            f"agent.{role.key}.completed",
            actor=actor,
            actor_kind=ActorKind.AGENT,
            entity_type="AgentOutput",
            entity_id=record.id,
            payload={
                "role": role.key,
                "cost_usd": round(response.cost_usd, 4),
                "turns": response.num_turns,
                "tool_calls": [
                    {"tool": t.tool_name, "ok": t.ok, "denied": t.denied_reason}
                    for t in response.tool_calls
                ][:50],
                "attempts": response.attempts,
                "reused": used,
                "file": record.file_path,
            },
        )
        return RoleRunResult(response=response, output_record=record, output=response.output)

    def _save_output(
        self,
        project: Project,
        role: AgentRole,
        response: AgentResponse,
        step_run_id: str | None,
        used: list[str],
    ) -> AgentOutput:
        name = self._files.next_version_name(
            project.output_dir, role.output_subdir, role.output_stem, ".json"
        )
        payload = response.output.model_dump(mode="json")
        data = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
        stored = self._files.save_bytes(project.output_dir, role.output_subdir, name, data)
        version = name.rsplit("_v", 1)[1].rsplit(".json", 1)[0]
        record = AgentOutput(
            project_id=project.id,
            role=role.key,
            version=f"v{version}",
            file_path=stored.relative_path,
            sha256=stored.sha256,
            step_run_id=step_run_id,
            cost_usd=response.cost_usd,
            num_turns=response.num_turns,
            tool_calls=len(response.tool_calls),
            attempts=response.attempts,
            inputs_used=used,
            summary={
                k: (len(v) if isinstance(v, list) else v)
                for k, v in payload.items()
                if isinstance(v, list | str | int | float)
            },
        )
        self._repos.agent_outputs.insert(record)
        return record

    # --- 연결 점검 ---------------------------------------------------------------------------
    def check_connections(self, project: Project, role_key: str) -> Any:
        role = get_role(role_key)
        return self._runner.test_connection(self.mcp_servers_for(project, role), role.builtin_tools)
