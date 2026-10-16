"""pytest를 실행하고 결과 요약을 ``workspace/DEVELOPMENT_STATUS.json``의 ``tests``에 기록한다 (Phase 16).

진행 상태 문서와 실제 테스트 결과가 어긋나지 않게 하는 장치다. 실행하지 않은 테스트를 성공으로 적지 않으며,
요약 줄을 해석하지 못하면 기록하지 않고 종료 코드 2를 돌려준다.

사용: ``python scripts/record_test_status.py``(전체 실행) · ``--summary "253 passed, 1 skipped"``(이미 실행한 요약만 기록)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "workspace" / "DEVELOPMENT_STATUS.json"
SUMMARY_RE = re.compile(r"(\d+) (passed|failed|skipped|deselected|error|errors|xfailed|xpassed)")


def parse_summary(text: str) -> dict[str, int] | None:
    tail = [ln for ln in text.strip().splitlines() if ln.strip()]
    for line in reversed(tail):
        found = dict((k, int(v)) for v, k in SUMMARY_RE.findall(line))
        if found:
            return {
                "passed": found.get("passed", 0),
                "failed": found.get("failed", 0) + found.get("error", 0) + found.get("errors", 0),
                "skipped": found.get("skipped", 0),
                "deselected": found.get("deselected", 0),
            }
    return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--summary" in sys.argv:
        text = sys.argv[sys.argv.index("--summary") + 1]
        command = "pytest -q (요약 입력)"
    else:
        command = "pytest -q -p no:cacheprovider"
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        text = res.stdout + "\n" + res.stderr
        print(text.strip().splitlines()[-1] if text.strip() else "(출력 없음)")
    counts = parse_summary(text)
    if counts is None:
        print("pytest 요약 줄을 해석하지 못해 기록하지 않습니다.")
        return 2
    data = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    data["tests"] = {"last_run": date.today().isoformat(), "command": command, **counts}
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기록: {counts} → {STATUS}")
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
