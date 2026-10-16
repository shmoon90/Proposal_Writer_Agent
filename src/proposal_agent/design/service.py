"""상세 설계 서비스 (지시문 §12, 단계 6): detail_designer 에이전트 입력 구성 → 결과를 화면(SCR)·테이블(TBL)·API·모듈(MOD)·
업무 규칙(DSG) 엔티티로 저장 → 추적표 연결 → 누락·모순·DB 호환성 검사 → 코드 생성 입력 패키지(D-22) 내보내기.

- 저장은 같은 이름이면 갱신(버전 ↑), 새 이름이면 코드 발급, 이번 결과에 없는 이전 객체는 ``status="dropped"`` 로 남긴다
  (물리 삭제 없음). 기준선 적재로 들어온 화면(``source="baseline"``) 은 이름이 같을 때만 갱신한다.
- 코드 생성 패키지는 RFP_JAVA 의 입력 모양(requirements / ui_design / architecture) 으로 쓴다. 단계 7 이 소비한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from proposal_agent.agents.schemas import DetailDesignReport
from proposal_agent.config.errors import ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.design.consistency import design_consistency_issues
from proposal_agent.design.context import client_context_block
from proposal_agent.models import (
    AcceptanceStatus,
    ApiSpec,
    CodeModule,
    DbColumn,
    DbTable,
    DesignItem,
    Project,
    ProjectSettings,
    RequirementTrace,
    Screen,
    TraceTargetType,
)
from proposal_agent.services.agent_step_service import AgentStepService
from proposal_agent.services.audit import AuditService
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

log = get_logger(__name__)

ROLE_DETAIL_DESIGNER = "detail_designer"
PACKAGE_SUBDIR = "05_Architecture_Design"


def _norm(s: str) -> str:
    return " ".join((s or "").split()).casefold()


class DetailDesignService:
    def __init__(
        self,
        repos: Repositories,
        audit: AuditService,
        steps: AgentStepService,
        paths: ProjectPaths,
        files: FileStore,
    ) -> None:
        self._repos = repos
        self._audit = audit
        self._steps = steps
        self._paths = paths
        self._files = files

    # --- 조회 -------------------------------------------------------------------------------------
    def screens(self, project: Project) -> list[Screen]:
        return [
            s
            for s in self._repos.screens.find(project.id, order_by="created_at")
            if s.status != "dropped"
        ]

    def tables(self, project: Project) -> list[DbTable]:
        return [
            t
            for t in self._repos.db_tables.find(project.id, order_by="code")
            if t.status != "dropped"
        ]

    def apis(self, project: Project) -> list[ApiSpec]:
        return [
            a
            for a in self._repos.api_specs.find(project.id, order_by="code")
            if a.status != "dropped"
        ]

    def modules(self, project: Project) -> list[CodeModule]:
        return [
            m
            for m in self._repos.code_modules.find(project.id, order_by="code")
            if m.status != "dropped"
        ]

    def rules(self, project: Project) -> list[DesignItem]:
        return [
            d
            for d in self._repos.design_items.find(project.id, order_by="code")
            if d.category == "business_rule" and d.status != "dropped"
        ]

    def has_design(self, project: Project) -> bool:
        return bool(self.screens(project) or self.tables(project) or self.apis(project))

    def latest(self, project: Project) -> dict[str, Any] | None:
        return self._steps.prior_output(project, ROLE_DETAIL_DESIGNER)

    def settings_of(self, project: Project) -> ProjectSettings:
        return ProjectSettings.from_project_settings(project.settings)

    # --- 입력 -------------------------------------------------------------------------------------
    def brief(self, project: Project) -> str:
        reqs = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.acceptance_status != AcceptanceStatus.REJECTED
            and r.change_state != "deleted"
            and r.type.value in ("functional", "non_functional", "constraint")
        ]
        analysis = self._steps.prior_output(project, "rfp_analyst")
        req_block = [
            {
                "id": r.id,
                "rfp_id": r.rfp_requirement_id or "",
                "type": r.type.value,
                "name": r.name,
                "description": (r.description or "")[:400],
                "approach": (r.implementation_approach or "")[:600],
                "analysis": {k: v for k, v in (r.analysis or {}).items() if v},
                "difficulty": r.difficulty.value if r.difficulty else "",
                "mandatory": r.is_mandatory,
            }
            for r in reqs
        ]
        from proposal_agent.requirements.design import DesignService

        designs = DesignService(self._repos, self._steps).designs(project)
        design_block = [
            {
                k: d.get(k)
                for k in (
                    "title",
                    "requirement_ids",
                    "overview",
                    "structure",
                    "flows",
                    "tech_choices",
                    "data_interfaces",
                    "auth_security",
                    "performance_scalability",
                )
            }
            for d in designs
        ]
        components = [
            {"code": c.id, "layer": c.layer, "name": c.name, "technology": c.technology or "미정"}
            for c in self._repos.components.find(project.id, order_by="id")[:60]
        ]
        research = [
            {
                "id": t.id,
                "topic": t.topic,
                "facts": t.confirmed_facts[:5],
                "stack": t.recommended_stack[:6],
            }
            for t in self._repos.research.find(project.id, order_by="created_at")[:30]
        ]
        parts = [
            client_context_block(project, analysis, self.settings_of(project)),
            "<requirements>\n"
            + json.dumps(req_block, ensure_ascii=False)[:40000]
            + "\n</requirements>",
            "<designs>\n" + json.dumps(design_block, ensure_ascii=False)[:30000] + "\n</designs>",
            "<architecture>\n"
            + json.dumps(components, ensure_ascii=False)[:8000]
            + "\n</architecture>",
            "<research>\n" + json.dumps(research, ensure_ascii=False)[:12000] + "\n</research>",
            "위 요구사항·구현 설계를 화면 설계·DB 설계·API 명세·코드 모듈·업무 규칙으로 상세화해 JSON 으로 반환하라. "
            "수용된 기능 요구는 화면·API·테이블 중 하나 이상에 연결하고, 자료형·검증 규칙·오류 코드·보존 정책까지 적어라.",
        ]
        return "\n\n".join(parts)

    # --- 저장 -------------------------------------------------------------------------------------
    def persist(
        self, project: Project, report: DetailDesignReport | dict[str, Any], *, actor: str = "user"
    ) -> dict[str, int]:
        rep = (
            report
            if isinstance(report, DetailDesignReport)
            else DetailDesignReport.model_validate(report)
        )
        req_ids = {r.id for r in self._repos.requirements.find(project.id)}
        rfp_map = {
            r.rfp_requirement_id: r.id
            for r in self._repos.requirements.find(project.id)
            if r.rfp_requirement_id
        }

        def rids(values: list[str]) -> list[str]:
            out: list[str] = []
            for v in values:
                rid = v if v in req_ids else rfp_map.get(v, "")
                if rid and rid not in out:
                    out.append(rid)
            return out

        counts = {"screens": 0, "tables": 0, "apis": 0, "modules": 0, "rules": 0, "traces": 0}
        # 화면
        existing_screens = {_norm(s.name): s for s in self._repos.screens.find(project.id)}
        seen: set[str] = set()
        screen_code: dict[str, str] = {}
        for sd in rep.screens:
            key = _norm(sd.name)
            seen.add(key)
            s = existing_screens.get(key)
            payload = {
                "description": sd.purpose,
                "screen_type": sd.screen_type or "list",
                "purpose": sd.purpose,
                "user_roles": list(sd.user_roles),
                "layout": {
                    "description": sd.layout.description,
                    "regions": [r.model_dump() for r in sd.layout.regions],
                }
                if sd.layout
                else {},
                "fields": [f.model_dump() for f in sd.fields],
                "actions": [a.model_dump() for a in sd.actions],
                "states": [st.model_dump() for st in sd.states],
                "functions": [fn.model_dump() for fn in sd.functions],
                "related_requirement_ids": rids(sd.requirement_ids),
                "source": "design",
                "status": "designed",
            }
            if s is None:
                s = Screen(
                    project_id=project.id,
                    code=self._unique_code(project, "SCR"),
                    name=sd.name,
                    **payload,
                )
                self._repos.screens.insert(s)
            else:
                for k, v in payload.items():
                    setattr(s, k, v)
                s.version = int(getattr(s, "version", 1)) + 1
                s.touch()
                self._repos.screens.update(s)
            screen_code[key] = s.code or s.id
            counts["screens"] += 1
            counts["traces"] += self._ensure_traces(project, s, list(rids(sd.requirement_ids)))
        for key, s in existing_screens.items():
            if key not in seen and getattr(s, "source", "") == "design":
                s.status = "dropped"
                s.touch()
                self._repos.screens.update(s)
        # 테이블
        table_code = self._upsert_coded(
            project,
            self._repos.db_tables,
            "TBL",
            [
                (
                    td.name,
                    {
                        "logical_name": td.logical_name,
                        "description": td.description,
                        "columns": [
                            DbColumn(
                                code=f"COL-{i + 1:03d}",
                                name=c.name,
                                data_type=c.data_type,
                                length=c.length,
                                nullable=c.nullable,
                                default=c.default,
                                is_pk=c.is_pk,
                                fk_ref=c.fk_ref,
                                constraint=c.constraint,
                                is_personal_data=c.is_personal_data,
                                description=c.description,
                            )
                            for i, c in enumerate(td.columns)
                        ],
                        "indexes": list(td.indexes),
                        "relations": list(td.relations),
                        "retention_policy": td.retention_policy,
                        "migration_note": td.migration_note,
                        "db_engine": td.db_engine,
                        "related_requirement_ids": rids(td.requirement_ids),
                        "status": "designed",
                    },
                )
                for td in rep.tables
            ],
            lambda e: e.name,
        )
        counts["tables"] = len(rep.tables)
        # API
        api_code = self._upsert_coded(
            project,
            self._repos.api_specs,
            "API",
            [
                (
                    ad.name,
                    {
                        "path": ad.path,
                        "method": ad.method,
                        "request_schema": {
                            "fields": list(ad.request_fields),
                            "description": ad.description,
                        },
                        "response_schema": {"description": ad.response},
                        "auth": ad.auth,
                        "error_codes": list(ad.error_codes),
                        "validation_rules": list(ad.validation_rules),
                        "idempotency": ad.idempotency,
                        "timeout_retry": ad.timeout_retry,
                        "paging_limits": ad.paging_limits,
                        "logging_audit": ad.logging_audit,
                        "api_version": ad.api_version or "v1",
                        "related_requirement_ids": rids(ad.requirement_ids),
                        "related_screen_ids": [
                            screen_code.get(_norm(x), x) for x in ad.screen_refs
                        ],
                        "related_table_ids": [table_code.get(_norm(x), x) for x in ad.table_refs],
                        "status": "designed",
                    },
                )
                for ad in rep.apis
            ],
            lambda e: e.name,
        )
        counts["apis"] = len(rep.apis)
        # 모듈
        self._upsert_coded(
            project,
            self._repos.code_modules,
            "MOD",
            [
                (
                    md.path or md.name,
                    {
                        "name": md.name,
                        "layer": md.layer,
                        "description": md.responsibility,
                        "depends_on": list(md.depends_on),
                        "related_requirement_ids": rids(md.requirement_ids),
                        "related_api_ids": [api_code.get(_norm(x), x) for x in md.api_refs],
                        "related_screen_ids": [
                            screen_code.get(_norm(x), x) for x in md.screen_refs
                        ],
                        "related_table_ids": [table_code.get(_norm(x), x) for x in md.table_refs],
                        "status": "planned",
                    },
                )
                for md in rep.modules
            ],
            lambda e: e.path or e.name,
            name_field="path",
        )
        counts["modules"] = len(rep.modules)
        # 업무 규칙 → 설계 항목(DSG)
        self._upsert_coded(
            project,
            self._repos.design_items,
            "DSG",
            [
                (
                    br.rule_id or br.description[:40],
                    {
                        "category": "business_rule",
                        "description": br.description,
                        "decisions": [f"적용 모듈: {br.enforced_in}"] if br.enforced_in else [],
                        "related_requirement_ids": rids(br.requirement_ids),
                        "status": "designed",
                    },
                )
                for br in rep.business_rules
            ],
            lambda e: e.name,
            only_category="business_rule",
        )
        counts["rules"] = len(rep.business_rules)
        self._audit.record(
            project.id,
            "design.detail_persisted",
            actor=actor,
            payload={**counts, "assumptions": rep.assumptions[:10], "notes": rep.notes[:300]},
        )
        return counts

    def _unique_code(self, project: Project, prefix: str) -> str:
        existing = {
            getattr(e, "code", "")
            for repo in (
                self._repos.screens,
                self._repos.db_tables,
                self._repos.api_specs,
                self._repos.code_modules,
                self._repos.design_items,
            )
            for e in repo.find(project.id)
        }
        for _ in range(1000):
            code = self._repos.next_code(project.id, prefix)
            if code not in existing:
                return code
        raise ValidationError(f"{prefix} 코드를 발급할 수 없습니다.")

    def _upsert_coded(
        self,
        project: Project,
        repo: Any,
        prefix: str,
        items: list[tuple[str, dict[str, Any]]],
        key_of: Any,
        *,
        name_field: str = "name",
        only_category: str | None = None,
    ) -> dict[str, str]:
        existing = {
            _norm(key_of(e)): e
            for e in repo.find(project.id)
            if only_category is None or getattr(e, "category", "") == only_category
        }
        seen: set[str] = set()
        codes: dict[str, str] = {}
        for name, payload in items:
            key = _norm(name)
            seen.add(key)
            e = existing.get(key)
            if e is None:
                data = {
                    "project_id": project.id,
                    "code": self._unique_code(project, prefix),
                    name_field: name,
                    **payload,
                }
                if name_field != "name" and "name" not in data:
                    data["name"] = name
                e = repo.model(**data)
                repo.insert(e)
            else:
                for k, v in payload.items():
                    setattr(e, k, v)
                e.version = int(getattr(e, "version", 1)) + 1
                e.touch()
                repo.update(e)
            codes[key] = e.code
            if name_field == "path":
                codes[_norm(e.name)] = e.code
        for key, e in existing.items():
            if key not in seen and e.status != "dropped":
                e.status = "dropped"
                e.touch()
                repo.update(e)
        return codes

    def _ensure_traces(self, project: Project, screen: Screen, req_ids: list[str]) -> int:
        have = {
            (t.requirement_id, t.target_id)
            for t in self._repos.traces.find(project.id)
            if t.target_type == TraceTargetType.SCREEN
        }
        n = 0
        for rid in req_ids:
            if (rid, screen.id) in have or (rid, screen.code) in have:
                continue
            self._repos.traces.insert(
                RequirementTrace(
                    project_id=project.id,
                    requirement_id=rid,
                    target_type=TraceTargetType.SCREEN,
                    target_id=screen.id,
                    note="상세 설계(detail_designer)",
                )
            )
            n += 1
        return n

    # --- 검사·요약 ---------------------------------------------------------------------------------
    def consistency(self, project: Project) -> tuple[list[str], list[str]]:
        reqs = self._repos.requirements.find(project.id, order_by="id")
        st = self.settings_of(project)
        return design_consistency_issues(
            reqs,
            self.screens(project),
            self.tables(project),
            self.apis(project),
            self.modules(project),
            component_techs=[c.technology for c in self._repos.components.find(project.id)],
            research_stack=[
                x for t in self._repos.research.find(project.id) for x in t.recommended_stack
            ],
            rfp_specified_tech=[str(x) for x in st.rfp_specified_tech],
        )

    def summary(self, project: Project) -> str:
        fails, revs = self.consistency(project)
        return (
            f"상세 설계: 화면 {len(self.screens(project))}·테이블 {len(self.tables(project))}·API {len(self.apis(project))}"
            f"·모듈 {len(self.modules(project))}·업무 규칙 {len(self.rules(project))}, 모순·누락 {len(fails)}건, 검토 {len(revs)}건"
        )

    # --- 코드 생성 입력 패키지 (D-22) --------------------------------------------------------------------
    def codegen_package(self, project: Project) -> dict[str, Any]:
        """RFP_JAVA Developer 입력 모양: requirements(명세)·ui_design(화면)·architecture(모듈·API·데이터·규칙·테스트 계획)."""
        reqs = [
            r
            for r in self._repos.requirements.find(project.id, order_by="id")
            if r.acceptance_status != AcceptanceStatus.REJECTED and r.change_state != "deleted"
        ]
        screens = self.screens(project)
        tables = self.tables(project)
        apis = self.apis(project)
        modules = self.modules(project)
        code_to_name = (
            {s.code: s.name for s in screens}
            | {t.code: t.name for t in tables}
            | {m.code: m.path or m.name for m in modules}
        )
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project": {"id": project.id, "name": project.name},
            "requirements": {
                "business_purpose": (
                    ProjectSettings.from_project_settings(project.settings).description
                    or project.name
                ),
                "requirements": [
                    {
                        "requirement_id": r.id,
                        "title": r.name,
                        "description": r.description,
                        "category": r.type.value,
                        "priority": r.priority.value if r.priority else "",
                        "acceptance_criteria": [r.acceptance_criteria]
                        if r.acceptance_criteria
                        else [],
                        "verification_method": r.verification_method or "",
                        "source_reference": r.rfp_requirement_id or "",
                        "business_rules": (r.analysis or {}).get("business_rules", []),
                        "assumptions": [],
                        "unresolved_questions": [],
                    }
                    for r in reqs
                ],
            },
            "ui_design": {
                "screens": [
                    {
                        "screen_id": s.code or s.id,
                        "name": s.name,
                        "screen_type": s.screen_type,
                        "purpose": getattr(s, "purpose", ""),
                        "user_roles": getattr(s, "user_roles", []),
                        "layout": getattr(s, "layout", {}),
                        "fields": getattr(s, "fields", []),
                        "actions": getattr(s, "actions", []),
                        "states": getattr(s, "states", []),
                        "functions": getattr(s, "functions", []),
                        "requirement_ids": getattr(s, "related_requirement_ids", []),
                    }
                    for s in screens
                ]
            },
            "architecture": {
                "modules": [
                    {
                        "path": m.path or m.name,
                        "responsibility": m.description,
                        "depends_on": list(getattr(m, "depends_on", []) or []),
                        "requirement_ids": m.related_requirement_ids,
                        "layer": m.layer,
                    }
                    for m in modules
                ],
                "data_models": [
                    {
                        "name": t.name,
                        "logical_name": t.logical_name,
                        "db_engine": t.db_engine,
                        "fields": [
                            {
                                "name": c.name,
                                "type": c.data_type + (f"({c.length})" if c.length else ""),
                                "required": not c.nullable,
                                "pk": c.is_pk,
                                "fk_ref": c.fk_ref,
                                "personal_data": c.is_personal_data,
                                "description": c.description,
                            }
                            for c in t.columns
                        ],
                        "retention_policy": t.retention_policy,
                        "requirement_ids": t.related_requirement_ids,
                    }
                    for t in tables
                ],
                "api_endpoints": [
                    {
                        "api_id": a.code or a.id,
                        "method": a.method,
                        "path": a.path,
                        "description": a.request_schema.get("description", ""),
                        "request_body": ", ".join(a.request_schema.get("fields", [])),
                        "response": a.response_schema.get("description", ""),
                        "auth": a.auth,
                        "error_codes": a.error_codes,
                        "validation_rules": a.validation_rules,
                        "idempotency": a.idempotency,
                        "screens": [code_to_name.get(x, x) for x in a.related_screen_ids],
                        "tables": [code_to_name.get(x, x) for x in a.related_table_ids],
                        "requirement_ids": a.related_requirement_ids,
                    }
                    for a in apis
                ],
                "business_rules": [
                    {
                        "rule_id": d.name,
                        "description": d.description,
                        "enforced_in": (
                            d.decisions[0].replace("적용 모듈: ", "") if d.decisions else ""
                        ),
                        "requirement_ids": d.related_requirement_ids,
                    }
                    for d in self.rules(project)
                ],
                "test_plan": [],  # 단계 7 에서 테스트 케이스(TC) 로 채운다
            },
        }

    def export_codegen_package(self, project: Project, *, actor: str = "user") -> str:
        data = json.dumps(self.codegen_package(project), ensure_ascii=False, indent=1).encode(
            "utf-8"
        )
        name = self._files.next_version_name(
            project.output_dir, PACKAGE_SUBDIR, "codegen_package", ".json"
        )
        stored = self._files.save_bytes(project.output_dir, PACKAGE_SUBDIR, name, data)
        self._audit.record(
            project.id,
            "design.codegen_package",
            actor=actor,
            payload={"path": stored.relative_path},
        )
        return stored.relative_path


__all__ = ["PACKAGE_SUBDIR", "ROLE_DETAIL_DESIGNER", "DetailDesignService"]
