"""QA-RFP: RFP 적합성 검사 (independent_qa 분할)."""

from __future__ import annotations

from proposal_agent.models import (
    ProjectMode,
    QaCategory,
    QaCheck,
    RequirementType,
    ScopeClass,
)
from proposal_agent.requirements.id_policy import normalize_text
from proposal_agent.validation.qa_checks.common import (
    EVALUATION_WORDS,
    MANDATORY_PATTERNS,
    SUBMISSION_WORDS,
    QaInputs,
    _block_text_index,
    _cap,
    _check,
    _finish,
    _not_run,
)


def check_rfp_fit(inp: QaInputs, ppt_sub_text: str) -> list[QaCheck]:
    gate = "gate5"
    cat = QaCategory.RFP_FIT
    checks = [
        _check(
            "QA-RFP-01",
            cat,
            "RFP 원문 ↔ 요구사항 목록",
            "의무 표현('하여야 한다' 등)이 있는 원문 블록이 모두 요구사항 출처로 연결되어 있는가",
            gate=gate,
            fix_suggestion="누락 블록을 검토해 요구사항을 추가(요구사항 화면 수동 추가)하거나 '해당 없음' 사유를 기록",
        ),
        _check(
            "QA-RFP-02",
            cat,
            "요구사항 범위 분류",
            "RFP 필수가 아닌 항목(부가 제안·범위 외)이 필수로 표시되지 않았는가, 필수 요구사항에 원문 출처가 있는가",
            gate=gate,
            fix_suggestion="범위 분류·필수 여부를 수정하고 출처를 보강",
        ),
        _check(
            "QA-RFP-03",
            cat,
            "요구사항 인용문 ↔ 원문",
            "요구사항의 원문 인용(rfp_quote)이 실제 원문 블록에 존재하는가",
            gate=gate,
            fix_suggestion="인용을 원문과 일치하도록 수정하거나 요구사항을 재추출",
        ),
        _check(
            "QA-RFP-04",
            cat,
            "제출 조건",
            "RFP가 제출 조건을 요구하면 제출 조건 요구사항이 있고 제출용 제안서에 반영되었는가",
            gate=gate,
            mandatory=False,
            fix_suggestion="제출 조건 요구사항(SUB-)을 추가하고 제안서 제출 안내 섹션에 반영",
        ),
        _check(
            "QA-RFP-05",
            cat,
            "평가 기준 대응",
            "RFP 평가 기준이 요구사항(EVA-)과 제출용 제안서에 대응되는가",
            gate=gate,
            mandatory=False,
            fix_suggestion="평가 항목별 대응 섹션을 제안서에 추가",
        ),
        _check(
            "QA-RFP-06",
            cat,
            "원본 출처 참조",
            "요구사항 출처(document_id·block_id)가 실제 등록 문서·추출 블록을 가리키는가",
            gate=gate,
            fix_suggestion="추출을 다시 실행하고 요구사항을 재검증",
        ),
        _check(
            "QA-RFP-07",
            cat,
            "RFP 요구사항 ID 커버리지",
            "RFP가 부여한 요구사항 ID(예: SFR-001)마다 추출 요구사항이 하나 이상 연결되어 있는가",
            gate=gate,
            fix_suggestion="누락 ID의 절을 확인해 요구사항을 추가 추출·수동 추가",
        ),
        _check(
            "QA-RFP-08",
            cat,
            "목차·전략 승인(Gate P)",
            "전체 제안서 작성 전에 목차 초안·주요 전략·차별화·핵심 기술·위험·제출/발표 구성 차이를 담은 브리프를 사람이 승인했는가 (요청서 §4)",
            gate="gate5",
            fix_suggestion="산출물 화면에서 '전략·목차 브리프 작성(에이전트)' 후 검토·승인하고 재생성",
        ),
        _check(
            "QA-RFP-09",
            cat,
            "요구사항 품질(중복·충돌·검증 불가·누락)",
            "요구사항에 중복·수치 조건 충돌·검증 불가 표현·구현 방안 불명확·RFP 근거 없음·업무 규칙 누락·비기능 누락·테스트 불가능한 수용 기준이 있는가 (지시문 §5.3, 코드 규칙 — 검토 목록)",
            gate="gate1",
            mandatory=False,
            fix_suggestion="요구사항 화면 '품질 검토' 패널의 항목을 확인해 요구사항을 수정·분리·보강하거나 확인 질문으로 관리",
        ),
    ]
    if not inp.blocks or inp.mode != ProjectMode.PROPOSAL:
        return [
            _not_run(c, "RFP 원문 블록이 없음 (구축 단계 프로젝트 또는 추출 전)") for c in checks
        ]
    norm_index = _block_text_index(inp.blocks)
    reqs = inp.requirements
    doc_ids = {d.id for d in inp.documents}
    block_ids = set(norm_index)
    covered: set[str] = set()
    quotes = [normalize_text(r.rfp_quote)[:40] for r in reqs if r.rfp_quote]
    for r in reqs:
        for s in r.source_refs:
            if s.block_id:
                covered.add(s.block_id)
    # 01: 의무 표현 블록 커버리지
    missing_blocks: list[str] = []
    for b in inp.blocks:
        if not any(p in b.text for p in MANDATORY_PATTERNS) or len(b.text) < 15:
            continue
        if b.id in covered:
            continue
        nb = norm_index[b.id]
        if any(q and q in nb for q in quotes):
            continue
        missing_blocks.append(f"{b.location.page or '-'}p/{b.id[:12]}: {b.text[:60]}")
    _finish(
        checks[0],
        review=[
            f"출처로 연결되지 않은 의무 표현 블록 {len(missing_blocks)}건",
            *_cap(missing_blocks, 8),
        ]
        if missing_blocks
        else [],
        files=[d.file_name for d in inp.documents if d.kind.value == "rfp"],
    )
    # 02: 과잉 해석
    over = [
        f"{r.id}: {r.scope_class.value}인데 필수로 표시"
        for r in reqs
        if r.is_mandatory
        and r.scope_class in (ScopeClass.OPTIONAL_PROPOSAL, ScopeClass.OUT_OF_SCOPE)
    ]
    nosrc = [
        f"{r.id}: 필수 요구사항에 원문 출처 없음"
        for r in reqs
        if r.is_mandatory
        and not r.source_refs
        and r.scope_class == ScopeClass.MANDATORY
        and not r.added_by
    ]
    _finish(checks[1], fail=over, review=nosrc, req_ids=[x.split(":")[0] for x in over + nosrc])
    # 03: 인용 ↔ 원문
    mismatch: list[str] = []
    for r in reqs:
        if not r.rfp_quote:
            continue
        q = normalize_text(r.rfp_quote)[:40]
        if not q:
            continue
        targets = [
            norm_index[s.block_id] for s in r.source_refs if s.block_id and s.block_id in norm_index
        ]
        pool = targets or list(norm_index.values())
        if not any(q in t for t in pool):
            mismatch.append(f"{r.id}: 인용 '{r.rfp_quote[:40]}…'이 원문 블록에 없음")
    _finish(checks[2], fail=mismatch, req_ids=[m.split(":")[0] for m in mismatch])
    # 04: 제출 조건
    rfp_text = "\n".join(b.text for b in inp.blocks)
    sub_reqs = [r for r in reqs if r.type == RequirementType.SUBMISSION]
    rev04: list[str] = []
    if any(w in rfp_text for w in SUBMISSION_WORDS) and not sub_reqs:
        rev04.append("RFP에 제출 조건 표현이 있으나 제출 조건 요구사항(SUB-)이 없음")
    for r in sub_reqs:
        if (
            ppt_sub_text
            and r.id not in ppt_sub_text
            and normalize_text(r.name)[:10] not in normalize_text(ppt_sub_text)
        ):
            rev04.append(f"{r.id} '{r.name}'이 제출용 제안서에 언급되지 않음")
    _finish(checks[3], review=rev04, req_ids=[r.id for r in sub_reqs])
    # 05: 평가 기준
    eva_reqs = [r for r in reqs if r.type == RequirementType.EVALUATION]
    rev05: list[str] = []
    if any(w in rfp_text for w in EVALUATION_WORDS) and not eva_reqs:
        rev05.append("RFP에 평가 기준 표현이 있으나 평가 기준 요구사항(EVA-)이 없음")
    for r in eva_reqs:
        if ppt_sub_text and r.id not in ppt_sub_text:
            rev05.append(f"{r.id} '{r.name}' 평가 기준에 대응하는 제안서 내용 없음")
    _finish(checks[4], review=rev05, req_ids=[r.id for r in eva_reqs])
    # 06: 출처 참조 유효성
    dangling: list[str] = []
    for r in reqs:
        for s in r.source_refs:
            if s.document_id not in doc_ids:
                dangling.append(f"{r.id}: 문서 {s.document_id[:12]} 없음")
            elif s.block_id and s.block_id not in block_ids:
                dangling.append(f"{r.id}: 블록 {s.block_id[:12]} 없음 (재추출됨?)")
    _finish(checks[5], fail=dangling, req_ids=[d.split(":")[0] for d in dangling])
    # 07: RFP ID 커버리지 (프로파일이 ID 체계를 찾은 경우만)
    prof = inp.rfp_profile
    if prof is None or not getattr(prof, "requirement_index", None):
        _not_run(checks[6], "RFP 자체 요구사항 ID 체계를 찾지 못함 (문장 단위 RFP)")
    else:
        covered_ids = {r.rfp_requirement_id for r in reqs if r.rfp_requirement_id}
        covered_blocks = {s.block_id for r in reqs for s in r.source_refs if s.block_id}
        uncovered = [
            f"{e.rfp_id} {e.name}".strip()
            for e in prof.requirement_index
            if e.rfp_id not in covered_ids and not (set(e.block_ids) & covered_blocks)
        ]
        _finish(
            checks[6],
            fail=[f"연결된 요구사항이 없는 RFP ID {len(uncovered)}건: " + ", ".join(uncovered[:10])]
            if uncovered
            else [],
        )
    # 08: 목차·전략 승인 (Gate P)
    if inp.gate_p_status == "PASS":
        brief = inp.strategy_brief or {}
        _finish(
            checks[7],
            review=[]
            if brief
            else [
                "브리프 없이 승인됨 — 코드 기본 목차·데이터 기반 문안 (목차·전략을 사람이 직접 확인했는지 기록 필요)"
            ],
        )
    elif inp.gate_p_status == "FAIL":
        _finish(checks[7], fail=["목차·전략 브리프가 반려됨 — 사유를 반영해 다시 작성·승인 필요"])
    else:
        _finish(
            checks[7],
            review=[
                "목차·전략(Gate P)이 아직 승인되지 않음 — 현재 산출물은 시안이며 승인 후 재생성 필요"
                + (" (브리프 작성됨, 검토 대기)" if inp.strategy_brief else " (브리프 미작성)")
            ],
        )
    # 09: 요구사항 품질 (단계 2, 코드 규칙)
    from proposal_agent.requirements.quality import check_requirement_quality

    findings = check_requirement_quality(list(inp.requirements))
    warn = [f.message for f in findings if f.level == "warning"]
    info = [f.message for f in findings if f.level == "info"]
    _finish(
        checks[8],
        review=_cap(warn, 12)
        + ([f"(참고 {len(info)}건: 규칙 초안·업무 규칙·비기능 누락 후보)"] if info else []),
        req_ids=sorted(
            {rid for f in findings if f.level == "warning" for rid in f.requirement_ids}
        ),
    )
    return checks
