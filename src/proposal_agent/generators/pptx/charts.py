"""네이티브 차트 (Phase 20).

PowerPoint에서 데이터·계열·색을 직접 고칠 수 있도록 python-pptx ``add_chart``(실제 차트 객체)로 그린다.
도형 막대(``shapes.draw_bars``)·도형 일정 축(``shapes.draw_timeline``)은 발표용처럼 자유 배치가 필요한 곳에 남긴다.

- ``add_category_chart``: 막대·세로 막대·누적·선·원 (공수·통계·비교)
- ``add_gantt_chart``: 누적 가로 막대로 만든 간트 (첫 계열 = 착수일 기준 시작 offset, 투명)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Cm, Pt

from proposal_agent.generators.pptx.template import Box

CHART_TYPES: dict[str, XL_CHART_TYPE] = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "stacked_bar": XL_CHART_TYPE.BAR_STACKED,
    "stacked_column": XL_CHART_TYPE.COLUMN_STACKED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
}
SERIES_COLORS = ("1F4E78", "5B9BD5", "A5A5A5", "FFC000", "70AD47", "ED7D31")


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.lstrip("#")[:6])


def parse_number(value: Any) -> float | None:
    """'1,234' · '12.5 MM' · 7 → 숫자. 숫자가 없으면 None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").replace(",", "").strip()
    num = ""
    for ch in text:
        if ch.isdigit() or ch in ".-":
            num += ch
        elif num:
            break
    try:
        return float(num) if num not in ("", "-", ".") else None
    except ValueError:
        return None


def add_category_chart(
    slide: Any,
    box: Box,
    categories: list[str],
    series: list[tuple[str, list[float]]],
    *,
    style: Any,
    chart_type: str = "bar",
    title: str = "",
    number_format: str = "0.##",
    legend: bool | None = None,
    data_labels: bool = True,
) -> Any:
    """범주형 네이티브 차트. 돌려주는 값은 GraphicFrame(차트 도형)."""
    categories = [str(c)[:30] for c in categories][:40]
    if not categories or not series:
        return None
    xl_type = CHART_TYPES.get(chart_type, XL_CHART_TYPE.BAR_CLUSTERED)
    data = CategoryChartData()
    data.categories = categories
    for name, values in series[:6]:
        vals = list(values)[: len(categories)] + [0.0] * max(0, len(categories) - len(values))
        data.add_series(str(name)[:30], vals, number_format=number_format)
    frame = slide.shapes.add_chart(
        xl_type, Cm(box.left), Cm(box.top), Cm(box.width), Cm(box.height), data
    )
    chart = frame.chart
    base_pt = float(getattr(style, "base_pt", 10.0))
    font = str(getattr(style, "font", "맑은 고딕"))
    chart.font.name = font
    chart.font.size = Pt(max(base_pt - 1, 7))
    chart.has_title = bool(title)
    if title:
        chart.chart_title.text_frame.text = title[:60]
        tp = chart.chart_title.text_frame.paragraphs[0]
        tp.font.size = Pt(base_pt + 1)
        tp.font.bold = True
        tp.font.name = font
    multi = len(series) > 1 or xl_type in (XL_CHART_TYPE.PIE, XL_CHART_TYPE.DOUGHNUT)
    chart.has_legend = multi if legend is None else legend
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(max(base_pt - 1, 7))
    plot = chart.plots[0]
    if xl_type in (XL_CHART_TYPE.PIE, XL_CHART_TYPE.DOUGHNUT):
        plot.vary_by_categories = True
        points = plot.series[0].points
        for i in range(len(categories)):
            points[i].format.fill.solid()
            points[i].format.fill.fore_color.rgb = _rgb(SERIES_COLORS[i % len(SERIES_COLORS)])
    else:
        plot.vary_by_categories = False
        try:
            plot.gap_width = 60
        except (AttributeError, ValueError):
            pass
        colors = (
            str(getattr(style, "primary", SERIES_COLORS[0])),
            str(getattr(style, "accent", SERIES_COLORS[1])),
            *SERIES_COLORS[2:],
        )
        for i, s in enumerate(plot.series):
            if xl_type == XL_CHART_TYPE.LINE_MARKERS:
                s.format.line.color.rgb = _rgb(colors[i % len(colors)])
                s.format.line.width = Pt(2)
            else:
                s.format.fill.solid()
                s.format.fill.fore_color.rgb = _rgb(colors[i % len(colors)])
        chart.value_axis.has_major_gridlines = True
        chart.value_axis.major_gridlines.format.line.color.rgb = _rgb("D9D9D9")
        chart.value_axis.tick_labels.font.size = Pt(max(base_pt - 2, 7))
        chart.category_axis.tick_labels.font.size = Pt(max(base_pt - 1, 7))
        chart.value_axis.tick_labels.number_format = number_format
        chart.value_axis.tick_labels.number_format_is_linked = False
    if data_labels:
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.font.size = Pt(max(base_pt - 2, 7))
        dl.number_format = number_format
        dl.number_format_is_linked = False
        if xl_type in (XL_CHART_TYPE.PIE, XL_CHART_TYPE.DOUGHNUT):
            dl.show_category_name = True
            dl.show_percentage = False
        dl.show_value = True
    frame.name = f"차트: {title or chart_type}"[:60]
    return frame


