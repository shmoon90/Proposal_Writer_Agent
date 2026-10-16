"""복합 장표 블록: 밴드 제목·표·기능 블록·높이 추정·블록 배치·도식 디스패치 — shapes 분할."""

from __future__ import annotations

import re
from typing import Any

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Pt

from proposal_agent.generators.pptx.shapes.base import (
    ShapeStyle,
    _grid,
    _rgb,
    arrow,
    group,
    label,
    rect,
)
from proposal_agent.generators.pptx.shapes.diagrams import (
    draw_cards,
    draw_compare,
    draw_data_model,
    draw_dataflow,
    draw_decision_table,
    draw_deployment,
    draw_flow,
    draw_kpis,
    draw_layers,
    draw_procedure,
    draw_raci,
    draw_screen,
    draw_security_layers,
    draw_two_column,
)
from proposal_agent.generators.pptx.template import Box


# --- Phase 22: 밴드 제목·기능 블록 도식·복합 장표 배치 ----------------------------------------------
def band_heading(
    slide: Any, left: float, top: float, width: float, text: str, *, style: ShapeStyle
) -> float:
    """장표 안 소제목 띠(어두운 바탕 + 왼쪽 강조 셰브론). 돌려주는 값은 띠 아래 y."""
    h = 0.7
    rect(
        slide,
        left,
        top,
        width,
        h,
        style=style,
        fill="404040",
        shape=MSO_SHAPE.RECTANGLE,
    )
    rect(
        slide,
        left + 0.1,
        top + 0.1,
        0.8,
        h - 0.2,
        style=style,
        fill=style.primary,
        shape=MSO_SHAPE.CHEVRON,
    )
    label(
        slide,
        left + 1.2,
        top,
        width - 1.4,
        h,
        text[:60],
        style=style,
        bold=True,
        color="FFFFFF",
        pt=style.base_pt + 1,
        anchor=MSO_ANCHOR.MIDDLE,
        heading=True,
    )
    return top + h + 0.25


