"""도형 기본: 스타일·글자 맞춤·사각형/라벨/화살표/그룹·상수 (shapes 분할, 단계 1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Cm, Pt

from proposal_agent.generators.pptx.template import Box

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

VISUAL_KINDS = (
    "cards",
    "flow",
    "two_column",
    "dataflow",
    "screen",
    "process",
    "architecture",
    "timeline",
    "bars",
    "kpis",
    "compare",
    # Phase 19
    "raci",
    "data_model",
    "procedure",
    "security_layers",
    "layers",
    "chart",  # Phase 20: 네이티브 차트 (charts.py)
    "deployment",  # 단계 4: 배포·네트워크 구조 (영역 열 + 노드 + 연결)
    "decision",  # 단계 4: 의사결정 표 (기준 × 대안, 가중 합계)
)

# 에이전트(proposal_writer)가 VisualSpec.kind 로 고를 수 있는 종류 14종(Phase 20: chart 추가). architecture/timeline/bars 는 코드가 데이터로 그린다.
AGENT_VISUAL_KINDS = (
    "cards",
    "flow",
    "process",
    "two_column",
    "dataflow",
    "screen",
    "kpis",
    "compare",
    "raci",
    "data_model",
    "procedure",
    "security_layers",
    "layers",
    "chart",
    "deployment",
    "decision",
)

DEPLOYMENT_ZONES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("외부·사용자", ("client", "external")),
    ("DMZ", ("web",)),
    ("내부망", ("app", "integration", "batch", "security")),
    ("데이터·인프라", ("data", "infra")),
)

# 화면 목업(screen) 항목 종류 (VisualItem.kind, Phase 20). 모두 개별 도형이며 목업 전체는 그룹(해제 가능).
SCREEN_KINDS = ("section", "input", "button", "menu", "tab", "message", "table", "list", "chart")

RACI_FILLS = {"R": "1F4E78", "A": "C00000", "C": "5B9BD5", "I": "A6A6A6"}

RACI_LABEL = {"R": "R 실행", "A": "A 책임", "C": "C 협의", "I": "I 통보"}

SECURITY_ZONE_ORDER = ("네트워크", "서버", "응용", "데이터", "관리")


@dataclass(frozen=True)
class ShapeStyle:
    font: str = "맑은 고딕"
    title_font: str | None = None
    primary: str = "1F4E78"
    accent: str = "5B9BD5"
    light: str = "DDEBF7"
    light2: str = "E2F0D9"
    text: str = "333333"
    base_pt: float = 10.0

    @property
    def heading_font(self) -> str:
        return self.title_font or self.font


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.lstrip("#")[:6])


def _fit(text: str, width_cm: float, height_cm: float, pt: float) -> str:
    """상자 용량(줄 수 × 줄당 글자 수)에 맞게 자른다. QA의 넘침 추정과 같은 가정(줄 높이 1.3em, 글자 폭 0.75em)."""
    if not text or (len(text) <= 6 and "\n" not in text):
        return text  # 짧은 라벨(월, 번호)은 자르지 않는다
    cpl = max(4, int(width_cm * 28.35 / (pt * 0.75)))
    lines = max(1, int(height_cm * 28.35 / (pt * 1.3)))
    out: list[str] = []
    used = 0
    for raw in text.split("\n"):
        need = max(1, -(-len(raw) // cpl))
        if used + need > lines:
            room = (lines - used) * cpl
            if room > 3:
                out.append(raw[: room - 1] + "…")
            break
        out.append(raw)
        used += need
    return "\n".join(out) if out else text[: max(cpl - 1, 1)] + "…"


def _set_text(
    shape: Any,
    text: str,
    *,
    style: ShapeStyle,
    pt: float | None = None,
    bold: bool = False,
    color: str | None = None,
    align: PP_ALIGN = PP_ALIGN.CENTER,
    anchor: MSO_ANCHOR = MSO_ANCHOR.MIDDLE,
    heading: bool = False,
) -> None:
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Cm(0.15)
    tf.margin_top = tf.margin_bottom = Cm(0.08)
    size_pt = pt or style.base_pt
    try:
        text = _fit(text, shape.width / 360000 - 0.3, shape.height / 360000 - 0.16, size_pt)
    except (TypeError, ZeroDivisionError):
        pass
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.font.size = Pt(pt or style.base_pt)
        p.font.bold = bold
        p.font.name = style.heading_font if heading else style.font
        p.font.color.rgb = _rgb(color or style.text)


def rect(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str = "",
    *,
    style: ShapeStyle,
    fill: str | None = None,
    line: str | None = None,
    shape: MSO_SHAPE = MSO_SHAPE.ROUNDED_RECTANGLE,
    pt: float | None = None,
    bold: bool = False,
    color: str | None = None,
    align: PP_ALIGN = PP_ALIGN.CENTER,
    anchor: MSO_ANCHOR = MSO_ANCHOR.MIDDLE,
    heading: bool = False,
) -> Any:
    sh = slide.shapes.add_shape(shape, Cm(left), Cm(top), Cm(max(width, 0.2)), Cm(max(height, 0.2)))
    if fill:
        sh.fill.solid()
        sh.fill.fore_color.rgb = _rgb(fill)
    else:
        sh.fill.background()
    if line:
        sh.line.color.rgb = _rgb(line)
        sh.line.width = Pt(0.75)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    if text:
        _set_text(
            sh,
            text,
            style=style,
            pt=pt,
            bold=bold,
            color=color,
            align=align,
            anchor=anchor,
            heading=heading,
        )
    return sh


def label(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    *,
    style: ShapeStyle,
    pt: float | None = None,
    bold: bool = False,
    color: str | None = None,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
    heading: bool = False,
) -> Any:
    box = slide.shapes.add_textbox(Cm(left), Cm(top), Cm(max(width, 0.2)), Cm(max(height, 0.2)))
    _set_text(
        box,
        text,
        style=style,
        pt=pt,
        bold=bold,
        color=color,
        align=align,
        anchor=anchor,
        heading=heading,
    )
    return box


def arrow(
    slide: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    style: ShapeStyle,
    text: str = "",
    color: str | None = None,
    width_pt: float = 1.25,
    label_w: float = 3.0,
) -> Any:
    """직선 연결선(끝 화살표). 라벨은 선 중앙 위의 작은 텍스트 상자(``label_w`` cm, 흰 바탕)."""
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(x1), Cm(y1), Cm(x2), Cm(y2))
    conn.line.color.rgb = _rgb(color or style.accent)
    conn.line.width = Pt(width_pt)
    ln = conn.line._get_or_add_ln()  # noqa: SLF001 - 화살촉은 python-pptx 공개 API 없음
    tail = OxmlElement("a:tailEnd")
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")
    ln.append(tail)
    if text:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        lab = label(
            slide,
            mx - label_w / 2,
            my - 0.85,
            label_w,
            0.8,
            text[:24],
            style=style,
            pt=max(style.base_pt - 2, 7),
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            color=style.primary,
        )
        lab.fill.solid()
        lab.fill.fore_color.rgb = _rgb("FFFFFF")
        lab.text_frame.margin_left = lab.text_frame.margin_right = Cm(0.05)
    return conn


# --- 도식 -------------------------------------------------------------------------------------
def _grid(
    n: int, box: Box, *, max_cols: int = 4, gap: float = 0.4
) -> list[tuple[float, float, float, float]]:
    """n개 항목을 영역 안에 격자로 배치한 (left, top, w, h) 목록."""
    if n <= 0:
        return []
    cols = min(max_cols, n)
    rows = -(-n // cols)
    w = (box.width - gap * (cols - 1)) / cols
    h = (box.height - gap * (rows - 1)) / rows
    cells = []
    for i in range(n):
        r, c = divmod(i, cols)
        cells.append((box.left + c * (w + gap), box.top + r * (h + gap), w, h))
    return cells


def group(slide: Any, name: str = "") -> Any:
    """그룹 도형(Phase 20). 돌려준 그룹을 ``rect``/``label``/``arrow``의 첫 인자로 넘기면 그 안에 그려지고,
    PowerPoint에서 '그룹 해제'로 개별 도형으로 되돌릴 수 있다. 표·차트·그림은 그룹에 넣을 수 없다."""
    g = slide.shapes.add_group_shape()
    if name:
        g.name = name[:60]
    return g
