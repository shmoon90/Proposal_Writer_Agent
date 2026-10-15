"""기존 산출물(Excel) → 기준 데이터 적재.

- 요구사항 정의서·추적표·WBS는 필수, 인력 투입계획은 선택. 업로드 원본은 ``01_RFP_Original``에 보존된다.
- 컬럼 매핑은 ``ingest.excel_reader``가 제안하고, 확신이 낮은 매핑은 사용자가 확정해야 적재한다.
- 기존 요구사항 ID는 그대로 유지한다(재발급 없음). 새 ID는 승인 후 ``LegacyIdScheme``으로 발급한다.
- 적재 결과는 Revision ``v1.0``(기준선)으로 기록하고, 스냅샷 JSON을 ``12_Revision_History``에 남긴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from proposal_agent.config.errors import ValidationError
from proposal_agent.config.logging import get_logger
from proposal_agent.config.paths import ProjectPaths
from proposal_agent.config.settings import Settings
from proposal_agent.ingest.excel_reader import (
    ParsedRow,
    WorkbookProfile,
    parse_date,
    parse_rows,
    profile_workbook,
)
from proposal_agent.models import (
    AcceptanceStatus,
    ActorKind,
    Dependency,
    DependencyType,
    DocumentKind,
    HistoryEntry,
    IntegrationTest,
    Priority,
    Project,
    Requirement,
    RequirementStatus,
    RequirementTrace,
    RequirementType,
    ReviewStatus,
    Revision,
    Screen,
    SourceDocument,
    StaffRole,
    TraceTargetType,
    UnitTest,
    VerificationStatus,
    WBSItem,
    WBSLevel,
    utcnow,
)
from proposal_agent.models.planning import TaskStatus
from proposal_agent.requirements.id_policy import LegacyIdScheme
from proposal_agent.storage.files import FileStore
from proposal_agent.storage.repositories import Repositories

if TYPE_CHECKING:
    from proposal_agent.services.audit import AuditService

log = get_logger("changes.baseline")

REVISION_SUBDIR = "12_Revision_History"
BASELINE_REQUIRED: tuple[DocumentKind, ...] = (
    DocumentKind.REQUIREMENT_SPEC,
    DocumentKind.TRACE_MATRIX,
    DocumentKind.WBS,
)
SHEET_TYPE_HINTS: dict[str, RequirementType] = {
    "기능요구사항": RequirementType.FUNCTIONAL,
    "비기능요구사항": RequirementType.NON_FUNCTIONAL,
}
TYPE_WORDS: dict[str, RequirementType] = {  # 순서 중요: '비기능'을 '기능'보다 먼저 검사
    "비기능": RequirementType.NON_FUNCTIONAL,
    "non_functional": RequirementType.NON_FUNCTIONAL,
    "non-functional": RequirementType.NON_FUNCTIONAL,
    "기능": RequirementType.FUNCTIONAL,
    "functional": RequirementType.FUNCTIONAL,
    "제약": RequirementType.CONSTRAINT,
    "constraint": RequirementType.CONSTRAINT,
    "평가": RequirementType.EVALUATION,
    "evaluation": RequirementType.EVALUATION,
    "제출": RequirementType.SUBMISSION,
    "submission": RequirementType.SUBMISSION,
}
ACCEPT_WORDS: dict[str, AcceptanceStatus] = {
    "수용": AcceptanceStatus.ACCEPTED,
    "조건부 수용": AcceptanceStatus.PARTIALLY_ACCEPTED,
    "미수용": AcceptanceStatus.REJECTED,
    "검토 필요": AcceptanceStatus.PROPOSED,
}
PENDING_VALUES = {"", "미정", "-", "none", "n/a"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def split_ids(value: Any) -> list[str]:
    text = _text(value)
    if text.casefold() in PENDING_VALUES:
        return []
    out: list[str] = []
    for part in text.replace(";", ",").replace("/", ",").replace("\n", ",").split(","):
        p = part.strip()
        if p and p.casefold() not in PENDING_VALUES and p not in out:
            out.append(p)
    return out


def _decimal(value: Any) -> Decimal:
    text = _text(value).replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def infer_type(row: dict[str, Any], prefixes: dict[str, str]) -> RequirementType:
    sheet = str(row.get("_sheet", ""))
    if sheet in SHEET_TYPE_HINTS:
        return SHEET_TYPE_HINTS[sheet]
    word = _text(row.get("type")).casefold()
    for key, t in TYPE_WORDS.items():
        if key in word:
            return t
    rid = _text(row.get("requirement_id"))
    for type_value, prefix in prefixes.items():
        if rid.upper().startswith(prefix.upper()):
            return RequirementType(type_value)
    if sheet == "제약·평가·제출조건":
        return RequirementType.CONSTRAINT
    return RequirementType.FUNCTIONAL


@dataclass
class DocumentProfile:
    document: SourceDocument
    profile: WorkbookProfile
    confirmed: bool
    overrides: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def blocking(self) -> list[str]:
        """확정되지 않은 필수 컬럼 (사용자 확인 필요)."""
        out: list[str] = []
        for sheet in self.profile.sheets:
            for col in sheet.columns:
                if col.needs_confirmation and col.field not in self.overrides.get(sheet.sheet, {}):
                    out.append(f"{sheet.sheet}.{col.field}")
        return out


@dataclass
class BaselineLoadResult:
    revision: Revision
    requirements: int = 0
    traces: int = 0
    screens: int = 0
    unit_tests: int = 0
    integration_tests: int = 0
    wbs_items: int = 0
    dependencies: int = 0
    roles: int = 0
    staffing_plan_present: bool = False
    warnings: list[str] = field(default_factory=list)
    id_scheme: str | None = None
    snapshot_path: str | None = None


class BaselineService:
    def __init__(
        self,
        repos: Repositories,
        paths: ProjectPaths,
        settings: Settings,
        audit: AuditService,
        files: FileStore,
    ) -> None:
        self._repos = repos
        self._paths = paths
        self._settings = settings
        self._audit = audit
        self._files = files

    # --- 문서 구조 분석 ----------------------------------------------------------------------
    def _read(self, doc: SourceDocument) -> bytes:
        return self._paths.resolve_output(doc.stored_path).read_bytes()

    def baseline_documents(self, project: Project) -> dict[DocumentKind, SourceDocument]:
        out: dict[DocumentKind, SourceDocument] = {}
        for d in self._repos.documents.find(project.id, order_by="created_at"):
            if d.kind in (*BASELINE_REQUIRED, DocumentKind.STAFFING_PLAN):
                out[d.kind] = d  # 같은 종류가 여러 개면 가장 최근 업로드
        return out

    def profile_document(self, project: Project, doc: SourceDocument) -> DocumentProfile:
        """매핑 제안을 만들고 ``SourceDocument.column_mapping``에 저장한다 (확정 전)."""
        profile = profile_workbook(self._read(doc), doc.kind)
        saved = doc.column_mapping or {}
        confirmed = bool(saved.get("confirmed"))
        overrides = {k: dict(v) for k, v in (saved.get("overrides") or {}).items()}
        if not saved.get("proposal"):
            doc.column_mapping = {
                "proposal": [s.to_dict() for s in profile.sheets],
                "needs_confirmation": profile.needs_confirmation,
                "quality": profile.quality + [w for s in profile.sheets for w in s.warnings],
                "confirmed": confirmed,
                "overrides": overrides,
            }
            self._repos.documents.update(doc)
        return DocumentProfile(
            document=doc, profile=profile, confirmed=confirmed, overrides=overrides
        )

    def confirm_mapping(
        self,
        project: Project,
        doc: SourceDocument,
        overrides: dict[str, dict[str, int]],
        *,
        actor: str = "user",
    ) -> DocumentProfile:
        """사용자가 확인한 컬럼 매핑을 저장한다. 사용자 입력은 AI/규칙 제안과 구분해 기록한다."""
        prof = self.profile_document(project, doc)
        merged = {**prof.overrides}
        for sheet, cols in overrides.items():
            merged.setdefault(sheet, {}).update({k: int(v) for k, v in cols.items()})
        mapping = dict(doc.column_mapping or {})
        mapping.update(
            {
                "confirmed": True,
                "overrides": merged,
                "confirmed_by": actor,
                "confirmed_at": utcnow().isoformat(),
            }
        )
        doc.column_mapping = mapping
        self._repos.documents.update(doc)
        self._audit.record(
            project.id,
            "baseline.mapping_confirmed",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="SourceDocument",
            entity_id=doc.id,
            payload={"kind": doc.kind.value, "overrides": merged},
        )
        return DocumentProfile(document=doc, profile=prof.profile, confirmed=True, overrides=merged)

    def profiles(self, project: Project) -> dict[DocumentKind, DocumentProfile]:
        return {
            k: self.profile_document(project, d)
            for k, d in self.baseline_documents(project).items()
        }

    # --- 적재 ----------------------------------------------------------------------------------
    def load(self, project: Project, *, actor: str = "user") -> BaselineLoadResult:
        docs = self.baseline_documents(project)
        missing = [k.value for k in BASELINE_REQUIRED if k not in docs]
        if missing:
            raise ValidationError(
                "기준 문서가 부족합니다: " + ", ".join(missing),
                resolution="요구사항 정의서·요구사항 추적표·WBS를 모두 업로드하십시오.",
            )
        profiles = {k: self.profile_document(project, d) for k, d in docs.items()}
        blocking = {
            k.value: p.blocking for k, p in profiles.items() if p.blocking and not p.confirmed
        }
        if blocking:
            raise ValidationError(
                "컬럼 매핑 확인이 필요한 문서가 있습니다.",
                cause="; ".join(f"{k}: {', '.join(v)}" for k, v in blocking.items()),
                resolution="문서 구조 화면에서 제안된 매핑을 확인·수정한 뒤 적재하십시오.",
                detail=blocking,
            )
        rows = {
            k: parse_rows(self._read(p.document), p.profile, overrides=p.overrides)
            for k, p in profiles.items()
        }
        warnings: list[str] = []
        for p in profiles.values():
            warnings.extend(p.profile.quality)
            for s in p.profile.sheets:
                warnings.extend(s.warnings)

        with self._repos.db.transaction():
            req_count, scheme = self._load_requirements(
                project, rows[DocumentKind.REQUIREMENT_SPEC], actor, warnings
            )
            trace_stats = self._load_traces(project, rows[DocumentKind.TRACE_MATRIX], warnings)
            wbs_count, dep_count = self._load_wbs(project, rows[DocumentKind.WBS], warnings)
            role_count = 0
            if DocumentKind.STAFFING_PLAN in rows:
                role_count = self._load_roles(project, rows[DocumentKind.STAFFING_PLAN], warnings)
            revision = self._record_revision(project, docs, actor)
        result = BaselineLoadResult(
            revision=revision,
            requirements=req_count,
            traces=trace_stats["traces"],
            screens=trace_stats["screens"],
            unit_tests=trace_stats["unit_tests"],
            integration_tests=trace_stats["integration_tests"],
            wbs_items=wbs_count,
            dependencies=dep_count,
            roles=role_count,
            staffing_plan_present=DocumentKind.STAFFING_PLAN in rows,
            warnings=warnings,
            id_scheme=f"{scheme.prefix}{'0' * scheme.width}" if scheme else None,
            snapshot_path=revision.snapshot_path,
        )
        self._audit.record(
            project.id,
            "baseline.loaded",
            actor=actor,
            actor_kind=ActorKind.USER,
            entity_type="Revision",
            entity_id=revision.id,
            payload={k: v for k, v in result.__dict__.items() if k not in ("revision", "warnings")},
        )
        log.info(
            "기준선 적재 %s: 요구사항 %d, WBS %d, 추적 %d",
            project.id,
            req_count,
            wbs_count,
            trace_stats["traces"],
        )
        return result

    # 요구사항 ---------------------------------------------------------------------------------
    def _load_requirements(
        self, project: Project, rows: list[ParsedRow], actor: str, warnings: list[str]
    ) -> tuple[int, LegacyIdScheme | None]:
        prefixes = {**self._settings.id_prefixes, **(project.settings.get("id_prefixes") or {})}
        existing = {r.id: r for r in self._repos.requirements.find(project.id)}
        seen: set[str] = set()
        count = 0
        for pr in rows:
            v = pr.values
            rid = _text(v.get("requirement_id"))
            name = _text(v.get("name"))
            if not rid:
                continue
            if rid in seen:
                warnings.append(f"{pr.sheet} {pr.row}행: 요구사항 ID {rid} 중복 — 첫 행만 적재")
                continue
            seen.add(rid)
            if not name:
                warnings.append(
                    f"{pr.sheet} {pr.row}행: {rid} 요구사항 명이 비어 있어 '(이름 없음)'으로 적재"
                )
                name = "(이름 없음)"
            req_type = infer_type(v, prefixes)
            accept = ACCEPT_WORDS.get(_text(v.get("acceptance")), AcceptanceStatus.ACCEPTED)
            added_on = parse_date(v.get("added_on"))
            fields: dict[str, Any] = {
                "name": name,
                "description": _text(v.get("description")),
                "type": req_type,
                "implementation_approach": _text(v.get("implementation")) or None,
                "acceptance_status": accept,
                "notes": _text(v.get("notes")),
                "priority": _priority(_text(v.get("priority"))),
                "is_mandatory": _text(v.get("mandatory"))
                not in ("N", "아니오", "no", "false", "선택"),
                "added_by": _text(v.get("added_by")) or None,
                "added_on": added_on,
            }
            if rid in existing:
                req = existing[rid]
                before = {k: getattr(req, k) for k in fields}
                changed = {
                    k: (str(before[k]), str(val)) for k, val in fields.items() if before[k] != val
                }
                for k, val in fields.items():
                    setattr(req, k, val)
                if changed:
                    req.add_history(
                        actor,
                        "baseline.reload",
                        changes=changed,
                        note=f"{pr.sheet} {pr.row}행 재적재",
                    )
                req.touch()
                self._repos.requirements.update(req)
            else:
                req = Requirement(
                    id=rid,
                    project_id=project.id,
                    status=RequirementStatus.BASELINE,
                    verification_status=VerificationStatus.VERIFIED,
                    review_status=ReviewStatus.APPROVED,
                    created_by=actor,
                    source_refs=[],
                    rationale=f"기준 문서 적재 ({pr.sheet} {pr.row}행)",
                    **fields,
                )
                req.history.append(
                    HistoryEntry(
                        at=utcnow().isoformat(),
                        actor=actor,
                        action="baseline.load",
                        note=f"{pr.sheet} {pr.row}행",
                    )
                )
                self._repos.requirements.insert(req)
            count += 1
        scheme = LegacyIdScheme.infer(seen)
        if scheme:
            self._repos.sequences.ensure_at_least(
                project.id, f"legacy:{scheme.prefix}", scheme.max_number(seen) + 1
            )
        else:
            warnings.append(
                "요구사항 ID 체계를 추론하지 못했습니다. 새 ID는 설정된 접두사(FR-/NFR-…)로 발급됩니다."
            )
        return count, scheme

    # 추적표 -----------------------------------------------------------------------------------
    def _load_traces(
        self, project: Project, rows: list[ParsedRow], warnings: list[str]
    ) -> dict[str, int]:
        req_ids = {r.id for r in self._repos.requirements.find(project.id)}
        self._repos.traces.clear_project(project.id)
        self._repos.screens.clear_project(project.id)
        self._repos.unit_tests.clear_project(project.id)
        self._repos.integration_tests.clear_project(project.id)
        screens: dict[str, Screen] = {}
        uts: dict[str, UnitTest] = {}
        its: dict[str, IntegrationTest] = {}
        traces = 0
        for pr in rows:
            v = pr.values
            rid = _text(v.get("requirement_id"))
            if not rid:
                continue
            if rid not in req_ids:
                warnings.append(
                    f"추적표 {pr.row}행: 요구사항 {rid}가 정의서에 없음 (추적 항목은 적재, 요구사항은 '정의서 누락'으로 표시)"
                )
            name = _text(v.get("name")) or rid
            review_status = _text(v.get("review_status")) or "유효"
            review_reason = _text(v.get("review_reason"))
            for sid in split_ids(v.get("screen_id")):
                screens.setdefault(
                    sid,
                    Screen(
                        code=sid,
                        project_id=project.id,
                        name=f"화면 {sid} ({name})",
                        status="baseline",
                    ),
                )
                self._repos.traces.insert(
                    RequirementTrace(
                        project_id=project.id,
                        requirement_id=rid,
                        target_type=TraceTargetType.SCREEN,
                        target_id=sid,
                        review_status=review_status,
                        review_reason=review_reason,
                    )
                )
                traces += 1
            ut_result = _text(v.get("unit_test_result"))
            for tid in split_ids(v.get("unit_test_id")):
                uts.setdefault(
                    tid,
                    UnitTest(
                        code=tid,
                        project_id=project.id,
                        name=f"단위테스트 {tid} ({name})",
                        status=ut_result or "미실행",
                    ),
                )
                self._repos.traces.insert(
                    RequirementTrace(
                        project_id=project.id,
                        requirement_id=rid,
                        target_type=TraceTargetType.UNIT_TEST,
                        target_id=tid,
                        note=ut_result or None,
                        review_status=review_status,
                        review_reason=review_reason,
                    )
                )
                traces += 1
            it_result = _text(v.get("integration_test_result"))
            for tid in split_ids(v.get("integration_test_id")):
                its.setdefault(
                    tid,
                    IntegrationTest(
                        code=tid,
                        project_id=project.id,
                        name=f"통합테스트 {tid} ({name})",
                        status=it_result or "미실행",
                    ),
                )
                self._repos.traces.insert(
                    RequirementTrace(
                        project_id=project.id,
                        requirement_id=rid,
                        target_type=TraceTargetType.INTEGRATION_TEST,
                        target_id=tid,
                        note=it_result or None,
                        review_status=review_status,
                        review_reason=review_reason,
                    )
                )
                traces += 1
            for code in split_ids(v.get("wbs")):
                self._repos.traces.insert(
                    RequirementTrace(
                        project_id=project.id,
                        requirement_id=rid,
                        target_type=TraceTargetType.WBS_ITEM,
                        target_id=code,
                        note="wbs_code",
                        review_status=review_status,
                        review_reason=review_reason,
                    )
                )
                traces += 1
        for s in screens.values():
            self._repos.screens.insert(s)
        for u in uts.values():
            self._repos.unit_tests.insert(u)
        for i in its.values():
            self._repos.integration_tests.insert(i)
        return {
            "traces": traces,
            "screens": len(screens),
            "unit_tests": len(uts),
            "integration_tests": len(its),
        }

    # WBS --------------------------------------------------------------------------------------
    def _load_wbs(
        self, project: Project, rows: list[ParsedRow], warnings: list[str]
    ) -> tuple[int, int]:
        self._repos.wbs.clear_project(project.id)
        self._repos.dependencies.clear_project(project.id)
        self._repos.allocations.clear_project(project.id)
        items: dict[str, WBSItem] = {}
        parent_codes: dict[str, str | None] = {}
        preds: dict[str, list[str]] = {}
        dep_rows: list[tuple[str, str, str, int]] = []
        order = 0
        for pr in rows:
            v = pr.values
            if pr.sheet == "의존관계":
                a, b = _text(v.get("pred")), _text(v.get("succ"))
                if a and b:
                    dep_rows.append(
                        (a, b, _text(v.get("dep_type")) or "FS", int(_decimal(v.get("lag"))))
                    )
                continue
            code = _text(v.get("wbs_id"))
            name = _text(v.get("name"))
            if not code or code in items:
                if code:
                    warnings.append(f"WBS {pr.row}행: 코드 {code} 중복 — 첫 행만 적재")
                continue
            depth = code.count(".") + 1
            level = (
                WBSLevel.PHASE if depth == 1 else WBSLevel.ACTIVITY if depth == 2 else WBSLevel.TASK
            )
            parent = _text(v.get("parent_id")) or (code.rsplit(".", 1)[0] if "." in code else None)
            parent_codes[code] = parent or None
            order += 1
            start = parse_date(v.get("planned_start"))
            end = parse_date(v.get("planned_end"))
            duration = int(_decimal(v.get("duration"))) or None
            status_text = _text(v.get("status"))
            try:
                status = TaskStatus(status_text) if status_text else TaskStatus.PLANNED
            except ValueError:
                status = TaskStatus.PLANNED
            items[code] = WBSItem(
                project_id=project.id,
                code=code,
                level=level,
                name=name or f"(이름 없음 {code})",
                description=_text(v.get("description")),
                related_requirement_ids=split_ids(v.get("requirement_id")),
                role=_text(v.get("role")),
                planned_start=start,
                planned_end=end,
                actual_start=parse_date(v.get("actual_start")),
                actual_end=parse_date(v.get("actual_end")),
                duration_days=duration,
                effort_md=_decimal(v.get("effort_md")),
                estimate_basis=_text(v.get("basis")) or "기준 문서 값",
                status=status,
                roles=[{"role": _text(v.get("role")), "ratio": "1"}]
                if _text(v.get("role"))
                else [],
                order=order,
                notes=_text(v.get("notes")),
            )
            preds[code] = split_ids(v.get("predecessors"))
        for code, item in items.items():
            p = parent_codes[code]
            if p and p in items:
                item.parent_id = items[p].id
            elif p:
                warnings.append(f"WBS {code}: 상위 코드 {p}를 찾지 못해 최상위로 적재")
            self._repos.wbs.insert(item)
        dep_count = 0
        seen_pairs: set[tuple[str, str]] = set()
        for code, plist in preds.items():
            for p in plist:
                dep_rows.append((p, code, "FS", 0))
        for p, s, t, lag in dep_rows:
            if (p, s) in seen_pairs:
                continue
            if p not in items or s not in items:
                warnings.append(f"WBS 의존 {p}→{s}: 존재하지 않는 코드 참조 (무시)")
                continue
            seen_pairs.add((p, s))
            try:
                dtype = DependencyType(t.upper())
            except ValueError:
                dtype = DependencyType.FS
            self._repos.dependencies.insert(
                Dependency(
                    project_id=project.id,
                    predecessor_id=items[p].id,
                    successor_id=items[s].id,
                    type=dtype,
                    lag_days=lag,
                )
            )
            dep_count += 1
        return len(items), dep_count

    # 인력 -------------------------------------------------------------------------------------
    def _load_roles(self, project: Project, rows: list[ParsedRow], warnings: list[str]) -> int:
        self._repos.staff_roles.clear_project(project.id)
        count = 0
        seen: set[str] = set()
        for pr in rows:
            v = pr.values
            role = _text(v.get("role"))
            if not role or role in seen or role in ("합계", "총계"):
                continue
            seen.add(role)
            unit = _decimal(v.get("unit_cost"))
            mm = _decimal(v.get("effort_mm"))
            self._repos.staff_roles.insert(
                StaffRole(
                    project_id=project.id,
                    role_name=role,
                    organization=_text(v.get("organization")),
                    grade=_text(v.get("grade")) or None,
                    skills=split_ids(v.get("skills")),
                    duties=_text(v.get("duties")),
                    unit_cost_per_mm=unit if unit > 0 else None,
                    headcount_planned=max(1, int(_decimal(v.get("headcount")) or 1)),
                    notes=f"기준 공수 {mm} MM; 투입 {parse_date(v.get('start'))}~{parse_date(v.get('end'))}"
                    if mm
                    else "",
                )
            )
            count += 1
        if not count:
            warnings.append(
                "인력 투입계획에서 역할을 읽지 못했습니다. 인력 영향은 시나리오 6(사용자 판단)으로 처리됩니다."
            )
        return count

    # Revision ---------------------------------------------------------------------------------
    def _record_revision(
        self, project: Project, docs: dict[DocumentKind, SourceDocument], actor: str
    ) -> Revision:
        snapshot = self.snapshot(project)
        name = self._files.next_version_name(
            project.output_dir, REVISION_SUBDIR, "baseline_snapshot", ".json"
        )
        stored = self._files.save_bytes(
            project.output_dir,
            REVISION_SUBDIR,
            name,
            json.dumps(snapshot, ensure_ascii=False, indent=1, default=str).encode("utf-8"),
        )
        existing = self._repos.revisions.find(project.id, order_by="created_at")
        number = "v1.0" if not existing else f"v{len(existing) + 1}.0"
        rev = Revision(
            project_id=project.id,
            number=number,
            label="기준선 적재",
            reason="기존 산출물 업로드·적재",
            snapshot_path=stored.relative_path,
            parent_revision_id=existing[-1].id if existing else None,
            created_by=actor,
        )
        rev.change_ids = [d.id for d in docs.values()]
        self._repos.revisions.insert(rev)
        project.baseline_revision_id = rev.id
        self._repos.projects.update(project)
        return rev

    def snapshot(self, project: Project) -> dict[str, Any]:
        """현재 기준 데이터 전체 스냅샷 (Revision 비교·롤백 근거)."""
        return {
            "project_id": project.id,
            "taken_at": utcnow().isoformat(),
            "requirements": [
                r.model_dump(mode="json")
                for r in self._repos.requirements.find(project.id, order_by="id")
            ],
            "traces": [t.model_dump(mode="json") for t in self._repos.traces.find(project.id)],
            "wbs": [w.model_dump(mode="json") for w in self._repos.wbs.tree(project.id)],
            "dependencies": [
                d.model_dump(mode="json") for d in self._repos.dependencies.find(project.id)
            ],
            "roles": [r.model_dump(mode="json") for r in self._repos.staff_roles.find(project.id)],
        }


def _priority(text: str) -> Priority:
    t = text.casefold()
    if t in ("상", "high", "높음", "1"):
        return Priority.HIGH
    if t in ("하", "low", "낮음", "3"):
        return Priority.LOW
    return Priority.MEDIUM
