"""Screen, UnitTest, IntegrationTest, ArchitectureComponent (DATA_MODEL.md 4.6, 4.10).
TechnologyResearch는 models/research.py 로 이동했다.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.models.common import ProjectScoped


class Screen(ProjectScoped):
    code: str = Field(
        default="", description="문서에 표시되는 ID (예: SCR-001). 비우면 내부 id 사용"
    )
    id_prefix: ClassVar[str] = "SCR"

    name: str
    description: str = ""
    screen_type: str = "list"
    status: str = "draft"


class UnitTest(ProjectScoped):
    code: str = Field(
        default="", description="문서에 표시되는 ID (예: SCR-001). 비우면 내부 id 사용"
    )
    id_prefix: ClassVar[str] = "UT"

    name: str
    target_component: str = ""
    description: str = ""
    status: str = "draft"


class IntegrationTest(ProjectScoped):
    code: str = Field(
        default="", description="문서에 표시되는 ID (예: SCR-001). 비우면 내부 id 사용"
    )
    id_prefix: ClassVar[str] = "IT"

    name: str
    scenario: str = ""
    description: str = ""
    status: str = "draft"


class DbColumn(BaseModel):
    """DB 컬럼 (테이블 안에 내장, 코드 COL-… 은 테이블 안에서 유일)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(default="", description="예: COL-001")
    name: str
    data_type: str = ""
    length: str = ""
    nullable: bool = True
    default: str = ""
    is_pk: bool = False
    fk_ref: str = Field(default="", description="참조 테이블.컬럼")
    constraint: str = ""
    is_personal_data: bool = Field(default=False, description="개인정보·민감 데이터 여부")
    description: str = ""


class DbTable(ProjectScoped):
    """DB 설계 (지시문 §12.2). 단계 6 에서 생성·관리, 단계 1 은 ID·구조만."""

    id_prefix: ClassVar[str] = "TBL"

    code: str = Field(default="", description="예: TBL-001")
    name: str = Field(min_length=1, description="물리 테이블명")
    logical_name: str = ""
    description: str = ""
    columns: list[DbColumn] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list, description="관계 (참조 테이블·종류)")
    retention_policy: str = Field(default="", description="보존·삭제 정책")
    migration_note: str = Field(default="", description="기존 데이터 영향·이관")
    db_engine: str = Field(default="", description="DB 종류·버전 (호환성 확인 대상)")
    related_requirement_ids: list[str] = Field(default_factory=list)
    status: str = "draft"
    version: int = 1


class ApiSpec(ProjectScoped):
    """API 설계 (지시문 §12.3)."""

    id_prefix: ClassVar[str] = "API"

    code: str = Field(default="", description="예: API-001")
    name: str = Field(min_length=1)
    path: str = ""
    method: str = Field(default="GET", description="HTTP 메서드 또는 프로토콜")
    request_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    auth: str = Field(default="", description="인증·권한")
    error_codes: list[str] = Field(default_factory=list)
    validation_rules: list[str] = Field(default_factory=list)
    idempotency: str = Field(default="", description="중복 요청 처리")
    timeout_retry: str = ""
    paging_limits: str = ""
    logging_audit: str = ""
    api_version: str = Field(default="v1", description="버전·하위 호환")
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_screen_ids: list[str] = Field(default_factory=list)
    related_table_ids: list[str] = Field(default_factory=list)
    status: str = "draft"
    version: int = 1


class DesignItem(ProjectScoped):
    """설계 항목 (화면·DB·API 로 분류되지 않는 설계 결정: 배치·연계·보안·배포 등)."""

    id_prefix: ClassVar[str] = "DSG"

    code: str = Field(default="", description="예: DSG-001")
    name: str = Field(min_length=1)
    category: str = Field(
        default="other", description="batch | integration | security | deploy | data | other"
    )
    description: str = ""
    decisions: list[str] = Field(default_factory=list, description="설계 결정과 근거")
    alternatives: list[str] = Field(default_factory=list)
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_component_ids: list[str] = Field(default_factory=list)
    status: str = "draft"
    version: int = 1


class CodeModule(ProjectScoped):
    """코드 모듈 (지시문 §13·§17 — 개발 관리 범위, 결정 D-14). 고객 시스템 코드 생성은 범위 밖."""

    id_prefix: ClassVar[str] = "MOD"

    code: str = Field(default="", description="예: MOD-001")
    name: str = Field(min_length=1)
    path: str = Field(default="", description="저장소 경로 또는 패키지")
    layer: str = ""
    description: str = ""
    owner: str = ""
    review_status: str = Field(
        default="not_reviewed",
        description="not_reviewed | in_review | approved | changes_requested",
    )
    review_checklist: list[str] = Field(default_factory=list)
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_api_ids: list[str] = Field(default_factory=list)
    related_screen_ids: list[str] = Field(default_factory=list)
    related_table_ids: list[str] = Field(default_factory=list)
    status: str = "planned"
    version: int = 1


class ComponentConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_component_id: str
    protocol: str = ""
    note: str = ""


class ArchitectureComponent(ProjectScoped):
    id_prefix: ClassVar[str] = "ARC"

    layer: str
    name: str
    technology: str = ""
    description: str = ""
    connections: list[ComponentConnection] = Field(default_factory=list)
    diagram_kinds: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
