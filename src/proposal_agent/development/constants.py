"""생성 앱 고정 상수 (RFP_JAVA app_templates/architecture 발췌)."""

from __future__ import annotations

import re

GENERATED_APP_SUBDIR = "14_Generated_App"
TEST_RESULTS_DIR = "test_results"  # 14_Generated_App/test_results/testing-N.json
BASE_PACKAGE = "com.app"
BASE_PACKAGE_DIR = BASE_PACKAGE.replace(".", "/") + "/"
MAIN_JAVA_ROOT = "src/main/java/"
TEST_JAVA_ROOT = "src/test/java/"
STATIC_ROOT = "src/main/resources/static/"
APPLICATION_CLASS_PATH = f"{MAIN_JAVA_ROOT}{BASE_PACKAGE_DIR}Application.java"
APPLICATION_PROPERTIES_PATH = "src/main/resources/application.properties"
POM_PATH = "pom.xml"
README_PATH = "README.md"
SPRING_BOOT_VERSION = "3.4.5"
JAVA_VERSION = "21"
# Docker 테스트 이미지(docker/seed/pom.xml)에 미리 내려받은 의존성과 같아야 오프라인 빌드가 된다.
FIXED_DEPENDENCIES = (
    "spring-boot-starter-web",
    "spring-boot-starter-validation",
    "spring-boot-starter-test",
)
GENERATED_EXTENSIONS = (
    ".java",
    ".js",
    ".html",
    ".css",
    ".properties",
    ".yml",
    ".yaml",
    ".json",
    ".xml",
    ".md",
    ".txt",
)
INSPECTED_EXTENSIONS = (".java", ".js", ".html")
MAX_GENERATED_FILE_BYTES = 200 * 1024
TEMPLATE_PATHS = (POM_PATH, APPLICATION_CLASS_PATH, APPLICATION_PROPERTIES_PATH, README_PATH)
# 요구사항 ID (이 프로젝트의 ID 체계: FR-001, NFR-003, SFR-010 …)
REQUIREMENT_REF_RE = re.compile(
    r"\b(?!TC-|DEF-|BR-|TBL-|API-|SCR-|MOD-|DSG-|STR-|NEG-|DEC-|COL-|CR-)[A-Z]{2,4}-\d{3}\b"
)  # 요구사항 ID 만 (테스트·결함·설계 코드 접두사는 제외)


def is_java_path(path: str) -> bool:
    return path.endswith(".java")


def is_generated_path(path: str) -> bool:
    """생성 앱에 둘 수 있는 경로인가 (Java 는 base package 아래, 정적 자원은 static 아래)."""
    p = path.replace("\\", "/")
    if p.endswith(".java"):
        return p.startswith(
            (f"{MAIN_JAVA_ROOT}{BASE_PACKAGE_DIR}", f"{TEST_JAVA_ROOT}{BASE_PACKAGE_DIR}")
        )
    if p.endswith((".js", ".html", ".css")):
        return p.startswith(STATIC_ROOT)
    return p.endswith(GENERATED_EXTENSIONS)


__all__ = [
    "APPLICATION_CLASS_PATH",
    "APPLICATION_PROPERTIES_PATH",
    "BASE_PACKAGE",
    "BASE_PACKAGE_DIR",
    "FIXED_DEPENDENCIES",
    "GENERATED_APP_SUBDIR",
    "GENERATED_EXTENSIONS",
    "INSPECTED_EXTENSIONS",
    "JAVA_VERSION",
    "MAIN_JAVA_ROOT",
    "MAX_GENERATED_FILE_BYTES",
    "POM_PATH",
    "README_PATH",
    "REQUIREMENT_REF_RE",
    "SPRING_BOOT_VERSION",
    "STATIC_ROOT",
    "TEMPLATE_PATHS",
    "TEST_JAVA_ROOT",
    "TEST_RESULTS_DIR",
    "is_generated_path",
    "is_java_path",
]
