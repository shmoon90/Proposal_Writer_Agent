"""Docker 격리 JUnit 실행기 (RFP_JAVA test_runner 발췌): 생성 앱을 임시 폴더로 복사해 읽기 전용으로 마운트하고,
네트워크 없는 컨테이너에서 오프라인 Maven 으로 테스트한 뒤 surefire 보고서를 해석한다. 로컬 실행 방식은 없다.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET  # noqa: N817
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from proposal_agent.development.constants import (
    GENERATED_EXTENSIONS,
    MAIN_JAVA_ROOT,
    TEST_JAVA_ROOT,
)
from proposal_agent.development.models import TestCaseResult, TestRunResult

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO_ROOT / "docker" / "test-runner.Dockerfile"
DEFAULT_IMAGE = "rfp-java-test-runner:jdk21-1"
MAX_COPY_BYTES = 20 * 1024 * 1024
MAX_JUNIT_BYTES = 10 * 1024 * 1024
MAX_CASE_MESSAGE = 2000
SKIP_DIRS = {"target", ".git", ".idea", "node_modules", "test_results"}
SUREFIRE_DIR = "surefire"
DOCKER_CLI_ERROR_CODES = {125, 126, 127}
TEST_ARGS = ("run-tests",)  # 이미지 안 고정 스크립트만 호출한다


def is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or (path.exists() and path.is_junction())
    except OSError:
        return True


@dataclass(frozen=True)
class ProcessOutcome:
    exit_code: int | None
    timed_out: bool = False
    launch_error: str | None = None


ProcessRunner = Callable[..., ProcessOutcome]


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    else:
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            pass
    if proc.poll() is None:
        proc.kill()


def run_process(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stdout_path: Path,
    stderr_path: Path,
    on_timeout: Callable[[], None] | None = None,
) -> ProcessOutcome:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    start_new_session = sys.platform != "win32"
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        try:
            proc = subprocess.Popen(  # noqa: S603 - 고정 인자 목록, shell=False
                cmd,
                cwd=cwd,
                env=env,
                stdout=out,
                stderr=err,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
        except OSError as exc:
            return ProcessOutcome(
                exit_code=None, launch_error=f"프로세스를 시작할 수 없습니다: {exc}"
            )
        try:
            return ProcessOutcome(exit_code=proc.wait(timeout=timeout))
        except subprocess.TimeoutExpired:
            if on_timeout is not None:
                on_timeout()
            _kill_tree(proc)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
            return ProcessOutcome(exit_code=None, timed_out=True)


def copy_app(src: Path, dst: Path) -> list[str]:
    copied: list[str] = []
    total = 0
    for root, dirs, files in os.walk(src, followlinks=False):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not is_link(root_path / d)]
        for name in files:
            path = root_path / name
            if is_link(path) or not name.endswith(GENERATED_EXTENSIONS):
                continue
            data = path.read_bytes()
            total += len(data)
            if total > MAX_COPY_BYTES:
                raise ValueError(f"생성 앱 크기가 제한({MAX_COPY_BYTES:,} bytes)을 초과합니다.")
            rel = path.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            copied.append(rel.as_posix())
    return sorted(copied)


def cli_env(extra_path: str | None = None) -> dict[str, str]:
    """docker CLI 환경: 비밀로 보이는 변수는 제거한다 (컨테이너에는 어차피 전달되지 않음)."""
    secret = re.compile(r"(API_KEY|SECRET|TOKEN|PASSWORD|ANTHROPIC)", re.IGNORECASE)
    env = {k: v for k, v in os.environ.items() if not secret.search(k)}
    if extra_path:
        path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
        env[path_key] = os.pathsep.join([extra_path, env.get(path_key, "")])
    return env


def find_docker() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    candidates = []
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
        if base:
            candidates += [
                Path(base) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe",
                Path(base) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe",
            ]
    return next((str(c) for c in candidates if c.is_file()), None)


def _read_limited(path: Path, limit: int) -> tuple[str, bool]:
    if not path.exists():
        return "", False
    with path.open("rb") as fh:
        data = fh.read(limit * 4 + 1)
    text = data.decode("utf-8", errors="replace")
    truncated = len(text) > limit or path.stat().st_size > len(data)
    return text[:limit], truncated


def _node_id(classname: str, name: str, known_files: set[str]) -> str:
    base = classname.split("$", 1)[0]
    nested = classname.split("$")[1:]
    rel = base.replace(".", "/") + ".java"
    method = name.split("(", 1)[0].split("[", 1)[0] or name
    for root in (TEST_JAVA_ROOT, MAIN_JAVA_ROOT):
        candidate = f"{root}{rel}"
        if candidate in known_files:
            return "::".join([candidate, *nested, method])
    return "::".join([classname, method]) if classname else method


def parse_surefire(directory: Path, known_files: set[str]) -> list[TestCaseResult] | None:
    if not directory.is_dir():
        return None
    cases: list[TestCaseResult] = []
    parsed_any = False
    for path in sorted(directory.glob("TEST-*.xml")):
        if path.stat().st_size > MAX_JUNIT_BYTES:
            continue
        try:
            root = ET.parse(path).getroot()  # noqa: S314 - 우리가 만든 surefire 보고서
        except ET.ParseError:
            continue
        parsed_any = True
        for case in root.iter("testcase"):
            outcome, message = "passed", ""
            for child, label in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
                element = case.find(child)
                if element is not None:
                    outcome = label
                    message = (element.get("message") or "") + (
                        "\n" + element.text if element.text else ""
                    )
                    break
            cases.append(
                TestCaseResult(
                    node_id=_node_id(case.get("classname", ""), case.get("name", ""), known_files),
                    outcome=outcome,
                    message=message.strip()[:MAX_CASE_MESSAGE],
                )
            )
    return cases if parsed_any else None


_SUMMARY_RE = re.compile(
    r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)"
)
_COMPILE_ERROR_RE = re.compile(r"COMPILATION ERROR|BUILD FAILURE")


def parse_summary_counts(stdout: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    matches = _SUMMARY_RE.findall(stdout)
    if matches:
        run, failures, errors, skipped = (int(v) for v in matches[-1])
        counts.update(
            failed=failures,
            errors=errors,
            skipped=skipped,
            passed=max(run - failures - errors - skipped, 0),
        )
    return counts


def compile_error_excerpt(stdout: str, limit: int = 1500) -> str:
    if not _COMPILE_ERROR_RE.search(stdout):
        return ""
    lines = [line for line in stdout.splitlines() if "[ERROR]" in line]
    text = "\n".join(lines)
    return text[:limit] + ("…" if len(text) > limit else "")


def _base_node(node_id: str) -> str:
    return node_id.split("[", 1)[0]


@dataclass(frozen=True)
class DockerStatus:
    installed: bool
    daemon_running: bool
    image_present: bool
    message: str

    @property
    def ready(self) -> bool:
        return self.installed and self.daemon_running and self.image_present


class DockerSandbox:
    """Docker CLI 래퍼. 모든 명령은 고정 인자 목록이다."""

    def __init__(self, image: str = DEFAULT_IMAGE, executable: str | None = None) -> None:
        self.image = image
        self.executable = executable or find_docker()

    def env(self) -> dict[str, str]:
        return cli_env(
            str(Path(self.executable).parent)
            if self.executable and Path(self.executable).is_absolute()
            else None
        )

    def _run(self, args: list[str], timeout: float) -> subprocess.CompletedProcess[str] | None:
        if not self.executable:
            return None
        try:
            return subprocess.run(  # noqa: S603 - 고정 인자 목록
                [self.executable, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=self.env(),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def status(self) -> DockerStatus:
        if not self.executable:
            return DockerStatus(False, False, False, "Docker 가 설치되어 있지 않습니다.")
        version = self._run(["version", "--format", "{{.Server.Version}}"], timeout=8)
        if version is None or version.returncode != 0:
            return DockerStatus(
                True,
                False,
                False,
                "Docker 엔진이 응답하지 않습니다. Docker Desktop 이 실행 중인지 확인하십시오.",
            )
        image = self._run(["image", "inspect", self.image], timeout=20)
        if image is None or image.returncode != 0:
            return DockerStatus(
                True,
                True,
                False,
                f"테스트 이미지 {self.image} 가 없습니다. 이미지를 빌드하십시오 (JDK 21 + Maven, 수 분 소요).",
            )
        return DockerStatus(
            True, True, True, f"준비됨 (Docker {version.stdout.strip()}, 이미지 {self.image})"
        )

    def build_image(self, timeout: float = 1800) -> tuple[bool, str]:
        result = self._run(
            ["build", "-t", self.image, "-f", str(DOCKERFILE), str(DOCKERFILE.parent)],
            timeout=timeout,
        )
        if result is None:
            return False, "docker build 를 실행할 수 없거나 시간이 초과되었습니다."
        return result.returncode == 0, (result.stdout + result.stderr)[-3000:]

    @staticmethod
    def mount(path: Path, target: str, *, readonly: bool) -> str:
        if "," in str(path):
            raise ValueError(f"마운트 경로에 ',' 를 사용할 수 없습니다: {path}")
        return f"type=bind,source={path},target={target}" + (",readonly" if readonly else "")

    def run_command(self, app_dir: Path, out_dir: Path, container_name: str) -> list[str]:
        return [
            self.executable or "docker", "run", "--rm", "--name", container_name,
            "--network", "none",
            "--read-only", "--tmpfs", "/tmp:rw,size=1g",
            "--memory", "2g", "--cpus", "2", "--pids-limit", "512",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "-e", "HOME=/tmp",
            "--mount", self.mount(app_dir, "/app", readonly=True),
            "--mount", self.mount(out_dir, "/out", readonly=False),
            "-w", "/tmp",
            self.image,
            *TEST_ARGS,
        ]  # fmt: skip

    def kill(self, container_name: str) -> None:
        self._run(["kill", container_name], timeout=30)


class TestRunner:
    __test__ = False

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        timeout_seconds: int = 420,
        max_output_chars: int = 200_000,
        process_runner: ProcessRunner = run_process,
        docker: DockerSandbox | None = None,
    ) -> None:
        self.timeout = timeout_seconds
        self.max_output = max_output_chars
        self._process = process_runner
        self.docker = docker or DockerSandbox(image)

    def run(self, app_dir: Path, *, required_tests: list[str], label: str) -> TestRunResult:
        started = datetime.now().astimezone()
        tmp = Path(tempfile.mkdtemp(prefix="pwa-test-"))
        command: list[str] = []
        try:
            app_copy, out_dir = tmp / "app", tmp / "out"
            for d in (app_copy, out_dir):
                d.mkdir()
            out_dir.chmod(0o777)
            try:
                known_files = set(copy_app(app_dir, app_copy))
            except (OSError, ValueError) as exc:
                return self._error(label, command, started, f"생성 앱 복사 실패: {exc}")
            status = self.docker.status()
            if not status.ready:
                return self._error(label, command, started, status.message)
            name = f"pwa-test-{uuid.uuid4().hex[:12]}"
            command = self.docker.run_command(app_copy, out_dir, name)
            outcome = self._process(
                command,
                cwd=tmp,
                env=self.docker.env(),
                timeout=self.timeout,
                stdout_path=tmp / "stdout.txt",
                stderr_path=tmp / "stderr.txt",
                on_timeout=lambda: self.docker.kill(name),
            )
            stdout, cut_out = _read_limited(tmp / "stdout.txt", self.max_output)
            stderr, cut_err = _read_limited(tmp / "stderr.txt", self.max_output)
            duration = (datetime.now().astimezone() - started).total_seconds()
            runner_error = outcome.launch_error
            if runner_error is None and outcome.exit_code in DOCKER_CLI_ERROR_CODES:
                runner_error = (
                    f"docker run 실패 (종료 코드 {outcome.exit_code}): {stderr.strip()[-500:]}"
                )
            cases = parse_surefire(out_dir / SUREFIRE_DIR, known_files)
            if cases is not None:
                counts = {
                    "passed": sum(c.outcome == "passed" for c in cases),
                    "failed": sum(c.outcome == "failed" for c in cases),
                    "errors": sum(c.outcome == "error" for c in cases),
                    "skipped": sum(c.outcome == "skipped" for c in cases),
                }
            else:
                cases, counts = [], parse_summary_counts(stdout)
                excerpt = compile_error_excerpt(stdout)
                if (
                    excerpt
                    and not outcome.timed_out
                    and runner_error is None
                    and outcome.exit_code not in (0, None)
                ):
                    counts["errors"] = max(counts["errors"], 1)
                    cases = [
                        TestCaseResult(
                            node_id="maven::compile",
                            outcome="error",
                            message=excerpt[:MAX_CASE_MESSAGE],
                        )
                    ]
            executed = {_base_node(c.node_id) for c in cases if c.outcome != "skipped"}
            missing = sorted({_base_node(r) for r in required_tests} - executed)
            if not cases and outcome.exit_code == 0:
                missing = sorted({_base_node(r) for r in required_tests})
            return TestRunResult(
                label=label,
                mode="docker",
                command=command,
                started_at=started,
                duration_seconds=round(duration, 2),
                exit_code=outcome.exit_code,
                timed_out=outcome.timed_out,
                runner_error=runner_error,
                stdout=stdout,
                stderr=stderr,
                output_truncated=cut_out or cut_err,
                cases=cases,
                missing_required=missing,
                **counts,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _error(
        self, label: str, command: list[str], started: datetime, message: str
    ) -> TestRunResult:
        return TestRunResult(
            label=label,
            mode="docker",
            command=command,
            started_at=started,
            duration_seconds=round((datetime.now().astimezone() - started).total_seconds(), 2),
            exit_code=None,
            runner_error=message,
        )


__all__ = [
    "DEFAULT_IMAGE",
    "DockerSandbox",
    "DockerStatus",
    "TestRunner",
    "copy_app",
    "parse_surefire",
    "run_process",
]
