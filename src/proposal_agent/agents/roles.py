"""에이전트 역할 정의 (AGENT_DESIGN.md).

각 역할은 입력·출력 스키마·허용 도구·MCP 서버·예산·턴·시간·재시도·실패 처리 규칙을 선언한다.
도구 권한은 최소화한다: 파일 쓰기 도구(Write/Edit/Bash/NotebookEdit)는 어떤 역할에도 주지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from proposal_agent.agents import schemas
from proposal_agent.models import VerificationReport

# 역할이 쓸 수 있는 내장 도구 목록 (화이트리스트). 이 밖의 내장 도구는 어떤 역할도 사용할 수 없다.
BUILTIN_TOOL_CATALOG: frozenset[str] = frozenset({"WebSearch", "WebFetch"})
FORBIDDEN_TOOLS: tuple[str, ...] = (
    "Bash",
    "Write",
    "Edit",
    "NotebookEdit",
    "Agent",
    "Skill",
    "KillShell",
)

MCP_PROJECT = "pwa"  # 인프로세스 프로젝트 데이터·파일 검증 서버
MCP_DOCS = "claude-code-docs"  # 예시 외부 HTTP MCP (Claude Code 문서)


@dataclass(frozen=True)
class AgentRole:
    key: str
    title: str
    description: str
    inputs: tuple[str, ...]
    output_schema: type[BaseModel]
    prompt_name: str
    builtin_tools: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()
    mcp_tool_patterns: tuple[str, ...] = ()
    max_turns: int = 8
    max_budget_usd: float = 2.0
    timeout_s: int = 600
    retries: int = 1
    effort: str = "high"
    model_key: str = "primary"  # primary | worker
    reuses: tuple[str, ...] = ()  # 재사용하는 이전 역할 출력 키
    failure_policy: str = "실패 시 StepRun을 failed로 기록하고 원인·조치를 표시한다. 자동 재시도는 일시 오류에 한해 retries 횟수만큼."
    output_subdir: str = "02_RFP_Analysis"
    output_stem: str = "output"

    def allowed_tool_names(self) -> list[str]:
        names = list(self.builtin_tools)
        names.extend(self.mcp_tool_patterns)
        return names

    def validate(self) -> None:
        bad = [t for t in self.builtin_tools if t not in BUILTIN_TOOL_CATALOG]
        if bad:
            raise ValueError(f"{self.key}: 허용되지 않은 내장 도구 {bad}")
        if any(t in FORBIDDEN_TOOLS for t in self.builtin_tools):
            raise ValueError(f"{self.key}: 금지 도구 포함")
        for pat in self.mcp_tool_patterns:
            if not pat.startswith("mcp__"):
                raise ValueError(f"{self.key}: MCP 도구 패턴 형식 오류 {pat}")
            server = pat.split("__")[1]
            if server not in self.mcp_servers:
                raise ValueError(f"{self.key}: 선언되지 않은 MCP 서버 {server}")


_PROJECT_READ = (
    f"mcp__{MCP_PROJECT}__get_project",
    f"mcp__{MCP_PROJECT}__list_requirements",
    f"mcp__{MCP_PROJECT}__get_requirement",
    f"mcp__{MCP_PROJECT}__search_source_text",
    f"mcp__{MCP_PROJECT}__get_source_block",
    f"mcp__{MCP_PROJECT}__list_research",
    f"mcp__{MCP_PROJECT}__list_findings",
    f"mcp__{MCP_PROJECT}__list_gates",
    f"mcp__{MCP_PROJECT}__get_prior_output",
)

ROLES: dict[str, AgentRole] = {}


def _register(role: AgentRole) -> AgentRole:
    role.validate()
    ROLES[role.key] = role
    return role


RFP_ANALYST = _register(
    AgentRole(
        key="rfp_analyst",
        title="RFP 문서 분석",
        description="추출된 RFP 블록에서 사업 개요·범위·제약·평가·일정·예산·명시 솔루션·연계 대상을 정리한다.",
        inputs=("추출 블록(청크)",),
        output_schema=schemas.RfpAnalysis,
        prompt_name="rfp_analyst",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=(
            f"mcp__{MCP_PROJECT}__search_source_text",
            f"mcp__{MCP_PROJECT}__get_source_block",
        ),
        max_turns=10,
        max_budget_usd=2.0,
        effort="high",
        output_subdir="02_RFP_Analysis",
        output_stem="rfp_analysis",
    )
)

REQUIREMENT_EXTRACTOR = _register(
    AgentRole(
        key="requirement_extractor",
        title="요구사항 분석(추출)",
        description="청크별 원문에서 요구사항 초안을 추출한다. ID·출처 검증·중복 병합은 코드가 수행한다.",
        inputs=("추출 블록(청크)", "RFP 분석 결과(있으면)"),
        output_schema=schemas.RequirementExtraction,
        prompt_name="requirement_extractor",
        max_turns=8,
        max_budget_usd=2.0,
        effort="high",
        reuses=("rfp_analyst",),
        output_subdir="03_Requirements",
        output_stem="requirement_extraction",
    )
)

REQUIREMENT_VERIFIER = _register(
    AgentRole(
        key="requirement_verifier",
        title="독립 요구사항 검증",
        description="추출과 분리된 컨텍스트에서 원문과 요구사항 목록을 대조해 누락·중복·왜곡·출처·모순·범위를 검사한다.",
        inputs=("추출 블록(청크)", "요구사항 목록"),
        output_schema=VerificationReport,
        prompt_name="requirement_verifier",
        max_turns=8,
        max_budget_usd=2.0,
        effort="high",
        output_subdir="03_Requirements",
        output_stem="verification",
    )
)

TECH_RESEARCHER = _register(
    AgentRole(
        key="tech_researcher",
        title="기술 조사",
        description="명시 솔루션·개발 가이드·프레임워크/WEB/WAS 선택·보안/성능/호환성·구현 가능성을 공식 문서 우선으로 조사하고 출처와 미확인 사항을 기록한다.",
        inputs=("요구사항 목록", "RFP 분석", "조사 주제"),
        output_schema=schemas.ResearchReport,
        prompt_name="tech_researcher",
        builtin_tools=("WebSearch", "WebFetch"),
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=(
            f"mcp__{MCP_PROJECT}__get_requirement",
            f"mcp__{MCP_PROJECT}__list_research",
        ),
        max_turns=30,
        max_budget_usd=6.0,
        timeout_s=1200,
        effort="high",
        reuses=("rfp_analyst",),
        output_subdir="04_Technology_Research",
        output_stem="research_report",
    )
)

ARCHITECT = _register(
    AgentRole(
        key="architect",
        title="아키텍처 설계",
        description="요구사항과 조사 결과로 시스템·SW·서비스 구성 요소와 연결을 설계한다. 도면 렌더링은 코드가 한다.",
        inputs=("요구사항 목록", "기술 조사 결과"),
        output_schema=schemas.ArchitectureDraft,
        prompt_name="architect",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=_PROJECT_READ,
        max_turns=12,
        max_budget_usd=3.0,
        reuses=("tech_researcher", "rfp_analyst"),
        output_subdir="05_Architecture_Design",
        output_stem="architecture",
    )
)

PLANNER = _register(
    AgentRole(
        key="planner",
        title="WBS·일정·공수 계획",
        description="요구사항·아키텍처로 WBS 항목·공수 제안·근거·선후행을 제안한다. 날짜·합계는 코드가 계산한다.",
        inputs=("요구사항 목록", "아키텍처", "사업 기간"),
        output_schema=schemas.WBSDraft,
        prompt_name="planner",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=_PROJECT_READ,
        max_turns=12,
        max_budget_usd=3.0,
        reuses=("architect", "rfp_analyst"),
        output_subdir="06_WBS_Effort_Schedule",
        output_stem="wbs_draft",
    )
)

PROPOSAL_WRITER = _register(
    AgentRole(
        key="proposal_writer",
        title="제안서 작성",
        description="기준 데이터로 제출용/발표용 제안 문안을 작성한다. 근거 없는 주장은 unverified_claims로 분리한다.",
        inputs=("요구사항", "조사", "아키텍처", "WBS"),
        output_schema=schemas.ProposalContent,
        prompt_name="proposal_writer",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=_PROJECT_READ,
        max_turns=15,
        max_budget_usd=4.0,
        effort="medium",
        reuses=("rfp_analyst", "tech_researcher", "architect", "planner", "design_writer"),
        output_subdir="07_Submission_Proposal_PPT",
        output_stem="proposal_content",
    )
)

DOCUMENT_GENERATOR = _register(
    AgentRole(
        key="document_generator",
        title="문서 생성(명세)",
        description="각 산출물의 구조·시트·컬럼·내용 규칙을 명세한다. 실제 파일은 generators 코드가 공통 데이터로 생성한다.",
        inputs=("기준 데이터 전체",),
        output_schema=schemas.DocumentPlan,
        prompt_name="document_generator",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=_PROJECT_READ,
        max_turns=10,
        max_budget_usd=2.0,
        effort="medium",
        reuses=("proposal_writer", "planner", "architect"),
        output_subdir="09_Excel_Deliverables",
        output_stem="document_plan",
    )
)

QA_REVIEWER = _register(
    AgentRole(
        key="qa_reviewer",
        title="QA·변경 검토",
        description="생성 산출물의 내용 정합성·누락·문체와 변경 요청의 영향을 검토한다. 파일 무결성은 코드가 먼저 검사한다.",
        inputs=("산출물 추출 텍스트", "기준 데이터", "변경 요청"),
        output_schema=schemas.QaReport,
        prompt_name="qa_reviewer",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=(*_PROJECT_READ, f"mcp__{MCP_PROJECT}__verify_deliverable_file"),
        max_turns=12,
        max_budget_usd=3.0,
        reuses=("document_generator", "proposal_writer"),
        output_subdir="11_QA_Validation_Reports",
        output_stem="qa_report",
    )
)


# --- 12. 목차·전략 브리프 (Phase 18) ----------------------------------------------------------
STRATEGY_PLANNER = _register(
    AgentRole(
        key="strategy_planner",
        title="목차·전략 브리프",
        description="RFP 분석·요구사항·조사 결과로 제안서 목차 초안과 주요 전략(3~5)·차별화 근거·핵심 기술·위험·제출/발표 구성 차이·확인 필요 사항을 정리한다. 전체 제안서 작성 전에 사용자가 승인한다(Gate P).",
        inputs=("RFP 프로파일·분석", "요구사항·구현 방안", "기술 조사", "검토 의견(재작성 시)"),
        output_schema=schemas.StrategyBrief,
        prompt_name="strategy_planner",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=_PROJECT_READ,
        max_turns=12,
        max_budget_usd=3.0,
        timeout_s=600,
        effort="high",
        reuses=("rfp_analyst",),
        output_subdir="07_Submission_Proposal_PPT",
        output_stem="strategy_brief",
    )
)


# --- 11. 요구사항별 구현 방안 (Phase 14) -----------------------------------------------------
APPROACH_WRITER = _register(
    AgentRole(
        key="approach_writer",
        title="요구사항 구현 방안 작성",
        description="요구사항 정의서의 '구현방안·난이도·검증 방법·검사 기준'을 요구사항마다 짧게 쓴다. 기술 조사·아키텍처 근거가 있는 것만 구체화하고, 근거가 없으면 웹 검색으로 확인한 출처를 기록하거나 추가 조사 필요로 남긴다.",
        inputs=("요구사항 목록(묶음)", "기술 조사 결과", "아키텍처 구성 요소", "구현 가능성 비교"),
        output_schema=schemas.ApproachReport,
        prompt_name="approach_writer",
        builtin_tools=("WebSearch", "WebFetch"),
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=(
            f"mcp__{MCP_PROJECT}__get_requirement",
            f"mcp__{MCP_PROJECT}__list_research",
        ),
        max_turns=20,
        max_budget_usd=4.0,
        timeout_s=900,
        effort="high",
        reuses=("rfp_analyst",),
        output_subdir="04_Technology_Research",
        output_stem="approach_report",
    )
)


# --- 13. 요구사항 묶음별 구현 설계 (Phase 23) ------------------------------------------------
DESIGN_WRITER = _register(
    AgentRole(
        key="design_writer",
        title="요구사항 묶음 구현 설계",
        description="요구사항 묶음마다 실제 구현 방법을 설계한다: 구현 구조(구성 요소·계층·기술), 처리 절차(담당·처리·분기), 적용 기술과 선정 이유·대안·근거(열람한 URL·조사 ID), 데이터·인터페이스, 전제·위험. 제안서 묶음 소절의 구조 도식·절차 도식·기술 표가 된다.",
        inputs=(
            "요구사항 묶음(정의서 구현방안 포함)",
            "기술 조사 결과",
            "아키텍처 구성 요소",
            "구현 가능성 비교",
        ),
        output_schema=schemas.DesignReport,
        prompt_name="design_writer",
        builtin_tools=("WebSearch", "WebFetch"),
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=(
            f"mcp__{MCP_PROJECT}__get_requirement",
            f"mcp__{MCP_PROJECT}__list_research",
        ),
        max_turns=30,
        max_budget_usd=6.0,
        timeout_s=1200,
        effort="high",
        reuses=("approach_writer", "architect"),
        output_subdir="04_Technology_Research",
        output_stem="implementation_design",
    )
)


# --- 10. 구축 단계 의미 비교 (Phase 6) ------------------------------------------------------
SEMANTIC_DIFFER = _register(
    AgentRole(
        key="semantic_differ",
        title="변경 요청 의미 비교",
        description="변경 요청 항목을 기존 요구사항과 의미 단위로 비교해 ADD/MODIFY/DELETE_REQUEST/NO_CHANGE/AMBIGUOUS로 분류하고 근거를 쓴다. 최종 분류·ID 발급·반영은 코드와 사람이 한다.",
        inputs=("변경 요청 항목", "기존 요구사항 목록", "규칙 기반 분류 결과"),
        output_schema=schemas.SemanticDiffDraft,
        prompt_name="semantic_differ",
        mcp_servers=(MCP_PROJECT,),
        mcp_tool_patterns=(
            f"mcp__{MCP_PROJECT}__list_requirements",
            f"mcp__{MCP_PROJECT}__get_requirement",
        ),
        max_turns=8,
        max_budget_usd=1.5,
        effort="high",
        output_subdir="12_Revision_History",
        output_stem="semantic_diff",
    )
)


def get_role(key: str) -> AgentRole:
    try:
        return ROLES[key]
    except KeyError as exc:
        raise KeyError(f"알 수 없는 에이전트 역할: {key}") from exc


__all__ = [
    "BUILTIN_TOOL_CATALOG",
    "FORBIDDEN_TOOLS",
    "MCP_DOCS",
    "MCP_PROJECT",
    "ROLES",
    "AgentRole",
    "get_role",
]