def draw_text_table(
    slide: Any,
    box: Box,
    headers: list[str],
    rows: list[list[str]],
    *,
    style: ShapeStyle,
    col_widths: list[float] | None = None,
    pt: float | None = None,
    cell_chars: int = 600,
) -> Any:
    """여러 줄 셀을 담는 네이티브 표 (구현 방안 전문용). 행 높이는 줄 수 추정으로 배분한다."""
    headers = headers or ["항목"]
    size = pt or max(style.base_pt - 1, 7)
    n_rows = len(rows) + 1
    widths = col_widths or [1.0] * len(headers)
    total = sum(widths)
    col_cm = [box.width * w / total for w in widths]

    def lines_of(ci: int, text: str) -> int:
        cpl = max(6, int((col_cm[ci] - 0.3) * 28.35 / (size * 0.72)))
        return sum(max(1, -(-len(line) // cpl)) for line in text.split("\n"))

    row_lines = [max(lines_of(ci, str(c)[:cell_chars]) for ci, c in enumerate(r)) for r in rows]
    line_cm = size * 1.25 / 28.35
    heights = [0.75] + [max(0.6, ln * line_cm + 0.15) for ln in row_lines]
    # 영역을 넘는 행은 그리지 않는다 (행 높이를 줄이면 PowerPoint 가 글에 맞춰 다시 키워 슬라이드를 넘긴다)
    while len(heights) > 2 and sum(heights) > box.height:
        heights.pop()
        rows = rows[:-1]
    n_rows = len(rows) + 1
    if sum(heights) > box.height:
        k = box.height / sum(heights)
        heights = [h * k for h in heights]
    shape = slide.shapes.add_table(
        n_rows,
        len(headers),
        Cm(box.left),
        Cm(box.top),
        Cm(box.width),
        Cm(sum(heights)),
    )
    table = shape.table
    for ci, w in enumerate(col_cm):
        table.columns[ci].width = Cm(w)
    for ri, hcm in enumerate(heights):
        table.rows[ri].height = Cm(hcm)
    for ci, hd in enumerate(headers):
        cell = table.cell(0, ci)
        cell.text = str(hd)[:30]
        para = cell.text_frame.paragraphs[0]
        para.font.size = Pt(size)
        para.font.bold = True
        para.font.name = style.heading_font
        para.font.color.rgb = _rgb("FFFFFF")
        para.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(style.primary)
    for ri, row in enumerate(rows, start=1):
        for ci in range(len(headers)):
            cell = table.cell(ri, ci)
            text = str(row[ci] if ci < len(row) else "")[:cell_chars]
            tf = cell.text_frame
            tf.word_wrap = True
            for li, line in enumerate(text.split("\n")):
                para = tf.paragraphs[0] if li == 0 else tf.add_paragraph()
                para.text = line
                para.font.size = Pt(size)
                para.font.name = style.font
            cell.margin_left = cell.margin_right = Cm(0.12)
            cell.margin_top = cell.margin_bottom = Cm(0.06)
    shape.name = f"표: {len(rows)}행"  # 호출자가 그린 행 수를 알 수 있게
    return shape


def draw_function_blocks(slide: Any, box: Box, spec: dict[str, Any], *, style: ShapeStyle) -> None:
    """요구사항 묶음 블록 도식: 왼쪽 사용자(액터) → 가운데 시스템 상자(기능 격자) → 오른쪽 연계 대상.

    spec: {title, actors:[str], functions:[{id,title,text}], externals:[str]}
    """
    actors = [str(x) for x in spec.get("actors", []) or []][:3]
    funcs = [dict(x) for x in spec.get("functions", []) or []][:12]
    externals = [str(x) for x in spec.get("externals", []) or []][:3]
    side_w = 3.3
    gap = 1.3
    left_x = box.left
    center_x = box.left + (side_w + gap if actors else 0.0)
    center_w = box.width - (side_w + gap if actors else 0.0) - (side_w + gap if externals else 0.0)
    # 가운데 시스템 상자
    sys_box = group(slide, f"기능 블록: {str(spec.get('title', ''))[:20]}")
    rect(
        sys_box,
        center_x,
        box.top,
        center_w,
        box.height,
        style=style,
        fill="F4F6FA",
        line=style.primary,
        shape=MSO_SHAPE.RECTANGLE,
    )
    rect(
        sys_box,
        center_x,
        box.top,
        center_w,
        0.75,
        str(spec.get("title", ""))[:40],
        style=style,
        fill=style.primary,
        shape=MSO_SHAPE.RECTANGLE,
        bold=True,
        color="FFFFFF",
        heading=True,
    )
    inner = Box(
        left=center_x + 0.3,
        top=box.top + 1.0,
        width=center_w - 0.6,
        height=max(box.height - 1.3, 1.5),
    )
    cols = 1 if len(funcs) <= 2 else (2 if len(funcs) <= 6 else 3)
    cells = _grid(len(funcs), inner, max_cols=cols, gap=0.3)
    cell_h = min(cells[0][3], 1.5) if cells else 1.3
    for i, (cl, _ct, cw, _ch) in enumerate(cells):
        f = funcs[i]
        top = inner.top + (i // cols) * (cell_h + 0.3)
        text = f"{f.get('title', '')}"
        if f.get("text"):
            text += f"\n난이도 {f['text']}"
        rect(
            sys_box,
            cl,
            top,
            cw,
            cell_h,
            text[:60],
            style=style,
            fill="FFFFFF",
            line=style.accent,
            pt=max(style.base_pt - 1, 7),
        )
    mid_y = box.top + box.height / 2
    # 액터
    if actors:
        a_h = min(1.6, (box.height - 0.4 * (len(actors) - 1)) / len(actors))
        start = box.top + (box.height - (a_h * len(actors) + 0.4 * (len(actors) - 1))) / 2
        for i, a in enumerate(actors):
            top = start + i * (a_h + 0.4)
            rect(
                slide,
                left_x,
                top,
                side_w,
                a_h,
                a[:16],
                style=style,
                fill=style.light,
                line=style.accent,
                shape=MSO_SHAPE.ROUNDED_RECTANGLE,
                bold=True,
                color=style.primary,
            )
            arrow(slide, left_x + side_w, top + a_h / 2, center_x, top + a_h / 2, style=style)
    # 연계 대상
    if externals:
        ex_x = center_x + center_w + gap
        e_h = min(1.6, (box.height - 0.4 * (len(externals) - 1)) / len(externals))
        start = box.top + (box.height - (e_h * len(externals) + 0.4 * (len(externals) - 1))) / 2
        for i, e in enumerate(externals):
            top = start + i * (e_h + 0.4)
            rect(
                slide,
                ex_x,
                top,
                side_w,
                e_h,
                e[:16],
                style=style,
                fill=style.light2,
                line=style.accent,
                shape=MSO_SHAPE.ROUNDED_RECTANGLE,
                bold=True,
                color=style.primary,
            )
            arrow(slide, center_x + center_w, top + e_h / 2, ex_x, top + e_h / 2, style=style)
    del mid_y


def estimate_block_height(block: dict[str, Any], width: float, style: ShapeStyle) -> float:
    """복합 장표 배치용 블록 필요 높이(cm) 추정."""
    kind = str(block.get("kind", ""))
    pt = style.base_pt
    if kind == "bullets":
        lines = block.get("lines", []) or []
        cpl = max(10, int((width - 0.6) * 28.35 / (pt * 0.82)))
        return 0.4 + sum(max(1, -(-len(str(x)) // cpl)) for x in lines) * pt * 1.5 / 28.35
    if kind == "table":
        rows = block.get("rows", []) or []
        widths = block.get("col_widths") or [1.0] * max(1, len(block.get("headers", []) or [1]))
        total = sum(widths)
        size = max(pt - 1, 7)
        est = 0.75
        for r in rows:
            ln = 1
            for ci, c in enumerate(r):
                col_cm = width * (widths[ci] if ci < len(widths) else 1.0) / total
                cpl = max(6, int((col_cm - 0.3) * 28.35 / (size * 0.7)))
                ln = max(ln, sum(max(1, -(-len(line) // cpl)) for line in str(c).split("\n")))
            est += max(0.6, ln * size * 1.25 / 28.35 + 0.15)
        return est
    if kind == "cards":
        items = block.get("items", []) or []
        cols = min(int(block.get("max_cols", 4) or 4), max(1, len(items)))
        rows = -(-max(1, len(items)) // cols)
        return rows * 3.2 + (rows - 1) * 0.4
    if kind == "visual":
        spec = block.get("spec", {}) or {}
        vk = str(spec.get("kind", "cards"))
        n = len(spec.get("items", []) or [])
        if vk in ("layers", "security_layers"):
            groups = len({str(x.get("group", "")) for x in spec.get("items", []) or []}) or 1
            return min(groups * 2.2 + (groups - 1) * 0.25, 11.0)
        if vk in ("flow", "process"):
            return 4.5
        if vk == "kpis":
            return 3.2
        if vk in ("two_column", "compare", "raci", "chart", "decision"):
            return 6.0
        if vk in ("cards",):
            return 3.4 * (-(-max(1, n) // 4))
        if vk == "procedure":  # 좁은 용지에서 단계가 많으면 세로 절차(단계 수에 비례)
            step_w = (width - 3.0 - 0.3 * max(n - 1, 0)) / max(n, 1)
            if n >= 3 and step_w < 2.4:
                return min(1.0 + n * 1.2 + 0.2 * (n - 1), 12.0)
            return 5.5
        return 7.0  # dataflow/data_model/screen
    if kind == "function_blocks":
        n = len(block.get("spec", {}).get("functions", []) or [])
        cols = 1 if n <= 2 else (2 if n <= 6 else 3)
        rows = -(-max(1, n) // cols)
        return min(9.0, 1.3 + rows * 1.5 + (rows - 1) * 0.3)
    return 4.0


LAST_BLOCK_META: list[dict[str, Any]] = []  # 직전 draw_blocks 가 그린 표의 행 수 등 (호출자 참고용)


def draw_blocks(
    slide: Any, box: Box, blocks: list[dict[str, Any]], *, style: ShapeStyle
) -> list[tuple[str, Box]]:
    """소제목 띠 + 내용 블록을 위에서 아래로 배치한다(샘플 제안서의 2~3 밴드 구성). 블록 kind:
    bullets{lines} · table{headers,rows,col_widths} · cards{items,max_cols} · visual{spec} · function_blocks{spec}.
    높이는 필요량 추정 비율로 나누되, 남는 공간은 마지막 블록이 쓰지 않고 비워 둔다(세로로 늘어진 상자 방지)."""
    blocks = [b for b in blocks if b][:4]
    if not blocks:
        return []
    head_h = 0.95  # 띠 0.7 + 간격
    needs = [estimate_block_height(b, box.width, style) for b in blocks]
    heads = sum(head_h if str(b.get("title", "") or "") else 0.0 for b in blocks)
    avail = box.height - heads - 0.3 * (len(blocks) - 1)
    fixed = [
        str(b.get("kind", "")) in ("bullets", "table") for b in blocks
    ]  # 글머리·표는 줄이지 않는다 (표 행은 렌더링 때 글에 맞춰 커지므로 줄이면 슬라이드를 넘긴다)
    fixed_need = sum(n for n, f in zip(needs, fixed, strict=True) if f)
    flex_need = sum(n for n, f in zip(needs, fixed, strict=True) if not f)
    flex_avail = max(avail - fixed_need, 1.0)
    min_h = {"cards": 3.0, "table": 2.4, "visual": 4.0, "function_blocks": 4.0}
    if flex_need > flex_avail:
        scale = flex_avail / flex_need
        heights = [
            n if f else max(min_h.get(str(b.get("kind", "")), 1.8), n * scale)
            for n, f, b in zip(needs, fixed, blocks, strict=True)
        ]
    else:
        heights = list(needs)
    y = box.top
    placed: list[tuple[str, Box]] = []
    LAST_BLOCK_META.clear()
    for blk, h in zip(blocks, heights, strict=True):
        if y + head_h + 1.0 > box.top + box.height:
            break
        title = str(blk.get("title", "") or "")
        if title:
            y = band_heading(slide, box.left, y, box.width, title, style=style)
        else:
            y += 0.0
        area = Box(left=box.left, top=y, width=box.width, height=min(h, box.top + box.height - y))
        kind = str(blk.get("kind", ""))
        if kind == "bullets":
            label(
                slide,
                area.left + 0.2,
                area.top,
                area.width - 0.4,
                area.height,
                "\n".join(f"• {str(x)}" for x in (blk.get("lines", []) or [])[:8]),
                style=style,
                pt=style.base_pt,
            )
        elif kind == "table":
            tbl = draw_text_table(
                slide,
                area,
                [str(h_) for h_ in blk.get("headers", []) or []],
                [[str(c) for c in r] for r in blk.get("rows", []) or []],
                style=style,
                col_widths=list(blk.get("col_widths") or []) or None,
            )
            LAST_BLOCK_META.append({"kind": "table", "rows_drawn": len(tbl.table.rows) - 1})
        elif kind == "cards":
            draw_cards(
                slide,
                area,
                list(blk.get("items", []) or []),
                style=style,
                numbered=bool(blk.get("numbered", False)),
                max_cols=int(blk.get("max_cols", 4) or 4),
            )
        elif kind == "visual":
            draw_visual(slide, area, dict(blk.get("spec", {}) or {}), style=style)
        elif kind == "function_blocks":
            draw_function_blocks(slide, area, dict(blk.get("spec", {}) or {}), style=style)
        placed.append((kind, area))
        y = area.top + area.height + 0.3
    return placed


# --- 에이전트 지정 도식 ----------------------------------------------------------------------------
def draw_visual(slide: Any, box: Box, spec: dict[str, Any], *, style: ShapeStyle) -> str:
    """``VisualSpec``(dict)을 종류에 맞게 그린다. 돌려주는 값은 실제로 그린 종류."""
    kind = str(spec.get("kind", "cards") or "cards")
    items = [dict(x) for x in spec.get("items", []) or []]
    edges = [dict(x) for x in spec.get("edges", []) or []]
    if kind == "flow" or kind == "process":
        draw_flow(slide, box, items, style=style)
    elif kind == "two_column":
        left = [
            str(x.get("title") or x.get("text") or "")
            for x in items
            if str(x.get("group", "")) in ("", "left")
        ]
        right = [
            str(x.get("title") or x.get("text") or "")
            for x in items
            if str(x.get("group", "")) == "right"
        ]
        if not right and len(left) > 1:
            half = -(-len(left) // 2)
            left, right = left[:half], left[half:]
        draw_two_column(
            slide,
            box,
            str(spec.get("left_title") or "현황 및 이슈"),
            left,
            str(spec.get("right_title") or "구성·개선 방안"),
            right,
            style=style,
        )
    elif kind == "dataflow":
        draw_dataflow(slide, box, items, edges, style=style)
    elif kind == "screen":
        draw_screen(slide, box, str(spec.get("title") or ""), items, style=style)
    elif kind == "kpis":
        draw_kpis(
            slide,
            box,
            [(str(x.get("title", "")), str(x.get("text", ""))) for x in items],
            style=style,
        )
    elif kind == "compare":
        draw_compare(
            slide,
            box,
            [str(h) for h in spec.get("headers", []) or []],
            [[str(c) for c in r] for r in spec.get("rows", []) or []],
            style=style,
        )
    elif kind == "raci":
        headers = [str(h) for h in spec.get("headers", []) or []]
        rows = [[str(c) for c in r] for r in spec.get("rows", []) or []]
        if not rows and items:  # items 로 준 경우: title=활동, text="R,A,C,I" 순
            rows = [[str(x.get("title", "")), *str(x.get("text", "")).split(",")] for x in items]
        draw_raci(slide, box, headers or ["활동"], rows, style=style)
    elif kind == "data_model":
        draw_data_model(slide, box, items, edges, style=style)
    elif kind == "procedure":
        draw_procedure(slide, box, items, style=style)
    elif kind == "security_layers":
        draw_security_layers(slide, box, items, style=style)
    elif kind == "layers":
        draw_layers(slide, box, items, style=style)
    elif kind == "deployment":
        draw_deployment(slide, box, items, edges, style=style)
    elif kind == "decision":
        draw_decision_table(
            slide,
            box,
            [str(h) for h in spec.get("headers", []) or []],
            [[str(c) for c in r] for r in spec.get("rows", []) or []],
            style=style,
        )
    elif kind == "chart":
        from proposal_agent.generators.pptx.charts import chart_from_spec

        if chart_from_spec(slide, box, spec, style=style) is None:
            kind = "compare"
            draw_compare(
                slide,
                box,
                [str(h) for h in spec.get("headers", []) or []],
                [[str(c) for c in r] for r in spec.get("rows", []) or []],
                style=style,
            )
    else:
        kind = "cards"
        draw_cards(slide, box, items, style=style)
    return kind


def visual_summary_text(spec: dict[str, Any]) -> str:
    """QA·검색용: 도식에 들어간 텍스트를 한 줄로."""
    parts = [str(spec.get("title", "") or "")]
    for x in spec.get("items", []) or []:
        parts.append(f"{x.get('title', '')} {x.get('text', '')}".strip())
    return re.sub(r"\s+", " ", " / ".join(p for p in parts if p)).strip()
