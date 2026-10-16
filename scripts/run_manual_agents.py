"""API 키 없이 제안 단계 전체를 실행하는 대행 스크립트 (계산기 RFP 예시).

에이전트 역할(RFP 분석·요구사항 추출·독립 검증·기술 조사·아키텍처·WBS·제안 문안)의 출력을 이 파일에 **사람(세션의
Claude)이 직접 작성한 JSON**으로 넣고, 나머지(추출·ID 발급·출처 검증·게이트·일정 계산·파일 생성·QA)는 실제 코드가
수행한다. 결과는 실제 데이터 루트(``Output/``, ``workspace/pwa.sqlite3``)에 저장되어 Streamlit 화면에서 열 수 있다.

주의: 에이전트 출력이 모델 응답이 아니라 수동 작성본이므로, 기록·보고서에 그 사실을 남긴다. 기술 조사 출처 URL은
세션에서 열람하지 않았으므로 '미확인'으로 표기한다. 게이트 승인은 대행 승인으로 기록하고 Gate 5(최종)는 사람에게 남긴다.

실행: .venv\\Scripts\\python scripts\\run_manual_agents.py "C:\\path\\to\\계산기.docx"
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from proposal_agent.agents import AgentRequest, FakeAgentRunner  # noqa: E402
from proposal_agent.config import ProjectPaths, Settings  # noqa: E402
from proposal_agent.models import DocumentKind, GateStatus, ProjectMode  # noqa: E402
from proposal_agent.models.verification import FINDING_KINDS  # noqa: E402
from proposal_agent.orchestrator import StepRunner  # noqa: E402
from proposal_agent.requirements.id_policy import normalize_text  # noqa: E402
from proposal_agent.services import AppContext, Services  # noqa: E402

ACTOR = "claude-session(대행)"
NOTE = "세션의 Claude가 API 키 없이 에이전트 출력을 수동 작성해 대행 — 사용자 확인 필요"

# --- 1. RFP 분석 ---------------------------------------------------------------------------------
RFP_ANALYSIS: dict[str, Any] = {
    "overview": "Windows 공학용 계산기 수준의 연산을 제공하는 PC 웹 기반 공학용 계산기 프로그램 개발. 사용자는 웹 UI에서 수식을 입력하고 결과와 계산 이력을 확인한다.",
    "client_goals": [
        "웹에서 공학용 계산 제공",
        "입력 오류를 즉시 알려 주는 사용성",
        "고정밀·큰 수 계산 지원",
    ],
    "scope_summary": "PC 웹 UI(모바일 미지원), 프론트 입력 유효성 검사, 서버 측 계산, 계산 이력 표시, 키보드·버튼 입력, 소수점 21자리 표시·반올림, 10^25까지 큰 수 계산, 부족한 요구사항·추천 기능의 추가 제안 및 구현",
    "sections": [
        {
            "title": "요구사항 목록(11개 항목)",
            "summary": "개발 목적, 지원 연산, 플랫폼, 이력, 역할 분담(프론트 검증/서버 계산), 오류 표시, 입력 방식, 정밀도, 계산 범위, 추가 제안",
            "source_block_ids": [],
        }
    ],
    "constraints": [
        "모바일 미지원, PC Web으로만 동작",
        "실제 계산은 서버에서 수행(프론트는 유효성 검사만)",
        "소수점 표시 0.000000000000000000001(21자리)까지, 초과 시 반올림",
        "계산 허용 범위 10,000,000,000,000,000,000,000,000(10^25)까지",
    ],
    "evaluation_criteria": [],
    "schedule_hints": [],
    "budget_hints": [],
    "named_solutions": ["Windows 계산기(공학용) — 연산 범위의 기준"],
    "integration_targets": [],
    "uncertainties": [
        "'윈도우 공학용 계산기가 제공하는 연산'의 정확한 목록은 RFP에 없음 — 삼각/로그/지수/팩토리얼/진법·각도 모드 등 범위 확정 필요",
        "계산 이력의 보존 기간·개수·저장 위치(세션/서버) 미정",
        "동시 사용자 수·응답 시간·보안 요구 없음",
        "사업 기간·예산·제출 조건·평가 기준이 RFP에 없음",
    ],
}

# --- 2. 요구사항 (rfp_quote는 원문 문장 그대로; source_block_ids는 실행 시 블록 매칭으로 채움) -----------
REQUIREMENTS: list[dict[str, Any]] = [
    {
        "name": "공학용 계산기 프로그램 개발",
        "description": "Windows에서 제공하는 공학용 계산기 수준의 공학용 계산기 프로그램을 개발한다.",
        "type": "functional",
        "category": "business",
        "rfp_quote": "공학용 계산기 프로그램을 개발합니다.",
        "priority": "high",
        "rationale": "사업 목적 문장",
    },
    {
        "name": "Windows 공학용 계산기 연산 지원",
        "description": "Windows 계산기(공학용)가 제공하는 연산(사칙·괄호·거듭제곱·제곱근·삼각함수·로그·지수·팩토리얼·역수·상수 π/e·부호·백분율 등)을 지원한다. 정확한 연산 목록은 확정 필요.",
        "type": "functional",
        "category": "business",
        "rfp_quote": "계산은 윈도우에서 제공하는 계산기(공학용)에서 제공하는 연산을 지원한다.",
        "priority": "high",
        "rationale": "지원 연산의 기준을 Windows 공학용 계산기로 명시",
        "verification_method": "시험(연산별 결과 대조)",
        "confidence": 0.75,
    },
    {
        "name": "웹 계산기 UI 수식 입력·결과 확인",
        "description": "웹으로 구현하며 사용자가 계산기 UI를 이용해 수식을 입력하고 결과를 확인할 수 있어야 한다.",
        "type": "functional",
        "category": "ui",
        "rfp_quote": "웹으로 구현하며 사용자가 계산기 UI를 이용하여 수식을 입력하고, 결과를 확인할 수 있어야 합니다",
        "priority": "high",
        "verification_method": "시연",
    },
    {
        "name": "PC 웹 전용(모바일 미지원)",
        "description": "모바일은 지원하지 않으며 PC Web 환경에서 동작한다.",
        "type": "constraint",
        "category": "compatibility",
        "rfp_quote": "모바일은 지원하지 않고, PC Web으로 동작합니다.",
        "priority": "medium",
        "verification_method": "검사(지원 브라우저 목록)",
    },
    {
        "name": "계산 이력 표시",
        "description": "수행한 계산의 이력(수식·결과)을 화면에 표시한다.",
        "type": "functional",
        "category": "ui",
        "rfp_quote": "계산 이력을 표시합니다.",
        "priority": "medium",
        "verification_method": "시연",
    },
    {
        "name": "프론트 입력 유효성 검사·서버 계산",
        "description": "프론트엔드에서 입력 유효성을 검사하고, 실제 계산은 서버에서 수행한다.",
        "type": "functional",
        "category": "interface",
        "rfp_quote": "프론트에서는 입력 유효성을 체크하고, 실제 계산은 서버에서 진행합니다.",
        "priority": "high",
        "verification_method": "시험(네트워크 요청 확인)",
    },
    {
        "name": "허용되지 않는 입력 오류 메시지 표시",
        "description": "허용되지 않는 입력이 들어오면 허용되지 않는 입력임과 어떤 오류인지를 화면 하단 메시지 박스에 표시한다.",
        "type": "functional",
        "category": "ui",
        "rfp_quote": "허용되지 않는 입력이 인입되는 경우 사용자에게 허용되지 않는 입력이며, 어떤 오류가 있는지 화면 하단 메시지 박스에 표시합니다.",
        "priority": "high",
        "verification_method": "시험(오류 입력 케이스)",
    },
    {
        "name": "키보드 및 UI 버튼 입력",
        "description": "키보드 입력과 화면 UI(버튼) 입력을 모두 허용한다.",
        "type": "functional",
        "category": "ui",
        "rfp_quote": "키보드 입력 및 UI 입력을 허용합니다.",
        "priority": "medium",
        "verification_method": "시연",
    },
    {
        "name": "소수점 21자리 표시·초과 시 반올림",
        "description": "소수점 아래 자리수 표시는 0.000000000000000000001(소수점 21자리)까지 지원하며, 자리수를 넘어서는 경우 반올림하여 표시한다.",
        "type": "non_functional",
        "category": "performance",
        "rfp_quote": "소수점 아래 자리수 표시는 0.000000000000000000001까지 지원하며, 자리수를 넘어서는 경우 반올림하여 표시합니다.",
        "priority": "high",
        "verification_method": "시험(경계값)",
        "rationale": "정밀도 요구 — 부동소수점이 아닌 고정밀 십진 연산 필요",
    },
    {
        "name": "큰 수 계산 허용 범위 10^25",
        "description": "계산 허용 범위는 10,000,000,000,000,000,000,000,000(10^25)까지의 큰 숫자 계산을 허용한다.",
        "type": "non_functional",
        "category": "performance",
        "rfp_quote": "계산 허용범위는 10000000000000000000000000 까지 큰 숫자 계산을 허용합니다.",
        "priority": "high",
        "verification_method": "시험(경계값)",
        "rationale": "64비트 부동소수점 유효자릿수(약 15~17자리)를 넘으므로 임의 정밀도 연산 필요",
    },
    {
        "name": "부족한 요구사항·추천 기능의 추가 제안 및 구현",
        "description": "RFP에 부족한 요구사항이나 추천 기능은 제안서에 추가 요건으로 제안하고 구현한다.",
        "type": "submission",
        "category": "constraint",
        "rfp_quote": "기타 부족한 요구사항이나 추천하고자 하는 기능은 추가 요건으로 제안하고, 구현합니다.",
        "priority": "medium",
        "verification_method": "검사(제안서 추가 요건 절)",
    },
    # 부가 제안 (RFP 마지막 문장에 근거, 필수 아님)
    {
        "name": "[부가 제안] 계산 이력 재사용·내보내기",
        "description": "이력 항목을 클릭하면 수식을 입력란에 다시 불러오고, 이력을 CSV로 내보낸다.",
        "type": "functional",
        "category": "ui",
        "scope_class": "optional_proposal",
        "is_mandatory": False,
        "rfp_quote": "",
        "_match": "기타 부족한 요구사항이나 추천하고자 하는 기능은 추가 요건으로 제안하고, 구현합니다.",
        "priority": "low",
        "impact_note": "프론트 2 M/D 추가, 일정 영향 없음, 운영 영향 없음",
        "rationale": "추가 제안 요건에 따른 추천 기능",
    },
    {
        "name": "[부가 제안] 정밀도·범위 초과 사전 경고",
        "description": "입력 중 소수점 21자리 또는 10^25를 넘는 값을 감지하면 계산 전에 경고를 표시한다.",
        "type": "functional",
        "category": "ui",
        "scope_class": "optional_proposal",
        "is_mandatory": False,
        "rfp_quote": "",
        "_match": "기타 부족한 요구사항이나 추천하고자 하는 기능은 추가 요건으로 제안하고, 구현합니다.",
        "priority": "low",
        "impact_note": "프론트 1 M/D 추가, 일정·운영 영향 없음",
        "rationale": "정밀도·범위 요구사항을 보완하는 추천 기능",
    },
]


UNRESOLVED: list[str] = [
    "'윈도우 공학용 계산기 연산' 목록 확정 필요",
    "계산 이력 보존 범위(세션/서버·개수) 미정",
    "사업 기간·예산·제출 조건·평가 기준 없음",
]
# 검증 대행: (chunk 모드에서 낼 소견 1건) — fixture 로 바꿀 수 있다
VERIFIER_FINDING: dict[str, Any] = {
    "kind": "feasibility_check_needed",
    "severity": "info",
    "requirement_prefix": "FR-00",
    "message": "'공학용 연산'의 구체 목록(삼각·로그·진법·각도 모드 등)이 원문에 없어 범위 확정이 필요함",
    "evidence_quote": "계산은 윈도우에서 제공하는 계산기(공학용)에서 제공하는 연산을 지원한다.",
    "suggested_fix": "발주처와 연산 목록을 합의하고 요구사항 설명에 명시",
}
VERIFIER_COMMENTS: dict[str, str] = {"FR-001": "사업 목적 문장 — 개별 기능보다 상위 항목"}
PROJECT: dict[str, Any] = {
    "name": "공학용 계산기 웹 개발",
    "start_date": date(2026, 11, 2),
    "end_date": date(2027, 1, 29),
    "client_name": "(RFP 미기재)",
    "placeholder_picture": True,
}


def extractor(request: AgentRequest) -> dict[str, Any]:
    blocks = [
        (m.group(1), m.group(2))
        for m in re.finditer(r'<block id="([^"]+)"[^>]*>\n?(.*?)\n?</block>', request.prompt, re.S)
    ]
    out = []
    for r in REQUIREMENTS:
        q = normalize_text(r.get("_match") or r["rfp_quote"])
        ids = [bid for bid, text in blocks if q and q in normalize_text(text)]
        if not ids:
            continue
        item = {
            "scope_class": "mandatory",
            "is_mandatory": True,
            "confidence": 0.9,
            "source_block_ids": ids,
            **{k: v for k, v in r.items() if k != "_match"},
        }
        out.append(item)
    return {
        "requirements": out,
        "unresolved_items": list(UNRESOLVED) if blocks else [],
        "notes": NOTE,
    }


def verifier(request: AgentRequest) -> dict[str, Any]:
    ids = re.findall(r'"id": "([A-Z]+-\d+)"', request.prompt)
    kind_missing = (
        "feasibility_check_needed"
        if "feasibility_check_needed" in FINDING_KINDS
        else FINDING_KINDS[0]
    )
    verdicts = []
    for i in ids:
        verdicts.append(
            {"requirement_id": i, "verdict": "verified", "comment": VERIFIER_COMMENTS.get(i, "")}
        )
    findings = []
    if "모드: chunk" in request.prompt and VERIFIER_FINDING:
        f = VERIFIER_FINDING
        findings.append(
            {
                "kind": f.get("kind", kind_missing)
                if f.get("kind", kind_missing) in FINDING_KINDS
                else kind_missing,
                "severity": f.get("severity", "info"),
                "requirement_ids": [
                    x for x in ids if x.startswith(f.get("requirement_prefix", ""))
                ][:1],
                "message": f["message"],
                "evidence_quote": f.get("evidence_quote", ""),
                "suggested_fix": f.get("suggested_fix", ""),
            }
        )
    return {
        "verdicts": verdicts,
        "findings": findings,
        "coverage_estimate": 1.0,
        "summary": f"요구사항 {len(ids)}건 검증 ({NOTE})",
    }


# --- 2-2. 요구사항별 구현 방안 (Phase 14, 세션의 Claude가 수동 작성; 요구사항 이름 키워드로 매칭) ------------
APPROACHES: list[tuple[tuple[str, ...], dict[str, Any]]] = [
    (
        ("프로그램 개발", "연산 지원"),
        {
            "approach": "서버 계산 엔진(Python decimal/mpmath)에 사칙·거듭제곱·삼각·로그·팩토리얼 연산을 구현\n수식 파서는 토큰화→후위 표기 변환→평가 순으로 서버에서 처리\n전제: 지원 연산 목록은 Windows 공학용 계산기 기준으로 고객과 확정",
            "difficulty": "중",
            "difficulty_basis": "임의 정밀도 연산·수식 파서 구현",
            "analysis": {
                "purpose": ["Windows 공학용 계산기 수준의 연산을 웹에서 제공"],
                "conditions": ["소수점 21자리 표시", "10^25 범위"],
                "inputs_outputs": ["입력: 수식 문자열", "출력: 결과 문자열 또는 오류 코드"],
                "business_rules": ["연산자 우선순위·괄호 규칙", "0 나누기·범위 초과는 오류"],
                "flow_exceptions": ["토큰화 → 후위 표기 → 평가", "문법 오류 시 E_SYNTAX"],
                "screens_interaction": ["입력창·버튼 패드·결과·이력 영역"],
                "api_integration": ["POST /api/calc"],
                "data_transactions": ["calc_history 1행 삽입(트랜잭션 단일)"],
                "auth_privacy_audit": ["개인정보 없음, 요청 로그만"],
                "performance_scalability": ["무상태 API, 수평 확장 가능"],
                "failure_recovery": ["계산 실패는 오류 코드, 서버 장애 시 재시도 안내"],
                "operations": ["오류율·응답 시간 로그"],
                "impact": [
                    "난이도 중: 파서·정밀도 시험 비용",
                    "assumption: 지원 연산 목록은 착수 시 확정",
                ],
                "test_acceptance": ["경계값 21자리·10^25 시험 케이스 통과"],
            },
            "verification_method": "시험",
            "acceptance_criteria": "지원 연산 목록의 각 연산이 기준 계산기와 같은 결과를 냄",
        },
    ),
    (
        ("수식 입력", "키보드"),
        {
            "approach": "React/TypeScript 웹 UI에 수식 입력창·버튼 패드·결과 영역 구성\n키보드 입력과 버튼 입력을 같은 입력 상태로 합쳐 처리\n전제: PC 브라우저 전용(반응형 모바일 미지원)",
            "difficulty": "하",
            "difficulty_basis": "일반 화면 구성",
            "verification_method": "시연",
            "acceptance_criteria": "키보드·버튼으로 같은 수식을 입력해 같은 결과를 표시",
        },
    ),
    (
        ("PC 웹",),
        {
            "approach": "데스크톱 브라우저(최신 Chrome/Edge) 기준으로 레이아웃 고정 폭 설계\n모바일 UA는 지원하지 않음을 안내",
            "difficulty": "하",
            "difficulty_basis": "제약 반영",
            "verification_method": "검사",
            "acceptance_criteria": "지원 브라우저 목록에서 정상 동작",
        },
    ),
    (
        ("이력 표시", "재사용"),
        {
            "approach": "계산 결과를 서버 DB(SQLite→PostgreSQL 전환 가능)에 저장하고 최근 이력을 목록으로 표시\n이력 클릭 시 수식을 입력창에 재적재, 내보내기는 CSV 다운로드",
            "difficulty": "하",
            "difficulty_basis": "단순 CRUD·목록",
            "verification_method": "시연",
            "acceptance_criteria": "계산 후 이력 목록에 즉시 표시되고 재적재·내보내기가 동작",
        },
    ),
    (
        ("유효성", "오류 메시지", "사전 경고"),
        {
            "approach": "프론트에서 괄호 짝·허용 문자·연속 연산자를 즉시 검사해 오류 메시지 표시\n실제 계산은 FastAPI 계산 API가 수행하고 오류 코드를 반환\n범위·정밀도 초과는 계산 전 사전 경고",
            "difficulty": "중",
            "difficulty_basis": "프론트·서버 이중 검증 규칙",
            "verification_method": "시험",
            "acceptance_criteria": "허용되지 않는 입력마다 정의된 메시지가 표시되고 서버가 거부",
        },
    ),
    (
        ("소수점", "큰 수"),
        {
            "approach": "서버 decimal 컨텍스트 정밀도 50자리, 표시 시 소수점 21자리 반올림\n10^25 범위 검사 후 초과 시 오류 반환\n전제: 삼각·로그 함수는 mpmath로 구현(조사 미확인 항목)",
            "difficulty": "상",
            "difficulty_basis": "임의 정밀도 수치 조건(21자리·10^25)",
            "verification_method": "시험",
            "acceptance_criteria": "경계값(21자리·10^25) 시험 케이스 통과",
        },
    ),
]


def approach_writer(request: AgentRequest) -> dict[str, Any]:
    """프롬프트의 <req id name> 묶음마다 키워드로 사람 작성 방안을 붙인다. 조사 ID는 related로 연결."""
    reqs = re.findall(r'<req id="([^"]+)"[^>]*>\nname: (.*)', request.prompt)
    items_in_prompt = re.findall(
        r'<item id="([^"]+)" feasibility="([^"]+)" related="([^"]*)"', request.prompt
    )
    items = []
    for rid, name in reqs:
        spec = next((v for keys, v in APPROACHES if any(k in name for k in keys)), None)
        if spec is None:
            continue
        refs = [tid for tid, _, rel in items_in_prompt if rid in rel.split(",")]
        feas = "feasible" if refs else "unknown"
        items.append(
            {
                "requirement_id": rid,
                "research_refs": refs,
                "sources": [],
                "feasibility": feas,
                "notes": "" if refs else "근거 조사 없음 — 설계 단계 확인",
                **spec,
            }
        )
    return {"items": items, "research_needed": [], "notes": NOTE}


# --- 2-4. 요구사항 묶음별 구현 설계 (Phase 23, 세션의 Claude가 수동 작성 — 샘플 계산기) ------------------
DESIGNS: dict[str, Any] = {
    "designs": [
        {
            "title": "수식 입력·계산 엔진·결과 표시",
            "requirement_ids": [
                "FR-001",
                "FR-002",
                "FR-003",
                "FR-005",
                "FR-006",
                "NFR-001",
                "NFR-002",
            ],
            "key_message": "입력 검증은 브라우저, 계산은 서버 decimal 엔진으로 나눠 정밀도와 범위를 보장한다",
            "overview": [
                "React/TypeScript 화면이 수식을 토큰 단위로 검증하고, FastAPI 계산 API가 후위 표기 평가로 결과를 낸다",
                "Python decimal 컨텍스트 정밀도 50자리로 계산한 뒤 표시 시 소수점 21자리로 반올림한다",
                "10^25 범위 검사를 서버에서 수행해 초과 시 오류 코드를 반환한다",
            ],
            "structure": [
                {
                    "name": "계산기 화면(SPA)",
                    "layer": "client",
                    "technology": "React 18 · TypeScript",
                    "role": "수식 입력창·버튼 패드·결과·이력 표시, 즉시 검증",
                    "requirement_ids": ["FR-003", "FR-005"],
                },
                {
                    "name": "계산 API",
                    "layer": "app",
                    "technology": "FastAPI",
                    "role": "수식 파싱·평가·오류 코드 반환",
                    "requirement_ids": ["FR-001", "FR-005"],
                },
                {
                    "name": "계산 엔진",
                    "layer": "app",
                    "technology": "Python decimal / mpmath",
                    "role": "사칙·거듭제곱·삼각·로그·팩토리얼 임의 정밀도 연산",
                    "requirement_ids": ["FR-001", "NFR-001", "NFR-002"],
                },
                {
                    "name": "이력 저장소",
                    "layer": "data",
                    "technology": "SQLite(개발) → PostgreSQL(운영 전환 가능)",
                    "role": "계산 이력 저장·최근 목록 조회",
                    "requirement_ids": ["FR-006"],
                },
            ],
            "flows": [
                {
                    "title": "수식 입력",
                    "actor": "사용자",
                    "action": "키보드·버튼 입력을 같은 입력 상태로 합쳐 표시",
                },
                {
                    "title": "즉시 검증",
                    "actor": "계산기 화면",
                    "action": "괄호 짝·허용 문자·연속 연산자 검사",
                    "decision": "오류 → 입력창 아래 메시지, 서버 호출 안 함",
                },
                {
                    "title": "계산 요청",
                    "actor": "계산기 화면",
                    "action": "POST /api/calc {expression} 호출",
                },
                {
                    "title": "파싱·평가",
                    "actor": "계산 API",
                    "action": "토큰화 → 후위 표기 변환 → decimal 평가",
                    "decision": "범위 초과·0 나누기 → 오류 코드 반환",
                },
                {
                    "title": "결과·이력 저장",
                    "actor": "계산 엔진",
                    "action": "21자리 반올림 결과 반환, 이력 테이블에 수식·결과 저장",
                },
                {
                    "title": "이력 재사용",
                    "actor": "사용자",
                    "action": "이력 클릭 → 수식을 입력창에 재적재",
                },
            ],
            "tech_choices": [
                {
                    "area": "업무 처리",
                    "choice": "Python decimal (정밀도 50자리 컨텍스트)",
                    "reason": "소수점 21자리·10^25 범위 요구를 부동소수점 오차 없이 만족",
                    "alternatives": [
                        "JavaScript Number — 배정밀도 15~17자리로 요구 미달",
                        "BigInt — 소수 미지원",
                    ],
                    "source": "https://docs.python.org/3/library/decimal.html",
                    "verified": False,
                },
                {
                    "area": "프레임워크",
                    "choice": "FastAPI + React/TypeScript",
                    "reason": "계산 API와 화면을 분리해 검증(프론트)과 계산(서버)을 나누는 RFP 요구에 맞음",
                    "alternatives": ["서버 렌더링 단일 앱 — 즉시 검증 UX가 약해 배제"],
                    "source": "RFP",
                    "verified": True,
                },
            ],
            "comparisons": [
                {
                    "topic": "고정밀 계산 엔진",
                    "options": [
                        {
                            "name": "Python decimal",
                            "pros": ["표준 라이브러리", "정밀도 컨텍스트 지정"],
                            "cons": ["삼각·로그 미지원"],
                            "constraints": ["초월함수는 별도 구현"],
                            "compatibility": "FastAPI 서버와 동일 런타임",
                            "cost_complexity": "낮음",
                            "risk": "초월함수 정밀도",
                            "performance": "충분",
                            "fit_conditions": "사칙·거듭제곱 중심",
                        },
                        {
                            "name": "mpmath",
                            "pros": ["임의 정밀도 초월함수"],
                            "cons": ["추가 의존성", "속도"],
                            "constraints": [],
                            "compatibility": "동일 런타임",
                            "cost_complexity": "낮음",
                            "risk": "낮음",
                            "performance": "느릴 수 있음",
                            "fit_conditions": "삼각·로그 포함",
                        },
                        {
                            "name": "JavaScript BigNumber(브라우저)",
                            "pros": ["서버 호출 불필요"],
                            "cons": ["RFP 의 서버 계산 요구와 불일치"],
                            "constraints": ["RFP 구조 위배"],
                            "compatibility": "낮음",
                            "cost_complexity": "중",
                            "risk": "요구 불일치",
                            "performance": "-",
                            "fit_conditions": "해당 없음",
                        },
                    ],
                    "recommended": "mpmath",
                    "reason": "삼각·로그까지 21자리를 보장해야 하므로 decimal 만으로는 부족",
                    "poc_needed": True,
                    "poc_scope": "sin·log 경계값 10건의 21자리 일치 여부",
                    "source": "설계 제안",
                },
            ],
            "performance_scalability": ["계산 API 는 무상태, 요청당 100ms 이내 목표(측정 후 확정)"],
            "failure_recovery": ["계산 오류는 오류 코드로 반환, 서버 재시작 시 이력은 DB 에 보존"],
            "operations_monitoring": ["요청 수·오류율 로그, 느린 계산(1초 초과) 경고"],
            "auth_security": ["입력 길이·연산자 화이트리스트로 과도한 계산 차단"],
            "test_approach": ["경계값(21자리·10^25) 단위 시험, 수식 파서 속성 기반 시험"],
            "data_interfaces": [
                "POST /api/calc 요청 {expression}, 응답 {result, error_code}",
                "calc_history(id, expression, result, created_at) — 최근 50건 조회 인덱스",
                "오류 코드: E_SYNTAX(문법), E_RANGE(범위 초과), E_DIVZERO(0 나누기)",
            ],
            "premises": ["지원 연산 목록은 Windows 공학용 계산기 기준으로 고객과 확정"],
            "risks": ["삼각·로그 함수의 정밀도 — mpmath 로 보강, 경계값 시험으로 검증"],
        },
        {
            "title": "PC 웹 호환성·레이아웃",
            "requirement_ids": ["FR-004", "FR-007", "FR-008", "FR-009", "CON-001"],
            "key_message": "데스크톱 최신 브라우저 기준 고정 폭 레이아웃으로 범위를 명확히 한다",
            "overview": [
                "Chrome·Edge 최신 2개 버전을 지원 범위로 두고 레이아웃을 고정 폭으로 설계",
                "모바일 UA는 지원하지 않음을 안내",
            ],
            "structure": [
                {
                    "name": "레이아웃 셸",
                    "layer": "client",
                    "technology": "CSS Grid 고정 폭 1200px",
                    "role": "입력·결과·이력 3영역 배치",
                },
                {
                    "name": "UA 안내 스크립트",
                    "layer": "client",
                    "technology": "navigator.userAgentData 분기",
                    "role": "모바일 접속 시 안내 문구",
                },
            ],
            "flows": [
                {"title": "접속", "actor": "사용자", "action": "URL 접속"},
                {
                    "title": "환경 판별",
                    "actor": "UA 안내 스크립트",
                    "action": "데스크톱 여부 판별",
                    "decision": "모바일 → 안내 화면",
                },
                {"title": "화면 표시", "actor": "레이아웃 셸", "action": "3영역 고정 폭 렌더링"},
            ],
            "tech_choices": [
                {
                    "area": "UI",
                    "choice": "CSS Grid 고정 폭 레이아웃",
                    "reason": "PC 전용 범위(CON-001)에서 반응형 분기 비용을 없앰",
                    "alternatives": ["반응형 레이아웃 — 범위 밖(모바일 미지원)이라 배제"],
                    "source": "RFP",
                    "verified": True,
                },
            ],
            "data_interfaces": ["지원 브라우저 목록(설정 파일) — 시험 체크리스트와 동일"],
            "premises": ["지원 브라우저 버전은 착수 시 고객과 확정"],
            "risks": [],
        },
    ],
    "research_needed": [],
    "notes": NOTE,
}


# --- 7-1. 코드 생성 대행 응답 (단계 7, D-22) — 계산기 Spring Boot 프로토타입 (실제 컴파일·JUnit 가능) ----------------
DEVELOPER_FILES: dict[str, str] = {
    "src/main/java/com/app/calc/CalcService.java": """package com.app.calc;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

