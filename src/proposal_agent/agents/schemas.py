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
    # Phase 17: 제안서 작성에 필요한 RFP 항목 (요청서 §3). 원문에 없으면 빈 목록으로 둔다.
    current_issues: list[str] = Field(
        default_factory=list, description="현행 시스템의 문제점·개선 필요 사항"
    )
    security_privacy: list[str] = Field(
        default_factory=list, description="정보보호·개인정보보호·준수해야 할 규정·인증"
    )
    data_migration_operation: list[str] = Field(
        default_factory=list, description="데이터 이관·전환·운영(백업·모니터링·운영 이관) 요구"
    )
    dev_environment: list[str] = Field(
        default_factory=list, description="개발 환경·기술 제약(프레임워크·DB·OS·표준·형상관리)"
    )
    deliverables_schedule: list[str] = Field(
        default_factory=list, description="프로젝트 단계와 단계별 산출물"
    )
    test_acceptance_training: list[str] = Field(
        default_factory=list, description="시험·검수·교육·안정화·유지관리(하자보수) 요구"
    )
    proposal_guidelines: list[str] = Field(
        default_factory=list, description="제안서 목차·작성 지침(장별 작성 요령)"
    )
    page_limit: str = Field(
        default="", description="페이지 제한 원문 문구 (예: '제안서는 100쪽 이내')"
    )
    document_format: list[str] = Field(
        default_factory=list, description="문서 규격·제출 형식(용지·글꼴·부수·파일 형식·제출 방법)"
    )
    required_submissions: list[str] = Field(
        default_factory=list, description="필수 제출 자료·별첨 서식 목록"
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
    category: str = Field(
        default="", description="구분 (업무 영역·시스템 단위, 예: 공통/민원/통계)"
    )
    organization: str = Field(default="", description="개발 조직 (수행사 팀·협력사)")
    assignee: str = Field(
        default="",
        description="개발자·담당자 이름. 제안 단계에서 미정이면 빈값(코드가 역할로 표시)",
    )
    quantity: str = Field(default="", description="수량·규모 (예: 화면 12개, 인터페이스 3건)")


class DependencyDraft(_Strict):
    predecessor_code: str
    successor_code: str
    type: str = Field(default="FS", description="FS/SS/FF/SF")
    lag_days: int = 0


class TeamMemberDraft(_Strict):
    """수행 조직 구성 (투입계획 행). 월별 공수는 코드가 WBS 배분으로 계산한다."""

    organization: str = Field(default="수행사", description="조직 (수행사·협력사·고객)")
    role: str = Field(description="역할 (items[].roles의 role과 같은 이름)")
    grade: str = Field(default="미정", description="기술 등급: 특급/고급/중급/초급/미정")
    name: str = Field(default="", description="구성원 이름 (미정이면 빈값)")
    headcount: int = Field(default=1, ge=1)
    skills: list[str] = Field(default_factory=list)
    duties: str = ""


class MilestoneDraft(_Strict):
    name: str = Field(description="예: 착수, 착수보고, 중간보고, 완료보고, 오픈, 종료")
    timing: str = Field(
        default="end",
        description="start | mid | end | after:<WBS code> (해당 항목 종료 직후) | +Nw (착수 N주 후)",
    )


class WBSDraft(_Strict):
    """날짜는 받지 않는다. 일정은 planning/scheduler.py가 계산한다."""

    items: list[WbsItemDraft] = Field(default_factory=list)
    dependencies: list[DependencyDraft] = Field(default_factory=list)
    team: list[TeamMemberDraft] = Field(
        default_factory=list,
        description="수행 조직 구성 (역할·등급·인원). 비우면 코드가 역할 부하로 산출",
    )
    milestones: list[MilestoneDraft] = Field(
        default_factory=list,
        description="보고용 WBS 마일스톤. 비우면 코드 기본값(착수·착수보고·중간보고·완료보고·종료)",
    )
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
    kind: str = Field(
        default="",
        description="screen 전용 컴포넌트 종류: section(구획) | input(입력 필드) | button | menu(좌측 메뉴) | tab | "
        "message(안내·오류) | table(목록 표, text='열1|열2') | list | chart(차트 영역)",
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
        "kpis(핵심 수치: title=라벨, text=값) | compare(비교 표: headers/rows) | "
        "raci(책임 분담표: headers=['활동', 역할…], rows=[활동, R/A/C/I…]) | "
        "data_model(데이터 모델: items=엔티티(title=이름, text=주요 속성 줄바꿈), edges=관계(label=1:N 등)) | "
        "procedure(운영·장애 대응 절차: items=단계(group=담당 조직·역할), 순서대로) | "
        "security_layers(보안 통제: items=통제(group=영역: 네트워크/서버/응용/데이터/관리), title=통제명, text=방식) | "
        "layers(계층 구성: items=요소(group=계층명), 위에서 아래로) | "
        "chart(네이티브 차트: headers=[범주 이름, 계열1, 계열2…], rows=[[범주, 값…]], chart_type)"
    )
    chart_type: str = Field(
        default="",
        description="kind=chart 일 때: bar | column | stacked_bar | stacked_column | line | pie | doughnut",
    )
    title: str = ""
    items: list[VisualItem] = Field(default_factory=list)
    edges: list[VisualEdge] = Field(default_factory=list)
    left_title: str = ""
    right_title: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class EvidenceRef(_Strict):
    """소절 주장·수치의 근거 (Phase 19). 데이터에 없는 근거는 적지 않는다."""

    kind: str = Field(
        description="rfp(RFP 본문) | requirement(요구사항) | research(기술 조사) | architecture(구성 요소) | "
        "wbs(WBS·일정) | staffing(인력) | reference_doc(참고 문서) | assumption(전제, 사람 확인 필요)"
    )
    ref: str = Field(
        default="", description="참조 ID (요구사항 ID, 조사 주제, 구성 요소 코드, WBS 코드, RFP 절)"
    )
    text: str = Field(default="", description="근거 요지 1문장 (수치가 있으면 출처의 값 그대로)")


class AlternativeOption(_Strict):
    """기술 대안 (상용/공개/자체) 비교 항목."""

    name: str
    kind: str = Field(description="commercial(상용) | open_source(공개 SW) | in_house(자체 개발)")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    cost_note: str = Field(
        default="", description="라이선스·구축·운영 비용 관점 (데이터·조사에 있는 것만)"
    )
    selected: bool = False
    basis: str = Field(default="", description="선정·배제 근거 (조사 주제·출처)")


class TechDetail(_Strict):
    """기술 소절 템플릿: 구성·연계·데이터·운영·보안 + 대안 비교 (Phase 19)."""

    components: list[str] = Field(
        default_factory=list, description="구성 요소·기술 (제품·버전은 조사 출처에 있는 것만)"
    )
    interfaces: list[str] = Field(
        default_factory=list, description="연계·인터페이스 (프로토콜·방식)"
    )
    data: list[str] = Field(default_factory=list, description="데이터 구조·저장·이관")
    operations: list[str] = Field(default_factory=list, description="운영·장애·백업·모니터링")
    security: list[str] = Field(
        default_factory=list, description="보안 통제 (인증·권한·암호화·감사)"
    )
    alternatives: list[AlternativeOption] = Field(
        default_factory=list, description="상용/공개/자체 대안 비교 (2~4개), 선정 1개"
    )
    selection_reason: str = Field(
        default="", description="선정 사유 1~2문장 (비전문가도 이해할 표현)"
    )


class GlossaryTerm(_Strict):
    term: str = Field(description="용어 또는 약어 (예: SSO)")
    full_form: str = Field(default="", description="약어 풀이 (예: Single Sign-On)")
    meaning: str = Field(description="비전문가용 설명 1~2문장")
    first_section: str = Field(default="", description="처음 나오는 소절 번호")


LAYOUT_TYPES = (
    "title_bullets",
    "lead_bullets",
    "table",
    "visual",
    "visual_bullets",
    "two_column",
    "tech_detail",
    "compare",
    "glossary",
)
AUDIENCES = ("evaluator", "business", "technical", "executive")


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
    # Phase 19: 슬라이드 단위 명세 (모두 선택)
    key_message: str = Field(
        default="",
        description="결론형 제목: 이 슬라이드가 말하는 결론 한 문장 (40자 내외, 명사형 제목이 아니라 주장)",
    )
    purpose: str = Field(default="", description="이 슬라이드의 목적 (무엇을 설득·설명하는가)")
    audience: str = Field(
        default="",
        description="주 독자: evaluator(평가위원) | business(현업) | technical(기술 심사) | executive(경영진)",
    )
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="주장·수치의 근거 (데이터에 있는 것만, 1개 이상 권장)"
    )
    links_prev: list[str] = Field(default_factory=list, description="앞에서 이어받는 소절 번호")
    links_next: list[str] = Field(default_factory=list, description="뒤로 이어지는 소절 번호")
    layout_type: str = Field(
        default="",
        description="title_bullets | lead_bullets | table | visual | visual_bullets | two_column | tech_detail | compare | glossary",
    )
    tech_detail: TechDetail | None = Field(
        default=None, description="기술 소절(구성·연계·데이터·운영·보안·대안 비교). 기술 소절에만"
    )
    terms: list[str] = Field(
        default_factory=list,
        description="이 소절에서 처음 쓰는 약어·전문 용어 (glossary에 설명이 있어야 함)",
    )
    picture: str = Field(
        default="",
        description="이 소절 뒤에 넣을 등록된 참고 그림(사진·일러스트)의 파일명 또는 설명 (Phase 20, 없으면 빈값)",
    )


