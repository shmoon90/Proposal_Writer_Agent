"""생성 코드(Java/Spring Boot, JavaScript, HTML) 정적 검사 — 실행·컴파일하지 않는다 (RFP_JAVA code_inspector 발췌).

검사: 중괄호·괄호 균형, package 선언과 경로 일치, 파일 이름 = public 타입, 허용/금지 import, 금지 호출(프로세스·네트워크·리플렉션),
정의된 타입·메서드 이름, 테스트 메서드의 요구사항 ID, 내부 import 의 실제 존재. 실행 격리를 대신하지 않는 1차 방어선이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from proposal_agent.development.constants import (
    BASE_PACKAGE,
    INSPECTED_EXTENSIONS,
    MAIN_JAVA_ROOT,
    REQUIREMENT_REF_RE,
    STATIC_ROOT,
    TEST_JAVA_ROOT,
)

ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    "java.",
    "jakarta.",
    "org.springframework.",
    "org.junit.",
    "org.mockito.",
    "org.assertj.",
    "org.hamcrest.",
    "com.fasterxml.jackson.",
    "org.slf4j.",
    f"{BASE_PACKAGE}.",
)
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "java.net.",
    "java.lang.reflect",
    "java.lang.ProcessBuilder",
    "java.lang.Runtime",
    "java.rmi",
    "java.sql",
    "javax.sql",
    "javax.script",
    "java.nio.channels",
    "sun.",
    "jdk.",
    "org.springframework.web.client",
    "org.springframework.web.reactive",
    "org.springframework.jdbc",
    "org.springframework.data",
)
FORBIDDEN_JAVA_CALLS: tuple[tuple[str, str], ...] = (
    ("Runtime.getRuntime(", "프로세스 실행(Runtime)"),
    ("new ProcessBuilder(", "프로세스 실행(ProcessBuilder)"),
    ("System.exit(", "JVM 종료(System.exit)"),
    ("Class.forName(", "리플렉션 로딩(Class.forName)"),
    ("new Socket(", "네트워크 소켓"),
    ("new ServerSocket(", "네트워크 소켓"),
    ("new URL(", "외부 URL 접근"),
    ("HttpClient.newHttpClient(", "외부 HTTP 호출"),
    ("new RestTemplate(", "외부 HTTP 호출"),
    ("System.setProperty(", "시스템 속성 변경"),
    ("Files.walkFileTree(", "파일 시스템 순회"),
    ("Files.deleteIfExists(", "파일 삭제"),
    ("Files.delete(", "파일 삭제"),
)
FORBIDDEN_JS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bnew\s+Function\s*\("), "new Function()"),
    (re.compile(r"document\.write\s*\("), "document.write()"),
    (
        re.compile(r"\b(?:fetch|open)\s*\(\s*['\"`](?:https?:)?//"),
        "외부 주소 호출 (상대 경로 /api/... 만 허용)",
    ),
    (re.compile(r"\bnew\s+WebSocket\s*\("), "WebSocket"),
)
FORBIDDEN_HTML_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"<script[^>]+src\s*=\s*['\"](?:https?:)?//", re.IGNORECASE), "외부 스크립트"),
    (re.compile(r"<link[^>]+href\s*=\s*['\"](?:https?:)?//", re.IGNORECASE), "외부 스타일시트"),
    (re.compile(r"\bon\w+\s*=\s*['\"][^'\"]*\beval\s*\(", re.IGNORECASE), "인라인 eval"),
)
JAVA_KEYWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "new",
        "else",
        "do",
        "try",
        "synchronized",
        "throw",
        "super",
        "this",
        "case",
    }
)
TYPE_DECL_RE = re.compile(r"\b(class|interface|enum|record)\s+([A-Z]\w*)")
METHOD_RE = re.compile(
    r"(?:^|[;{}\n])\s*(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|protected|private|static|final|abstract|synchronized|default|native)\s+)*"
    r"(?:<[^>]+>\s*)?"
    r"(?P<type>[\w<>\[\],.?]+(?:\s*<[^>]*>)?(?:\[\])*)\s+(?P<name>[a-z_]\w*)\s*\(",
    re.MULTILINE,
)
IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?([\w.]+?)(\.\*)?\s*;", re.MULTILINE)
PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
TEST_ANNOTATION_RE = re.compile(r"@(?:Test|ParameterizedTest|RepeatedTest)\b")
TEST_METHOD_RE = re.compile(r"\bvoid\s+(\w+)\s*\(")
JS_FUNCTION_RE = re.compile(r"\bfunction\s+(\w+)\s*\(")
JS_ARROW_RE = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>")
JS_CLASS_RE = re.compile(r"\bclass\s+(\w+)")


@dataclass
class TestFunctionInfo:
    __test__ = False
    node_id: str
    requirement_ids: list[str]


@dataclass
class LocalImport:
    module: str
    names: list[str]
    lineno: int


@dataclass
class InspectionResult:
    path: str
    errors: list[str] = field(default_factory=list)
    imports: set[str] = field(default_factory=set)
    local_imports: list[LocalImport] = field(default_factory=list)
    symbols: set[str] = field(default_factory=set)
    tests: list[TestFunctionInfo] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def is_java_file(path: str) -> bool:
    return path.endswith(".java")


def is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return path.startswith(TEST_JAVA_ROOT) and (
        name.endswith("Test.java") or name.endswith("Tests.java")
    )


def is_inspectable(path: str) -> bool:
    return path.endswith(INSPECTED_EXTENSIONS)


def java_class_name(path: str) -> str:
    for root in (MAIN_JAVA_ROOT, TEST_JAVA_ROOT):
        if path.startswith(root):
            return ".".join(PurePosixPath(path[len(root) :]).with_suffix("").parts)
    return ""


def expected_package(path: str) -> str:
    fqcn = java_class_name(path)
    return fqcn.rsplit(".", 1)[0] if "." in fqcn else ""


def class_paths(fqcn: str) -> tuple[str, str]:
    rel = fqcn.replace(".", "/") + ".java"
    return f"{MAIN_JAVA_ROOT}{rel}", f"{TEST_JAVA_ROOT}{rel}"


def strip_code(content: str) -> str:
    """주석과 문자열 리터럴 내용을 공백으로 바꾼다 (줄 수와 위치는 유지)."""

    def blank(match: re.Match[str]) -> str:
        text = match.group(0)
        if text.startswith(("/*", "//", "<!--")):
            return re.sub(r"[^\n]", " ", text)
        return text[0] + re.sub(r"[^\n]", " ", text[1:-1]) + text[-1]

    pattern = r'/\*[\s\S]*?\*/|//[^\n]*|<!--[\s\S]*?-->|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`'
    return re.sub(pattern, blank, content)


def _blank_generics(code: str) -> str:
    """제네릭 인자 내용을 비운다 (<A<B, C>> → <>). 위치·줄 수는 유지되지 않으므로 이름 추출에만 쓴다."""
    pattern = re.compile(r"<[^<>]*>")
    prev = None
    while prev != code:
        prev = code
        code = pattern.sub("<>", code)
    return code


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _brace_balance(path: str, code: str, result: InspectionResult) -> None:
    opened, closed = code.count("{"), code.count("}")
    if opened != closed:
        result.errors.append(
            f"{path}: 중괄호가 맞지 않습니다 ('{{' {opened}개, '}}' {closed}개) — 문법 오류로 보입니다."
        )
    po, pc = code.count("("), code.count(")")
    if po != pc:
        result.errors.append(
            f"{path}: 괄호가 맞지 않습니다 ('(' {po}개, ')' {pc}개) — 문법 오류로 보입니다."
        )


def _inspect_java(path: str, content: str, result: InspectionResult) -> None:
    code = strip_code(content)
    _brace_balance(path, code, result)
    declared = PACKAGE_RE.search(code)
    package = declared.group(1) if declared else ""
    expected = expected_package(path)
    if not expected or not (expected == BASE_PACKAGE or expected.startswith(f"{BASE_PACKAGE}.")):
        result.errors.append(
            f"{path}: Java 파일은 {MAIN_JAVA_ROOT} 또는 {TEST_JAVA_ROOT} 아래 {BASE_PACKAGE} 패키지 경로에 있어야 합니다."
        )
    elif package != expected:
        result.errors.append(
            f"{path}:1: package 선언({package or '없음'})이 경로와 다릅니다. 'package {expected};' 이어야 합니다."
        )
    for match in IMPORT_RE.finditer(code):
        is_static, name = bool(match.group(1)), match.group(2)
        lineno = _line_of(code, match.start())
        result.imports.add(name)
        if any(name.startswith(prefix) for prefix in FORBIDDEN_IMPORT_PREFIXES):
            result.errors.append(f"{path}:{lineno}: 금지된 import: {name}")
            continue
        if not any(name.startswith(prefix) for prefix in ALLOWED_IMPORT_PREFIXES):
            result.errors.append(
                f"{path}:{lineno}: 허용되지 않은 패키지 import: {name} (허용: java.*, jakarta.*, org.springframework.*, org.junit.*, "
                f"org.mockito.*, org.assertj.*, com.fasterxml.jackson.*, org.slf4j.*, {BASE_PACKAGE}.*)"
            )
            continue
        if name.startswith(f"{BASE_PACKAGE}."):
            if is_static:
                owner, member = name.rsplit(".", 1)
                result.local_imports.append(LocalImport(owner, [member], lineno))
            elif not match.group(3):
                result.local_imports.append(LocalImport(name, [], lineno))
    for needle, label in FORBIDDEN_JAVA_CALLS:
        index = code.find(needle)
        if index >= 0:
            result.errors.append(
                f"{path}:{_line_of(code, index)}: 금지된 호출: {label} ({needle.rstrip('(')})"
            )
    file_stem = PurePosixPath(path).stem
    types = [(m.group(2), m.start()) for m in TYPE_DECL_RE.finditer(code)]
    type_names = [name for name, _ in types]
    if file_stem not in type_names:
        result.errors.append(
            f"{path}: 파일 이름과 같은 타입 {file_stem} 이(가) 정의되어 있지 않습니다."
        )
    result.symbols.update(type_names)
    for name, _ in types:
        if name != file_stem:
            result.symbols.add(f"{file_stem}.{name}")
    method_code = _blank_generics(
        code
    )  # List<Map<String, Object>> 같은 중첩 제네릭은 <> 로 비워 메서드 이름을 찾는다
    for match in METHOD_RE.finditer(method_code):
        name = match.group("name")
        if (
            name in JAVA_KEYWORDS
            or match.group("type") in JAVA_KEYWORDS
            or match.group("type") in ("record", "class", "enum", "interface")
        ):
            continue
        owner = file_stem
        for type_name, position in types:
            if position < match.start():
                owner = type_name
        result.symbols.add(f"{owner}.{name}")
        if owner != file_stem:
            result.symbols.add(f"{file_stem}.{name}")
    if is_test_file(path):
        result.tests = _collect_java_tests(path, content, code)
    elif path.startswith(TEST_JAVA_ROOT) and TEST_ANNOTATION_RE.search(code):
        result.errors.append(f"{path}: 테스트 클래스 파일 이름은 *Test.java 로 끝나야 합니다.")


def _collect_java_tests(path: str, raw: str, code: str) -> list[TestFunctionInfo]:
    tests: list[TestFunctionInfo] = []
    seen: set[str] = set()
    for match in TEST_ANNOTATION_RE.finditer(code):
        method = TEST_METHOD_RE.search(code, match.end())
        if method is None:
            continue
        name = method.group(1)
        if name in seen:
            continue
        seen.add(name)
        start_line = max(0, _line_of(code, match.start()) - 7)
        window = "\n".join(raw.splitlines()[start_line : _line_of(code, method.end())])
        ids = sorted(set(REQUIREMENT_REF_RE.findall(window)))
        tests.append(TestFunctionInfo(node_id=f"{path}::{name}", requirement_ids=ids))
    return tests


def _inspect_js(path: str, content: str, result: InspectionResult) -> None:
    code = strip_code(content)
    _brace_balance(path, code, result)
    for pattern, label in FORBIDDEN_JS_PATTERNS:
        match = pattern.search(content)
        if match:
            result.errors.append(f"{path}:{_line_of(content, match.start())}: 금지된 사용: {label}")
    for regex in (JS_FUNCTION_RE, JS_ARROW_RE, JS_CLASS_RE):
        result.symbols.update(m.group(1) for m in regex.finditer(code))


def _inspect_html(path: str, content: str, result: InspectionResult) -> None:
    for pattern, label in FORBIDDEN_HTML_PATTERNS:
        match = pattern.search(content)
        if match:
            result.errors.append(f"{path}:{_line_of(content, match.start())}: 금지된 사용: {label}")
    if not path.startswith(STATIC_ROOT):
        result.errors.append(f"{path}: HTML 은 {STATIC_ROOT} 아래에 있어야 합니다.")


def inspect_source(path: str, content: str) -> InspectionResult:
    result = InspectionResult(path=path)
    if is_java_file(path):
        _inspect_java(path, content, result)
    elif path.endswith(".js"):
        _inspect_js(path, content, result)
    elif path.endswith(".html"):
        _inspect_html(path, content, result)
    return result


def inspect_all(snapshot: dict[str, str]) -> dict[str, InspectionResult]:
    return {p: inspect_source(p, c) for p, c in snapshot.items() if is_inspectable(p)}


def cross_check_imports(
    results: dict[str, InspectionResult], known_paths: set[str] | None = None
) -> list[str]:
    """내부 import 가 실제 파일(또는 계획된 경로)을 가리키는지 (불일치는 경고)."""
    known = set(results) | (known_paths or set())
    problems: list[str] = []
    for path, result in results.items():
        for imp in result.local_imports:
            main_path, test_path = class_paths(imp.module)
            target = results.get(main_path) or results.get(test_path)
            if target is None:
                if main_path in known or test_path in known:
                    continue
                outer = imp.module.rsplit(".", 1)[0]
                outer_main, outer_test = class_paths(outer)
                if outer_main in known or outer_test in known:
                    continue
                problems.append(
                    f"{path}:{imp.lineno}: 생성되지 않은 내부 클래스를 import 합니다: {imp.module}"
                )
                continue
            for name in imp.names:
                stem = PurePosixPath(main_path).stem
                if f"{stem}.{name}" not in target.symbols and name not in target.symbols:
                    problems.append(
                        f"{path}:{imp.lineno}: {imp.module} 에 '{name}' 이(가) 정의되어 있지 않습니다."
                    )
    return problems


def check_test_rules(result: InspectionResult, known_ids: set[str]) -> list[str]:
    """테스트 파일 규칙: @Test 메서드가 있어야 하고, @DisplayName/주석에 실제 요구사항 ID 가 있어야 한다."""
    if not is_test_file(result.path):
        return []
    if not result.tests:
        return [f"{result.path}: @Test 메서드가 없습니다."]
    errors: list[str] = []
    for test in result.tests:
        if not test.requirement_ids:
            errors.append(
                f"{test.node_id}: @DisplayName 또는 바로 위 주석에 요구사항 ID 가 없습니다."
            )
            continue
        unknown = [r for r in test.requirement_ids if r not in known_ids]
        if unknown:
            errors.append(f"{test.node_id}: 존재하지 않는 요구사항 ID: {', '.join(unknown)}")
    return errors


__all__ = [
    "InspectionResult",
    "TestFunctionInfo",
    "check_test_rules",
    "cross_check_imports",
    "inspect_all",
    "inspect_source",
    "is_inspectable",
    "is_test_file",
]
