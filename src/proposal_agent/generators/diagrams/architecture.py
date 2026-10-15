"""구성도·차트 (Pillow로 직접 그린 도형 — 외부 이미지·matplotlib 미사용).

matplotlib은 이 개발 PC의 애플리케이션 제어 정책이 렌더링 DLL(_backend_agg)을 차단해 쓸 수 없다 (RISK R-25).

- 시스템 구성도: 레이어별 박스 + 연결 화살표 (client/web/app/integration/data/infra/security)
- SW 구성도: 구성 요소의 기술 스택 표기 중심
- 서비스 구성도: 요구사항 범위(요구사항 수)와 연계 대상
- 간트 차트: WBS 데이터와 동일한 날짜
- 공수 차트: 실제 산정된 역할별 M/M (데이터 없으면 생성하지 않음)
"""

from __future__ import annotations

import io
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from proposal_agent.generators.base import GenerationContext
from proposal_agent.models import ArchitectureComponent, RequirementType

LAYER_ORDER = ("client", "web", "app", "integration", "data", "infra", "security")
LAYER_LABEL = {
    "client": "사용자/클라이언트",
    "web": "웹",
    "app": "애플리케이션",
    "integration": "연계",
    "data": "데이터",
    "infra": "인프라",
    "security": "보안",
}
LAYER_COLOR = {
    "client": "#DCE6F1",
    "web": "#C6E0B4",
    "app": "#FFE699",
    "integration": "#F8CBAD",
    "data": "#B4C7E7",
    "infra": "#D9D9D9",
    "security": "#F4B183",
}
WHITE = "#FFFFFF"
DARK = "#404040"
GREY = "#7F7F7F"
BLUE = "#2E75B6"
LIGHT_BLUE = "#5B9BD5"
PALE_BLUE = "#9DC3E6"

W, H_ROW, PAD = 1800, 150, 40
_FONT_CACHE: dict[tuple[str | None, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def configure_font(font_path: str | None) -> str | None:
    """한글 폰트 경로를 확인한다. 없으면 None (기본 비트맵 폰트는 한글을 깨뜨리므로 경고 대상)."""
    if font_path and Path(font_path).exists():
        return font_path
    return None


def _font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = (font_path, size)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = (
                ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
            )
        except OSError:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _text_center(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str = DARK,
) -> None:
    x0, y0, x1, y1 = box
    lines = text.split("\n")
    heights = []
    widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        widths.append(bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])
    total_h = sum(heights) + 6 * (len(lines) - 1)
    y = y0 + ((y1 - y0) - total_h) / 2
    for line, w, h in zip(lines, widths, heights, strict=True):
        draw.text((x0 + ((x1 - x0) - w) / 2, y), line, font=font, fill=fill)
        y += h + 6


def _arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = "#595959",
) -> None:
    draw.line([start, end], fill=color, width=3)
    import math

    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 14
    p1 = (end[0] - size * math.cos(ang - math.pi / 6), end[1] - size * math.sin(ang - math.pi / 6))
    p2 = (end[0] - size * math.cos(ang + math.pi / 6), end[1] - size * math.sin(ang + math.pi / 6))
    draw.polygon([end, p1, p2], fill=color)


def _layout(
    components: list[ArchitectureComponent],
) -> tuple[dict[str, tuple[int, int, int, int]], list[tuple[str, int]]]:
    by_layer: OrderedDict[str, list[ArchitectureComponent]] = OrderedDict(
        (layer, []) for layer in LAYER_ORDER
    )
    for c in components:
        by_layer.setdefault(c.layer if c.layer in LAYER_ORDER else "app", []).append(c)
    rows = [(layer, comps) for layer, comps in by_layer.items() if comps]
    boxes: dict[str, tuple[int, int, int, int]] = {}
    layer_rows: list[tuple[str, int]] = []
    top = 110
    label_w = 230
    for layer, comps in rows:
        y0 = top
        layer_rows.append((layer, y0))
        n = len(comps)
        avail = W - label_w - 2 * PAD
        gap = 30
        bw = min(420, int((avail - gap * (n - 1)) / n))
        total = n * bw + gap * (n - 1)
        x = label_w + PAD + (avail - total) // 2
        for comp in comps:
            boxes[comp.id] = (x, y0 + 20, x + bw, y0 + H_ROW - 20)
            x += bw + gap
        top += H_ROW + 20
    return boxes, layer_rows