class RequirementGroupSpec(_Strict):
    """제안서에서 한 소절로 묶어 다룰 요구사항 묶음 (Phase 22). 코드가 정의서 구현방안 전문을 표로 싣는다."""

    title: str = Field(description="묶음 제목 (예: 민원 접수·배정·종결 워크플로)")
    requirement_ids: list[str] = Field(
        description="묶는 요구사항 ID (내부 ID 또는 RFP 고유번호 — RFP 번호면 그 세부 요구 전부)"
    )
    key_message: str = Field(default="", description="묶음 결론형 제목 (40자 내외)")
    summary: list[str] = Field(default_factory=list, description="묶음 공통 방안 요약 2~4줄")
    notes: list[str] = Field(default_factory=list, description="전제·협의 필요 사항 (※ 주석)")


class ProposalContent(_Strict):
    profile: str = Field(description="submission(제출용) 또는 presentation(발표용)")
    sections: list[ProposalSection] = Field(default_factory=list)
    requirement_groups: list[RequirementGroupSpec] = Field(
        default_factory=list,
        description="요구사항 묶음 (Phase 22). 비우면 코드가 RFP 고유번호·분류로 묶는다",
    )
    key_messages: list[str] = Field(default_factory=list)
    unverified_claims: list[str] = Field(
        default_factory=list, description="근거 데이터가 없어 사람 확인이 필요한 문구"
    )
    glossary: list[GlossaryTerm] = Field(
        default_factory=list,
        description="용어집: 본문에 쓴 약어·전문 용어의 풀이와 비전문가용 설명 (Phase 19, 부록 소절로 생성)",
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


# --- 6-2. 목차·전략 브리프 (Phase 18, 사용자 승인 대상) ------------------------------------------


class RequirementDirection(_Strict):
    requirement_id: str = Field(description="입력에 있는 요구사항 ID")
    priority: str = Field(default="중", description="중요도 상/중/하 (RFP 필수·평가 배점 기준)")
    direction: str = Field(description="대응 방향 한 줄 (수용 방식·핵심 구현·차별점)")


class TocChapter(_Strict):
    numeral: str = Field(default="", description="장 번호 (Ⅰ, Ⅱ … 또는 1, 2)")
    title: str
    sections: list[str] = Field(
        default_factory=list, description="절 제목 목록 (RFP 지정 목차 우선)"
    )
    rfp_mandatory: bool = Field(default=False, description="RFP가 지정한 필수 목차인가")
    note: str = Field(default="", description="RFP 작성 지침·배점·이 장에서 다룰 핵심")


class StrategyItem(_Strict):
    title: str = Field(description="전략 제목 (결론형 한 문장)")
    description: str = Field(description="무엇을 어떻게 — 구체적 구현 방향")
    differentiator: str = Field(
        description="차별화 근거 (경쟁 대비 왜 유리한가; 근거 없는 실적·수치 금지)"
    )
    related_requirement_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list,
        description="근거 구분과 출처: 'RFP: …' / '참고 문서: …' / '조사 TR-…: …' / '설계 제안'",
    )
    # 단계 3 (지시문 §7.1): 발주처 문제·구현 방법·기술·기대 효과·위험/전제·미확인 주장
    client_problem: str = Field(default="", description="발주처 관점의 문제 또는 목표")
    approach: str = Field(default="", description="구현 방법 (무엇을 어떻게)")
    technologies: list[str] = Field(
        default_factory=list, description="적용 기술·아키텍처 (조사·RFP 근거)"
    )
    expected_effects: list[str] = Field(
        default_factory=list, description="기대 효과 — 근거 있는 것만 (수치는 출처 필수)"
    )
    risks: list[str] = Field(default_factory=list, description="위험·전제 조건")
    unverified_claims: list[str] = Field(
        default_factory=list, description="근거가 없어 사람 확인이 필요한 주장"
    )


