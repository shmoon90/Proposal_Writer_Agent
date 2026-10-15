"""공통 enum (DATA_MODEL.md 3절)."""

from __future__ import annotations

from enum import StrEnum


class ProjectMode(StrEnum):
    PROPOSAL = "proposal"
    BUILD = "build"

    @property
    def label(self) -> str:
        return {"proposal": "제안 단계", "build": "구축 단계"}[self.value]


class ProjectStatus(StrEnum):
    CREATED = "created"
    ANALYZING = "analyzing"
    REQUIREMENTS_REVIEW = "requirements_review"
    RESEARCHING = "researching"
    PLANNING = "planning"
    GENERATING = "generating"
    QA = "qa"
    APPROVED = "approved"
    ARCHIVED = "archived"


class DocumentKind(StrEnum):
    RFP = "rfp"
    RFP_ATTACHMENT = "rfp_attachment"
    REQUIREMENT_SPEC = "requirement_spec"
    TRACE_MATRIX = "trace_matrix"
    WBS = "wbs"
    STAFFING_PLAN = "staffing_plan"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {
            "rfp": "RFP",
            "rfp_attachment": "RFP 첨부",
            "requirement_spec": "요구사항 정의서",
            "trace_matrix": "요구사항 추적표",
            "wbs": "WBS",
            "staffing_plan": "인력 투입계획서",
            "other": "기타",
        }[self.value]


class ExtractionMethod(StrEnum):
    PENDING = "pending"
    TEXT = "text"
    OCR = "ocr"
    MIXED = "mixed"


class RequirementType(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"


class RequirementCategory(StrEnum):
    UI = "ui"
    BUSINESS = "business"
    DATA = "data"
    INTERFACE = "interface"
    REPORT = "report"
    ADMIN = "admin"
    PERFORMANCE = "performance"
    SECURITY = "security"
    AVAILABILITY = "availability"
    COMPATIBILITY = "compatibility"
    OPERABILITY = "operability"
    CONSTRAINT = "constraint"
    OTHER = "other"


class ScopeClass(StrEnum):
    MANDATORY = "mandatory"
    OPTIONAL_PROPOSAL = "optional_proposal"
    OUT_OF_SCOPE = "out_of_scope"


class AcceptanceStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class RequirementStatus(StrEnum):
    DRAFT = "draft"
    VERIFIED = "verified"
    BASELINE = "baseline"
    CHANGED = "changed"
    DELETED = "deleted"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChangeType(StrEnum):
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    RESTORE = "restore"


class ChangeStatus(StrEnum):
    REQUESTED = "requested"
    ANALYZED = "analyzed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    WITHDRAWN = "withdrawn"


class TraceTargetType(StrEnum):
    SCREEN = "screen"
    WBS_ITEM = "wbs_item"
    UNIT_TEST = "unit_test"
    INTEGRATION_TEST = "integration_test"
    COMPONENT = "component"
    DELIVERABLE = "deliverable"


class WBSLevel(StrEnum):
    PHASE = "phase"
    ACTIVITY = "activity"
    TASK = "task"


class DependencyType(StrEnum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


class DeliverableKind(StrEnum):
    REQUIREMENT_SPEC_XLSX = "requirement_spec_xlsx"
    TRACE_MATRIX_XLSX = "trace_matrix_xlsx"
    WBS_GANTT_XLSX = "wbs_gantt_xlsx"
    STAFFING_PLAN_XLSX = "staffing_plan_xlsx"
    SUBMISSION_PPTX = "submission_pptx"
    PRESENTATION_PPTX = "presentation_pptx"
    SYSTEM_DIAGRAM_PNG = "system_diagram_png"
    SW_DIAGRAM_PNG = "sw_diagram_png"
    SERVICE_DIAGRAM_PNG = "service_diagram_png"
    QA_REPORT_MD = "qa_report_md"
    PROJECT_SUMMARY_MD = "project_summary_md"


class IntegrityStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class QaStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"


class ValidationLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationTargetType(StrEnum):
    REQUIREMENT = "requirement"
    DELIVERABLE = "deliverable"
    PLAN = "plan"
    CHANGE = "change"
    DOCUMENT = "document"
    STEP = "step"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVED_WITH_COMMENTS = "approved_with_comments"


class ApprovalTarget(StrEnum):
    REQUIREMENT_SET = "requirement_set"
    RESEARCH = "research"
    PLAN = "plan"
    DELIVERABLE = "deliverable"
    CHANGE_REQUEST = "change_request"
    REVISION = "revision"
    STEP = "step"


class FeasibilityVerdict(StrEnum):
    FEASIBLE = "feasible"
    FEASIBLE_WITH_RISK = "feasible_with_risk"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"


class SourceTrust(StrEnum):
    OFFICIAL_DOC = "official_doc"
    VENDOR_GUIDE = "vendor_guide"
    STANDARD = "standard"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


class StepStatus(StrEnum):
    """파이프라인 단계 상태 (WORKFLOW_DESIGN.md 2절)."""

    PENDING = "pending"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def label(self) -> str:
        return {
            "pending": "대기",
            "running": "실행 중",
            "needs_review": "검토 필요",
            "approved": "승인",
            "failed": "실패",
            "skipped": "건너뜀",
        }[self.value]


class ActorKind(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