/** 고정밀 계산 엔진: 토큰화 → 후위 표기(Shunting-yard) → BigDecimal 평가. FR-001·FR-002·NFR-001 */
public class CalcService {
    public static final int PRECISION = 21;
    private static final MathContext MC = new MathContext(PRECISION, RoundingMode.HALF_UP);
    private static final BigDecimal LIMIT = new BigDecimal("1E25");

    /** 수식 문법 오류·범위 초과를 코드로 구분한다 (E001 문법, E002 0 나누기, E003 범위 초과). */
    public static class CalcException extends RuntimeException {
        private final String code;

        public CalcException(String code, String message) {
            super(message);
            this.code = code;
        }

        public String getCode() {
            return code;
        }
    }

    public BigDecimal evaluate(String expression) {
        if (expression == null || expression.isBlank() || expression.length() > 200) {
            throw new CalcException("E001", "수식은 1~200자여야 합니다");
        }
        List<String> tokens = tokenize(expression);
        List<String> rpn = toPostfix(tokens);
        BigDecimal result = evalPostfix(rpn);
        if (result.abs().compareTo(LIMIT) > 0) {
            throw new CalcException("E003", "결과가 범위(10^25)를 초과합니다");
        }
        return result.round(MC).stripTrailingZeros();
    }

    private List<String> tokenize(String expr) {
        List<String> out = new ArrayList<>();
        int i = 0;
        while (i < expr.length()) {
            char c = expr.charAt(i);
            if (Character.isWhitespace(c)) {
                i++;
            } else if (Character.isDigit(c) || c == '.') {
                int j = i;
                while (j < expr.length() && (Character.isDigit(expr.charAt(j)) || expr.charAt(j) == '.')) {
                    j++;
                }
                out.add(expr.substring(i, j));
                i = j;
            } else if ("+-*/()".indexOf(c) >= 0) {
                out.add(String.valueOf(c));
                i++;
            } else {
                throw new CalcException("E001", "허용되지 않은 문자: " + c);
            }
        }
        return out;
    }