class KeyTechnology(_Strict):
    area: str = Field(description="framework/ui_ux/web_was/db/api/security/deploy_ops/업무 영역")
    choice: str = Field(description="선택 기술·방식 (조사·RFP 명시 기준)")
    rationale: str = ""
    feasibility_basis: str = Field(default="", description="근거 조사 ID·구현 가능성")


class RiskItem(_Strict):
    risk: str
    mitigation: str
    related_requirement_ids: list[str] = Field(default_factory=list)


class StrategyBrief(_Strict):
    """RFP 분석 후 전체 제안서 작성 전에 사용자가 검토·승인하는 브리프 (요청서 §4의 10항목)."""

    rfp_summary: str = Field(description="1. RFP 분석 요약 (목적·범위·현행 문제·제약·평가 기준)")
    requirement_directions: list[RequirementDirection] = Field(
        default_factory=list, description="2·3. 요구사항별 중요도와 대응 방향"
    )
    toc: list[TocChapter] = Field(
        default_factory=list, description="4. 제안서 목차 초안 (RFP 필수 목차 보존)"
    )
    toc_change_requests: list[str] = Field(
        default_factory=list,
        description="필수 목차 변경이 필요하거나 RFP 요구가 모호한 경우 이유와 대안",
    )
    strategies: list[StrategyItem] = Field(
        default_factory=list, description="5·6. 주요 제안 전략 3~5개와 차별화 근거"
    )
    key_technologies: list[KeyTechnology] = Field(
        default_factory=list, description="7. 핵심 기술·구현 방향"
    )
    risks: list[RiskItem] = Field(default_factory=list, description="8. 예상 위험과 대응")
    submission_vs_presentation: str = Field(
        default="", description="9. 제출용과 발표용 구성 차이 (무엇을 상세히/압축해서 다루는가)"
    )
    open_questions: list[str] = Field(
        default_factory=list, description="10. 자료 부족·사용자 확인 필요 사항"
    )