def build_architecture_diagram(
    ctx: GenerationContext, kind: str, *, font_path: str | None = None
) -> bytes:
    """kind: system | sw | service."""
    fp = configure_font(font_path)
    comps = [
        c for c in ctx.components if not c.diagram_kinds or kind in c.diagram_kinds
    ] or ctx.components
    boxes, layer_rows = _layout(comps)
    height = (layer_rows[-1][1] + H_ROW + 70) if layer_rows else 400
    img = Image.new("RGB", (W, height), WHITE)
    draw = ImageDraw.Draw(img)
    titles = {"system": "시스템 구성도", "sw": "SW 구성도", "service": "서비스 구성도"}
    draw.text(
        (PAD, 30), f"{ctx.project.name} — {titles.get(kind, kind)}", font=_font(fp, 36), fill=BLUE
    )
    for layer, y0 in layer_rows:
        draw.rounded_rectangle(
            (PAD, y0, W - PAD, y0 + H_ROW), radius=12, fill="#FAFAFA", outline="#D0D0D0", width=2
        )
        draw.text(
            (PAD + 16, y0 + H_ROW // 2 - 14),
            LAYER_LABEL.get(layer, layer),
            font=_font(fp, 24),
            fill=DARK,
        )
    small = _font(fp, 22)
    for c in comps:
        box = boxes[c.id]
        draw.rounded_rectangle(
            box, radius=10, fill=LAYER_COLOR.get(c.layer, "#EEEEEE"), outline=DARK, width=2
        )
        label = c.name
        if kind == "sw":
            label = f"{c.name}\n{c.technology or '(기술 미정)'}"
        elif kind == "service":
            n_req = len((c.extra or {}).get("requirement_ids", []))
            label = f"{c.name}" + (f"\n요구사항 {n_req}건" if n_req else "")
        _text_center(draw, box, label, small)
    row_index = {layer: i for i, (layer, _y) in enumerate(layer_rows)}
    detour = 0
    for c in comps:
        for conn in c.connections:
            if conn.to_component_id not in boxes:
                continue
            x0, y0, x1, y1 = boxes[c.id]
            tx0, ty0, tx1, ty1 = boxes[conn.to_component_id]
            target = next(t for t in comps if t.id == conn.to_component_id)
            skip = abs(row_index.get(target.layer, 0) - row_index.get(c.layer, 0))
            if skip <= 1:
                start = ((x0 + x1) / 2, y1 if ty0 > y1 else y0)
                end = ((tx0 + tx1) / 2, ty0 - 2 if ty0 > y1 else ty1 + 2)
                _arrow(draw, start, end)
                label_pos = ((start[0] + end[0]) / 2 + 8, (start[1] + end[1]) / 2 - 10)
            else:
                # 층을 건너뛰는 연결은 오른쪽 바깥으로 우회해 중간 박스와 겹치지 않게 한다
                detour += 1
                xr = max(x1, tx1) + 30 + 36 * detour
                mid_y_src = (y0 + y1) / 2
                mid_y_dst = (ty0 + ty1) / 2
                draw.line(
                    [(x1, mid_y_src), (xr, mid_y_src), (xr, mid_y_dst)], fill="#595959", width=3
                )
                _arrow(draw, (xr, mid_y_dst), (tx1 + 2, mid_y_dst))
                label_pos = (xr + 6, (mid_y_src + mid_y_dst) / 2 - 10)
            if conn.protocol:
                draw.text(label_pos, conn.protocol, font=_font(fp, 18), fill=GREY)
    note = (
        "자동 생성(코드 기본값) — 검토 필요"
        if any((c.extra or {}).get("auto_generated") for c in comps)
        else "에이전트 설계 결과 기반"
    )
    if fp is None:
        note += " · 한글 폰트 없음(PWA_FONT_PATH 설정 필요)"
    draw.text(
        (PAD, height - 40), f"{note} · 생성 {ctx.generated_on}", font=_font(fp, 18), fill=GREY
    )
    return _png(img)


def build_gantt_chart(
    ctx: GenerationContext, *, font_path: str | None = None, max_rows: int = 40
) -> bytes:
    fp = configure_font(font_path)
    items = [w for w in ctx.wbs if w.planned_start and w.planned_end][:max_rows]
    row_h = 34
    label_w = 520
    height = 120 + row_h * max(len(items), 1) + 60
    img = Image.new("RGB", (W, height), WHITE)
    draw = ImageDraw.Draw(img)
    draw.text(
        (PAD, 24),
        f"{ctx.project.name} — 일정 (계획 시작·종료, 영업일 기준 계산)",
        font=_font(fp, 30),
        fill=BLUE,
    )
    if not items:
        draw.text((PAD, 100), "일정 데이터 없음", font=_font(fp, 24), fill=GREY)
        return _png(img)
    start = min(w.planned_start for w in items if w.planned_start)
    end = max(w.planned_end for w in items if w.planned_end)
    total_days = max((end - start).days + 1, 1)
    chart_x0, chart_x1 = label_w, W - PAD
    scale = (chart_x1 - chart_x0) / total_days
    # 월 눈금
    m = date(start.year, start.month, 1)
    while m <= end:
        x = chart_x0 + (m - start).days * scale
        if x >= chart_x0:
            draw.line([(x, 80), (x, height - 50)], fill="#E0E0E0", width=1)
            draw.text((x + 4, 84), m.strftime("%Y-%m"), font=_font(fp, 16), fill=GREY)
        m = date(m.year + (m.month // 12), m.month % 12 + 1, 1)
    y = 110
    small = _font(fp, 18)
    for w in items:
        depth = w.code.count(".")
        color = BLUE if depth == 0 else LIGHT_BLUE if depth == 1 else PALE_BLUE
        x0 = chart_x0 + (w.planned_start - start).days * scale  # type: ignore[operator]
        x1 = chart_x0 + ((w.planned_end - start).days + 1) * scale  # type: ignore[operator]
        draw.rectangle((x0, y + 6, max(x1, x0 + 4), y + row_h - 6), fill=color)
        draw.text((PAD + depth * 18, y + 7), f"{w.code} {w.name[:26]}", font=small, fill=DARK)
        y += row_h
    draw.text(
        (PAD, height - 34),
        f"기간 {start} ~ {end} · 생성 {ctx.generated_on}",
        font=_font(fp, 16),
        fill=GREY,
    )
    return _png(img)


def build_staffing_chart(ctx: GenerationContext, *, font_path: str | None = None) -> bytes | None:
    """역할별 M/M 막대. 산정된 공수가 없으면 None (수치 없는 차트는 만들지 않는다)."""
    from proposal_agent.planning.effort import md_to_mm

    totals: dict[str, Decimal] = {}
    roles = ctx.roles_by_id
    for a in ctx.allocations:
        role = roles.get(a.staff_role_id)
        if role:
            totals[role.role_name] = totals.get(role.role_name, Decimal("0")) + a.effort_md
    if not totals:
        return None
    fp = configure_font(font_path)
    names = list(totals)
    values = [float(md_to_mm(totals[n])) for n in names]
    width, height = 1400, 700
    img = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(img)
    draw.text(
        (PAD, 24),
        "역할별 예상 공수 (WBS 산정 합계, 1 MM = 20 M/D 가정)",
        font=_font(fp, 28),
        fill=BLUE,
    )
    vmax = max(values) or 1.0
    base_y, top_y = height - 120, 110
    n = len(names)
    slot = (width - 2 * PAD) / n
    bar_w = min(120, slot * 0.6)
    for i, (name, v) in enumerate(zip(names, values, strict=True)):
        x0 = PAD + i * slot + (slot - bar_w) / 2
        y0 = base_y - (base_y - top_y) * (v / vmax)
        draw.rectangle((x0, y0, x0 + bar_w, base_y), fill=LIGHT_BLUE)
        draw.text((x0, y0 - 28), f"{v:.1f}", font=_font(fp, 20), fill=DARK)
        draw.text((x0 - 10, base_y + 10), name[:8], font=_font(fp, 20), fill=DARK)
    draw.line([(PAD, base_y), (width - PAD, base_y)], fill=DARK, width=2)
    draw.text((PAD, height - 40), f"생성 {ctx.generated_on}", font=_font(fp, 16), fill=GREY)
    return _png(img)


def default_components(ctx: GenerationContext) -> list[ArchitectureComponent]:
    """아키텍처 에이전트 결과가 없을 때 요구사항 분류로 만드는 기본 구성 (검토 필요 표시)."""
    reqs = ctx.requirements
    func = [r for r in reqs if r.type == RequirementType.FUNCTIONAL]
    nonf = [r for r in reqs if r.type == RequirementType.NON_FUNCTIONAL]
    integration = [
        r
        for r in reqs
        if r.category.value == "interface" or "연계" in r.name or "인터페이스" in r.name
    ]
    security = [
        r for r in nonf if r.category.value == "security" or "보안" in r.name or "암호" in r.name
    ]
    comps: list[ArchitectureComponent] = []

    def add(
        code: str, layer: str, name: str, tech: str, desc: str, req_ids: list[str], kinds: list[str]
    ) -> ArchitectureComponent:
        c = ArchitectureComponent(
            id=code,
            project_id=ctx.project.id,
            layer=layer,
            name=name,
            technology=tech,
            description=desc,
            diagram_kinds=kinds,
            extra={"requirement_ids": req_ids, "auto_generated": True},
        )
        comps.append(c)
        return c

    add(
        "CLI01",
        "client",
        "사용자 (웹 브라우저)",
        "HTML5 브라우저",
        "내부·외부 사용자",
        [],
        ["system", "service"],
    )
    add(
        "WEB01",
        "web",
        "웹 서버",
        "미정 (기술 조사 참조)",
        "정적 자원·리버스 프록시",
        [],
        ["system", "sw"],
    )
    add(
        "APP01",
        "app",
        "애플리케이션 서버",
        "미정 (기술 조사 참조)",
        f"기능 요구사항 {len(func)}건 처리",
        [r.id for r in func],
        ["system", "sw", "service"],
    )
    add("DB01", "data", "DBMS", "미정", "업무 데이터 저장", [], ["system", "sw"])
    if integration:
        add(
            "INT01",
            "integration",
            "연계 서버",
            "미정",
            f"외부 연계 {len(integration)}건",
            [r.id for r in integration],
            ["system", "sw", "service"],
        )
    if security:
        add(
            "SEC01",
            "security",
            "보안 (인증·암호화)",
            "미정",
            f"보안 요구 {len(security)}건",
            [r.id for r in security],
            ["system", "sw"],
        )
    add(
        "INF01",
        "infra",
        "서버·네트워크",
        "미정",
        "이중화·백업 (비기능 요구 참조)",
        [r.id for r in nonf],
        ["system"],
    )
    from proposal_agent.models.design import ComponentConnection

    def link(a: str, b: str, proto: str) -> None:
        src = next(c for c in comps if c.id == a)
        if any(c.id == b for c in comps):
            src.connections.append(ComponentConnection(to_component_id=b, protocol=proto))

    link("CLI01", "WEB01", "HTTPS")
    link("WEB01", "APP01", "HTTP")
    link("APP01", "DB01", "JDBC/ODBC")
    link("APP01", "INT01", "REST/MQ")
    link("APP01", "SEC01", "SSO/암호화")
    _ = timedelta  # 날짜 유틸 보존 (간트에서 사용)
    return comps
