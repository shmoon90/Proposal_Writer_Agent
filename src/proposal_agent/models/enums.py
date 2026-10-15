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
    PROPOSAL_TEMPLATE = "proposal_template"
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
            "proposal_template": "제안서 템플릿(PPT)",
            "other": "기타",
        }[self.value]


class ExtractionMethod(StrEnum):
    PENDING = "pending"
    TEXT = "text"
    OCR = "ocr"
    MIXED = "mixed"


class RequirementType(StrEnum):
    """요구사항 종류. 기능/비기능을 명확히 분리하고 제약·평가·제출 조건은 별도 종류로 둔다."""

    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"
    EVALUATION = "evaluation"
    SUBMISSION = "submission"

    @property
    def label(self) -> str:
        return {
            "functional": "기능",
            "non_functional": "비기능",
            "constraint": "제약사항",
            "evaluation": "평가 기준",
            "submission": "제출 조건",
        }[self.value]


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
    """범위 분류 (4단계)."""

    MANDATORY = "mandatory"  # 1. RFP 필수
    SUPPORTING = "supporting"  # 2. 필수 구현에 필요한 지원 범위
    OPTIONAL_PROPOSAL = "optional_proposal"  # 3. 선택적 부가 제안
    OUT_OF_SCOPE = "out_of_scope"  # 4. 불필요하거나 위험한 과잉 범위

    @property
    def label(self) -> str:
        return {
            "mandatory": "RFP 필수",
            "supporting": "지원 범위",
            "optional_proposal": "부가 제안",
            "out_of_scope": "과잉 범위",
        }[self.value]


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


class ReviewStatus(StrEnum):
    """사람 검토 상태."""

    PENDING = "pending"
    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"


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
    ERROR = "error"  # 반영 중 오류 → 기준 데이터 롤백, 재시도 가능


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


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class FileFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    UNSUPPORTED = "unsupported"


class ExtractionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"  # 일부 페이지 실패/저품질
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class BlockType(StrEnum):
    TITLE = "title"
    HEADING = "heading"
    TOC = "toc"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_CELL = "table_cell"
    PAGE_TEXT = "page_text"  # OCR/PDF 페이지 단위 텍스트
    APPENDIX = "appendix"


class ActorKind(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
