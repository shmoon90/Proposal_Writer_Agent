"""코드 생성 배치 계획 (RFP_JAVA codegen_plan 발췌): 모듈을 의존 순서(위상 정렬)로 묶어 Developer 에이전트 호출 단위로 나눈다.
테스트 모듈(src/test/java)은 모든 소스가 생성된 뒤 마지막 배치다.
"""

from __future__ import annotations

from dataclasses import dataclass

from proposal_agent.development.constants import TEST_JAVA_ROOT, is_generated_path
from proposal_agent.models import CodeModule


@dataclass(frozen=True)
class CodeBatchPlan:
    label: str
    kind: str  # source | tests
    target_paths: tuple[str, ...]
    module_codes: tuple[str, ...] = ()


def is_test_module(path: str) -> bool:
    return path.startswith(TEST_JAVA_ROOT)


def generatable_modules(modules: list[CodeModule]) -> tuple[list[CodeModule], list[str]]:
    """생성 앱 규칙(Java 는 base package 아래, 정적 자원은 static 아래)에 맞는 모듈만. 나머지는 경고로 돌려준다."""
    ok: list[CodeModule] = []
    warnings: list[str] = []
    for m in modules:
        path = (m.path or "").replace("\\", "/")
        if not path:
            warnings.append(f"{m.code}: 경로 없음 — 생성 대상에서 제외")
        elif not is_generated_path(path):
            warnings.append(
                f"{m.code}: 생성 규칙에 맞지 않는 경로 {path} — 제외 (Java 는 src/main/java/com/app/…, 정적 자원은 src/main/resources/static/…)"
            )
        else:
            ok.append(m)
    return ok, warnings


def dependency_order(modules: list[CodeModule]) -> list[str]:
    sources = [m for m in modules if not is_test_module(m.path)]
    pending = {
        m.path: {d for d in (m.depends_on or []) if not is_test_module(d) and d != m.path}
        for m in sources
    }
    order: list[str] = []
    while pending:
        ready = [
            p for p in (m.path for m in sources) if p in pending and not (pending[p] - set(order))
        ]
        if not ready:  # 순환 의존 — 남은 것은 원래 순서
            ready = [next(m.path for m in sources if m.path in pending)]
        for path in ready:
            order.append(path)
            del pending[path]
    return order


def plan_batches(modules: list[CodeModule], max_files: int = 3) -> list[CodeBatchPlan]:
    if max_files < 1:
        raise ValueError("max_files 는 1 이상이어야 합니다.")
    code_of = {m.path: m.code for m in modules}
    sources = dependency_order(modules)
    tests = [m.path for m in modules if is_test_module(m.path)]
    src_chunks = [sources[i : i + max_files] for i in range(0, len(sources), max_files)]
    test_chunks = [tests[i : i + max_files] for i in range(0, len(tests), max_files)]
    total = len(src_chunks) + len(test_chunks)
    plans: list[CodeBatchPlan] = []
    for chunk in src_chunks:
        plans.append(
            CodeBatchPlan(
                f"{len(plans) + 1}/{total} 소스",
                "source",
                tuple(chunk),
                tuple(code_of[p] for p in chunk),
            )
        )
    for chunk in test_chunks:
        plans.append(
            CodeBatchPlan(
                f"{len(plans) + 1}/{total} 테스트",
                "tests",
                tuple(chunk),
                tuple(code_of[p] for p in chunk),
            )
        )
    return plans


__all__ = [
    "CodeBatchPlan",
    "dependency_order",
    "generatable_modules",
    "is_test_module",
    "plan_batches",
]