# --- 8-2. 요구사항별 구현 방안 (Phase 14) -------------------------------------------------------


class RequirementAnalysis(_Strict):
    """요구사항별 기술 검토 14항목 (지시문 §4.1, 단계 3). 각 항목은 짧은 글머리 목록, 모르면 비우고 가정은 'assumption:' 접두."""

    purpose: list[str] = Field(default_factory=list, description="목적·사용자 관점의 필요성")
    conditions: list[str] = Field(default_factory=list, description="기능·비기능 조건")
    inputs_outputs: list[str] = Field(default_factory=list, description="입력값·출력값")
    business_rules: list[str] = Field(default_factory=list, description="업무 규칙·데이터 처리")
    flow_exceptions: list[str] = Field(default_factory=list, description="처리 흐름·예외 상황")
    screens_interaction: list[str] = Field(default_factory=list, description="화면·사용자 인터랙션")
    api_integration: list[str] = Field(default_factory=list, description="API·외부 시스템 연계")
    data_transactions: list[str] = Field(default_factory=list, description="데이터 모델·트랜잭션")
    auth_privacy_audit: list[str] = Field(
        default_factory=list, description="인증·권한·개인정보·감사 로그"
    )
    performance_scalability: list[str] = Field(default_factory=list, description="성능·확장성")
    failure_recovery: list[str] = Field(default_factory=list, description="장애·복구 전략")
    operations: list[str] = Field(default_factory=list, description="운영·유지보수")
    impact: list[str] = Field(default_factory=list, description="구현 난이도·의존성·일정·비용 영향")
    test_acceptance: list[str] = Field(default_factory=list, description="테스트 방법·수용 기준")

    def filled_count(self) -> int:
        return sum(1 for v in self.model_dump().values() if v)