def add_gantt_chart(
    slide: Any,
    box: Box,
    items: list[tuple[str, date | None, date | None]],
    period_start: date | None,
    period_end: date | None,
    *,
    style: Any,
    title: str = "",
) -> Any:
    """누적 가로 막대 간트(네이티브 차트). 값 축은 착수일 기준 경과 일수, 라벨은 기간(일)."""
    dated = [(n, s, e) for n, s, e in items if s and e and e >= s][:20]
    if not dated or not period_start or not period_end or period_end <= period_start:
        return None
    total_days = max((period_end - period_start).days, 1)
    names = [str(n)[:28] for n, _s, _e in dated]
    offsets = [float(max((s - period_start).days, 0)) for _n, s, _e in dated]
    durations = [float(max((e - s).days + 1, 1)) for _n, s, e in dated]
    data = CategoryChartData()
    data.categories = names
    data.add_series("시작(착수 후 일수)", offsets, number_format="0")
    data.add_series("기간(일)", durations, number_format="0")
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_STACKED,
        Cm(box.left),
        Cm(box.top),
        Cm(box.width),
        Cm(box.height),
        data,
    )
    chart = frame.chart
    base_pt = float(getattr(style, "base_pt", 10.0))
    font = str(getattr(style, "font", "맑은 고딕"))
    chart.font.name = font
    chart.font.size = Pt(max(base_pt - 1, 7))
    chart.has_legend = False
    chart.has_title = bool(title)
    if title:
        chart.chart_title.text_frame.text = title[:60]
        chart.chart_title.text_frame.paragraphs[0].font.size = Pt(base_pt + 1)
    plot = chart.plots[0]
    plot.gap_width = 40
    plot.overlap = 100
    offset_series, bar_series = plot.series[0], plot.series[1]
    offset_series.format.fill.background()  # 시작 offset 은 보이지 않는 막대
    offset_series.format.line.fill.background()
    bar_series.format.fill.solid()
    bar_series.format.fill.fore_color.rgb = _rgb(str(getattr(style, "accent", "5B9BD5")))
    bar_series.has_data_labels = True
    dl = bar_series.data_labels
    dl.show_value = True
    dl.number_format = '0"일"'
    dl.number_format_is_linked = False
    dl.font.size = Pt(max(base_pt - 2, 7))
    cat = chart.category_axis
    cat.reverse_order = True  # 첫 작업이 맨 위
    cat.tick_labels.font.size = Pt(max(base_pt - 1, 7))
    val = chart.value_axis
    val.minimum_scale = 0
    val.maximum_scale = float(total_days)
    val.major_unit = float(max(7, round(total_days / 8 / 7) * 7))
    val.has_major_gridlines = True
    val.major_gridlines.format.line.color.rgb = _rgb("D9D9D9")
    val.tick_labels.font.size = Pt(max(base_pt - 2, 7))
    val.tick_labels.number_format = '0"일"'
    val.tick_labels.number_format_is_linked = False
    val.has_title = True
    val.axis_title.text_frame.text = f"착수({period_start}) 기준 경과 일수 · 종료 {period_end}"
    val.axis_title.text_frame.paragraphs[0].font.size = Pt(max(base_pt - 2, 7))
    frame.name = f"차트: {title or '일정(간트)'}"[:60]
    return frame


def chart_from_spec(slide: Any, box: Box, spec: dict[str, Any], *, style: Any) -> Any:
    """VisualSpec(kind=chart): headers=[범주 이름, 계열1, 계열2…], rows=[[범주, 값1, 값2…]], chart_type."""
    headers = [str(h) for h in spec.get("headers", []) or []]
    rows = [list(r) for r in spec.get("rows", []) or []]
    if not rows:
        return None
    n_series = max(len(r) for r in rows) - 1
    if n_series < 1:
        return None
    categories = [str(r[0]) for r in rows]
    series: list[tuple[str, list[float]]] = []
    for si in range(1, n_series + 1):
        name = headers[si] if si < len(headers) else f"계열 {si}"
        values = [parse_number(r[si]) if si < len(r) else None for r in rows]
        series.append((name, [v if v is not None else 0.0 for v in values]))
    return add_category_chart(
        slide,
        box,
        categories,
        series,
        style=style,
        chart_type=str(spec.get("chart_type", "") or "column"),
        title=str(spec.get("title", "") or ""),
    )


__all__ = [
    "CHART_TYPES",
    "add_category_chart",
    "add_gantt_chart",
    "chart_from_spec",
    "parse_number",
]
