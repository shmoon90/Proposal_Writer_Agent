"""에이전트 구조화 출력 스키마 (9개 역할).

모든 스키마는 Pydantic v2 모델이며 ``model_json_schema()`` 결과가 Agent SDK ``output_format``에 그대로 들어간다.
ID·날짜·공수 합계 등 결정적 값은 스키마에서 받지 않거나 "제안값"으로만 받고 코드가 재계산한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models import RequirementDraft, VerificationReport
from proposal_agent.models.enums import FeasibilityVerdict, SourceTrust


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- 1. RFP 문서 분석 ------------------------------------------------------------------------


class RfpSection(_Strict):
    title: str
    summary: str = ""
    source_block_ids: list[str] = Field(default_factory=list)


class RfpAnalysis(_Strict):
    """RFP 분석가 출력: 사업 개요·범위·제약·평가·일정·예산 힌트."""

    overview: str = Field(description="사업 목적과 배경 요약 (원문 근거)")
    client_goals: list[str] = Field(default_factory=list)
    scope_summary: str = ""
    sections: list[RfpSection] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(default_factory=list)
    schedule_hints: list[str] = Field(
        default_factory=list, description="기간·마일스톤 관련 원문 문구"
    )
    budget_hints: list[str] = Field(default_factory=list)
    named_solutions: list[str] = Field(
        default_factory=list, description="원문에 명시된 제품·솔루션·기술 명칭"
    )
    integration_targets: list[str] = Field(default_factory=list, description="연계 대상 시스템")
    uncertainties: list[str] = Field(
        default_factory=list, description="원문만으로 판단할 수 없는 항목"
    )


# --- 2·3. 요구사항 추출·검증 --------------------------------------------------------------------


class RequirementExtraction(_Strict):
    """추출 에이전트 출력."""

    requirements: list[RequirementDraft] = Field(default_factory=list)
    unresolved_items: list[str] = Field(
        default_factory=list,
        description="요구사항인지 판단하기 어려워 사람 검토가 필요한 원문 항목",
    )
    notes: str = Field(
        default="", description="청크 전반에 대한 짧은 메모 (표/이미지 누락 의심 등)"
    )


# --- 4. 기술 조사 --------------------------------------------------------------------------------


class ResearchSourceDraft(_Strict):
    url: str = Field(description="실제로 열람한 URL. 열람하지 않은 URL은 적지 않는다")
    title: str = ""
    product: str = Field(default="", description="제품·프레임워크 이름")
    version: str = Field(default="", description="문서가 다루는 제품 버전 (명시된 경우만)")
    trust: SourceTrust = Field(
        default=SourceTrust.UNKNOWN,
        description="official_doc/vendor_guide/standard/community/unknown",
    )
    excerpt: str = Field(default="", description="근거가 된 문장 (요약 아닌 인용)")


class ResearchItemDraft(_Strict):
    topic: str
    related_requirement_ids: list[str] = Field(default_factory=list)
    summary: str
    confirmed_facts: list[str] = Field(default_factory=list, description="출처로 확인한 사실만")
    applicability_conditions: list[str] = Field(default_factory=list, description="적용 조건·제약")
    unverified_items: list[str] = Field(
        default_factory=list, description="출처를 찾지 못했거나 확인하지 못한 항목"
    )
    impact_on_implementation: str = ""
    impact_on_proposal: str = ""
    feasibility: FeasibilityVerdict = FeasibilityVerdict.UNKNOWN
    risks: list[str] = Field(default_factory=list)
    recommended_stack: list[str] = Field(default_factory=list)
    sources: list[ResearchSourceDraft] = Field(default_factory=list)


class TechAlternative(_Strict):
    name: str = Field(description="예: Java/Spring Boot, Node.js/NestJS, .NET 8, Python/Django")
    scores: dict[str, str] = Field(
        default_factory=dict, description="비교 기준 → 평가 요약 (상/중/하 + 근거)"
    )
    license_and_cost: str = ""
    notes: str = ""
    sources: list[ResearchSourceDraft] = Field(default_factory=list)


class FeasibilityComparison(_Strict):
    area: str = Field(description="framework/ui_ux/web_was/db/api/security/deploy_ops")
    rfp_specified: str | None = Field(default=None, description="RFP가 명시한 기술 (있으면 우선)")
    alternatives: list[TechAlternative] = Field(default_factory=list)
    recommendation: str = ""
    rationale: str = ""
    unverified_items: list[str] = Field(default_factory=list)


class ResearchReport(_Strict):
    items: list[ResearchItemDraft] = Field(default_factory=list)
    comparisons: list[FeasibilityComparison] = Field(default_factory=list)
    notes: str = ""


# --- 5. 아키텍처 ---------------------------------------------------------------------------------


class ComponentDraft(_Strict):
    code: str = Field(description="컴포넌트 식별 코드 (예: WEB01). ID는 코드가 발급")
    layer: str = Field(description="client/web/app/data/integration/infra/security")
    name: str
    technology: str = ""
    description: str = ""
    related_requirement_ids: list[str] = Field(default_factory=list)
    diagram_kinds: list[str] = Field(
        default_factory=list, description="system/sw/service 중 포함될 도면"
    )


class ConnectionDraft(_Strict):
    from_code: str
    to_code: str
    protocol: str = ""
    note: str = ""


class ArchitectureDraft(_Strict):
    components: list[ComponentDraft] = Field(default_factory=list)
    connections: list[ConnectionDraft] = Field(default_factory=list)
    diagram_notes: str = ""
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


# --- 6. WBS·일정·공수 ----------------------------------------------------------------------------


class WbsItemDraft(_Strict):
    code: str = Field(description="WBS 코드 (1, 1.1, 1.1.1)")
    parent_code: str | None = None
    level: str = Field(description="phase/activity/task")
    name: str
    description: str = ""
    effort_md_estimate: float = Field(
        default=0.0, ge=0, description="공수 제안값(M/D). 합계·일정은 코드가 계산"
    )
    estimate_basis: str = Field(description="산정 근거 (필수)")
    deliverables: list[str] = Field(default_factory=list)
    roles: list[dict[str, str]] = Field(default_factory=list, description="[{role, ratio}]")
    related_requirement_ids: list[str] = Field(default_factory=list)


class DependencyDraft(_Strict):
    predecessor_code: str
    successor_code: str
    type: str = Field(default="FS", description="FS/SS/FF/SF")
    lag_days: int = 0


class WBSDraft(_Strict):
    """날짜는 받지 않는다. 일정은 planning/scheduler.py가 계산한다."""

    items: list[WbsItemDraft] = Field(default_factory=list)
    dependencies: list[DependencyDraft] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


# --- 7. 제안서 작성 ------------------------------------------------------------------------------


class VisualItem(_Strict):
    id: str = Field(default="", description="노드 식별자 (dataflow/process 연결용)")
    title: str
    text: str = ""
    group: str = Field(
        default="",
        description="열·그룹 (two_column: left/right, screen: nav/본문, dataflow: 시스템명)",
    )


class VisualEdge(_Strict):
    source: str
    target: str
    label: str = ""


class VisualSpec(_Strict):
    """소절 도식 명세. 코드가 편집 가능한 도형·연결선으로 그린다 (그림 삽입 없음)."""

    kind: str = Field(
        description="cards(배경·목표·전략 카드) | flow(단계 흐름·절차) | process(호출 순서) | two_column(현황·이슈 ↔ 방안) | "
        "dataflow(데이터 흐름: items=노드(group=시스템), edges=연결) | screen(화면 설계: items=영역, group=nav는 좌측 메뉴) | "
        "kpis(핵심 수치: title=라벨, text=값) | compare(비교 표: headers/rows)"
    )
    title: str = ""
    items: list[VisualItem] = Field(default_factory=list)
    edges: list[VisualEdge] = Field(default_factory=list)
    left_title: str = ""
    right_title: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class ProposalSection(_Strict):
    slide_group: str = Field(
        description="cover/toc/understanding/requirements/architecture/schedule/staffing/quality/risk/closing"
    )
    title: str
    bullets: list[str] = Field(default_factory=list)
    body: str = ""
    speaker_notes: str = ""
    data_refs: list[str] = Field(default_factory=list, description="참조한 요구사항·조사·WBS ID")
    # Phase 12: 템플릿·RFP 지정 목차 구조 (모두 선택)
    chapter: str = Field(default="", description="장 (예: 'Ⅲ. 사업수행 부문') — RFP 지정 목차의 장")
    section: str = Field(default="", description="절 (예: '2. 제안 시스템 주요 기능')")
    number: str = Field(default="", description="소절 번호 (예: '2.1')")
    lead_message: str = Field(default="", description="소절 첫 슬라이드 상단 리드 메시지 1~2문장")
    table_headers: list[str] = Field(default_factory=list, description="표가 필요하면 머리글")
    table_rows: list[list[str]] = Field(
        default_factory=list, description="표 행 (머리글 수와 같은 길이)"
    )
    requirement_ids: list[str] = Field(
        default_factory=list, description="이 소절이 대응하는 요구사항 ID (RFP ID 포함 가능)"
    )
    footnotes: list[str] = Field(
        default_factory=list, description="슬라이드 하단 ※ 주석 (전제·협의 사항)"
    )
    visual: VisualSpec | None = Field(
        default=None,
        description="소절 도식 (배경·목표·구조·데이터 흐름·호출 절차·화면 설계 등). 발표용은 소절마다 권장",
    )
    feasibility_basis: list[str] = Field(
        default_factory=list,
        description="이 소절 구현 방안의 근거 조사 주제 (tech_researcher 기록의 topic)",
    )


class ProposalContent(_Strict):
    profile: str = Field(description="submission(제출용) 또는 presentation(발표용)")
    sections: list[ProposalSection] = Field(default_factory=list)
    key_messages: list[str] = Field(default_factory=list)
    unverified_claims: list[str] = Field(
        default_factory=list, description="근거 데이터가 없어 사람 확인이 필요한 문구"
    )


# --- 8. 문서 생성 (문서 구조·내용 명세; 파일은 generators 코드가 만든다) -------------------------------


class DocumentSpec(_Strict):
    deliverable_kind: str = Field(
        description="requirement_spec_xlsx/trace_matrix_xlsx/wbs_gantt_xlsx/staffing_plan_xlsx/submission_pptx/presentation_pptx/…"
    )
    title: str
    sheets_or_sections: list[str] = Field(default_factory=list)
    column_or_field_notes: list[str] = Field(default_factory=list)
    content_notes: list[str] = Field(default_factory=list, description="데이터 출처·채우는 규칙")
    source_data_refs: list[str] = Field(default_factory=list)


class DocumentPlan(_Strict):
    documents: list[DocumentSpec] = Field(default_factory=list)
    missing_inputs: list[str] = Field(
        default_factory=list, description="생성에 필요한데 없는 데이터"
    )


# --- 9. QA·변경 검토 -----------------------------------------------------------------------------


class SemanticDiffCandidate(_Strict):
    item_index: int = Field(description="요청 항목 번호 (1부터)")
    classification: str = Field(description="ADD | MODIFY | DELETE_REQUEST | NO_CHANGE | AMBIGUOUS")
    requirement_id: str | None = Field(default=None, description="관련 기존 요구사항 ID (있으면)")
    related_ids: list[str] = Field(default_factory=list)
    proposed_name: str = ""
    proposed_description: str = ""
    rationale: str = Field(
        default="", description="목적·사용자·입출력·규칙·제약·성능/보안·화면 비교 근거"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    needs_confirmation: bool = True


class SemanticDiffDraft(_Strict):
    candidates: list[SemanticDiffCandidate] = Field(default_factory=list)
    notes: str = ""


class QaFinding(_Strict):
    target: str = Field(description="산출물 종류 또는 요구사항 ID")
    level: str = Field(description="error/warning/info")
    message: str
    location: str = ""
    suggestion: str = ""


class QaReport(_Strict):
    findings: list[QaFinding] = Field(default_factory=list)
    overall: str = Field(description="pass/needs_fix/fail")
    summary: str = ""
    change_impact_notes: list[str] = Field(
        default_factory=list, description="변경 검토 시 영향 메모"
    )


__all__ = [
    "ArchitectureDraft",
    "DocumentPlan",
    "FeasibilityComparison",
    "ProposalContent",
    "QaReport",
    "RequirementExtraction",
    "ResearchItemDraft",
    "ResearchReport",
    "ResearchSourceDraft",
    "RfpAnalysis",
    "TechAlternative",
    "VerificationReport",
    "VisualEdge",
    "VisualItem",
    "VisualSpec",
    "WBSDraft",
]