ANALYSIS_FIELDS: tuple[tuple[str, str], ...] = (
    ("purpose", "목적·필요성"),
    ("conditions", "기능·비기능 조건"),
    ("inputs_outputs", "입력·출력"),
    ("business_rules", "업무 규칙·데이터 처리"),
    ("flow_exceptions", "처리 흐름·예외"),
    ("screens_interaction", "화면·인터랙션"),
    ("api_integration", "API·연계"),
    ("data_transactions", "데이터 모델·트랜잭션"),
    ("auth_privacy_audit", "인증·권한·개인정보·감사"),
    ("performance_scalability", "성능·확장성"),
    ("failure_recovery", "장애·복구"),
    ("operations", "운영·유지보수"),
    ("impact", "난이도·의존·일정·비용 영향"),
    ("test_acceptance", "테스트·수용 기준"),
)


class ApproachItem(_Strict):
    """요구사항 정의서 '구현방안' 한 칸. 제안서보다 짧게(글머리 2~5줄, 300자 내외) 쓴다."""

    requirement_id: str = Field(description="입력에 있는 요구사항 ID만")
    approach: str = Field(
        min_length=1,
        description="구현 방안 요약. 줄마다 '- '로 시작, 2~5줄, 실제 구현 가능한 방식·제품·구조만",
    )
    difficulty: str = Field(default="중", description="구현 난이도: 상 | 중 | 하")
    difficulty_basis: str = Field(
        default="", description="난이도 판단 근거 (연계 수·신기술·수치 조건 등)"
    )
    verification_method: str = Field(default="", description="검증 방법: 시연 | 시험 | 검사 | 분석")
    acceptance_criteria: str = Field(
        default="", description="검사(판정) 기준 1~3줄 — 완료를 판정할 수 있는 조건"
    )
    research_refs: list[str] = Field(
        default_factory=list, description="근거로 쓴 조사 ID(TR-…) — 입력 <research>에 있는 것만"
    )
    sources: list[ResearchSourceDraft] = Field(
        default_factory=list, description="이 항목을 위해 새로 열람한 출처 (열람하지 않은 URL 금지)"
    )
    feasibility: FeasibilityVerdict = Field(
        default=FeasibilityVerdict.UNKNOWN, description="근거 기준 구현 가능성"
    )
    notes: str = Field(default="", description="가정·확인 필요 사항")
    response_strategy: str = Field(
        default="",
        description="추적표 '대응 전략' 한 줄: 수용 방식·핵심 대응(예: '표준 공통컴포넌트 재사용으로 수용')",
    )
    analysis: RequirementAnalysis | None = Field(
        default=None, description="요구사항별 기술 검토 14항목 (단계 3) — 주요 요구사항에 작성"
    )