    private int precedence(String op) {
        return (op.equals("*") || op.equals("/")) ? 2 : 1;
    }

    private List<String> toPostfix(List<String> tokens) {
        List<String> out = new ArrayList<>();
        Deque<String> ops = new ArrayDeque<>();
        int depth = 0;
        for (String t : tokens) {
            if (t.equals("(")) {
                ops.push(t);
                depth++;
            } else if (t.equals(")")) {
                depth--;
                if (depth < 0) {
                    throw new CalcException("E001", "괄호 짝이 맞지 않습니다");
                }
                while (!ops.isEmpty() && !ops.peek().equals("(")) {
                    out.add(ops.pop());
                }
                ops.pop();
            } else if ("+-*/".contains(t)) {
                while (!ops.isEmpty() && !ops.peek().equals("(") && precedence(ops.peek()) >= precedence(t)) {
                    out.add(ops.pop());
                }
                ops.push(t);
            } else {
                out.add(t);
            }
        }
        if (depth != 0) {
            throw new CalcException("E001", "괄호 짝이 맞지 않습니다");
        }
        while (!ops.isEmpty()) {
            out.add(ops.pop());
        }
        return out;
    }

    private BigDecimal evalPostfix(List<String> rpn) {
        Deque<BigDecimal> stack = new ArrayDeque<>();
        for (String t : rpn) {
            if ("+-*/".contains(t)) {
                if (stack.size() < 2) {
                    throw new CalcException("E001", "연산자 위치가 잘못되었습니다");
                }
                BigDecimal b = stack.pop();
                BigDecimal a = stack.pop();
                switch (t) {
                    case "+" -> stack.push(a.add(b, MC));
                    case "-" -> stack.push(a.subtract(b, MC));
                    case "*" -> stack.push(a.multiply(b, MC));
                    default -> {
                        if (b.signum() == 0) {
                            throw new CalcException("E002", "0 으로 나눌 수 없습니다");
                        }
                        stack.push(a.divide(b, MC));
                    }
                }
            } else {
                try {
                    stack.push(new BigDecimal(t));
                } catch (NumberFormatException e) {
                    throw new CalcException("E001", "숫자 형식 오류: " + t);
                }
            }
        }
        if (stack.size() != 1) {
            throw new CalcException("E001", "수식이 완전하지 않습니다");
        }
        return stack.pop();
    }
}
""",
    "src/main/java/com/app/calc/CalcController.java": """package com.app.calc;

import java.math.BigDecimal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import com.app.history.HistoryRepository;

/** 계산 실행 API (POST /api/calc). FR-002·FR-006·NFR-002 */
@RestController
public class CalcController {
    private final CalcService service;
    private final HistoryRepository history;

    public CalcController(HistoryRepository history) {
        this.service = new CalcService();
        this.history = history;
    }

    @PostMapping("/api/calc")
    public Map<String, Object> calc(@RequestBody Map<String, String> body) {
        String expression = body.getOrDefault("expression", "");
        BigDecimal result = service.evaluate(expression);
        history.add(expression, result.toPlainString(), null);
        return Map.of("result", result.toPlainString());
    }

    @ExceptionHandler(CalcService.CalcException.class)
    public ResponseEntity<Map<String, String>> onCalcError(CalcService.CalcException e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("code", e.getCode(), "message", e.getMessage()));
    }
}
""",
    "src/main/java/com/app/history/HistoryRepository.java": """package com.app.history;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Repository;

/** 계산 이력 저장소 (메모리, 최근 순). FR-004·FR-005 — 프로토타입은 메모리 보관, 운영은 CALC_HISTORY 테이블 */
@Repository
public class HistoryRepository {
    private final List<Map<String, Object>> items = Collections.synchronizedList(new ArrayList<>());
    private final AtomicLong seq = new AtomicLong();

    public Map<String, Object> add(String expression, String result, String errorCode) {
        Map<String, Object> row = Map.of(
                "history_id", seq.incrementAndGet(),
                "expression", expression,
                "result", result == null ? "" : result,
                "error_code", errorCode == null ? "" : errorCode,
                "created_at", LocalDateTime.now().toString());
        items.add(0, row);
        return row;
    }

    public List<Map<String, Object>> list(String keyword, int page, int size) {
        List<Map<String, Object>> filtered = new ArrayList<>();
        synchronized (items) {
            for (Map<String, Object> row : items) {
                if (keyword == null || keyword.isBlank() || String.valueOf(row.get("expression")).contains(keyword)) {
                    filtered.add(row);
                }
            }
        }
        int from = Math.min(page * size, filtered.size());
        int to = Math.min(from + size, filtered.size());
        return new ArrayList<>(filtered.subList(from, to));
    }

    public int total() {
        return items.size();
    }

    public boolean delete(long id) {
        synchronized (items) {
            return items.removeIf(row -> Long.valueOf(id).equals(row.get("history_id")));
        }
    }
}
""",
    "src/main/java/com/app/history/HistoryController.java": """package com.app.history;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 이력 조회·삭제 API. FR-005·FR-008 */
@RestController
public class HistoryController {
    private final HistoryRepository history;

    public HistoryController(HistoryRepository history) {
        this.history = history;
    }

