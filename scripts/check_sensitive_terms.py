"""커밋 전 고객 자료 유래 식별 정보 검사 (pre-commit 훅용).

고객 실과제 샘플(RFP·제안서·정의서·추적표·WBS·투입계획)은 저장소 밖에만 두고, 문서·테스트·코드에
고객사명·사업명·제품명·담당자·원문 문장을 적지 않는다. 금지 용어는 저장소에 올리지 않는 로컬 파일
``.sensitive-terms.local``(한 줄에 하나, ``#`` 주석)에 둔다. 스테이징된 텍스트 파일과 추가되는 바이너리
문서(pdf/pptx/docx/xlsx/hwp)를 검사해 하나라도 걸리면 종료 코드 1로 커밋을 막는다.

사용: ``python scripts/check_sensitive_terms.py`` (스테이징 검사) · ``--all``(추적 파일 전체) ·
``--install-hook``(.git/hooks/pre-commit 설치)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMS_FILE = ROOT / ".sensitive-terms.local"
BINARY_DOC_SUFFIXES = {
    ".pdf",
    ".pptx",
    ".docx",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".hwp",
    ".hwpx",
    ".doc",
    ".ppt",
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".sqlite3", ".db"}
ALLOWED_BINARY_DOCS = {
    "docs/AGENT_OVERVIEW.pptx",
    "docs/FLOW_DIAGRAM.pptx",
}  # 코드가 그린 설계 다이어그램
HOOK = """#!/bin/sh
# 고객 자료 유래 식별 정보 검사 (scripts/check_sensitive_terms.py)
python "$(git rev-parse --show-toplevel)/scripts/check_sensitive_terms.py" || exit 1
"""


def load_terms() -> list[str]:
    if not TERMS_FILE.exists():
        return []
    out: list[str] = []
    for line in TERMS_FILE.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            out.append(t)
    return out


def git_files(all_tracked: bool) -> list[str]:
    args = (
        ["git", "ls-files"]
        if all_tracked
        else ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    )
    res = subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False
    )
    return [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]


def file_text(path: str, all_tracked: bool) -> str | None:
    if all_tracked:
        try:
            return (ROOT / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    res = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True, check=False)
    try:
        return res.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949) 대비
    if "--install-hook" in sys.argv:
        hook = ROOT / ".git" / "hooks" / "pre-commit"
        hook.write_text(HOOK, encoding="utf-8", newline="\n")
        print(f"pre-commit 훅 설치: {hook}")
        return 0
    all_tracked = "--all" in sys.argv
    terms = load_terms()
    problems: list[str] = []
    for path in git_files(all_tracked):
        suffix = Path(path).suffix.lower()
        if suffix in BINARY_DOC_SUFFIXES:
            if path.replace("\\", "/") not in ALLOWED_BINARY_DOCS:
                problems.append(
                    f"{path}: 문서 바이너리({suffix})는 저장소에 올리지 않습니다 (고객 샘플 가능성)"
                )
            continue
        if suffix in SKIP_SUFFIXES:
            continue
        text = file_text(path, all_tracked)
        if text is None:
            continue
        for term in terms:
            if term in text:
                line_no = next((i + 1 for i, ln in enumerate(text.splitlines()) if term in ln), 0)
                problems.append(f"{path}:{line_no}: 금지 용어 '{term[:2]}…' 포함")
    if not terms:
        print("경고: .sensitive-terms.local 이 없어 용어 검사는 건너뜀 (문서 바이너리만 검사)")
    if problems:
        print("커밋 차단 - 고객 자료 유래 식별 정보:")
        for p in problems[:50]:
            print("  " + p)
        return 1
    print(f"민감 용어 검사 통과 ({len(terms)}개 용어)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