class ApproachReport(_Strict):
    items: list[ApproachItem] = Field(default_factory=list)
    research_needed: list[str] = Field(
        default_factory=list, description="근거가 없어 추가 기술 조사가 필요한 요구사항 ID와 주제"
    )
    notes: str = ""


# --- 8-3. 요구사항 묶음별 구현 설계 (Phase 23) --------------------------------------------------


class DesignComponent(_Strict):
    """구현 구조의 구성 요소 하나 (계층·기술·역할)."""

    name: str
    layer: str = Field(
        default="app",
        description="client | web | app | batch | integration | data | infra | external | security",
    )
    technology: str = Field(
        default="", description="제품·버전·표준 (조사·아키텍처 출처에 있는 것만)"
    )
    role: str = Field(default="", description="이 묶음에서 하는 일 1문장")
    requirement_ids: list[str] = Field(default_factory=list)


class DesignStep(_Strict):
    """처리 절차 한 단계 (담당·처리·분기)."""

    title: str
    actor: str = Field(default="", description="담당: 사용자 역할 또는 시스템 모듈")
    action: str = Field(default="", description="처리 내용: 입력 → 처리 → 저장/출력")
    decision: str = Field(default="", description="분기 조건 → 결과 (있으면)")


class AlternativeOptionDetail(_Strict):
    """구현 대안 하나 (지시문 §4.2)."""

    name: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list, description="기술적 제약")
    compatibility: str = Field(default="", description="기존 시스템과의 호환성")
    cost_complexity: str = Field(default="", description="개발·운영 비용과 복잡도")
    risk: str = Field(default="", description="보안·장애 위험")
    performance: str = Field(default="", description="성능에 미치는 영향")
    fit_conditions: str = Field(default="", description="적합한 적용 조건")


class AlternativeComparison(_Strict):
    """선택에 실제로 영향을 주는 경우에만 쓰는 대안 비교 (A/B/C)."""

    topic: str = Field(description="비교 주제 (예: 표 머리글 고정 방식)")
    options: list[AlternativeOptionDetail] = Field(default_factory=list, description="2~4개")
    recommended: str = Field(default="", description="추천안 이름 (options 중 하나)")
    reason: str = Field(default="", description="추천 이유")
    poc_needed: bool = Field(default=False, description="PoC·추가 검증 필요 여부")
    poc_scope: str = Field(default="", description="PoC 범위·판정 기준")
    source: str = Field(default="", description="근거: 열람 URL | 조사 ID | RFP | 설계 제안")


class TechChoice(_Strict):
    """적용 기술 선택과 선정 이유·대안·근거."""

    area: str = Field(
        description="프레임워크 | WAS | DB | UI | 연계 | 보안 | 배치 | 인프라 | 업무 처리"
    )
    choice: str = Field(description="선택 기술·방식 (버전 포함)")
    reason: str = Field(description="선정 이유 (요구·제약·근거 기준)")
    alternatives: list[str] = Field(default_factory=list, description="검토한 대안과 배제 이유")
    source: str = Field(
        default="", description="근거: 열람한 URL | 조사 ID(TR-…) | RFP | 설계 제안"
    )
    verified: bool = Field(default=False, description="공식 문서·조사로 확인했는가")
    checked_on: str = Field(default="", description="확인 날짜 YYYY-MM-DD (열람했을 때)")


