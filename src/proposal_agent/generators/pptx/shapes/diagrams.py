"""도식 14종 (카드·흐름·2열·데이터 흐름·화면·구성도·일정·막대·KPI·비교·RACI·데이터 모델·절차·계층) — shapes 분할."""

from __future__ import annotations

from datetime import date
from typing import Any

from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Pt

from proposal_agent.generators.pptx.shapes.base import (
    LAYER_LABEL,
    LAYER_ORDER,
    RACI_FILLS,
    RACI_LABEL,
    SECURITY_ZONE_ORDER,
    ShapeStyle,
    _grid,
    _rgb,
    arrow,
    group,
    label,
    rect,
)
from proposal_agent.generators.pptx.template import Box


def draw_cards(
    slide: Any,
    box: Box,
    items: list[dict[str, Any]],
    *,
    style: ShapeStyle,
    numbered: bool = True,
    max_cols: int = 4,
) -> None:
    """번호 카드: 제목 띠 + 설명. 배경·목표·핵심 성공 요소·전략에 쓴다. 카드마다 그룹(해제 가능)."""
    items = items[:8]
    if not items:
        return
    cells = _grid(len(items), box, max_cols=max_cols)
    # 카드 높이는 내용에 맞춘다: 제목 띠 + 본문 줄 수(폭 기준 추정) — 빈 세로 상자가 생기지 않게 (Phase 22)
    w0 = cells[0][2] if cells else box.width
    cpl = max(8, int((w0 - 0.3) * 28.35 / (style.base_pt * 0.75)))
    lines = max(1, max(-(-len(str(it.get("text", ""))[:220]) // cpl) for it in items))
    cap = min(box.height, 1.1 + 0.2 + lines * style.base_pt * 1.35 / 28.35 + 0.4)
    rows = -(-len(items) // min(max_cols, len(items)))
    gap = 0.4
    row_h = min(cells[0][3], max(cap, 2.0)) if cells else cap
    for i, (left, _top, w, _h) in enumerate(cells):
        top = box.top + (i // min(max_cols, len(items))) * (row_h + gap)
        h = row_h if rows > 1 else min(cells[0][3], max(cap, 2.0))
        it = items[i]
        card = group(slide, f"카드 {i + 1}: {str(it.get('title', ''))[:20]}")
        rect(card, left, top, w, h, style=style, fill="FFFFFF", line=style.accent)
        head_h = min(1.1, h * 0.3)
        rect(
            card,
            left,
            top,
            w,
            head_h,
            (f"{i + 1:02d}  " if numbered else "") + str(it.get("title", ""))[:40],
            style=style,
            fill=style.primary,
            shape=MSO_SHAPE.RECTANGLE,
            pt=style.base_pt + 1,
            bold=True,
            color="FFFFFF",
            heading=True,
        )
        text = str(it.get("text", ""))
        if text:
            label(
                card,
                left + 0.15,
                top + head_h + 0.1,
                w - 0.3,
                h - head_h - 0.2,
                text[:220],
                style=style,
            )


def draw_flow(
    slide: Any,
    box: Box,
    steps: list[dict[str, Any]],
    *,
    style: ShapeStyle,
) -> None:
    """단계 흐름: 셰브론(단계명) 한 줄 + 아래 설명 상자. 절차·호출 순서·방법론 단계에 쓴다."""
    steps = steps[:7]
    if not steps:
        return
    n = len(steps)
    gap = 0.15
    w = (box.width - gap * (n - 1)) / n
    chev_h = min(1.4, box.height * 0.3)
    for i, st in enumerate(steps):
        left = box.left + i * (w + gap)
        rect(
            slide,
            left,
            box.top,
            w,
            chev_h,
            f"{i + 1}. {str(st.get('title', ''))[:24]}",
            style=style,
            fill=style.primary if i % 2 == 0 else style.accent,
            shape=MSO_SHAPE.CHEVRON if i else MSO_SHAPE.PENTAGON,
            pt=style.base_pt,
            bold=True,
            color="FFFFFF",
            heading=True,
        )
        text = str(st.get("text", ""))
        if text:
            rect(
                slide,
                left,
                box.top + chev_h + 0.25,
                w,
                max(box.height - chev_h - 0.25, 1.0),
                text[:200],
                style=style,
                fill="FFFFFF",
                line=style.accent,
                shape=MSO_SHAPE.RECTANGLE,
                pt=max(style.base_pt - 1, 7),
                align=PP_ALIGN.LEFT,
                anchor=MSO_ANCHOR.TOP,
            )


def draw_two_column(
    slide: Any,
    box: Box,
    left_title: str,
    left_items: list[str],
    right_title: str,
    right_items: list[str],
    *,
    style: ShapeStyle,
) -> None:
    """2열 비교: 현황·이슈 ↔ 방안, AS-IS ↔ TO-BE. 가운데 화살표."""
    col_w = (box.width - 1.6) / 2
    # 열 높이는 항목 수에 맞춘다 (Phase 22: 빈 공간 방지)
    cpl = max(10, int((col_w - 0.4) * 28.35 / (style.base_pt * 0.75)))
    est_lines = sum(
        max(1, -(-len(x[:90]) // cpl))
        for x in (left_items[:8] if len(left_items) >= len(right_items) else right_items[:8])
    )
    col_h = min(box.height, max(2.6, 1.0 + 0.3 + est_lines * style.base_pt * 1.4 / 28.35 + 0.3))
    box = Box(left=box.left, top=box.top, width=box.width, height=col_h)
    for i, (title, items, fill) in enumerate(
        ((left_title, left_items, style.light), (right_title, right_items, style.light2))
    ):
        left = box.left + i * (col_w + 1.6)
        rect(
            slide,
            left,
            box.top,
            col_w,
            0.9,
            title[:40],
            style=style,
            fill=style.primary if i else style.accent,
            shape=MSO_SHAPE.RECTANGLE,
            bold=True,
            color="FFFFFF",
            heading=True,
            pt=style.base_pt + 1,
        )
        rect(
            slide,
            left,
            box.top + 1.0,
            col_w,
            max(box.height - 1.0, 1.0),
            "\n".join(f"• {x[:90]}" for x in items[:8]) or "(내용 없음 — 검토 필요)",
            style=style,
            fill=fill,
            shape=MSO_SHAPE.RECTANGLE,
            align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.TOP,
        )
    mid_y = box.top + box.height / 2
    arrow(
        slide,
        box.left + col_w + 0.3,
        mid_y,
        box.left + col_w + 1.3,
        mid_y,
        style=style,
        width_pt=2.5,
    )


def draw_dataflow(
    slide: Any,
    box: Box,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    style: ShapeStyle,
) -> None:
    """데이터 흐름·호출 절차: 그룹(열)별 노드 상자와 라벨 달린 화살표."""
    nodes = nodes[:16]
    if not nodes:
        return
    groups: list[str] = []
    for n in nodes:
        g = str(n.get("group", "") or "")
        if g not in groups:
            groups.append(g)
    cols = max(len(groups), 1)
    # 라벨 달린 화살표가 있으면 열 사이 간격을 라벨 폭만큼 둔다 (라벨이 상자를 덮지 않게, Phase 21 렌더링 점검)
    col_gap = 2.2 if any(str(e.get("label", "") or "") for e in edges) else 0.6
    col_w = (box.width - col_gap * (cols - 1)) / cols
    pos: dict[str, tuple[float, float, float, float]] = {}
    for ci, g in enumerate(groups):
        members = [n for n in nodes if str(n.get("group", "") or "") == g]
        left = box.left + ci * (col_w + col_gap)
        head = 0.0
        if g:
            rect(
                slide,
                left,
                box.top,
                col_w,
                0.7,
                g[:30],
                style=style,
                fill=style.light,
                shape=MSO_SHAPE.RECTANGLE,
                bold=True,
                color=style.primary,
                heading=True,
            )
            head = 0.85
        avail = box.height - head
        gap = 0.5
        h = min(2.4, (avail - gap * (len(members) - 1)) / max(len(members), 1))
        for ri, n in enumerate(members):
            top = box.top + head + ri * (h + gap)
            nid = str(n.get("id") or n.get("title") or ri)
            pos[nid] = (left, top, col_w, h)
            text = str(n.get("title", ""))[:40]
            if n.get("text"):
                text += "\n" + str(n["text"])[:60]
            rect(
                slide,
                left,
                top,
                col_w,
                h,
                text,
                style=style,
                fill="FFFFFF",
                line=style.primary,
                pt=max(style.base_pt - 1, 7),
            )
    seen_pairs: dict[tuple[str, str], int] = {}
    for e in edges[:24]:
        sid, tid = str(e.get("source", "")), str(e.get("target", ""))
        a, b = pos.get(sid), pos.get(tid)
        if not a or not b:
            continue
        # 같은 두 노드 사이의 두 번째(역방향) 화살표는 아래로 비켜 그려 선·라벨이 겹치지 않게 한다
        pair = (min(sid, tid), max(sid, tid))
        shift = 0.6 * seen_pairs.get(pair, 0)
        seen_pairs[pair] = seen_pairs.get(pair, 0) + 1
        if a[0] < b[0]:
            x1, y1, x2, y2 = a[0] + a[2], a[1] + a[3] / 2 + shift, b[0], b[1] + b[3] / 2 + shift
        elif a[0] > b[0]:
            x1, y1, x2, y2 = a[0], a[1] + a[3] / 2 + shift, b[0] + b[2], b[1] + b[3] / 2 + shift
        else:
            x1, y1, x2, y2 = a[0] + a[2] / 2, a[1] + a[3], b[0] + b[2] / 2, b[1]
        arrow(
            slide,
            x1,
            y1,
            x2,
            y2,
            style=style,
            text=str(e.get("label", ""))[:24],
            label_w=max(col_gap - 0.2, 1.2),
        )


def draw_screen(
    slide: Any,
    box: Box,
    title: str,
    regions: list[dict[str, Any]],
    *,
    style: ShapeStyle,
) -> Any:
    """화면 설계(와이어프레임, Phase 20): 창 틀 + 상단 바 + 탭 + 좌측 메뉴 + 본문 컴포넌트.

    항목 ``kind``(SCREEN_KINDS): section(구획) · input(입력 필드) · button(버튼) · menu(좌측 메뉴, group=nav 와 같음) ·
    tab(상단 탭) · message(안내·오류 메시지) · table(목록 표) · list(목록) · chart(차트 영역). 모두 개별 도형이며
    목업 전체는 그룹 하나로 묶는다(그룹 해제 가능). 돌려주는 값은 그룹 도형.
    """
    grp = group(slide, f"화면 목업: {title[:24] or '화면'}")
    rect(
        grp,
        box.left,
        box.top,
        box.width,
        box.height,
        style=style,
        fill="FAFAFA",
        line=style.text,
        shape=MSO_SHAPE.RECTANGLE,
    )
    small = max(style.base_pt - 2, 7)
    bar_h = 0.9
    rect(
        grp,
        box.left,
        box.top,
        box.width,
        bar_h,
        title[:50] or "화면",
        style=style,
        fill=style.primary,
        shape=MSO_SHAPE.RECTANGLE,
        bold=True,
        color="FFFFFF",
        align=PP_ALIGN.LEFT,
        heading=True,
    )
    kinds = {id(r): str(r.get("kind", "") or "") for r in regions}
    tabs = [r for r in regions if kinds[id(r)] == "tab"][:6]
    nav = [r for r in regions if str(r.get("group", "")) == "nav" or kinds[id(r)] == "menu"][:10]
    body = [r for r in regions if r not in tabs and r not in nav][:8]
    y = box.top + bar_h
    if tabs:
        tab_h = 0.7
        tab_w = min(3.6, (box.width - 0.2) / len(tabs))
        for i, t in enumerate(tabs):
            rect(
                grp,
                box.left + 0.1 + i * tab_w,
                y + 0.05,
                tab_w - 0.1,
                tab_h - 0.1,
                str(t.get("title", ""))[:14],
                style=style,
                fill=style.accent if i == 0 else style.light,
                line=style.accent,
                shape=MSO_SHAPE.ROUND_2_SAME_RECTANGLE,
                pt=small,
                bold=i == 0,
                color="FFFFFF" if i == 0 else style.text,
            )
        y += tab_h
    nav_w = min(4.0, box.width * 0.22) if nav else 0.0
    if nav:
        rect(
            grp,
            box.left,
            y,
            nav_w,
            box.top + box.height - y,
            style=style,
            fill=style.light,
            shape=MSO_SHAPE.RECTANGLE,
        )
        item_h = min(0.75, (box.top + box.height - y - 0.2) / max(len(nav), 1))
        for i, r in enumerate(nav):
            rect(
                grp,
                box.left + 0.15,
                y + 0.1 + i * item_h,
                nav_w - 0.3,
                item_h - 0.1,
                f"▸ {str(r.get('title', ''))[:16]}",
                style=style,
                fill=style.accent if i == 0 else "FFFFFF",
                line=style.accent,
                shape=MSO_SHAPE.RECTANGLE,
                align=PP_ALIGN.LEFT,
                pt=small,
                color="FFFFFF" if i == 0 else style.text,
            )
    inner = Box(
        left=box.left + nav_w + 0.3,
        top=y + 0.3,
        width=box.width - nav_w - 0.6,
        height=box.top + box.height - y - 0.6,
    )
    for i, (left, top, w, h) in enumerate(_grid(len(body), inner, max_cols=2, gap=0.3)):
        r = body[i]
        kind = kinds[id(r)]
        ttl = str(r.get("title", ""))[:30]
        txt = str(r.get("text", "") or "")
        if kind == "input":
            label(
                grp, left, top, w, 0.45, ttl, style=style, bold=True, pt=small, color=style.primary
            )
            rect(
                grp,
                left,
                top + 0.5,
                w,
                min(0.8, max(h - 0.5, 0.5)),
                txt[:40] or "입력",
                style=style,
                fill="FFFFFF",
                line="A6A6A6",
                align=PP_ALIGN.LEFT,
                pt=small,
                color="7F7F7F",
            )
        elif kind == "button":
            rect(
                grp,
                left,
                top,
                min(w, 4.0),
                min(h, 0.9),
                ttl or "확인",
                style=style,
                fill=style.primary,
                pt=small,
                bold=True,
                color="FFFFFF",
            )
            if txt:
                label(
                    grp,
                    left,
                    top + min(h, 0.9) + 0.05,
                    w,
                    max(h - 1.0, 0.3),
                    txt[:80],
                    style=style,
                    pt=small,
                )
        elif kind == "message":
            rect(
                grp,
                left,
                top,
                w,
                min(h, 1.0),
                f"ⓘ {txt or ttl}"[:90],
                style=style,
                fill="FFF4CE",
                line="F0C36D",
                shape=MSO_SHAPE.RECTANGLE,
                align=PP_ALIGN.LEFT,
                pt=small,
            )
        elif kind == "table":
            cols = [c.strip() for c in txt.split("|") if c.strip()][:6] or ["항목", "내용"]
            col_w = w / len(cols)
            head_h = 0.55
            for ci, c in enumerate(cols):
                rect(
                    grp,
                    left + ci * col_w,
                    top,
                    col_w,
                    head_h,
                    c[:12],
                    style=style,
                    fill=style.accent,
                    line="FFFFFF",
                    shape=MSO_SHAPE.RECTANGLE,
                    pt=small,
                    bold=True,
                    color="FFFFFF",
                )
            rows = max(1, min(4, int((h - head_h) // 0.5)))
            for ri in range(rows):
                rect(
                    grp,
                    left,
                    top + head_h + ri * 0.5,
                    w,
                    0.5,
                    style=style,
                    fill="FFFFFF" if ri % 2 == 0 else "F2F2F2",
                    line="D9D9D9",
                    shape=MSO_SHAPE.RECTANGLE,
                )
            label(
                grp,
                left + 0.1,
                top - 0.45,
                w,
                0.45,
                ttl,
                style=style,
                bold=True,
                pt=small,
                color=style.primary,
            )
        elif kind == "list":
            rect(
                grp,
                left,
                top,
                w,
                h,
                style=style,
                fill="FFFFFF",
                line=style.accent,
                shape=MSO_SHAPE.RECTANGLE,
            )
            lines = [x.strip() for x in txt.split("\n") if x.strip()][:6]
            label(
                grp,
                left + 0.1,
                top + 0.05,
                w - 0.2,
                h - 0.1,
                ttl + ("\n" + "\n".join(f"• {x[:30]}" for x in lines) if lines else ""),
                style=style,
                pt=small,
            )
        elif kind == "chart":
            rect(
                grp,
                left,
                top,
                w,
                h,
                style=style,
                fill=style.light2,
                line=style.accent,
                shape=MSO_SHAPE.RECTANGLE,
            )
            label(
                grp,
                left + 0.1,
                top + 0.05,
                w - 0.2,
                0.5,
                ttl,
                style=style,
                bold=True,
                pt=small,
                color=style.primary,
            )
            for bi in range(4):
                bh = (h - 1.0) * (0.35 + 0.15 * bi)
                rect(
                    grp,
                    left + 0.4 + bi * ((w - 0.8) / 4),
                    top + h - 0.2 - bh,
                    (w - 0.8) / 4 - 0.2,
                    bh,
                    style=style,
                    fill=style.accent,
                    shape=MSO_SHAPE.RECTANGLE,
                )
        else:  # section
            rect(
                grp,
                left,
                top,
                w,
                h,
                style=style,
                fill="FFFFFF",
                line=style.accent,
                shape=MSO_SHAPE.RECTANGLE,
            )
            label(
                grp,
                left + 0.1,
                top + 0.05,
                w - 0.2,
                0.5,
                ttl,
                style=style,
                bold=True,
                color=style.primary,
                pt=small,
            )
            if txt:
                label(
                    grp,
                    left + 0.1,
                    top + 0.55,
                    w - 0.2,
                    max(h - 0.6, 0.3),
                    txt[:120],
                    style=style,
                    pt=small,
                )
    return grp


def draw_architecture(
    slide: Any,
    box: Box,
    components: list[Any],
    *,
    style: ShapeStyle,
) -> None:
    """시스템 구성도: 레이어 띠(세로 순서) 안에 구성 요소 상자, 연결은 화살표. 그림이 아닌 도형이라 편집 가능."""
    by_layer: dict[str, list[Any]] = {}
    for c in components:
        by_layer.setdefault(c.layer if c.layer in LAYER_ORDER else "app", []).append(c)
    rows = [(layer, by_layer[layer]) for layer in LAYER_ORDER if layer in by_layer]
    if not rows:
        label(
            slide,
            box.left,
            box.top,
            box.width,
            1.0,
            "구성 요소 없음 — 아키텍처 설계 필요",
            style=style,
        )
        return
    gap = 0.3
    row_h = (box.height - gap * (len(rows) - 1)) / len(rows)
    label_w = min(3.2, box.width * 0.18)
    pos: dict[str, tuple[float, float, float, float]] = {}
    for ri, (layer, comps) in enumerate(rows):
        top = box.top + ri * (row_h + gap)
        rect(
            slide,
            box.left,
            top,
            box.width,
            row_h,
            style=style,
            fill=style.light if ri % 2 == 0 else "F5F5F5",
            shape=MSO_SHAPE.RECTANGLE,
        )
        rect(
            slide,
            box.left,
            top,
            label_w,
            row_h,
            LAYER_LABEL.get(layer, layer),
            style=style,
            fill=style.primary,
            shape=MSO_SHAPE.RECTANGLE,
            bold=True,
            color="FFFFFF",
            heading=True,
            pt=max(style.base_pt - 1, 7),
        )
        n = len(comps)
        cw = (box.width - label_w - 0.3 * (n + 1)) / n
        ch = min(row_h - 0.4, 2.2)
        for ci, c in enumerate(comps):
            left = box.left + label_w + 0.3 + ci * (cw + 0.3)
            ctop = top + (row_h - ch) / 2
            pos[c.id] = (left, ctop, cw, ch)
            tech = c.technology or "미정"
            rect(
                slide,
                left,
                ctop,
                cw,
                ch,
                f"{c.name[:24]}\n{tech[:28]}",
                style=style,
                fill="FFFFFF",
                line=style.primary,
                pt=max(style.base_pt - 1, 7),
            )
    row_of = {c.id: ri for ri, (_layer, comps) in enumerate(rows) for c in comps}
    for c in components:
        for conn in c.connections:
            a, b = pos.get(c.id), pos.get(conn.to_component_id)
            if not a or not b or a == b:
                continue
            adjacent = abs(row_of.get(c.id, 0) - row_of.get(conn.to_component_id, 0)) == 1
            # 세로(레이어 간) 연결만 라벨을 단다 — 라벨은 레이어 사이 간격(gap)에 놓여 상자와 겹치지 않는다
            if a[1] < b[1]:
                far = adjacent and b[1] - (a[1] + a[3]) >= 0.8
                arrow(
                    slide,
                    a[0] + a[2] / 2,
                    a[1] + a[3],
                    b[0] + b[2] / 2,
                    b[1],
                    style=style,
                    text=conn.protocol[:16] if far else "",
                    label_w=2.2,  # 구성도는 세로 화살표가 나란히 놓여 라벨을 좁게 (겹침 방지)
                )
            elif a[1] > b[1]:
                far = adjacent and a[1] - (b[1] + b[3]) >= 0.8
                arrow(
                    slide,
                    a[0] + a[2] / 2,
                    a[1],
                    b[0] + b[2] / 2,
                    b[1] + b[3],
                    style=style,
                    text=conn.protocol[:16] if far else "",
                    label_w=2.2,  # 구성도는 세로 화살표가 나란히 놓여 라벨을 좁게 (겹침 방지)
                )
            else:
                arrow(
                    slide,
                    a[0] + a[2],
                    a[1] + a[3] / 2,
                    b[0],
                    b[1] + b[3] / 2,
                    style=style,
                )


def _month_starts(start: date, end: date) -> list[date]:
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def draw_timeline(
    slide: Any,
    box: Box,
    items: list[tuple[str, date | None, date | None]],
    period_start: date | None,
    period_end: date | None,
    *,
    style: ShapeStyle,
) -> None:
    """일정 축(간트): 월 눈금 + 작업별 막대. 막대·라벨은 개별 도형."""
    dated = [(n, s, e) for n, s, e in items if s and e][:14]
    if not dated or not period_start or not period_end or period_end <= period_start:
        label(slide, box.left, box.top, box.width, 1.0, "일정 데이터 없음 — 검토 필요", style=style)
        return
    label_w = min(5.0, box.width * 0.3)
    axis_left = box.left + label_w
    axis_w = box.width - label_w
    total_days = max((period_end - period_start).days, 1)

    def x_of(d: date) -> float:
        return axis_left + axis_w * max(0.0, min(1.0, (d - period_start).days / total_days))

    head_h = 0.7
    months = _month_starts(period_start, period_end)
    spacing = axis_w / max(len(months), 1)
    step = 1 if spacing >= 1.6 else (2 if spacing >= 0.8 else 3)
    for mi, ms in enumerate(months):
        x = x_of(max(ms, period_start))
        if mi % step:
            continue  # 월 간격이 좁으면 격월·3개월 단위로만 라벨
        label(
            slide,
            x,
            box.top,
            min(1.55, spacing * step - 0.05),
            head_h,
            ms.strftime("%y.%m"),
            style=style,
            pt=max(style.base_pt - 2, 7),
            color=style.primary,
            bold=True,
        )
        line = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Cm(x), Cm(box.top + head_h), Cm(x), Cm(box.top + box.height)
        )
        line.line.color.rgb = _rgb("BFBFBF")
        line.line.width = Pt(0.5)
    row_h = (box.height - head_h) / len(dated)
    bar_h = min(0.7, row_h * 0.6)
    for i, (name, s, e) in enumerate(dated):
        top = box.top + head_h + i * row_h
        label(
            slide,
            box.left,
            top,
            label_w - 0.2,
            row_h,
            name[:28],
            style=style,
            pt=max(style.base_pt - 1, 7),
            anchor=MSO_ANCHOR.MIDDLE,
        )
        x1, x2 = x_of(s), x_of(e)
        rect(
            slide,
            x1,
            top + (row_h - bar_h) / 2,
            max(x2 - x1, 0.25),
            bar_h,
            style=style,
            fill=style.accent if i % 2 == 0 else style.primary,
            shape=MSO_SHAPE.RECTANGLE,
        )


def draw_bars(
    slide: Any,
    box: Box,
    items: list[tuple[str, float, str]],
    *,
    style: ShapeStyle,
) -> None:
    """가로 막대: 역할별 공수(MM) 등. 막대 길이는 최대값 기준."""
    items = items[:10]
    if not items:
        label(slide, box.left, box.top, box.width, 1.0, "데이터 없음 — 검토 필요", style=style)
        return
    vmax = max((v for _n, v, _u in items), default=0.0) or 1.0
    label_w = min(4.5, box.width * 0.3)
    val_w = 2.6
    row_h = box.height / len(items)
    bar_h = min(0.8, row_h * 0.6)
    for i, (name, v, unit) in enumerate(items):
        top = box.top + i * row_h
        label(
            slide,
            box.left,
            top,
            label_w - 0.2,
            row_h,
            name[:24],
            style=style,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        w = max((box.width - label_w - val_w) * (v / vmax), 0.2)
        rect(
            slide,
            box.left + label_w,
            top + (row_h - bar_h) / 2,
            w,
            bar_h,
            style=style,
            fill=style.accent,
            shape=MSO_SHAPE.RECTANGLE,
        )
        label(
            slide,
            box.left + label_w + w + 0.15,
            top,
            val_w,
            row_h,
            f"{v:g} {unit}",
            style=style,
            anchor=MSO_ANCHOR.MIDDLE,
            bold=True,
            color=style.primary,
        )


def draw_kpis(slide: Any, box: Box, items: list[tuple[str, str]], *, style: ShapeStyle) -> None:
    """핵심 수치 카드: 큰 값 + 라벨 (기간·인력·공수·요구사항 수)."""
    items = items[:5]
    if not items:
        return
    for i, (left, top, w, h) in enumerate(_grid(len(items), box, max_cols=5)):
        lab, val = items[i]
        card = group(slide, f"수치 카드: {str(lab)[:20]}")
        rect(
            card,
            left,
            top,
            w,
            h,
            style=style,
            fill=style.light if i % 2 == 0 else style.light2,
            line=style.accent,
        )
        label(
            card,
            left,
            top + 0.1,
            w,
            h * 0.55,
            str(val)[:24],
            style=style,
            pt=min(style.base_pt * 2.4, 32),
            bold=True,
            color=style.primary,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            heading=True,
        )
        label(
            card,
            left,
            top + h * 0.68,
            w,
            h * 0.3,
            str(lab)[:30],
            style=style,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )


def draw_compare(
    slide: Any, box: Box, headers: list[str], rows: list[list[str]], *, style: ShapeStyle
) -> None:
    """비교 표 (네이티브 표)."""
    headers = headers or ["항목"]
    n_rows = min(len(rows), 12) + 1
    shape = slide.shapes.add_table(
        n_rows,
        len(headers),
        Cm(box.left),
        Cm(box.top),
        Cm(box.width),
        Cm(min(box.height, 0.7 * n_rows)),
    )
    table = shape.table
    for ci, hd in enumerate(headers):
        cell = table.cell(0, ci)
        cell.text = str(hd)[:30]
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(max(style.base_pt - 1, 7))
        p.font.bold = True
        p.font.name = style.heading_font
        p.font.color.rgb = _rgb("FFFFFF")
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(style.primary)
    for ri, row in enumerate(rows[:12], start=1):
        for ci in range(len(headers)):
            cell = table.cell(ri, ci)
            cell.text = str(row[ci] if ci < len(row) else "")[:80]
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(max(style.base_pt - 1, 7))
            p.font.name = style.font


# --- Phase 19: 책임 분담·데이터 모델·절차·보안 통제·계층 -----------------------------------------
def draw_raci(
    slide: Any, box: Box, headers: list[str], rows: list[list[str]], *, style: ShapeStyle
) -> None:
    """RACI 책임 분담표: 네이티브 표, R/A/C/I 셀은 색으로 구분. headers[0]=활동, 나머지=역할."""
    headers = [str(h) for h in headers] or ["활동"]
    n_rows = min(len(rows), 12) + 1
    legend_h = 0.6
    shape = slide.shapes.add_table(
        n_rows,
        len(headers),
        Cm(box.left),
        Cm(box.top),
        Cm(box.width),
        Cm(min(box.height - legend_h, 0.7 * n_rows)),
    )
    table = shape.table
    for ci, hd in enumerate(headers):
        cell = table.cell(0, ci)
        cell.text = hd[:30]
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(max(style.base_pt - 1, 7))
        p.font.bold = True
        p.font.name = style.heading_font
        p.font.color.rgb = _rgb("FFFFFF")
        p.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(style.primary)
    for ri, row in enumerate(rows[:12], start=1):
        for ci in range(len(headers)):
            raw = str(row[ci] if ci < len(row) else "").strip()
            cell = table.cell(ri, ci)
            cell.text = raw[:60]
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(max(style.base_pt - 1, 7))
            p.font.name = style.font
            code = raw.upper()[:1] if ci > 0 and raw else ""
            if ci > 0 and code in RACI_FILLS and len(raw) <= 3:
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(RACI_FILLS[code])
                p.font.color.rgb = _rgb("FFFFFF")
                p.font.bold = True
                p.alignment = PP_ALIGN.CENTER
    legend = "   ".join(RACI_LABEL[k] for k in ("R", "A", "C", "I"))
    label(
        slide,
        box.left,
        box.top + box.height - legend_h,
        box.width,
        legend_h,
        legend,
        style=style,
        pt=max(style.base_pt - 2, 7),
        color=style.primary,
    )


def draw_data_model(
    slide: Any,
    box: Box,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    *,
    style: ShapeStyle,
) -> None:
    """데이터 모델(개념 ERD): 엔티티 상자(이름 띠 + 속성 목록)와 관계 화살표(라벨 1:N 등)."""
    entities = entities[:12]
    if not entities:
        return
    pos: dict[str, tuple[float, float, float, float]] = {}
    for i, (left, top, w, h) in enumerate(_grid(len(entities), box, max_cols=4, gap=1.0)):
        ent = entities[i]
        eid = str(ent.get("id") or ent.get("title") or i)
        pos[eid] = (left, top, w, h)
        box_g = group(slide, f"엔티티: {str(ent.get('title', ''))[:20]}")
        rect(
            box_g,
            left,
            top,
            w,
            h,
            style=style,
            fill="FFFFFF",
            line=style.primary,
            shape=MSO_SHAPE.RECTANGLE,
        )
        head_h = min(0.8, h * 0.3)
        rect(
            box_g,
            left,
            top,
            w,
            head_h,
            str(ent.get("title", ""))[:30],
            style=style,
            fill=style.primary,
            shape=MSO_SHAPE.RECTANGLE,
            bold=True,
            color="FFFFFF",
            heading=True,
        )
        attrs = str(ent.get("text", "") or "")
        if attrs:
            label(
                box_g,
                left + 0.1,
                top + head_h + 0.05,
                w - 0.2,
                h - head_h - 0.1,
                "\n".join(f"• {a.strip()[:28]}" for a in attrs.split("\n") if a.strip())[:400],
                style=style,
                pt=max(style.base_pt - 1, 7),
            )
    for e in relations[:24]:
        a, b = pos.get(str(e.get("source", ""))), pos.get(str(e.get("target", "")))
        if not a or not b:
            continue
        if a[0] + a[2] <= b[0]:
            x1, y1, x2, y2 = a[0] + a[2], a[1] + a[3] / 2, b[0], b[1] + b[3] / 2
        elif b[0] + b[2] <= a[0]:
            x1, y1, x2, y2 = a[0], a[1] + a[3] / 2, b[0] + b[2], b[1] + b[3] / 2
        elif a[1] < b[1]:
            x1, y1, x2, y2 = a[0] + a[2] / 2, a[1] + a[3], b[0] + b[2] / 2, b[1]
        else:
            x1, y1, x2, y2 = a[0] + a[2] / 2, a[1], b[0] + b[2] / 2, b[1] + b[3]
        arrow(slide, x1, y1, x2, y2, style=style, text=str(e.get("label", ""))[:16])


def draw_procedure(
    slide: Any,
    box: Box,
    steps: list[dict[str, Any]],
    *,
    style: ShapeStyle,
) -> None:
    """운영·장애 대응 절차: 담당(group)별 가로 레인, 단계는 순서대로 왼쪽→오른쪽, 연속 단계는 화살표."""
    steps = steps[:10]
    if not steps:
        return
    lanes: list[str] = []
    for st in steps:
        g = str(st.get("group", "") or "")
        if g not in lanes:
            lanes.append(g)
    if lanes == [""]:
        draw_flow(slide, box, steps, style=style)
        return
    lane_label_w = 2.8
    n = len(steps)
    gap = 0.3
    lane_h = (box.height - gap * (len(lanes) - 1)) / len(lanes)
    step_w = (box.width - lane_label_w - 0.2 - gap * (n - 1)) / n
    if n >= 3 and step_w < 2.4:  # 좁은 용지(A4 세로)에서 단계가 많으면 세로 절차로
        _draw_procedure_vertical(slide, box, steps, lanes, style=style)
        return
    pos: list[tuple[float, float, float, float]] = []
    for li, lane in enumerate(lanes):
        top = box.top + li * (lane_h + gap)
        rect(
            slide,
            box.left,
            top,
            box.width,
            lane_h,
            style=style,
            fill=style.light if li % 2 == 0 else "F7F7F7",
            line=style.accent,
            shape=MSO_SHAPE.RECTANGLE,
        )
        rect(
            slide,
            box.left,
            top,
            lane_label_w,
            lane_h,
            lane[:16] or "담당",
            style=style,
            fill=style.primary,
            shape=MSO_SHAPE.RECTANGLE,
            bold=True,
            color="FFFFFF",
            heading=True,
        )
    box_h = min(lane_h - 0.3, 2.2)
    for i, st in enumerate(steps):
        li = lanes.index(str(st.get("group", "") or ""))
        left = box.left + lane_label_w + 0.2 + i * (step_w + gap)
        top = box.top + li * (lane_h + gap) + (lane_h - box_h) / 2
        text = f"{i + 1}. {str(st.get('title', ''))[:24]}"
        if st.get("text"):
            text += "\n" + str(st["text"])[:60]
        rect(
            slide,
            left,
            top,
            step_w,
            box_h,
            text,
            style=style,
            fill="FFFFFF",
            line=style.primary,
            pt=max(style.base_pt - 1, 7),
        )
        pos.append((left, top, step_w, box_h))
    for (l1, t1, w1, h1), (l2, t2, _w2, h2) in zip(pos, pos[1:], strict=False):
        arrow(slide, l1 + w1, t1 + h1 / 2, l2, t2 + h2 / 2, style=style)


def _draw_procedure_vertical(
    slide: Any, box: Box, steps: list[dict[str, Any]], lanes: list[str], *, style: ShapeStyle
) -> None:
    """세로 절차: 담당은 열(머리글), 단계는 위→아래 행. 연속 단계는 화살표로 잇는다 (Phase 23)."""
    head_h = 0.8
    gap = 0.2
    col_gap = 0.25
    n = len(steps)
    col_w = (box.width - col_gap * (len(lanes) - 1)) / len(lanes)
    row_h = min(1.5, (box.height - head_h - 0.2 - gap * (n - 1)) / n)
    if row_h < 0.9:  # 영역이 좁으면 간격을 줄이고 상자는 한 줄(제목)만
        gap = 0.1
        row_h = max(0.5, min(1.5, (box.height - head_h - 0.2 - gap * (n - 1)) / n))
    one_line = row_h < 0.8
    for ci, lane in enumerate(lanes):
        left = box.left + ci * (col_w + col_gap)
        rect(
            slide,
            left,
            box.top,
            col_w,
            head_h,
            lane[:16] or "담당",
            style=style,
            fill=style.primary,
            shape=MSO_SHAPE.RECTANGLE,
            bold=True,
            color="FFFFFF",
            heading=True,
        )
        rect(
            slide,
            left,
            box.top + head_h + 0.1,
            col_w,
            max(box.height - head_h - 0.1, 1.0),
            style=style,
            fill=style.light if ci % 2 == 0 else "F7F7F7",
            line=style.accent,
            shape=MSO_SHAPE.RECTANGLE,
        )
    pos: list[tuple[float, float, float, float]] = []
    for i, st in enumerate(steps):
        ci = lanes.index(str(st.get("group", "") or ""))
        left = box.left + ci * (col_w + col_gap) + 0.15
        top = box.top + head_h + 0.2 + i * (row_h + gap)
        text = f"{i + 1}. {str(st.get('title', ''))[:24]}"
        if st.get("text") and not one_line:
            text += "\n" + str(st["text"])[:40]
        w = col_w - 0.3
        rect(
            slide,
            left,
            top,
            w,
            row_h,
            text,
            style=style,
            fill="FFFFFF",
            line=style.primary,
            pt=max(style.base_pt - 1, 7),
        )
        pos.append((left, top, w, row_h))
    for (l1, t1, w1, h1), (l2, t2, w2, _h2) in zip(pos, pos[1:], strict=False):
        arrow(slide, l1 + w1 / 2, t1 + h1, l2 + w2 / 2, t2, style=style)


def _draw_bands(
    slide: Any,
    box: Box,
    items: list[dict[str, Any]],
    *,
    style: ShapeStyle,
    order: tuple[str, ...] = (),
    fills: tuple[str, str] = ("DDEBF7", "E2F0D9"),
) -> None:
    """group 별 가로 띠(위→아래) 안에 항목 상자. 보안 통제·계층 구성 공용."""
    items = items[:20]
    if not items:
        return
    groups: list[str] = []
    for it in items:
        g = str(it.get("group", "") or "")
        if g not in groups:
            groups.append(g)
    if order:
        groups.sort(key=lambda g: next((i for i, o in enumerate(order) if o in g), len(order)))
    gap = 0.25
    band_h = min(
        2.2, (box.height - gap * (len(groups) - 1)) / len(groups)
    )  # Phase 22: 띠 높이 상한
    label_w = 2.6
    for gi, g in enumerate(groups):
        top = box.top + gi * (band_h + gap)
        rect(
            slide,
            box.left,
            top,
            box.width,
            band_h,
            style=style,
            fill=fills[gi % 2],
            line=style.accent,
            shape=MSO_SHAPE.RECTANGLE,
        )
        rect(
            slide,
            box.left,
            top,
            label_w,
            band_h,
            g[:16] or "구분",
            style=style,
            fill=style.primary,
            shape=MSO_SHAPE.RECTANGLE,
            bold=True,
            color="FFFFFF",
            heading=True,
        )
        members = [it for it in items if str(it.get("group", "") or "") == g][:6]
        inner_w = box.width - label_w - 0.4
        w = (inner_w - 0.25 * (len(members) - 1)) / max(len(members), 1)
        h = band_h - 0.3
        for mi, it in enumerate(members):
            text = str(it.get("title", ""))[:30]
            if it.get("text"):
                text += "\n" + str(it["text"])[: 120 if len(members) <= 2 else 70]
            rect(
                slide,
                box.left + label_w + 0.2 + mi * (w + 0.25),
                top + 0.15,
                w,
                h,
                text,
                style=style,
                fill="FFFFFF",
                line=style.primary,
                pt=max(style.base_pt - 1, 7),
            )


def draw_security_layers(
    slide: Any, box: Box, controls: list[dict[str, Any]], *, style: ShapeStyle
) -> None:
    """보안 통제 도식: 영역(네트워크→서버→응용→데이터→관리) 띠마다 통제 상자."""
    _draw_bands(
        slide, box, controls, style=style, order=SECURITY_ZONE_ORDER, fills=("FBE5D6", "FFF2CC")
    )


def draw_layers(slide: Any, box: Box, items: list[dict[str, Any]], *, style: ShapeStyle) -> None:
    """계층 구성(사용자 → 응용 → 데이터 → 인프라 등): group 순서대로 띠."""
    _draw_bands(slide, box, items, style=style)