    @GetMapping("/api/history")
    public ResponseEntity<Map<String, Object>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        if (size > 20 || page < 0) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("code", "E101", "message", "잘못된 페이지"));
        }
        return ResponseEntity.ok(Map.of("items", history.list(keyword, page, size), "total", history.total()));
    }

    @DeleteMapping("/api/history/{id}")
    public ResponseEntity<Map<String, Object>> delete(@PathVariable long id) {
        boolean deleted = history.delete(id);
        if (!deleted) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("code", "E102", "message", "없는 이력"));
        }
        return ResponseEntity.ok(Map.of("deleted", true));
    }
}
""",
    "src/main/resources/static/index.html": """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>공학용 계산기 (프로토타입)</title>
  <style>
    body { font-family: sans-serif; margin: 16px; }
    #expression { width: 100%; font-size: 1.2em; }
    #result { font-size: 1.4em; min-height: 1.6em; }
    .state { color: #555; }
    .error { color: #b00; }
  </style>
</head>
<body>
  <h1>공학용 계산기</h1>
  <input id="expression" placeholder="수식 입력 (예: (1+2)*3/4)" maxlength="200">
  <button id="calc">계산</button>
  <div id="state" class="state"></div>
  <div id="result"></div>
  <h2>계산 이력</h2>
  <ul id="history"></ul>
  <script>
    const expr = document.getElementById('expression');
    const state = document.getElementById('state');
    const result = document.getElementById('result');
    const history = document.getElementById('history');
    function validate(v) {
      if (!v.trim()) return '수식을 입력하십시오';
      if (v.length > 200) return '수식은 200자 이내';
      let depth = 0;
      for (const ch of v) { if (ch === '(') depth++; if (ch === ')') depth--; if (depth < 0) return '괄호 짝 오류'; }
      return depth === 0 ? '' : '괄호 짝 오류';
    }
    async function loadHistory() {
      const res = await fetch('/api/history?size=20');
      const data = await res.json();
      history.innerHTML = '';
      if (!data.items || data.items.length === 0) { history.innerHTML = '<li class="state">계산 이력이 없습니다</li>'; return; }
      for (const item of data.items) {
        const li = document.createElement('li');
        li.textContent = item.expression + ' = ' + item.result;
        li.onclick = () => { expr.value = item.expression; };
        history.appendChild(li);
      }
    }
    document.getElementById('calc').onclick = async () => {
      const msg = validate(expr.value);
      if (msg) { state.textContent = msg; state.className = 'error'; return; }
      state.textContent = '계산 중…'; state.className = 'state';
      const res = await fetch('/api/calc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expression: expr.value }) });
      const data = await res.json();
      if (res.ok) { result.textContent = data.result; state.textContent = ''; }
      else { result.textContent = ''; state.textContent = '계산할 수 없는 수식입니다 (' + data.code + ')'; state.className = 'error'; }
      loadHistory();
    };
    loadHistory();
  </script>
</body>
</html>
""",
    "src/test/java/com/app/calc/CalcServiceTest.java": """package com.app.calc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** FR-002 계산 엔진 단위 테스트 */
class CalcServiceTest {
    private final CalcService service = new CalcService();

    @Test
    @DisplayName("FR-002 TC-001: 사칙연산과 괄호 우선순위를 계산한다")
    void evaluatesArithmetic() {
        assertEquals(new BigDecimal("2.25"), service.evaluate("(1+2)*3/4"));
    }

    @Test
    @DisplayName("NFR-001 TC-002: 21자리 유효 숫자로 반올림한다")
    void roundsToPrecision() {
        BigDecimal v = service.evaluate("1/3");
        assertEquals(21, v.precision());
    }

    @Test
    @DisplayName("FR-001 TC-003: 괄호 짝이 맞지 않으면 E001 오류")
    void rejectsBrokenParentheses() {
        CalcService.CalcException e = assertThrows(CalcService.CalcException.class, () -> service.evaluate("(1+2"));
        assertEquals("E001", e.getCode());
    }

    @Test
    @DisplayName("FR-002 TC-004: 0 으로 나누면 E002 오류")
    void rejectsDivisionByZero() {
        CalcService.CalcException e = assertThrows(CalcService.CalcException.class, () -> service.evaluate("1/0"));
        assertEquals("E002", e.getCode());
    }
}
""",
}


def developer_responder(request: Any) -> dict[str, Any]:
    """배치 프롬프트의 target_paths 에 해당하는 파일만 돌려준다 (실제 모델 대신)."""
    import json as _json
    import re as _re

    m = _re.search(r"target_paths=(\[[^\]]*\])", request.prompt)
    targets = _json.loads(m.group(1)) if m else []
    files = [
        {
            "path": p_,
            "content": DEVELOPER_FILES[p_],
            "purpose": "설계 구현",
            "requirement_ids": ["FR-002"] if "calc" in p_ else ["FR-005"],
        }
        for p_ in targets
        if p_ in DEVELOPER_FILES
    ]
    links = []
    for f in files:
        if f["path"].endswith("CalcService.java"):
            links.append(
                {
                    "requirement_id": "FR-002",
                    "path": f["path"],
                    "symbols": ["CalcService.evaluate"],
                    "description": "수식 평가",
                }
            )
        elif f["path"].endswith("HistoryRepository.java"):
            links.append(
                {
                    "requirement_id": "FR-005",
                    "path": f["path"],
                    "symbols": ["HistoryRepository.list"],
                    "description": "이력 조회",
                }
            )
    return {"files": files, "implementation_map": links, "notes": []}


# --- 6-1. 상세 설계 대행 응답 (단계 6, 지시문 §12) — 계산기 샘플 ------------------------------------------
DETAIL_DESIGNS: dict[str, Any] = {
    "screens": [
        {
            "name": "계산기 메인 화면",
            "screen_type": "form",
            "purpose": "수식을 입력하고 계산 결과·이력을 한 화면에서 본다",
            "user_roles": ["일반 사용자"],
            "layout": {
                "description": "상단 수식 입력, 본문 좌측 버튼 패드·우측 결과, 하단 이력",
                "regions": [
                    {"name": "상단", "components": ["수식 입력창", "삭제 버튼"]},
                    {"name": "본문", "components": ["버튼 패드(숫자·연산자·함수)", "결과 표시"]},
                    {"name": "하단", "components": ["계산 이력 목록(최근 20건)"]},
                ],
            },
            "fields": [
                {
                    "name": "expression",
                    "label": "수식",
                    "field_type": "text",
                    "required": True,
                    "validation_rules": [
                        "길이 1~200자",
                        "허용 문자: 숫자·연산자·괄호·함수명",
                        "괄호 짝 검증",
                        "키보드 입력과 버튼 패드 입력을 같은 검증기로 처리",
                        "21자리 유효 숫자·10^25 범위 초과가 예상되면 사전 경고",
                    ],
                    "error_message": "수식 형식이 올바르지 않습니다",
                    "requirement_ids": ["FR-001", "FR-003", "FR-007", "FR-009"],
                },
                {
                    "name": "result",
                    "label": "결과",
                    "field_type": "text",
                    "required": False,
                    "validation_rules": ["유효 숫자 21자리 표시"],
                    "error_message": "",
                    "requirement_ids": ["FR-002", "NFR-001"],
                },
            ],
            "actions": [
                {
                    "label": "계산",
                    "description": "수식을 서버로 보내 결과를 받는다",
                    "expected_result": "결과 표시·이력 추가",
                    "api_ref": "계산 실행 API",
                    "requirement_ids": ["FR-002"],
                },
                {
                    "label": "이력 선택",
                    "description": "이력 항목을 눌러 수식을 다시 불러온다",
                    "expected_result": "수식 입력창에 채움",
                    "api_ref": "",
                    "requirement_ids": ["FR-005"],
                },
            ],
            "states": [
                {"state": "LOADING", "message": "계산 중…"},
                {"state": "ERROR", "message": "계산할 수 없는 수식입니다 (오류 코드 표시)"},
                {"state": "EMPTY", "message": "계산 이력이 없습니다"},
            ],
            "functions": [
                {
                    "name": "수식 검증",
                    "trigger": "입력 변경",
                    "inputs": ["expression"],
                    "process": "토큰 단위 문법 검사, 괄호 짝·연속 연산자 검출 → 오류 표시",
                    "outputs": ["유효 여부"],
                    "requirement_ids": ["FR-001"],
                },
                {
                    "name": "계산 요청",
                    "trigger": "계산 버튼",
                    "inputs": ["expression"],
                    "process": "POST /api/calc 호출, 응답 1초 이내 아니면 LOADING 유지, 오류 코드면 ERROR 상태",
                    "outputs": ["result"],
                    "requirement_ids": ["FR-002", "NFR-002"],
                },
            ],
            "requirement_ids": [
                "FR-001",
                "FR-002",
                "FR-003",
                "FR-004",
                "FR-005",
                "FR-007",
                "FR-009",
                "NFR-001",
                "NFR-002",
            ],
        },
        {
            "name": "계산 이력 화면",
            "screen_type": "list",
            "purpose": "저장된 계산 이력을 조회·삭제한다",
            "user_roles": ["일반 사용자"],
            "layout": {
                "description": "본문 목록 표, 하단 페이지 이동",
                "regions": [
                    {"name": "본문", "components": ["이력 표(수식·결과·일시)"]},
                    {"name": "하단", "components": ["페이지 이동"]},
                ],
            },
            "fields": [
                {
                    "name": "keyword",
                    "label": "검색어",
                    "field_type": "text",
                    "required": False,
                    "validation_rules": ["길이 0~50자"],
                    "error_message": "",
                    "requirement_ids": ["FR-005"],
                }
            ],
            "actions": [
                {
                    "label": "삭제",
                    "description": "선택 이력 삭제",
                    "expected_result": "목록에서 제거",
                    "api_ref": "이력 삭제 API",
                    "requirement_ids": ["FR-005"],
                }
            ],
            "states": [
                {"state": "EMPTY", "message": "이력이 없습니다"},
                {"state": "ERROR", "message": "이력을 불러오지 못했습니다"},
            ],
            "functions": [
                {
                    "name": "이력 조회",
                    "trigger": "화면 진입",
                    "inputs": ["keyword"],
                    "process": "GET /api/history?keyword= 호출, 최근 순 정렬, 20건 페이지",
                    "outputs": ["이력 목록"],
                    "requirement_ids": ["FR-005", "FR-004"],
                },
                {
                    "name": "이력 재사용·내보내기",
                    "trigger": "이력 선택·내보내기 버튼",
                    "inputs": ["history_id"],
                    "process": "선택 이력 수식을 메인 화면에 채우거나 CSV 로 내보내기, 실패 시 ERROR 상태",
                    "outputs": ["수식", "CSV"],
                    "requirement_ids": ["FR-008"],
                },
            ],
            "requirement_ids": ["FR-004", "FR-005", "FR-008"],
        },
    ],
    "tables": [
        {
            "name": "CALC_HISTORY",
            "logical_name": "계산 이력",
            "description": "사용자가 실행한 계산 수식·결과",
            "columns": [
                {
                    "name": "HISTORY_ID",
                    "data_type": "INTEGER",
                    "length": "",
                    "nullable": False,
                    "is_pk": True,
                    "description": "이력 ID",
                },
                {
                    "name": "EXPRESSION",
                    "data_type": "VARCHAR",
                    "length": "200",
                    "nullable": False,
                    "description": "수식",
                },
                {
                    "name": "RESULT",
                    "data_type": "VARCHAR",
                    "length": "64",
                    "nullable": True,
                    "description": "결과(문자열, 21자리 유효 숫자)",
                },
                {
                    "name": "ERROR_CODE",
                    "data_type": "VARCHAR",
                    "length": "16",
                    "nullable": True,
                    "description": "오류 코드",
                },
                {
                    "name": "CREATED_AT",
                    "data_type": "TIMESTAMP",
                    "length": "",
                    "nullable": False,
                    "description": "계산 일시",
                },
            ],
            "indexes": ["IX_CALC_HISTORY_CREATED (CREATED_AT DESC)"],
            "relations": [],
            "retention_policy": "90일 보관 후 배치 삭제 (설정 가능)",
            "migration_note": "신규 테이블, 이관 없음",
            "db_engine": "SQLite (단일 서버) 또는 PostgreSQL",
            "requirement_ids": ["FR-005"],
        }
    ],
    "apis": [
        {
            "name": "계산 실행 API",
            "method": "POST",
            "path": "/api/calc",
            "description": "수식을 받아 고정밀 계산 결과를 돌려준다",
            "request_fields": ["expression:string(1~200)", "precision:int(기본 21)"],
            "response": "{result:string, error_code?:string}",
            "auth": "없음(공개) — 요청 한도 60회/분",
            "error_codes": [
                "E001: 문법 오류",
                "E002: 0 나누기",
                "E003: 범위 초과(10^25)",
                "E004: 타임아웃",
            ],
            "validation_rules": ["expression 길이 1~200", "허용 토큰만"],
            "idempotency": "동일 수식 재요청은 같은 결과 (부작용 없음)",
            "timeout_retry": "1초 타임아웃, 재시도 없음",
            "paging_limits": "",
            "logging_audit": "수식·결과·소요 시간 로그",
            "screen_refs": ["계산기 메인 화면"],
            "table_refs": ["CALC_HISTORY"],
            "module_path": "src/main/java/com/app/calc/CalcController.java",
            "requirement_ids": ["FR-002", "FR-006", "NFR-001", "NFR-002"],
        },
        {
            "name": "이력 조회 API",
            "method": "GET",
            "path": "/api/history",
            "description": "계산 이력을 최근 순으로 돌려준다",
            "request_fields": ["keyword:string(0~50)", "page:int", "size:int(≤20)"],
            "response": "{items:[{history_id, expression, result, created_at}], total:int}",
            "auth": "없음",
            "error_codes": ["E101: 잘못된 페이지"],
            "validation_rules": ["size ≤ 20"],
            "idempotency": "조회",
            "timeout_retry": "1초",
            "paging_limits": "20건/페이지",
            "logging_audit": "조회 로그",
            "screen_refs": ["계산 이력 화면", "계산기 메인 화면"],
            "table_refs": ["CALC_HISTORY"],
            "module_path": "src/main/java/com/app/history/HistoryController.java",
            "requirement_ids": ["FR-005"],
        },
        {
            "name": "이력 삭제 API",
            "method": "DELETE",
            "path": "/api/history/{id}",
            "description": "이력 1건 삭제",
            "request_fields": ["id:int"],
            "response": "{deleted:bool}",
            "auth": "없음",
            "error_codes": ["E102: 없는 이력"],
            "validation_rules": [],
            "idempotency": "두 번 호출해도 결과 동일",
            "timeout_retry": "1초",
            "paging_limits": "",
            "logging_audit": "삭제 로그",
            "screen_refs": ["계산 이력 화면"],
            "table_refs": ["CALC_HISTORY"],
            "module_path": "src/main/java/com/app/history/HistoryController.java",
            "requirement_ids": ["FR-005"],
        },
    ],
    "modules": [
        {
            "path": "src/main/java/com/app/calc/CalcController.java",
            "layer": "controller",
            "responsibility": "계산 API 엔드포인트·입력 검증",
            "depends_on": [
                "src/main/java/com/app/calc/CalcService.java",
                "src/main/java/com/app/history/HistoryRepository.java",
            ],
            "requirement_ids": ["FR-002", "FR-006"],
            "api_refs": ["계산 실행 API"],
            "screen_refs": ["계산기 메인 화면"],
            "table_refs": ["CALC_HISTORY"],
        },
        {
            "path": "src/main/java/com/app/history/HistoryController.java",
            "layer": "controller",
            "responsibility": "이력 조회·삭제 API",
            "depends_on": ["src/main/java/com/app/history/HistoryRepository.java"],
            "requirement_ids": ["FR-005"],
            "api_refs": ["이력 조회 API", "이력 삭제 API"],
            "screen_refs": ["계산 이력 화면"],
            "table_refs": ["CALC_HISTORY"],
        },
        {
            "path": "src/main/java/com/app/calc/CalcService.java",
            "layer": "service",
            "responsibility": "토큰화·후위 표기 평가·BigDecimal 고정밀 연산",
            "depends_on": [],
            "requirement_ids": ["FR-001", "FR-002", "NFR-001"],
            "api_refs": [],
            "screen_refs": [],
            "table_refs": [],
        },
        {
            "path": "src/main/java/com/app/history/HistoryRepository.java",
            "layer": "repository",
            "responsibility": "CALC_HISTORY 저장·조회·삭제",
            "depends_on": [],
            "requirement_ids": ["FR-005"],
            "api_refs": [],
            "screen_refs": [],
            "table_refs": ["CALC_HISTORY"],
        },
        {
            "path": "src/main/resources/static/index.html",
            "layer": "web",
            "responsibility": "메인 화면·수식 검증·API 호출",
            "depends_on": [],
            "requirement_ids": ["FR-001", "FR-003"],
            "api_refs": ["계산 실행 API"],
            "screen_refs": ["계산기 메인 화면"],
            "table_refs": [],
        },
        {
            "path": "src/test/java/com/app/calc/CalcServiceTest.java",
            "layer": "test",
            "responsibility": "계산 엔진 단위 테스트 (JUnit 5)",
            "depends_on": ["src/main/java/com/app/calc/CalcService.java"],
            "requirement_ids": ["FR-002", "NFR-001"],
            "api_refs": [],
            "screen_refs": [],
            "table_refs": [],
        },
    ],
    "business_rules": [
        {
            "rule_id": "BR-001",
            "description": "수식은 200자 이내, 허용 토큰만 포함, 괄호 짝이 맞아야 한다",
            "enforced_in": "src/main/java/com/app/calc/CalcService.java",
            "requirement_ids": ["FR-001"],
        },
        {
            "rule_id": "BR-002",
            "description": "결과는 유효 숫자 21자리, 10^25 초과는 E003 오류",
            "enforced_in": "src/main/java/com/app/calc/CalcService.java",
            "requirement_ids": ["FR-002", "NFR-001"],
        },
    ],
    "assumptions": ["이력 보관 90일은 가정(RFP 미기재)", "VARCHAR 길이는 가정"],
    "research_needed": [],
    "notes": "FR-004(모바일 안내) 는 메인 화면 상태 메시지로 처리 — 별도 화면 없음",
}


# --- 5-1. 회의록(샘플)과 구조화 대행 응답 (단계 5, 지시문 §10) ------------------------------------------
MEETING_NOTE: str = """제안 준비 회의록 (2026-10-16)
참석: 영업 PM, 기술 PL, 고객 담당자(정보화팀)
결정: 제안서 분량은 요약 모드로 하고 요구사항별 상세는 정의서에 둔다 (담당: 기술 PL)
요청: 고객이 계산 이력 보관 기간을 1년으로 늘려 달라고 요청함 (FR-004 관련)
미결: 모바일 지원 범위(PC 전용인지, 반응형까지인지) 확인 필요 — 담당: 영업 PM, 기한 2026-10-20
조치: 고정밀 연산 PoC 결과를 10/22 까지 공유 (담당: 기술 PL, 기한 2026-10-22)
의견: 내부적으로는 FastAPI 대신 Flask 도 검토해 볼 만하다는 의견
위험: 발주처 서버 사양이 미정이라 성능 목표(응답 1초) 보장이 어려울 수 있음
"""
MEETING_REPORT: dict[str, Any] = {
    "meeting_title": "제안 준비 회의",
    "held_on": "2026-10-16",
    "attendees": ["영업 PM", "기술 PL", "고객 담당자(정보화팀)"],
    "items": [
        {
            "kind": "official_decision",
            "title": "제안서 분량은 요약 모드, 상세는 정의서",
            "content": "제안서는 요약 모드로 작성하고 요구사항별 상세는 정의서에 둔다.",
            "owner": "기술 PL",
            "authority_hint": "",
            "evidence": "결정: 제안서 분량은 요약 모드로 하고 요구사항별 상세는 정의서에 둔다",
        },
        {
            "kind": "customer_request",
            "title": "계산 이력 보관 기간 1년으로 연장",
            "content": "고객이 계산 이력 보관 기간을 1년으로 늘려 달라고 요청.",
            "related_requirement_ids": ["FR-004"],
            "evidence": "요청: 고객이 계산 이력 보관 기간을 1년으로 늘려 달라고 요청함 (FR-004 관련)",
        },
        {
            "kind": "open_question",
            "title": "모바일 지원 범위 확인",
            "content": "PC 전용인지 반응형까지인지 확인 필요.",
            "owner": "영업 PM",
            "due_date": "2026-10-20",
            "evidence": "미결: 모바일 지원 범위(PC 전용인지, 반응형까지인지) 확인 필요",
        },
        {
            "kind": "action_item",
            "title": "고정밀 연산 PoC 결과 공유",
            "content": "PoC 결과를 10/22 까지 공유.",
            "owner": "기술 PL",
            "due_date": "2026-10-22",
            "evidence": "조치: 고정밀 연산 PoC 결과를 10/22 까지 공유",
        },
        {
            "kind": "internal_opinion",
            "title": "Flask 검토 의견",
            "content": "FastAPI 대신 Flask 도 검토해 볼 만하다는 내부 의견.",
            "evidence": "의견: 내부적으로는 FastAPI 대신 Flask 도 검토해 볼 만하다는 의견",
        },
        {
            "kind": "risk_issue",
            "title": "발주처 서버 사양 미정으로 성능 목표 보장 어려움",
            "content": "서버 사양이 미정이라 응답 1초 목표 보장이 어려울 수 있음.",
            "evidence": "위험: 발주처 서버 사양이 미정이라 성능 목표(응답 1초) 보장이 어려울 수 있음",
        },
    ],
    "unresolved": [],
}


# --- 2-5. 사업 참여 타당성 검토 (단계 2, 대행 응답) -------------------------------------------------
BID_REVIEW: dict[str, Any] = {
    "items": [
        {
            "key": "tech_capability",
            "rating": "good",
            "comment": "조사 주제가 모두 구현 가능 판정(사실). 범용 기술이라 확보 위험은 낮다(판단).",
        },
        {
            "key": "ambiguity",
            "rating": "caution",
            "comment": "지원 연산 목록이 기준 계산기 수준이라는 표현은 범위가 넓다(사실). 착수 시 연산 목록을 확정해야 한다(판단).",
        },
        {
            "key": "profitability",
            "rating": "unknown",
            "comment": "단가·예산이 없어 산정 불가(사실). 소규모 사업이라 마진보다 레퍼런스 가치로 판단할 여지(판단).",
        },
    ],
    "key_risks": ["지원 연산 범위 미확정", "정밀도 요구(21자리) 검증 비용"],
    "open_questions": ["역할별 단가와 예산은?", "모바일 미지원이 발주처와 합의됐는가?"],
    "overall_comment": "코드 권고에 동의한다. 연산 범위와 정밀도 검증 기준을 착수 전에 확정하는 조건이면 참여할 만하다. 먼저 단가·예산을 입력해 수익성을 산정해야 한다.",
}


# --- 2-3. 목차·전략 브리프 (Phase 18, 세션의 Claude가 수동 작성 — Gate P 대행 승인) -------------------
STRATEGY: dict[str, Any] = {
    "rfp_summary": "PC 웹 기반 공학용 계산기 개발. Windows 공학용 계산기 수준의 연산, 프론트 입력 검증·서버 계산, 소수점 21자리·10^25 범위, 계산 이력 표시가 핵심이며 모바일은 범위 밖이다. 평가 기준·페이지 제한은 RFP에 없다.",
    "requirement_directions": [
        {
            "requirement_id": "FR-001",
            "priority": "상",
            "direction": "서버 계산 엔진(Python decimal/mpmath)으로 수용",
        },
        {
            "requirement_id": "FR-003",
            "priority": "상",
            "direction": "React/TypeScript 단일 화면 UI로 수용",
        },
        {
            "requirement_id": "FR-005",
            "priority": "상",
            "direction": "프론트 검증 + FastAPI 계산 API 분리로 수용",
        },
        {
            "requirement_id": "NFR-001",
            "priority": "상",
            "direction": "decimal 정밀도 50자리·21자리 반올림, 경계값 시험으로 검증",
        },
        {
            "requirement_id": "NFR-002",
            "priority": "상",
            "direction": "10^25 범위 검사, 초과 시 오류 반환",
        },
        {
            "requirement_id": "CON-001",
            "priority": "중",
            "direction": "데스크톱 브라우저 전용 레이아웃(모바일 미지원 안내)",
        },
    ],
    "toc": [
        {
            "numeral": "Ⅰ",
            "title": "사업 이해",
            "sections": ["사업 배경·목적", "요구사항 이해", "추진 방향"],
            "rfp_mandatory": False,
            "note": "RFP에 지정 목차 없음 — 기본 순서",
        },
        {
            "numeral": "Ⅱ",
            "title": "사업 수행 방안",
            "sections": [
                "요구사항 대응 방안",
                "시스템 구성",
                "계산 엔진·정밀도",
                "화면·입력 검증",
                "계산 이력",
            ],
            "rfp_mandatory": False,
            "note": "",
        },
        {
            "numeral": "Ⅲ",
            "title": "사업 관리 방안",
            "sections": ["추진 일정", "투입 인력", "품질·시험", "위험 관리"],
            "rfp_mandatory": False,
            "note": "",
        },
        {
            "numeral": "Ⅳ",
            "title": "지원 방안",
            "sections": ["교육·인수인계", "유지관리"],
            "rfp_mandatory": False,
            "note": "",
        },
    ],
    "toc_change_requests": [],
    "strategies": [
        {
            "title": "서버 임의 정밀도 연산으로 21자리·10^25 요구를 충족한다",
            "description": "계산은 서버 decimal/mpmath로 수행하고 프론트는 유효성 검사만 맡겨 정밀도 손실을 없앤다.",
            "client_problem": "브라우저 부동소수점으로는 21자리 정밀도와 10^25 범위를 보장할 수 없다",
            "approach": "FastAPI 계산 API 뒤에 decimal 컨텍스트(50자리) 엔진을 두고 표시 시 21자리로 반올림",
            "technologies": ["Python decimal/mpmath", "FastAPI"],
            "expected_effects": ["경계값(21자리·10^25) 시험 케이스 통과 — RFP 요구 그대로"],
            "risks": ["삼각·로그 함수 정밀도는 mpmath 보강 필요(조사 미확인)"],
            "unverified_claims": [],
            "differentiator": "IEEE 754 배정밀도(15~17자리)로는 불가능한 요구를 설계 단계에서 해결",
            "related_requirement_ids": ["NFR-001", "NFR-002", "FR-005"],
            "evidence": ["조사 고정밀 십진 연산: feasible_with_risk", "RFP: 소수점 21자리·10^25"],
        },
        {
            "title": "입력 오류를 즉시 알리는 이중 검증으로 사용성을 높인다",
            "description": "프론트 토크나이저와 서버 파서가 같은 문법을 공유해 오류 메시지를 일관되게 낸다.",
            "differentiator": "오류 코드 체계를 설계 단계에서 확정해 메시지 누락 방지",
            "related_requirement_ids": ["FR-005", "FR-006"],
            "evidence": ["조사 웹 계산기 UI·입력 유효성 검사: feasible", "설계 제안"],
        },
        {
            "title": "계산 이력 재사용·내보내기로 반복 작업을 줄인다",
            "description": "이력 클릭 재적재와 CSV 내보내기를 부가 제안으로 구현한다.",
            "differentiator": "RFP 추가 제안 요구(SUB-001)에 대한 구체 대안",
            "related_requirement_ids": ["FR-004"],
            "evidence": ["설계 제안", "RFP: 추가 제안 및 구현"],
        },
    ],
    "key_technologies": [
        {
            "area": "framework",
            "choice": "Python/FastAPI 계산 API",
            "rationale": "decimal 모듈과 결합",
            "feasibility_basis": "조사 서버 계산 API: feasible",
        },
        {
            "area": "ui_ux",
            "choice": "React/TypeScript",
            "rationale": "PC 웹 단일 화면",
            "feasibility_basis": "조사 웹 계산기 UI: feasible",
        },
        {
            "area": "db",
            "choice": "SQLite(→PostgreSQL 전환 가능)",
            "rationale": "이력 저장 단순",
            "feasibility_basis": "조사 정적 서빙·저장소: feasible",
        },
    ],
    "risks": [
        {
            "risk": "삼각·로그 함수의 21자리 정밀도 보장 라이브러리 미확인",
            "mitigation": "mpmath 공식 문서 확인 후 확정, 미달 시 교체(2.2.1 공수 증가)",
            "related_requirement_ids": ["NFR-001"],
        },
        {
            "risk": "초대형 지수·팩토리얼 입력으로 서버 부하",
            "mitigation": "입력 상한·시간 제한 적용",
            "related_requirement_ids": ["NFR-002"],
        },
    ],
    "submission_vs_presentation": "제출용은 요구사항 대응표·계산 엔진 구조·API/오류 코드 설계·시험 계획을 상세히 싣고, 발표용은 정밀도 전략·이중 검증·이력 재사용 3개 전략을 흐름도로 압축한다.",
    "open_questions": [
        "Windows 공학용 계산기 기준 지원 연산 목록 확정",
        "mpmath 삼각함수 정밀도 공식 문서 미열람",
        "이력 보관 기간·개인 식별 여부",
    ],
}


def SRC(url: str, title: str, product: str, version: str, excerpt: str) -> dict[str, Any]:  # noqa: N802
    return {
        "url": url,
        "title": title,
        "product": product,
        "version": version,
        "trust": "official_doc",
        "excerpt": excerpt + " (세션에서 열람하지 않음 — 미확인)",
    }


RESEARCH: dict[str, Any] = {
    "items": [
        {
            "topic": "고정밀 십진 연산·큰 수(10^25) 처리",
            "related_requirement_ids": ["NFR-001", "NFR-002"],
            "summary": "소수점 21자리와 10^25 범위는 IEEE 754 배정밀도(유효 15~17자리)로 만족할 수 없어 서버에서 임의 정밀도 십진 연산이 필요하다.",
            "confirmed_facts": [],
            "applicability_conditions": [
                "서버 계산 엔진에서 decimal 컨텍스트 정밀도를 50자리 이상으로 설정",
                "삼각·로그 함수는 Decimal용 구현 또는 mpmath 검토",
            ],
            "unverified_items": [
                "Python decimal 모듈의 삼각함수 미지원 여부와 대안(mpmath) — 공식 문서 열람 필요",
                "math.js BigNumber의 함수 지원 범위",
            ],
            "impact_on_implementation": "계산 엔진을 서버(Python decimal/mpmath)로 두고 프론트는 유효성 검사만 수행",
            "impact_on_proposal": "정밀도·범위 요구 충족 방안을 제안서에 명시",
            "feasibility": "feasible_with_risk",
            "risks": ["초월함수(sin, log 등)의 21자리 정밀도 보장은 라이브러리 선택에 따라 다름"],
            "recommended_stack": ["Python decimal", "mpmath"],
            "sources": [
                SRC(
                    "https://docs.python.org/3/library/decimal.html",
                    "decimal — Decimal fixed point and floating point arithmetic",
                    "Python",
                    "3.12",
                    "decimal 모듈은 사용자 지정 정밀도의 십진 연산을 제공",
                ),
                SRC(
                    "https://mpmath.org/doc/current/",
                    "mpmath documentation",
                    "mpmath",
                    "",
                    "임의 정밀도 실수 연산과 초월함수 제공",
                ),
            ],
        },
        {
            "topic": "웹 계산기 UI·입력 유효성 검사",
            "related_requirement_ids": ["FR-003", "FR-005", "FR-006", "FR-007"],
            "summary": "SPA 프레임워크로 계산기 UI와 키보드·버튼 입력, 하단 메시지 박스를 구현하고 프론트에서 토큰 단위 유효성 검사를 수행한다.",
            "confirmed_facts": [],
            "applicability_conditions": ["PC 웹 전용이므로 반응형 모바일 레이아웃은 범위 밖"],
            "unverified_items": ["React 현재 안정 버전 — 공식 문서 열람 필요"],
            "impact_on_implementation": "수식 토크나이저를 프론트·서버가 공유(동일 문법)",
            "impact_on_proposal": "입력 오류 즉시 표시(UX) 강조",
            "feasibility": "feasible",
            "risks": [],
            "recommended_stack": ["React", "TypeScript"],
            "sources": [
                SRC("https://react.dev/", "React", "React", "", "컴포넌트 기반 UI 라이브러리")
            ],
        },
        {
            "topic": "서버 계산 API",
            "related_requirement_ids": ["FR-005", "FR-006"],
            "summary": "계산 요청을 받아 수식을 파싱·평가하고 결과 또는 구조화된 오류(위치·원인)를 반환하는 REST API.",
            "confirmed_facts": [],
            "applicability_conditions": ["요청 크기·수식 길이 제한으로 서비스 거부 방지"],
            "unverified_items": ["FastAPI 현재 버전 — 공식 문서 열람 필요"],
            "impact_on_implementation": "수식 파서(shunting-yard 또는 재귀 하강)와 평가기를 서버에 구현",
            "impact_on_proposal": "오류 메시지 체계(허용되지 않는 입력·원인)를 API 응답에 포함",
            "feasibility": "feasible",
            "risks": ["악의적 입력(초대형 지수·팩토리얼)으로 인한 서버 부하 — 상한 필요"],
            "recommended_stack": ["Python", "FastAPI"],
            "sources": [
                SRC(
                    "https://fastapi.tiangolo.com/",
                    "FastAPI",
                    "FastAPI",
                    "",
                    "Python 웹 API 프레임워크",
                )
            ],
        },
        {
            "topic": "정적 서빙·리버스 프록시와 계산 이력 저장소",
            "related_requirement_ids": ["FR-004", "CON-001"],
            "summary": "프론트 정적 파일은 Nginx로 서빙·프록시하고, 계산 이력은 단일 서버면 SQLite, 다중 서버면 PostgreSQL로 저장한다.",
            "confirmed_facts": [],
            "applicability_conditions": ["이력 보존 기간·개수가 확정되면 저장소 선택 재검토"],
            "unverified_items": ["Nginx·SQLite·PostgreSQL 현재 안정 버전 — 공식 문서 열람 필요"],
            "impact_on_implementation": "배포 단위 1대 기준",
            "impact_on_proposal": "소규모 구성으로 비용 최소화",
            "feasibility": "feasible",
            "risks": [],
            "recommended_stack": ["Nginx", "SQLite", "PostgreSQL"],
            "sources": [
                SRC(
                    "https://nginx.org/en/docs/",
                    "nginx documentation",
                    "Nginx",
                    "",
                    "정적 파일 서빙·리버스 프록시",
                ),
                SRC(
                    "https://www.sqlite.org/docs.html",
                    "SQLite Documentation",
                    "SQLite",
                    "",
                    "서버리스 임베디드 DB",
                ),
                SRC(
                    "https://www.postgresql.org/docs/",
                    "PostgreSQL Documentation",
                    "PostgreSQL",
                    "",
                    "관계형 DBMS",
                ),
            ],
        },
    ],
    "comparisons": [
        {
            "area": "framework",
            "rfp_specified": None,
            "alternatives": [
                {
                    "name": "Python/FastAPI + decimal/mpmath",
                    "scores": {
                        "rfp_fit": "상 — 고정밀 연산 라이브러리",
                        "security": "중",
                        "ops": "상",
                    },
                    "license_and_cost": "MIT/BSD, 무료",
                    "notes": "정밀도 요구에 유리",
                },
                {
                    "name": "Node.js/Express + math.js BigNumber",
                    "scores": {
                        "rfp_fit": "중 — 초월함수 정밀도 확인 필요",
                        "security": "중",
                        "ops": "상",
                    },
                    "license_and_cost": "MIT, 무료",
                    "notes": "프론트와 언어 통일",
                },
            ],
            "recommendation": "Python/FastAPI + decimal/mpmath",
            "rationale": "21자리·10^25 요구를 임의 정밀도 라이브러리로 충족하기 쉬움",
            "unverified_items": ["각 라이브러리의 초월함수 정밀도 — 실측 필요"],
        },
        {
            "area": "ui_ux",
            "rfp_specified": None,
            "alternatives": [
                {
                    "name": "React/TypeScript",
                    "scores": {"rfp_fit": "상", "security": "중"},
                    "license_and_cost": "MIT",
                    "notes": "",
                },
                {
                    "name": "Vue",
                    "scores": {"rfp_fit": "상", "security": "중"},
                    "license_and_cost": "MIT",
                    "notes": "",
                },
            ],
            "recommendation": "React/TypeScript",
            "rationale": "키보드·버튼 입력 처리와 상태 관리에 충분, 인력 수급 용이",
            "unverified_items": [],
        },
    ],
    "notes": NOTE + ". 출처 URL은 세션에서 열람하지 않았으며 코드가 '미확인'으로 분류한다.",
}

ARCHITECTURE: dict[str, Any] = {
    "components": [
        {
            "code": "CLI01",
            "layer": "client",
            "name": "계산기 웹 UI (브라우저)",
            "technology": "React/TypeScript",
            "description": "계산기 버튼·키보드 입력, 수식 표시, 결과·이력 표시, 하단 메시지 박스, 입력 유효성 검사",
            "related_requirement_ids": [
                "FR-003",
                "FR-004",
                "FR-005",
                "FR-006",
                "FR-007",
                "CON-001",
            ],
            "diagram_kinds": ["system", "sw", "service"],
        },
        {
            "code": "WEB01",
            "layer": "web",
            "name": "정적 서빙·리버스 프록시",
            "technology": "Nginx",
            "description": "프론트 정적 파일 서빙, /api 프록시, 요청 크기 제한",
            "related_requirement_ids": [],
            "diagram_kinds": ["system", "service"],
        },
        {
            "code": "APP01",
            "layer": "app",
            "name": "계산 API 서버",
            "technology": "Python/FastAPI",
            "description": "수식 파싱·평가 요청 처리, 구조화된 오류 응답",
            "related_requirement_ids": ["FR-005", "FR-006"],
            "diagram_kinds": ["system", "sw", "service"],
        },
        {
            "code": "APP02",
            "layer": "app",
            "name": "수식 파서·고정밀 평가 엔진",
            "technology": "Python decimal/mpmath",
            "description": "토크나이저·파서·평가기, 소수점 21자리 반올림, 10^25 범위 검사, 공학 함수",
            "related_requirement_ids": ["FR-002", "NFR-001", "NFR-002"],
            "diagram_kinds": ["sw"],
        },
        {
            "code": "DB01",
            "layer": "data",
            "name": "계산 이력 저장소",
            "technology": "SQLite(단일 서버) 또는 PostgreSQL",
            "description": "세션별 계산 이력 저장·조회",
            "related_requirement_ids": ["FR-004"],
            "diagram_kinds": ["system", "sw"],
        },
        {
            "code": "SEC01",
            "layer": "security",
            "name": "입력 제한·보호",
            "technology": "FastAPI 미들웨어",
            "description": "수식 길이·지수 크기 상한, 요청 속도 제한",
            "related_requirement_ids": ["FR-006"],
            "diagram_kinds": ["system"],
        },
    ],
    "connections": [
        {"from_code": "CLI01", "to_code": "WEB01", "protocol": "HTTPS"},
        {"from_code": "WEB01", "to_code": "APP01", "protocol": "HTTP(proxy)"},
        {"from_code": "APP01", "to_code": "APP02", "protocol": "in-process"},
        {"from_code": "APP01", "to_code": "DB01", "protocol": "SQL"},
        {"from_code": "APP01", "to_code": "SEC01", "protocol": "middleware"},
    ],
    "diagram_notes": "PC 웹 전용. 계산은 서버 엔진에서만 수행.",
    "assumptions": [
        "단일 서버 배포, 동시 사용자 소규모",
        "이력은 브라우저 세션 단위로 서버에 저장",
    ],
    "open_questions": [
        "이력 보존 기간·개수",
        "지원 브라우저 목록",
        "공학 연산 목록(각도 모드·진법 포함 여부)",
    ],
}

WBS: dict[str, Any] = {
    "items": [
        {
            "code": "1",
            "level": "phase",
            "name": "분석·설계",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "1.1",
            "parent_code": "1",
            "level": "activity",
            "name": "요구사항 분석·연산 목록 확정",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "1.1.1",
            "parent_code": "1.1",
            "level": "task",
            "name": "요구사항 분석 및 공학 연산 목록 합의",
            "effort_md_estimate": 5,
            "estimate_basis": "요구사항 13건 검토 + Windows 공학용 계산기 연산 목록 정리·합의 회의 2회",
            "roles": [{"role": "PL", "ratio": "1"}],
            "related_requirement_ids": ["FR-001", "FR-002", "SUB-001"],
            "deliverables": ["요구사항 정의서", "연산 목록"],
        },
        {
            "code": "1.2",
            "parent_code": "1",
            "level": "activity",
            "name": "UI·API 설계",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "1.2.1",
            "parent_code": "1.2",
            "level": "task",
            "name": "화면 설계(계산기 UI·이력·메시지 박스)",
            "effort_md_estimate": 4,
            "estimate_basis": "화면 2종(계산기, 이력) + 메시지 박스·키보드 매핑 설계",
            "roles": [{"role": "프런트엔드", "ratio": "1"}],
            "related_requirement_ids": ["FR-003", "FR-004", "FR-006", "FR-007"],
        },
        {
            "code": "1.2.2",
            "parent_code": "1.2",
            "level": "task",
            "name": "수식 문법·API·오류 코드 설계",
            "effort_md_estimate": 4,
            "estimate_basis": "수식 문법(토큰·우선순위) 정의, 계산 API 1종, 오류 코드 체계",
            "roles": [{"role": "백엔드", "ratio": "1"}],
            "related_requirement_ids": ["FR-005", "FR-006", "NFR-001", "NFR-002"],
        },
        {"code": "2", "level": "phase", "name": "구현", "estimate_basis": "하위 합계", "roles": []},
        {
            "code": "2.1",
            "parent_code": "2",
            "level": "activity",
            "name": "프론트엔드 개발",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "2.1.1",
            "parent_code": "2.1",
            "level": "task",
            "name": "계산기 UI·키보드/버튼 입력",
            "effort_md_estimate": 8,
            "estimate_basis": "버튼 약 40개 레이아웃, 키보드 매핑, 수식 표시 컴포넌트",
            "roles": [{"role": "프런트엔드", "ratio": "1"}],
            "related_requirement_ids": ["FR-003", "FR-007", "CON-001"],
        },
        {
            "code": "2.1.2",
            "parent_code": "2.1",
            "level": "task",
            "name": "입력 유효성 검사·오류 메시지 박스",
            "effort_md_estimate": 5,
            "estimate_basis": "토큰 검증 규칙 약 15종, 메시지 박스 컴포넌트",
            "roles": [{"role": "프런트엔드", "ratio": "1"}],
            "related_requirement_ids": ["FR-005", "FR-006"],
        },
        {
            "code": "2.1.3",
            "parent_code": "2.1",
            "level": "task",
            "name": "계산 이력 표시(+재사용·내보내기 부가 제안)",
            "effort_md_estimate": 4,
            "estimate_basis": "이력 목록 컴포넌트 2 M/D + 부가 제안(클릭 재입력·CSV) 2 M/D",
            "roles": [{"role": "프런트엔드", "ratio": "1"}],
            "related_requirement_ids": ["FR-004", "FR-008", "FR-009"],
        },
        {
            "code": "2.2",
            "parent_code": "2",
            "level": "activity",
            "name": "백엔드 개발",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "2.2.1",
            "parent_code": "2.2",
            "level": "task",
            "name": "수식 파서·고정밀 평가 엔진",
            "effort_md_estimate": 10,
            "estimate_basis": "토크나이저·파서 4 M/D, 공학 함수 약 25종 평가기 6 M/D (decimal/mpmath)",
            "roles": [{"role": "백엔드", "ratio": "1"}],
            "related_requirement_ids": ["FR-002", "NFR-001", "NFR-002"],
        },
        {
            "code": "2.2.2",
            "parent_code": "2.2",
            "level": "task",
            "name": "계산 API·오류 응답·이력 저장",
            "effort_md_estimate": 5,
            "estimate_basis": "API 2종(계산, 이력), 오류 코드 매핑, 이력 테이블",
            "roles": [{"role": "백엔드", "ratio": "1"}],
            "related_requirement_ids": ["FR-005", "FR-006", "FR-004"],
        },
        {
            "code": "2.2.3",
            "parent_code": "2.2",
            "level": "task",
            "name": "정밀도·범위 처리(21자리 반올림, 10^25 상한)",
            "effort_md_estimate": 3,
            "estimate_basis": "반올림 규칙·범위 검사·경계값 테스트 케이스",
            "roles": [{"role": "백엔드", "ratio": "1"}],
            "related_requirement_ids": ["NFR-001", "NFR-002"],
        },
        {
            "code": "3",
            "level": "phase",
            "name": "시험·이행",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "3.1",
            "parent_code": "3",
            "level": "activity",
            "name": "시험",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "3.1.1",
            "parent_code": "3.1",
            "level": "task",
            "name": "단위·통합 시험(연산별 Windows 계산기 대조)",
            "effort_md_estimate": 8,
            "estimate_basis": "연산 25종 × 케이스 5 + 오류 입력 케이스 30 + 경계값",
            "roles": [{"role": "QA", "ratio": "1"}],
            "related_requirement_ids": ["FR-002", "FR-006", "NFR-001", "NFR-002"],
        },
        {
            "code": "3.2",
            "parent_code": "3",
            "level": "activity",
            "name": "이행",
            "estimate_basis": "하위 합계",
            "roles": [],
        },
        {
            "code": "3.2.1",
            "parent_code": "3.2",
            "level": "task",
            "name": "배포·인수 시연",
            "effort_md_estimate": 3,
            "estimate_basis": "서버 1대 배포 스크립트, 인수 시연 1회",
            "roles": [{"role": "백엔드", "ratio": "0.5"}, {"role": "PL", "ratio": "0.5"}],
            "related_requirement_ids": ["CON-001"],
        },
    ],
    "dependencies": [
        {"predecessor_code": "1.1.1", "successor_code": "1.2.1"},
        {"predecessor_code": "1.1.1", "successor_code": "1.2.2"},
        {"predecessor_code": "1.2.1", "successor_code": "2.1.1"},
        {"predecessor_code": "2.1.1", "successor_code": "2.1.2"},
        {"predecessor_code": "2.1.2", "successor_code": "2.1.3"},
        {"predecessor_code": "1.2.2", "successor_code": "2.2.1"},
        {"predecessor_code": "2.2.1", "successor_code": "2.2.2"},
        {"predecessor_code": "2.2.2", "successor_code": "2.2.3"},
        {"predecessor_code": "2.1.3", "successor_code": "3.1.1"},
        {"predecessor_code": "2.2.3", "successor_code": "3.1.1"},
        {"predecessor_code": "3.1.1", "successor_code": "3.2.1"},
    ],
    "team": [
        {
            "organization": "수행사",
            "role": "PL",
            "grade": "특급",
            "headcount": 1,
            "duties": "분석·설계 리드, 연산 목록 합의",
        },
        {
            "organization": "수행사",
            "role": "프런트엔드",
            "grade": "고급",
            "headcount": 1,
            "skills": ["React", "TypeScript"],
            "duties": "계산기 UI·이력 화면",
        },
        {
            "organization": "수행사",
            "role": "백엔드",
            "grade": "고급",
            "headcount": 1,
            "skills": ["Python", "FastAPI"],
            "duties": "수식 파서·계산 API",
        },
        {
            "organization": "수행사",
            "role": "QA",
            "grade": "중급",
            "headcount": 1,
            "duties": "경계값·통합 시험",
        },
    ],
    "milestones": [
        {"name": "착수", "timing": "start"},
        {"name": "착수보고", "timing": "+1w"},
        {"name": "중간보고", "timing": "after:1.2.2"},
        {"name": "완료보고", "timing": "-1w"},
        {"name": "종료", "timing": "end"},
    ],
    "assumptions": ["1 M/D = 1인 1영업일", "프런트·백엔드 병행 개발", "연산 목록은 1.1.1에서 확정"],
    "risks": [
        "초월함수 정밀도 미달 시 라이브러리 교체로 2.2.1 공수 증가",
        "연산 목록 확정 지연 시 전체 일정 지연",
    ],
}

PROPOSAL: dict[str, Any] = {
    "profile": "submission",
    "sections": [
        {
            "slide_group": "understanding",
            "title": "사업 이해",
            "picture": "photo__사업 수행 환경 사진(자리표시).png",
            "bullets": [
                "Windows 공학용 계산기 수준의 연산을 PC 웹에서 제공",
                "프론트 유효성 검사 + 서버 고정밀 계산의 역할 분담",
                "소수점 21자리·10^25 범위의 정밀 계산 요구 충족",
            ],
            "data_refs": ["FR-001", "FR-005", "NFR-001", "NFR-002"],
        },
        {
            "slide_group": "requirements",
            "title": "요구사항 대응",
            "bullets": [
                "필수 요구사항 11건 전부 수용, 부가 제안 2건(이력 재사용·내보내기, 정밀도·범위 사전 경고)",
                "허용되지 않는 입력은 하단 메시지 박스에 원인과 함께 표시",
                "키보드·버튼 입력 모두 지원, PC 웹 전용",
            ],
            "data_refs": ["FR-006", "FR-007", "FR-008", "FR-009"],
        },
        {
            "slide_group": "architecture",
            "title": "시스템 구성",
            "key_message": "정밀 계산은 서버 엔진이, 입력 검사는 브라우저가 맡아 오류를 즉시 알린다",
            "purpose": "목표 시스템 구조와 기술 선택 근거(상용/공개/자체 비교)를 설명",
            "audience": "technical",
            "layout_type": "tech_detail",
            "bullets": [
                "React/TypeScript 계산기 UI — Nginx — FastAPI 계산 API — decimal/mpmath 평가 엔진 — 이력 저장소",
                "계산은 서버에서만 수행, 프론트는 유효성 검사·표시",
                "입력 길이·지수 상한으로 서버 보호",
            ],
            "evidence": [
                {"kind": "requirement", "ref": "NFR-001", "text": "소수점 21자리 정밀도 요구"},
                {
                    "kind": "research",
                    "ref": "고정밀 계산 라이브러리",
                    "text": "decimal·mpmath 임의 정밀도 지원",
                },
            ],
            "links_prev": ["요구사항 대응"],
            "links_next": ["추진 일정"],
            "terms": ["API", "UI"],
            "tech_detail": {
                "components": [
                    "React/TypeScript 계산기 UI",
                    "Nginx 정적 서빙·역프록시",
                    "FastAPI 계산 API",
                    "decimal/mpmath 평가 엔진",
                ],
                "interfaces": ["브라우저 ↔ 계산 API: HTTPS JSON 호출"],
                "data": ["계산 이력(식·결과·시각) 저장소"],
                "operations": ["무상태 API로 재기동 단순", "입력 길이·지수 상한으로 과부하 방지"],
                "security": ["HTTPS 전송 암호화", "입력 검증으로 식 주입 차단"],
                "alternatives": [
                    {
                        "name": "상용 수식 엔진",
                        "kind": "commercial",
                        "pros": ["벤더 지원"],
                        "cons": ["라이선스 비용", "웹 연동 추가 개발"],
                        "cost_note": "라이선스",
                        "basis": "고정밀 계산 라이브러리",
                    },
                    {
                        "name": "decimal/mpmath (공개)",
                        "kind": "open_source",
                        "pros": ["임의 정밀도", "비용 없음"],
                        "cons": ["초월함수 21자리 실측 필요"],
                        "selected": True,
                        "basis": "고정밀 계산 라이브러리",
                    },
                    {
                        "name": "자체 평가기 개발",
                        "kind": "in_house",
                        "pros": ["요구에 맞춘 제어"],
                        "cons": ["검증 부담·일정 위험"],
                        "basis": "조사 필요",
                    },
                ],
                "selection_reason": "조사된 공개 라이브러리가 정밀도 요구를 만족하고 비용이 없어 선정",
            },
            "visual": {
                "kind": "layers",
                "items": [
                    {"title": "브라우저 계산기 UI", "group": "사용자", "text": "입력 검사·표시"},
                    {"title": "Nginx", "group": "웹"},
                    {"title": "FastAPI 계산 API", "group": "응용", "text": "decimal/mpmath 엔진"},
                    {"title": "이력 저장소", "group": "데이터"},
                ],
            },
            "data_refs": ["CLI01", "APP01", "APP02"],
        },
        {
            "slide_group": "schedule",
            "title": "추진 일정",
            "bullets": [
                "분석·설계 → 프런트·백엔드 병행 구현 → 연산별 대조 시험 → 배포·인수 시연",
                "총 공수는 WBS 산정 합계 기준(코드 계산)",
            ],
            "data_refs": ["WBS"],
        },
        {
            "slide_group": "staffing",
            "title": "인력 투입",
            "bullets": [
                "PL·프런트엔드·백엔드·QA 역할 투입, 월별 M/M은 WBS 공수에서 코드가 계산",
                "단가는 입력 시 비용 자동 계산",
            ],
            "data_refs": ["인력투입계획"],
        },
        {
            "slide_group": "quality",
            "title": "품질 보증",
            "bullets": [
                "연산 25종 × 케이스 5의 Windows 계산기 대조 시험",
                "경계값(21자리, 10^25) 자동 테스트",
                "오류 입력 30케이스 메시지 검증",
            ],
            "data_refs": ["3.1.1"],
        },
        {
            "slide_group": "risk",
            "title": "위험과 대응",
            "bullets": [
                "초월함수 21자리 정밀도: mpmath 실측 후 확정",
                "연산 목록 미확정: 착수 시 합의 회의로 확정",
            ],
            "data_refs": ["NFR-001"],
        },
    ],
    "key_messages": [
        "정밀 계산은 서버 고정밀 엔진으로, 사용성은 즉시 오류 표시로",
        "Windows 공학용 계산기와 결과 대조 시험으로 검증",
    ],
    "unverified_claims": [
        "mpmath/decimal의 초월함수 21자리 정밀도 — 실측 전",
        "기술 조사 출처 URL은 세션에서 열람하지 않음",
    ],
    "glossary": [
        {
            "term": "API",
            "full_form": "Application Programming Interface",
            "meaning": "프로그램끼리 기능을 주고받는 약속된 호출 방식",
            "first_section": "시스템 구성",
        },
        {
            "term": "UI",
            "full_form": "User Interface",
            "meaning": "사용자가 보고 조작하는 화면",
            "first_section": "시스템 구성",
        },
        {
            "term": "QA",
            "full_form": "Quality Assurance",
            "meaning": "품질을 확인하고 보증하는 활동",
            "first_section": "인력 투입",
        },
        {
            "term": "HTTPS",
            "full_form": "HyperText Transfer Protocol Secure",
            "meaning": "브라우저와 서버 사이를 암호화해 주고받는 웹 통신 방식",
            "first_section": "시스템 구성",
        },
        {
            "term": "JSON",
            "full_form": "JavaScript Object Notation",
            "meaning": "프로그램끼리 자료를 주고받을 때 쓰는 글자 형식",
            "first_section": "시스템 구성",
        },
    ],
}


FIXTURE_NAMES = (
    "RFP_ANALYSIS",
    "REQUIREMENTS",
    "APPROACHES",
    "DESIGNS",
    "DETAIL_DESIGNS",
    "BID_REVIEW",
    "MEETING_NOTE",
    "MEETING_REPORT",
    "STRATEGY",
    "RESEARCH",
    "ARCHITECTURE",
    "WBS",
    "PROPOSAL",
    "UNRESOLVED",
    "VERIFIER_FINDING",
    "VERIFIER_COMMENTS",
    "PROJECT",
    "ID_ALIASES",
)
ID_ALIASES: dict[
    str, str
] = {}  # "@별칭" → 요구사항 이름에 포함되는 문자열 (fixture 가 실제 ID 를 모를 때)


def load_fixture(path: Path) -> list[str]:
    """다른 RFP용 대행 응답 파이썬 파일(저장소 밖)을 읽어 같은 이름의 전역을 바꾼다. 고객 자료는 저장소에 두지 않는다."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("manual_fixture", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"fixture 를 읽을 수 없습니다: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    loaded = []
    for name in FIXTURE_NAMES:
        if hasattr(mod, name):
            globals()[name] = getattr(mod, name)
            loaded.append(name)
    return loaded


def resolve_fixture_aliases(s: Services, project) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """fixture 의 '@별칭' 을 추출된 실제 요구사항 ID 로 바꾼다 (딕셔너리를 제자리에서 수정)."""
    if not ID_ALIASES:
        return {}
    reqs = s.requirements.list_requirements(project)
    mapping: dict[str, str] = {}
    for alias, needle in ID_ALIASES.items():
        hit = next((r for r in reqs if needle in r.name), None)
        if hit is not None:
            mapping[alias] = hit.id
    pattern = re.compile("|".join(re.escape(a) for a in sorted(mapping, key=len, reverse=True)))

    def walk(obj: Any) -> Any:
        if isinstance(obj, str):
            return pattern.sub(lambda m: mapping[m.group(0)], obj) if mapping else obj
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = walk(v)
            return obj
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                obj[k] = walk(v)
            return obj
        if isinstance(obj, tuple):
            return tuple(walk(list(obj)))
        return obj

    for name in (
        "STRATEGY",
        "RESEARCH",
        "ARCHITECTURE",
        "WBS",
        "PROPOSAL",
        "RFP_ANALYSIS",
        "DESIGNS",
        "DETAIL_DESIGNS",
    ):
        walk(globals()[name])
    for _keys, spec in APPROACHES:
        walk(spec)
    missing = [a for a in ID_ALIASES if a not in mapping]
    if missing:
        print("별칭 미해결:", ", ".join(missing))
    return mapping


def purge_previous(ctx: AppContext, name: str) -> None:
    """이 스크립트가 이전에 만든(created_by=ACTOR) 같은 이름의 프로젝트를 DB·폴더에서 제거한다. 사용자 프로젝트는 건드리지 않는다."""
    import shutil

    conn = ctx.db.conn
    rows = conn.execute("SELECT id, data FROM projects").fetchall()
    for row in rows:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else {}
        if data.get("name") != name or data.get("created_by") != ACTOR:
            continue
        pid = row["id"]
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        with ctx.db.transaction() as c:
            for t in tables:
                cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})").fetchall()]
                if "project_id" in cols:
                    c.execute(f"DELETE FROM {t} WHERE project_id = ?", (pid,))
            c.execute("DELETE FROM projects WHERE id = ?", (pid,))
        for folder in (
            ctx.paths.output_root / data.get("output_dir", "__none__"),
            ctx.paths.workspace_root / data.get("workspace_dir", pid),
        ):
            if folder.exists():
                shutil.rmtree(folder)
        print(f"이전 대행 실행 정리: {pid} ({data.get('output_dir')})")


def approve_if_needed(s: Services, project, gate: str) -> str:  # type: ignore[no-untyped-def]
    st = s.gates.state(project, gate)
    if (
        st.status == GateStatus.NEEDS_HUMAN_REVIEW
        and st.evaluation
        and not st.evaluation.approval_id
    ):
        s.gates.approve_human_review(
            project,
            gate,
            approver=ACTOR,
            comments=f"대행 승인: {NOTE}. 사유: {'; '.join(st.evaluation.reasons)[:200]}",
        )
        return f"{gate} 대행 승인"
    return f"{gate} {st.status.value}"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows 콘솔(cp949)에서 '—' 등 출력 오류 방지
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(
            "사용: run_manual_agents.py <RFP 경로> [--template <제안서 템플릿 .pptx>]... [--name <프로젝트명>] [--fixture <대행 응답 .py>] [--rate 역할=원/MM]... [--budget 원] [--detail detailed|summary] [--group-cap N]"
        )
        return 2
    rfp = Path(sys.argv[1])
    templates: list[Path] = []
    name: str | None = None
    cost_rates: dict[str, Decimal] = {}
    budget_amount: Decimal | None = None
    detail_level = "detailed"
    group_cap: int | None = None
    args = sys.argv[2:]
    while args:
        if args[0] == "--template" and len(args) >= 2:
            templates.append(Path(args[1]))
            args = args[2:]
        elif args[0] == "--name" and len(args) >= 2:
            name = args[1]  # 다른 이름이면 기존 프로젝트(승인·최종본)를 지우지 않는다
            args = args[2:]
        elif args[0] == "--fixture" and len(args) >= 2:
            loaded = load_fixture(Path(args[1]))
            print(f"fixture 적용: {args[1]} ({', '.join(loaded)})")
            args = args[2:]
        elif (
            args[0] == "--rate" and len(args) >= 2
        ):  # 단계 4: 역할별 단가(원/MM) "역할=금액" (A-3: 사용자 입력)
            role, _, amount = args[1].partition("=")
            cost_rates[role.strip()] = Decimal(amount.replace(",", ""))
            args = args[2:]
        elif (
            args[0] == "--budget" and len(args) >= 2
        ):  # 단계 4: 예산(원) — 없으면 RFP 예산 문구를 쓴다
            budget_amount = Decimal(args[1].replace(",", ""))
            args = args[2:]
        elif args[0] == "--detail" and len(args) >= 2:  # 단계 4: 분량 모드 detailed|summary
            detail_level = args[1]
            args = args[2:]
        elif args[0] == "--group-cap" and len(args) >= 2:  # 단계 4: 묶음 소절당 장 수 상한
            group_cap = int(args[1])
            args = args[2:]
        else:
            print(f"알 수 없는 인자: {args[0]}")
            return 2
    name = name or str(PROJECT.get("name") or "공학용 계산기 웹 개발")
    ctx = AppContext.create(
        Settings(
            qa_render_check=True
        ),  # 이 PC에 PowerPoint가 있으면 실제 렌더링·재열기(QA-FILE-14)까지 수행
        paths=ProjectPaths(),
        configure_logging=True,
    )
    runner = FakeAgentRunner(
        {
            "rfp_analyst": RFP_ANALYSIS,
            "requirement_extractor": extractor,
            "requirement_verifier": verifier,
            "tech_researcher": RESEARCH,
            "architect": ARCHITECTURE,
            "planner": WBS,
            "proposal_writer": PROPOSAL,
            "approach_writer": approach_writer,
            "strategy_planner": STRATEGY,
            "design_writer": DESIGNS,
            "detail_designer": DETAIL_DESIGNS,
            "developer": developer_responder,
            "bid_reviewer": BID_REVIEW,
            "meeting_analyzer": MEETING_REPORT,
        },
        cost_per_call=0.0,
    )
    s = Services.from_context(ctx, runner=runner)
    purge_previous(ctx, name)
    p = s.projects.create(
        name=name,
        mode=ProjectMode.PROPOSAL,
        start_date=PROJECT.get("start_date") or date(2026, 11, 2),
        end_date=PROJECT.get("end_date") or date(2027, 1, 29),
        client_name=str(PROJECT.get("client_name") or "(RFP 미기재)"),
        created_by=ACTOR,
    )
    log: list[str] = []
    if cost_rates or budget_amount is not None or detail_level != "detailed" or group_cap:
        ps = s.projects.settings_of(p).model_copy(
            update={
                "cost_rates": cost_rates,
                "budget_amount": budget_amount,
                "proposal_detail_level": detail_level,
                "max_slides_per_group": group_cap,
            }
        )
        s.projects.update_settings(p, ps, actor=ACTOR)
        log.append(
            f"프로젝트 설정: 단가 {len(cost_rates)}개 역할, 예산 {budget_amount or '(RFP 문구)'}, 분량 {detail_level}, 장 수 상한 {group_cap or '없음'}"
        )
    s.documents.register_upload(
        p, kind=DocumentKind.RFP, file_name=rfp.name, data=rfp.read_bytes(), actor=ACTOR
    )
    for tpl in templates:  # 제안서 템플릿(고객 양식): 추출 대상이 아니라 서식 입력
        doc = s.documents.register_upload(
            p,
            kind=DocumentKind.PROPOSAL_TEMPLATE,
            file_name=tpl.name,
            data=tpl.read_bytes(),
            actor=ACTOR,
        )
        log.append(f"템플릿 등록: {doc.file_name} → {doc.stored_path}")
    # 참고 그림(사진 태그, Phase 20): 실제 사진 대신 Pillow로 만든 자리표시 이미지 — 덱에 태그 달린 그림으로 들어간다
    import io

    from PIL import Image

    if PROJECT.get("placeholder_picture", True):
        buf = io.BytesIO()
        Image.new("RGB", (640, 360), (120, 140, 160)).save(buf, format="PNG")
        pic = s.documents.register_upload(
            p,
            kind=DocumentKind.PICTURE,
            file_name="photo__사업 수행 환경 사진(자리표시).png",
            data=buf.getvalue(),
            actor=ACTOR,
        )
        log.append(f"참고 그림 등록: {pic.file_name} → {pic.stored_path}")
    r = StepRunner(s)
    r.run_extraction(p, actor=ACTOR)
    log.append(approve_if_needed(s, p, "gate0"))
    out, res = r.run_requirement_extraction(p, actor=ACTOR)
    log.append(out.summary)
    out, vres = r.run_verification(p, actor=ACTOR)
    log.append(out.summary)
    log.append(approve_if_needed(s, p, "gate1"))
    # 수용 여부: 필수 → 수용, 부가 제안 → 조건부 수용 (대행 결정, 사용자 확인 필요)
    from proposal_agent.models import AcceptanceStatus

    for req in s.requirements.list_requirements(p):
        req.acceptance_status = (
            AcceptanceStatus.ACCEPTED if req.is_mandatory else AcceptanceStatus.PARTIALLY_ACCEPTED
        )
        if not req.is_mandatory:
            req.notes = "부가 제안 — 발주처 합의 시 구현 (대행 결정, 사용자 확인 필요)"
        ctx.repos.requirements.update(req)
    aliases = resolve_fixture_aliases(s, p)
    if aliases:
        log.append(f"fixture 별칭 → ID {len(aliases)}건 해결")
    log.append(r.run_rfp_analysis(p, actor=ACTOR).summary)
    log.append(r.run_bid_assessment(p, actor=ACTOR).summary)
    _bid = s.feasibility.latest(p)
    if _bid is not None:
        s.feasibility.review_with_agent(p, _bid, actor=ACTOR)
        _dec = s.feasibility.record_decision(
            p,
            _bid,
            choice=_bid.recommendation,
            rationale=f"대행 결정: 코드 권고를 그대로 채택 ({NOTE}). 사용자 확인 필요",
            decider=ACTOR,
            authority_confirmed=False,
        )
        log.append(
            f"참여 결정 {_dec.code} 기록(제안 상태, 권한 미확인) — 권고 {_bid.recommendation.label}"
        )
    # 단계 5: 회의록 등록 → 구조화(규칙 + 대행 에이전트) → 결정 1건 확정(권한 확인) · 미결은 그대로
    _mdoc = s.documents.register_upload(
        p,
        kind=DocumentKind.MEETING_NOTE,
        file_name="제안준비회의록_20261016.txt",
        data=MEETING_NOTE.encode("utf-8"),
        actor=ACTOR,
    )
    _decs, _mwarn = s.decisions.structure_meeting(p, _mdoc, actor=ACTOR)
    _official = [d for d in _decs if d.kind.value == "official_decision"]
    if _official:
        from proposal_agent.models import DecisionStatus

        s.decisions.confirm_decision(
            p,
            _official[0].id,
            status=DecisionStatus.APPROVED,
            approver="영업 PM",
            authority_confirmed=True,
            comments="사업 책임자 확인",
        )
    log.append(
        f"회의록 구조화: {len(_decs)}건 ({', '.join(sorted({d.kind.value for d in _decs}))}), 공식 결정 승인 {len(_official[:1])}건, 경고 {len(_mwarn)}건"
    )
    log.append(r.run_tech_research(p, actor=ACTOR).summary)
    log.append(r.run_approach_writing(p, actor=ACTOR).summary)
    log.append(r.run_strategy_brief(p, actor=ACTOR).summary)
    log.append(approve_if_needed(s, p, "gateP"))
    log.append(
        r.run_role_step(
            p, StepRunner.STEP_ARCHITECTURE, "architect", "아키텍처 설계", actor=ACTOR
        ).summary
    )
    log.append(r.run_design_writing(p, actor=ACTOR).summary)
    log.append(r.run_detail_design(p, actor=ACTOR).summary)  # 단계 6
    log.append("코드 생성 패키지: " + s.detail_design.export_codegen_package(p, actor=ACTOR))
    log.append(r.run_role_step(p, StepRunner.STEP_WBS, "planner", "WBS 초안", actor=ACTOR).summary)
    # 단계 7: WBS 모듈 분해 → 테스트 계획 → 코드 생성(대행) → Docker 테스트(이미지 있을 때) → 문서
    log.append(r.run_wbs_decompose(p, actor=ACTOR).summary)
    log.append(r.run_test_plan(p, actor=ACTOR).summary)
    _batches, _bw = s.development.plan(p)
    _covered = bool(_batches) and all(
        t_ in DEVELOPER_FILES for b_ in _batches for t_ in b_.target_paths
    )  # 대행 파일이 모든 배치를 덮을 때만 (실모델이면 항상 실행)
    if _covered:
        log.append(r.run_code_generation(p, actor=ACTOR).summary)
        _ds = s.development.docker_status()
        if _ds.ready and os.environ.get("PWA_SKIP_DOCKER") != "1":
            log.append(r.run_code_test(p, actor=ACTOR).summary)
        else:
            log.append(f"Docker 테스트 생략: {_ds.message}")
    else:
        log.append(
            "코드 생성 생략: " + ("; ".join(_bw)[:200] or "대행 파일이 없는 모듈(실모델 실행 필요)")
        )
    log.append(
        "테스트·검수·이관 문서: "
        + ", ".join(
            s.testing.write_documents(
                p, s.development.test_results(p), decisions=s.decisions.open_items(p), actor=ACTOR
            )
        )
    )
    s.steps.run_role(p, "proposal_writer", "제안 문안", actor=ACTOR)
    log.append(r.run_generation(p, actor=ACTOR).summary)
    log.append(r.run_qa(p, actor=ACTOR).summary)
    qa = s.qa.latest_run(p)
    print("\n".join(log))
    print("\n[산출물]")
    for d in s.generation.latest_deliverables(p).values():
        print(f"  {d.kind.value:24} {ctx.paths.resolve_output(d.file_path)}")
    print("\n[통합 QA]", qa.verdict if qa else "-", qa.counts if qa else "", qa.gates if qa else "")
    if qa:
        for c in qa.checks:
            if c.executed and c.final_result.value != "PASS":
                print(f"  {c.check_id} {c.final_result.value}: {'; '.join(c.issues)[:140]}")
    print(
        "\nGate 5는 사람 승인 대기. 프로젝트 ID:",
        p.id,
        "폴더:",
        ctx.paths.project_output_dir(p.output_dir),
    )
    summary = {
        "project_id": p.id,
        "output_dir": p.output_dir,
        "log": log,
        "qa": qa.model_dump(mode="json") if qa else None,
        "note": NOTE,
    }
    (
        ctx.paths.project_output_dir(p.output_dir) / "00_Project_Summary" / "manual_agent_run.json"
    ).write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