class ImplementationDesign(_Strict):
    """요구사항 묶음 하나의 구현 설계. 덱의 묶음 소절(구조 도식·절차 도식·기술 표)이 된다."""

    title: str = Field(description="묶음 제목 (구현 대상이 드러나게)")
    requirement_ids: list[str] = Field(description="묶는 요구사항 ID (내부 ID 또는 RFP 고유번호)")
    key_message: str = Field(default="", description="결론형 제목 (40자 내외)")
    overview: list[str] = Field(
        default_factory=list, description="무엇을 어떤 구조·방식으로 — 2~4줄"
    )
    structure: list[DesignComponent] = Field(default_factory=list, description="구현 구조 2개 이상")
    flows: list[DesignStep] = Field(default_factory=list, description="처리 절차 3~8단계")
    tech_choices: list[TechChoice] = Field(default_factory=list, description="적용 기술 1개 이상")
    data_interfaces: list[str] = Field(
        default_factory=list, description="테이블·엔티티·상태 코드·API·메시지/파일 규격·배치 주기"
    )
    premises: list[str] = Field(default_factory=list, description="전제·협의 필요 사항")
    risks: list[str] = Field(default_factory=list, description="설계 위험과 대응")
    research_refs: list[str] = Field(default_factory=list, description="근거 조사 ID (TR-…)")
    sources: list[ResearchSourceDraft] = Field(
        default_factory=list, description="새로 열람한 출처 (열람하지 않은 URL 금지)"
    )
    # 단계 3 (지시문 §4.2·§8): 대안 비교와 비기능 설계
    comparisons: list[AlternativeComparison] = Field(
        default_factory=list, description="선택에 영향을 주는 대안 비교 (필요한 경우만)"
    )
    performance_scalability: list[str] = Field(default_factory=list, description="성능·확장 전략")
    failure_recovery: list[str] = Field(default_factory=list, description="장애 대응·복구")
    operations_monitoring: list[str] = Field(default_factory=list, description="운영·모니터링")
    auth_security: list[str] = Field(default_factory=list, description="인증·보안·개인정보")
    test_approach: list[str] = Field(default_factory=list, description="개발·테스트 방안·수용 기준")


class DesignReport(_Strict):
    designs: list[ImplementationDesign] = Field(default_factory=list)
    research_needed: list[str] = Field(
        default_factory=list, description="근거가 없어 추가 조사가 필요한 묶음과 주제"
    )
    notes: str = ""


# --- 8-4. 사업 참여 타당성 검토 (단계 2, 지시문 §6) --------------------------------------------------


class BidReviewItem(_Strict):
    key: str = Field(description="평가 항목 키 (입력 items[].key 중 하나)")
    rating: str = Field(
        default="unknown", description="good | caution | risk | unknown — 제안 판정"
    )
    comment: str = Field(description="사실(데이터 확인)과 판단을 구분한 의견 1~3문장")


class BidReviewDraft(_Strict):
    items: list[BidReviewItem] = Field(default_factory=list)
    key_risks: list[str] = Field(
        default_factory=list, description="실패 요인 3~6개 (근거 있는 것만)"
    )
    open_questions: list[str] = Field(default_factory=list, description="사용자 확인 질문")
    overall_comment: str = Field(
        default="", description="권고 동의 여부·참여 조건·우선 확인 사항 3~5문장"
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
    change_aspects: list[str] = Field(
        default_factory=list,
        description="문맥상 달라진 관점: 범위 | 대상 사용자 | 입력/출력 | 업무 규칙 | 수치 조건 | 화면 | 연계 | 성능/보안 | 데이터",
    )
    difficulty: str | None = Field(
        default=None, description="변경 구현 난이도: 상 | 중 | 하 (판단 불가면 null)"
    )
    difficulty_basis: str = Field(default="", description="난이도 근거")
    effort_hint: str = Field(
        default="", description="공수·일정 영향 힌트 (예: 연계 1건 추가로 설계·시험 공수 증가)"
    )


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
    "AlternativeOption",
    "EvidenceRef",
    "GlossaryTerm",
    "RequirementGroupSpec",
    "TechDetail",
    "DesignComponent",
    "DesignStep",
    "TechChoice",
    "ImplementationDesign",
    "DesignReport",
    "ANALYSIS_FIELDS",
    "AlternativeComparison",
    "AlternativeOptionDetail",
    "RequirementAnalysis",
    "BidReviewDraft",
    "BidReviewItem",
    "LAYOUT_TYPES",
    "AUDIENCES",
]
