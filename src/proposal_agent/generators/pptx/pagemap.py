"""덱 바이트에서 요구사항 ID ↔ 슬라이드 번호 대응을 만든다 (Phase 17, 추적표 '대응 제안서 페이지').

생성된 PPTX를 다시 열어 슬라이드마다 텍스트 상자·표·그룹 안의 문자열에서 내부 ID(FR-001)와 RFP ID(SFR-001)를 찾는다.
덱이 실제로 담은 내용만 근거로 하므로, 에이전트가 적은 `requirement_ids`와 달라도 파일 기준이 우선한다.
"""

from __future__ import annotations

import io
import re
from typing import Any

from pptx import Presentation

from proposal_agent.models import Requirement

ID_RE = re.compile(r"[A-Z]{2,5}-\d{2,5}(?:-\d{1,3})?")


def _texts(shapes: Any, depth: int = 0) -> list[str]:
    out: list[str] = []
    for sh in shapes:
        if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
            out.append(sh.text_frame.text)
        if getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                for cell in row.cells:
                    out.append(cell.text)
        st = str(getattr(sh, "shape_type", "") or "")
        if "GROUP" in st and depth < 4:
            out.extend(_texts(sh.shapes, depth + 1))
    return out


def requirement_page_map(data: bytes, requirements: list[Requirement]) -> dict[str, list[int]]:
    """요구사항 ID → 그 ID(또는 RFP ID)가 나타난 슬라이드 번호 목록(1부터, 오름차순)."""
    by_token: dict[str, set[str]] = {}
    for r in requirements:
        by_token.setdefault(r.id, set()).add(r.id)
        if r.rfp_requirement_id:
            by_token.setdefault(r.rfp_requirement_id, set()).add(r.id)
    found: dict[str, set[int]] = {}
    prs = Presentation(io.BytesIO(data))
    for idx, slide in enumerate(prs.slides, start=1):
        text = "\n".join(_texts(slide.shapes))
        for tok in set(ID_RE.findall(text)):
            for rid in by_token.get(tok, ()):
                found.setdefault(rid, set()).add(idx)
    return {rid: sorted(pages) for rid, pages in found.items()}


def format_pages(pages: list[int] | None) -> str:
    """[3, 4, 5, 9] → '3-5, 9'. 없으면 '—'."""
    if not pages:
        return "—"
    out: list[str] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        out.append(f"{start}-{prev}" if prev > start else str(start))
        start = prev = p
    out.append(f"{start}-{prev}" if prev > start else str(start))
    return ", ".join(out)


__all__ = ["format_pages", "requirement_page_map"]
