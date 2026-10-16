"""제안서 템플릿(PPTX) 프로파일과 템플릿 기반 슬라이드 빌더 (Phase 12).

고객사마다 제안서 양식이 다르므로 샘플의 값을 하드코딩하지 않는다. 제안 때마다 업로드한 템플릿 PPTX에서
코드가 다음을 읽어 ``TemplateProfile``로 만들고, ``TemplateDeckBuilder``가 그 파일의 마스터·레이아웃 위에
새 슬라이드를 그린다.

- 용지 크기·방향, 레이아웃 목록, 장 표지 레이아웃과 본문 레이아웃
- 본문 슬라이드에서 같은 위치에 반복되는 상단 텍스트 상자(머리글 1단 "N. 절", 2단 "N.M 소절")의 좌표·글꼴
- 머리글 아래 반복되는 넓은 도형(리드 메시지 상자), 본문 영역, 하단 주석 위치
- 글꼴·크기·색, 표 머리글 채움색, 장·절·소절 구성(샘플 내용), 쪽번호 패턴
- 작성 관행(리드 문장, "(계속)", RFP ID 카드, 표 유형)을 에이전트에게 전달할 문장 목록

인식은 휴리스틱이며 찾지 못한 항목은 기본값을 쓰고 ``warnings``에 남긴다.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Emu, Pt
from pydantic import BaseModel, ConfigDict, Field

from proposal_agent.generators.base import picture_name

ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
ROMAN_RE = re.compile(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]{1,4})\s*[.．]?\s*(?P<title>.*)$")
SECTION_RE = re.compile(r"^\s*(?P<no>\d{1,2})\s*(?P<sep>[.．/])\s*(?P<title>[^>]{1,60})")
FRACTION_RE = re.compile(r"\s*[(（]\s*\d{1,2}\s*/\s*\d{1,2}\s*[)）]\s*$")
SUBSECTION_RE = re.compile(
    r"^\s*(?P<no>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s*[.．]?\s*(?P<title>.{1,60})"
)
CONTINUED_RE = re.compile(r"\s*[(（]\s*계속\s*[)）]\s*$")
RFP_ID_RE = re.compile(r"(?<![A-Za-z])[A-Z]{2,5}-\d{2,4}(?!\d)")
PAGE_FIELD = "‹#›"


def _cm(v: int | None) -> float:
    return round(Emu(v).cm, 2) if v is not None else 0.0


class Box(BaseModel):
    """슬라이드 위 사각 영역과 그 안의 글꼴 (cm, pt)."""

    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    width: float
    height: float
    font_name: str | None = None
    font_size: float | None = None
    bold: bool | None = None
    color: str | None = Field(default=None, description="RRGGBB")

    @property
    def bottom(self) -> float:
        return self.top + self.height


class TemplateChapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numeral: str = ""
    title: str = ""
    sections: list[str] = Field(default_factory=list, description="'N. 절' 제목")
    subsections: list[str] = Field(default_factory=list, description="'N.M 소절' 제목")
    layout: str | None = Field(default=None, description="이 장의 본문 레이아웃 이름")


class TemplateProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str = ""
    document_id: str | None = None
    purpose: str = Field(default="submission", description="submission | presentation")
    slide_width_cm: float
    slide_height_cm: float
    slide_count: int = 0
    layouts: list[str] = Field(default_factory=list)
    content_layout: str | None = None
    chapter_layout: str | None = None
    headers: list[Box] = Field(default_factory=list, description="머리글 상자 (위→아래)")
    lead: Box | None = Field(default=None, description="리드 메시지 상자")
    body: Box
    footnote: Box | None = None
    chapter_title_box: Box | None = None
    chapter_numeral_box: Box | None = None
    chapter_list_box: Box | None = None
    chapter_label_boxes: list[Box] = Field(
        default_factory=list, description="레이아웃에 고정된 장 이름·로마숫자 상자"
    )
    band_color: str | None = None
    page_number_pattern: str | None = None
    section_format: str = Field(
        default="{no}. {title}",
        description="머리글 절 번호 표기 (예: '{no}. {title}' 또는 '{no:02d}/ {title}')",
    )
    continued_format: str = Field(
        default="(계속)", description="같은 절 분할 표기: '(계속)' 또는 '({i}/{n})'"
    )
    fonts: dict[str, str] = Field(default_factory=dict, description="title/body")
    font_sizes: dict[str, float] = Field(default_factory=dict)
    colors: dict[str, str] = Field(default_factory=dict, description="primary/accent/lead")
    table_style: dict[str, Any] = Field(default_factory=dict)
    chapters: list[TemplateChapter] = Field(default_factory=list)
    table_patterns: list[str] = Field(default_factory=list, description="관찰된 표 머리글 행")
    uses_rfp_ids: bool = False
    has_notes: bool = False
    conventions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def orientation(self) -> str:
        return "portrait" if self.slide_height_cm > self.slide_width_cm else "landscape"

    @property
    def body_font(self) -> str:
        return self.fonts.get("body", "맑은 고딕")

    @property
    def title_font(self) -> str:
        return self.fonts.get("title", self.body_font)

    def size(self, key: str, default: float) -> float:
        return float(self.font_sizes.get(key, default))

    def summary_text(self) -> str:
        """에이전트·UI용 요약."""
        parts = [
            f"용지: {self.slide_width_cm}×{self.slide_height_cm} cm "
            f"({'세로' if self.orientation == 'portrait' else '가로'}), "
            f"샘플 {self.slide_count}장, 용도 {self.purpose}",
        ]
        if self.headers:
            hs = " / ".join(
                f"{i + 1}단 top {h.top}cm {h.font_size or '?'}pt"
                for i, h in enumerate(self.headers)
            )
            parts.append(f"머리글 {len(self.headers)}단: {hs}")
        if self.chapters:
            for ch in self.chapters[:8]:
                label = f"{ch.numeral} {ch.title}".strip()
                parts.append(
                    f"장 {label or '(이름 없음)'}: "
                    + (" / ".join(ch.sections[:8]) if ch.sections else "절 없음")
                    + (f" ; 소절 예 {', '.join(ch.subsections[:4])}" if ch.subsections else "")
                )
        if self.table_patterns:
            parts.append("표 유형: " + " ; ".join(self.table_patterns[:6]))
        parts.extend(self.conventions)
        return "\n".join(parts)


# --- 프로파일링 -----------------------------------------------------------------------------------


def _run_style(shape: Any) -> tuple[str | None, float | None, bool | None, str | None]:
    """첫 번째 비어 있지 않은 run의 (글꼴, 크기, 굵게, 색)."""
    if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
        return None, None, None, None
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            if not r.text.strip():
                continue
            color = None
            try:
                if r.font.color is not None and r.font.color.type is not None:
                    rgb = r.font.color.rgb if r.font.color.type == 1 else None
                    color = str(rgb) if rgb is not None else None
            except Exception:  # noqa: BLE001 - 테마색 등 읽기 실패는 무시
                color = None
            return r.font.name, (r.font.size.pt if r.font.size else None), r.font.bold, color
    return None, None, None, None


def _iter_text_shapes(shapes: Any, *, depth: int = 0) -> list[Any]:
    """그룹 안까지 내려가며 텍스트가 있는 도형을 모은다 (그룹은 좌표가 절대값)."""
    out: list[Any] = []
    for sh in shapes:
        if getattr(sh, "shape_type", None) is not None and "GROUP" in str(sh.shape_type):
            if depth < 3:
                out.extend(_iter_text_shapes(sh.shapes, depth=depth + 1))
            continue
        if (
            getattr(sh, "has_text_frame", False)
            and sh.has_text_frame
            and sh.text_frame.text.strip()
        ):
            out.append(sh)
    return out


def _all_runs(shapes: Any) -> list[Any]:
    runs: list[Any] = []
    for sh in _iter_text_shapes(shapes):
        for p in sh.text_frame.paragraphs:
            runs.extend(r for r in p.runs if r.text.strip())
    return runs


def _box_from(shape: Any) -> Box:
    name, size, bold, color = _run_style(shape)
    return Box(
        left=_cm(shape.left),
        top=_cm(shape.top),
        width=_cm(shape.width),
        height=_cm(shape.height),
        font_name=name,
        font_size=size,
        bold=bold,
        color=color,
    )


def _near(a: tuple[float, float, float], b: tuple[float, float, float]) -> bool:
    """(top, left, width) cm 가 머리글로 볼 만큼 가까운가 (±0.45 / ±1.0 cm). 폭은 제목 길이에 따라
    자동 맞춤되는 양식(발표용)이 있어 크게 허용한다(±12 cm)."""
    return abs(a[0] - b[0]) <= 0.45 and abs(a[1] - b[1]) <= 1.0 and abs(a[2] - b[2]) <= 12.0


def _geom(shape: Any) -> tuple[float, float, float]:
    return (_cm(shape.top), _cm(shape.left), _cm(shape.width))


def _norm_title(text: str) -> str:
    return re.sub(r"[\s.．]", "", text)


def _strip_no(text: str) -> str:
    """'01/ 제목', '1. 제목', '1.1 제목' 의 번호를 뗀다."""
    return re.sub(r"^\s*\d{1,2}(\.\d{1,2})*\s*[.．/]?\s*", "", text).strip()


def _solid_fill_hex(shape: Any) -> str | None:
    try:
        if shape.fill.type == 1:  # MSO_FILL.SOLID
            return str(shape.fill.fore_color.rgb)
    except Exception:  # noqa: BLE001
        return None
    return None


def profile_template(
    data: bytes, *, purpose: str | None = None, file_name: str = "", document_id: str | None = None
) -> TemplateProfile:
    prs = Presentation(io.BytesIO(data))
    w_cm, h_cm = _cm(prs.slide_width), _cm(prs.slide_height)
    warnings: list[str] = []
    slides = list(prs.slides)
    layouts = [lo.name for m in prs.slide_masters for lo in m.slide_layouts]
    if purpose is None:
        purpose = "submission" if h_cm > w_cm else "presentation"

    # 1) 슬라이드별 상단 텍스트 상자 → 반복 좌표가 머리글
    top_limit = h_cm * 0.3
    per_slide: list[list[Any]] = [
        [s for s in _iter_text_shapes(sl.shapes) if _cm(s.top) < top_limit] for sl in slides
    ]
    clusters: list[tuple[tuple[float, float, float], list[Any]]] = []
    for shapes in per_slide:
        seen: set[int] = set()
        for s in shapes:
            g = _geom(s)
            if g[2] < w_cm * 0.15:
                continue  # 발표형은 제목 길이에 따라 폭이 달라 좁은 머리글도 있다
            for ci, (center, members) in enumerate(clusters):
                if _near(center, g) and ci not in seen:
                    members.append(s)
                    seen.add(ci)
                    break
            else:
                clusters.append((g, [s]))
                seen.add(len(clusters) - 1)
    threshold = max(2, int(len(slides) * 0.5))

    def numbered_ratio(members: list[Any]) -> float:
        hits = sum(
            1
            for m in members
            if SECTION_RE.match(m.text_frame.text.strip())
            or SUBSECTION_RE.match(m.text_frame.text.strip())
        )
        return hits / max(len(members), 1)

    ranked = sorted([(c, m) for c, m in clusters if len(m) >= threshold], key=lambda cm_: cm_[0][0])
    header_clusters = ranked[:1]
    # 2단 머리글은 '절.소절 제목'처럼 번호가 붙은 텍스트가 절반 이상일 때만 (큰따옴표 리드 문장은 머리글이 아니다)
    for cand in ranked[1:3]:
        if numbered_ratio(cand[1]) >= 0.5:
            header_clusters.append(cand)
            break
    header_keys = [c for c, _m in header_clusters]
    headers: list[Box] = []
    for _key, samples in header_clusters:
        styles = Counter(_run_style(s)[:2] for s in samples)
        (fname, fsize), _ = styles.most_common(1)[0]
        hdr_colors = Counter(c for c in (_run_style(s)[3] for s in samples) if c)
        headers.append(
            Box(
                left=round(sum(_cm(s.left) for s in samples) / len(samples), 2),
                top=round(sum(_cm(s.top) for s in samples) / len(samples), 2),
                width=round(max(_cm(s.width) for s in samples), 2),
                height=round(max(_cm(s.height) for s in samples), 2),
                font_name=fname,
                font_size=fsize,
                bold=True,
                color=hdr_colors.most_common(1)[0][0] if hdr_colors else None,
            )
        )

    def has_headers(shapes: list[Any]) -> bool:
        return bool(header_keys) and any(_near(k, _geom(s)) for s in shapes for k in header_keys)

    def looks_like_chapter(i: int) -> bool:
        shapes = _iter_text_shapes(slides[i].shapes)
        # 장 표지 = 로마숫자 단독 상자 또는 'CHAPTER' 라벨이 있는 슬라이드 (큰 글꼴만으로는 판정하지 않는다: 인용부호·표지 제외)
        numerals = {
            s.text_frame.text.strip()
            for s in shapes
            if re.fullmatch(rf"[{ROMAN}]+", s.text_frame.text.strip())
        }
        chapter_label = any(s.text_frame.text.strip().upper() == "CHAPTER" for s in shapes)
        agenda = any(
            s.text_frame.text.strip().upper() in ("CONTENTS", "목차", "AGENDA") for s in shapes
        )
        # 로마숫자가 여러 개면 목차(CONTENTS) 슬라이드다
        return (len(numerals) == 1 or chapter_label) and not agenda and len(numerals) <= 1

    content_idx = [i for i, shapes in enumerate(per_slide) if has_headers(shapes)]
    chapter_idx = [i for i in range(len(slides)) if i not in content_idx and looks_like_chapter(i)]
    other_idx = [i for i in range(len(slides)) if i not in content_idx and i not in chapter_idx]
    content_layout = (
        Counter(slides[i].slide_layout.name for i in content_idx).most_common(1)[0][0]
        if content_idx
        else (layouts[0] if layouts else None)
    )
    chapter_layout = None
    if chapter_idx:
        cands = Counter(
            slides[i].slide_layout.name
            for i in chapter_idx
            if slides[i].slide_layout.name != content_layout
        )
        chapter_layout = cands.most_common(1)[0][0] if cands else None
    if not headers:
        warnings.append("반복되는 머리글 상자를 찾지 못해 기본 머리글 배치를 사용합니다.")

    # 2) 본문 영역: 머리글 아래 ~ 하단 고정 요소 위
    header_bottom = max((h.bottom for h in headers), default=h_cm * 0.12)
    bottom_static = h_cm - 1.2
    page_pattern: str | None = None
    chapter_label_boxes: list[Box] = []
    band_color: str | None = None
    layout_obj = next(
        (lo for m in prs.slide_masters for lo in m.slide_layouts if lo.name == content_layout), None
    )
    if layout_obj is not None:
        for sh in layout_obj.shapes:
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                text = sh.text_frame.text.strip()
                if PAGE_FIELD in text:
                    page_pattern = text
                    bottom_static = min(bottom_static, _cm(sh.top) - 0.2)
                elif text and _cm(sh.top) < h_cm * 0.15 and not sh.is_placeholder:
                    chapter_label_boxes.append(
                        _box_from(sh)
                    )  # 자리표시자('마스터 제목 스타일 편집')는 제외
        for sh in layout_obj.slide_master.shapes:
            if _cm(sh.top) > h_cm * 0.8:
                bottom_static = min(bottom_static, _cm(sh.top) - 0.2)
            if chapter_label_boxes and _solid_fill_hex(sh):
                lb = chapter_label_boxes[0]
                if _cm(sh.top) <= lb.top and _cm(sh.top) + _cm(sh.height) >= lb.bottom:
                    band_color = _solid_fill_hex(sh)
    body_left = headers[0].left if headers else round(w_cm * 0.08, 2)
    body_width = max((h.width for h in headers), default=round(w_cm * 0.84, 2))
    body = Box(
        left=body_left,
        top=round(header_bottom + 0.3, 2),
        width=body_width,
        height=round(max(bottom_static - header_bottom - 0.6, 3.0), 2),
    )

    # 3) 리드 상자: 머리글 바로 아래 넓은 도형이 본문 슬라이드의 30% 이상에서 반복
    lead: Box | None = None
    lead_samples: list[Any] = []
    for i in content_idx:
        for s in _iter_text_shapes(slides[i].shapes):
            t = _cm(s.top)
            if header_bottom - 0.2 <= t <= header_bottom + 2.0 and _cm(s.width) >= body_width * 0.6:
                lead_samples.append(s)
                break
    if content_idx and len(lead_samples) >= max(1, int(len(content_idx) * 0.3)):
        sizes = Counter(_run_style(s)[1] for s in lead_samples if _run_style(s)[1])
        lead = Box(
            left=round(min(_cm(s.left) for s in lead_samples), 2),
            top=round(sum(_cm(s.top) for s in lead_samples) / len(lead_samples), 2),
            width=round(max(_cm(s.width) for s in lead_samples), 2),
            height=round(sum(_cm(s.height) for s in lead_samples) / len(lead_samples), 2),
            font_name=_run_style(lead_samples[0])[0],
            font_size=sizes.most_common(1)[0][0] if sizes else None,
            bold=True,
        )

    # 4) 하단 주석(※) 상자
    foot_samples = [
        s
        for i in content_idx
        for s in _iter_text_shapes(slides[i].shapes)
        if s.text_frame.text.strip().startswith("※") and _cm(s.top) > h_cm * 0.8
    ]
    footnote = (
        Box(
            left=round(min(_cm(s.left) for s in foot_samples), 2),
            top=round(min(_cm(s.top) for s in foot_samples), 2),
            width=round(max(_cm(s.width) for s in foot_samples), 2),
            height=round(max(_cm(s.height) for s in foot_samples), 2),
            font_name=_run_style(foot_samples[0])[0],
            font_size=_run_style(foot_samples[0])[1],
        )
        if foot_samples
        else None
    )

    # 5) 글꼴·크기·색
    all_runs = [r for sl in slides for r in _all_runs(sl.shapes)]
    font_names = Counter(r.font.name for r in all_runs if r.font.name)
    header_fonts = Counter(h.font_name for h in headers if h.font_name)
    title_font = header_fonts.most_common(1)[0][0] if header_fonts else None
    body_candidates = Counter(
        r.font.name for r in all_runs if r.font.name and r.font.size and r.font.size.pt <= 12
    )
    body_font = (
        (body_candidates or font_names).most_common(1)[0][0]
        if (body_candidates or font_names)
        else "맑은 고딕"
    )
    fonts = {"body": body_font, "title": title_font or body_font}
    body_sizes = Counter(
        r.font.size.pt
        for r in all_runs
        if r.font.size and 7 <= r.font.size.pt <= 14 and (r.font.bold is not True)
    )
    body_size = body_sizes.most_common(1)[0][0] if body_sizes else (10.0 if h_cm > w_cm else 16.0)
    font_sizes: dict[str, float] = {"body": float(body_size)}
    for i, h in enumerate(headers):
        if h.font_size:
            font_sizes["section" if i == 0 else "subsection"] = float(h.font_size)
    if lead and lead.font_size:
        font_sizes["lead"] = float(lead.font_size)
    # 장 표지 요소
    chapter_title_box = chapter_numeral_box = chapter_list_box = None
    colors: dict[str, str] = {}
    for i in chapter_idx:
        shapes = _iter_text_shapes(slides[i].shapes)
        for s in shapes:
            text = s.text_frame.text.strip()
            name, size, _bold, color = _run_style(s)
            if re.fullmatch(rf"[{ROMAN}]+", text) and chapter_numeral_box is None:
                chapter_numeral_box = _box_from(s)
            elif (
                size
                and size >= 24
                and chapter_title_box is None
                and not re.fullmatch(rf"[{ROMAN}]+", text)
            ):
                chapter_title_box = _box_from(s)
                if color:
                    colors["primary"] = color
                if size:
                    font_sizes["chapter"] = float(size)
            elif (
                "\n" in text
                and len([ln for ln in text.splitlines() if re.search(r"[가-힣A-Za-z]", ln)]) >= 2
                and (chapter_list_box is None or _cm(s.width) > chapter_list_box.width)
            ):
                # 절 목록 상자: 글자가 있는 줄이 2개 이상인 상자 중 가장 넓은 것 (번호만 있는 '01/02' 상자 제외)
                chapter_list_box = _box_from(s)
        if chapter_title_box is not None:
            break
    if "primary" not in colors:
        hc = next((h.color for h in headers if h.color), None)
        colors["primary"] = hc or "1F4E78"
    lead_color_values = [c for c in (_run_style(s)[3] for s in lead_samples) if c]
    if lead_color_values:
        colors["lead"] = Counter(lead_color_values).most_common(1)[0][0]
    if band_color:
        colors["band"] = band_color

    # 6) 표 서식·유형
    table_style: dict[str, Any] = {}
    table_patterns: list[str] = []
    table_sizes: Counter[float] = Counter()
    for sl in slides:
        for sh in sl.shapes:
            if not (getattr(sh, "has_table", False) and sh.has_table):
                continue
            tbl = sh.table
            header_cells = [
                c.text.strip().splitlines()[0].strip() if c.text.strip() else ""
                for c in tbl.rows[0].cells
            ]
            if sum(1 for c in header_cells if c) >= 2 and len(table_patterns) < 12:
                pat = " | ".join(c[:12] for c in header_cells if c)
                if pat not in table_patterns:
                    table_patterns.append(pat)
            if "header_fill" not in table_style:
                try:
                    cell = tbl.cell(0, 0)
                    if cell.fill.type == 1:
                        table_style["header_fill"] = str(cell.fill.fore_color.rgb)
                except Exception:  # noqa: BLE001
                    pass
            for row in list(tbl.rows)[:3]:
                for c in row.cells:
                    for p in c.text_frame.paragraphs:
                        for r in p.runs:
                            if r.font.size:
                                table_sizes[r.font.size.pt] += 1
    if table_sizes:
        table_style["font_size"] = table_sizes.most_common(1)[0][0]
    table_style.setdefault("font_size", max(body_size - 1, 7))
    table_style.setdefault("header_fill", colors["primary"])

    # 7) 장·절·소절 구성 (샘플 내용에서)
    chapters: list[TemplateChapter] = []
    current: TemplateChapter | None = None
    layout_numeral: dict[str, str] = {}
    section_format = "{no}. {title}"
    continued_format = "(계속)"
    for m in prs.slide_masters:
        for lo in m.slide_layouts:
            for sh in lo.shapes:
                if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                    mnum = re.search(rf"[{ROMAN}]+", sh.text_frame.text)
                    if mnum and lo.name not in layout_numeral:
                        layout_numeral[lo.name] = mnum.group(0)
    for i, sl in enumerate(slides):
        if i in other_idx:
            continue
        shapes = sorted(_iter_text_shapes(sl.shapes), key=lambda s: (_cm(s.top), _cm(s.left)))
        if i in chapter_idx:
            numeral = next(
                (
                    s.text_frame.text.strip()
                    for s in shapes
                    if re.fullmatch(rf"[{ROMAN}]+", s.text_frame.text.strip())
                ),
                "",
            )
            title = ""
            best = 0.0
            for s in shapes:
                _n, size, _b, _c = _run_style(s)
                text = s.text_frame.text.strip()
                if (
                    size
                    and size > best
                    and not re.fullmatch(rf"[{ROMAN}]+", text)
                    and text.upper() != "CHAPTER"
                    and re.search(r"[가-힣A-Za-z0-9]", text)
                    and len(text.replace("\n", " ")) <= 30
                ):
                    best, title = size, " ".join(text.split())
            sections = [
                ln.strip()
                for s in shapes
                for ln in s.text_frame.text.splitlines()
                if SECTION_RE.match(ln.strip()) and "\n" in s.text_frame.text
            ]
            if not sections:
                # 번호 없는 절 목록 (번호는 별도 상자 "01 / 02 …"): 줄 2개 이상, 각 줄 40자 이하, 숫자만인 줄 제외
                list_cands = [
                    [ln.strip() for ln in s.text_frame.text.splitlines() if ln.strip()]
                    for s in shapes
                    if "\n" in s.text_frame.text
                ]
                list_cands = [
                    c
                    for c in list_cands
                    if len(c) >= 2
                    and all(len(x) <= 40 and not re.fullmatch(r"[\d/ .]+", x) for x in c)
                ]
                if list_cands:
                    sections = max(list_cands, key=len)
            current = TemplateChapter(numeral=numeral, title=title[:60], sections=sections[:12])
            chapters.append(current)
            continue
        if current is None:
            current = TemplateChapter(layout=sl.slide_layout.name)
            chapters.append(current)
        if current.layout is None:
            current.layout = sl.slide_layout.name
        if not current.numeral:
            current.numeral = layout_numeral.get(sl.slide_layout.name, "")
        texts = [s.text_frame.text.strip() for s in shapes[:2]]
        for t in texts:
            if FRACTION_RE.search(t):
                continued_format = "({i}/{n})"
            head = t.split(">")[0].strip()
            msub = SUBSECTION_RE.match(t)
            msec = SECTION_RE.match(head)
            if msec and msec.group("sep") == "/" and section_format == "{no}. {title}":
                section_format = "{no:02d}/ {title}"
            if msub:
                sub = FRACTION_RE.sub("", CONTINUED_RE.sub("", t)).strip()
                if _norm_title(sub) not in {_norm_title(x) for x in current.subsections}:
                    current.subsections.append(sub[:60])
            elif msec:
                numbers = {
                    m.group("no") for m in (SECTION_RE.match(x) for x in current.sections) if m
                }
                clean = FRACTION_RE.sub("", CONTINUED_RE.sub("", head)).strip()
                known = {_norm_title(_strip_no(x)) for x in current.sections}
                if msec.group("no") not in numbers and _norm_title(_strip_no(clean)) not in known:
                    current.sections.append(clean[:60])
    chapters = [c for c in chapters if c.sections or c.subsections or c.title]
    for c in chapters:
        c.subsections = c.subsections[:30]

    uses_rfp_ids = any(RFP_ID_RE.search(r.text) for r in all_runs)
    has_notes = any(
        sl.has_notes_slide and sl.notes_slide.notes_text_frame.text.strip() for sl in slides
    )
    conventions = _conventions(
        headers=headers,
        lead=lead,
        footnote=footnote,
        page_pattern=page_pattern,
        fonts=fonts,
        font_sizes=font_sizes,
        orientation="portrait" if h_cm > w_cm else "landscape",
        uses_rfp_ids=uses_rfp_ids,
        has_notes=has_notes,
        chapters=chapters,
    )
    return TemplateProfile(
        file_name=file_name,
        document_id=document_id,
        purpose=purpose,
        slide_width_cm=w_cm,
        slide_height_cm=h_cm,
        slide_count=len(slides),
        layouts=layouts,
        content_layout=content_layout,
        chapter_layout=chapter_layout,
        headers=headers,
        lead=lead,
        body=body,
        footnote=footnote,
        chapter_title_box=chapter_title_box,
        chapter_numeral_box=chapter_numeral_box,
        chapter_list_box=chapter_list_box,
        chapter_label_boxes=chapter_label_boxes,
        band_color=band_color,
        page_number_pattern=page_pattern,
        section_format=section_format,
        continued_format=continued_format,
        fonts=fonts,
        font_sizes=font_sizes,
        colors=colors,
        table_style=table_style,
        chapters=chapters,
        table_patterns=table_patterns,
        uses_rfp_ids=uses_rfp_ids,
        has_notes=has_notes,
        conventions=conventions,
        warnings=warnings,
    )


def _conventions(
    *,
    headers: list[Box],
    lead: Box | None,
    footnote: Box | None,
    page_pattern: str | None,
    fonts: dict[str, str],
    font_sizes: dict[str, float],
    orientation: str,
    uses_rfp_ids: bool,
    has_notes: bool,
    chapters: list[TemplateChapter],
) -> list[str]:
    out: list[str] = []
    out.append(
        f"용지 {'세로(A4형)' if orientation == 'portrait' else '가로'} — "
        f"{'한 슬라이드가 제안서 한 쪽이며 본문 밀도가 높다 (글머리 6~10개, 표 10행 내외)' if orientation == 'portrait' else '발표형 슬라이드 (글머리 5개 이하)'}"
    )
    if len(headers) >= 2:
        out.append(
            f"본문 슬라이드 머리글 2단: 1단 '절 번호. 절 제목'({font_sizes.get('section', '?')}pt), "
            f"2단 '절.소절 소절 제목'({font_sizes.get('subsection', '?')}pt). 같은 소절이 이어지면 '(계속)'"
        )
    elif headers:
        out.append(
            f"본문 슬라이드 머리글 1단 '절 번호와 제목'({font_sizes.get('section', '?')}pt), 발표형: 절마다 슬라이드 1~2장, "
            "리드 문장 1개 + 도식(카드·흐름·2열 비교·구성도) + 요점 5개 이하"
        )
    if lead:
        out.append(
            f"소절 첫 슬라이드 머리글 아래에 리드 메시지(요약 문장 1~2개, {font_sizes.get('lead', '?')}pt 굵게)"
        )
    if chapters:
        out.append(
            "장 표지에 로마숫자·장 제목·절 목록, 본문은 장 → 절(1.) → 소절(1.1) 3단 번호 체계"
            if any(c.numeral for c in chapters)
            else "본문은 절(1.) → 소절(1.1) 번호 체계"
        )
    if uses_rfp_ids:
        out.append(
            "RFP 요구사항 ID(예: SFR-001)를 요구 명칭과 짝지어 카드·표로 인용하고 그 아래 대응 내용을 쓴다"
        )
    if footnote:
        out.append("슬라이드 하단에 '※ …' 주석으로 전제·협의 사항을 적는다")
    if page_pattern:
        out.append(
            f"쪽번호 패턴 '{page_pattern.replace(PAGE_FIELD, 'N')}' (장별 번호, 레이아웃 고정)"
        )
    out.append(
        f"글꼴: 제목 {fonts.get('title')}, 본문 {fonts.get('body')} {font_sizes.get('body', '?')}pt"
    )
    out.append("발표자 노트 사용" if has_notes else "발표자 노트 없음 (제출용)")
    return out


# --- 템플릿 기반 빌더 ----------------------------------------------------------------------------


def _rgb(hex_str: str | None, default: str = "1F4E78") -> RGBColor:
    h = (hex_str or default).lstrip("#")
    try:
        return RGBColor.from_string(h[:6])
    except Exception:  # noqa: BLE001
        return RGBColor.from_string(default)


class TemplateDeckBuilder:
    """업로드한 템플릿 PPTX의 마스터·레이아웃 위에 슬라이드를 만든다. ``DeckBuilder``와 같은 호출 규약.

    장(chapter) → 절(section) → 소절(subsection) 번호는 코드가 매긴다. ``begin_chapter``가 장 표지를 만들고
    이후 ``bullet_slides``/``table_slides``/``image_slide`` 호출마다 소절 번호가 하나씩 올라간다.
    """

    def __init__(
        self,
        template: bytes,
        profile: TemplateProfile,
        *,
        max_bullets: int | None = None,
        max_chars: int | None = None,
        body_font_pt: float | None = None,
    ) -> None:
        self.profile = profile
        self.prs = Presentation(io.BytesIO(template))
        self._remove_all_slides()
        self._layouts = {lo.name: lo for m in self.prs.slide_masters for lo in m.slide_layouts}
        self._content_layout = self._pick_layout(profile.content_layout)
        self._chapter_layout = (
            self._layouts.get(profile.chapter_layout) if profile.chapter_layout else None
        )
        self._layout_numeral: dict[str, str] = {}
        for name, lo in self._layouts.items():
            for sh in lo.shapes:
                if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                    m = re.search(rf"[{ROMAN}]+", sh.text_frame.text)
                    if m:
                        self._layout_numeral.setdefault(name, m.group(0))
        self.body_font_pt = float(body_font_pt or profile.size("body", 10.0))
        body = profile.body
        line_h_cm = self.body_font_pt * 1.55 / 28.35
        self.max_bullets = int(max_bullets or max(4, min(12, body.height * 0.55 // line_h_cm)))
        per_line = body.width / (self.body_font_pt * 0.0335)
        self.max_chars = int(max_chars or max(60, min(200, per_line * 2)))
        self.rows_per_slide = int(max(6, min(18, (body.height - 1.0) // 0.75)))
        self.slide_count = 0
        self.chapter_numeral = ""
        self.chapter_title = ""
        self.section_no = 0
        self.section_title = ""
        self.sub_no = 0
        self.chapter_slides: list[tuple[str, int]] = []  # (numeral, slide index) — QA용
        from proposal_agent.generators.pptx.shapes import ShapeStyle

        self.style = ShapeStyle(
            font=profile.body_font,
            title_font=profile.title_font,
            primary=profile.colors.get("primary", "1F4E78"),
            accent=profile.colors.get("accent", profile.colors.get("lead", "5B9BD5")),
            base_pt=float(max(min(self.body_font_pt, 12), 7)),
        )

    # --- 내부 --------------------------------------------------------------------------------
    def _remove_all_slides(self) -> None:
        id_list = self.prs.slides._sldIdLst  # noqa: SLF001 - python-pptx 공개 API 없음
        for sld_id in list(id_list):
            self.prs.part.drop_rel(sld_id.rId)
            id_list.remove(sld_id)

    def _pick_layout(self, name: str | None) -> Any:
        if name and name in self._layouts:
            return self._layouts[name]
        # 자리표시자가 가장 적은 레이아웃(빈 레이아웃에 가까운 것)
        return min(self._layouts.values(), key=lambda lo: len(lo.placeholders))

    def _layout_for_chapter(self) -> Any:
        for name, numeral in self._layout_numeral.items():
            if numeral == self.chapter_numeral and name != self.profile.chapter_layout:
                return self._layouts[name]
        return self._content_layout

    def _new_slide(self, layout: Any) -> Any:
        slide = self.prs.slides.add_slide(layout)
        for ph in list(slide.placeholders):  # 레이아웃 자리표시자는 쓰지 않는다 (빈 틀 방지)
            ph._element.getparent().remove(ph._element)  # noqa: SLF001
        self.slide_count += 1
        return slide

    def _text(
        self,
        slide: Any,
        box: Box,
        text: str,
        *,
        size: float | None = None,
        bold: bool | None = None,
        color: str | None = None,
        font: str | None = None,
        align: PP_ALIGN | None = None,
        anchor: MSO_ANCHOR | None = None,
        fill: str | None = None,
    ) -> Any:
        shape = slide.shapes.add_textbox(Cm(box.left), Cm(box.top), Cm(box.width), Cm(box.height))
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = _rgb(fill)
        tf = shape.text_frame
        tf.word_wrap = True
        if anchor is not None:
            tf.vertical_anchor = anchor
        p = tf.paragraphs[0]
        p.text = text
        p.font.name = font or box.font_name or self.profile.title_font
        p.font.size = Pt(size or box.font_size or self.body_font_pt)
        p.font.bold = bold if bold is not None else box.bold
        if color or box.color:
            p.font.color.rgb = _rgb(color or box.color)
        if align is not None:
            p.alignment = align
        return shape

    def _header_boxes(self) -> tuple[Box, Box]:
        prof = self.profile
        if len(prof.headers) >= 2:
            return prof.headers[0], prof.headers[1]
        w = prof.slide_width_cm
        base = (
            prof.headers[0]
            if prof.headers
            else Box(left=w * 0.08, top=prof.body.top - 1.6, width=w * 0.84, height=0.5)
        )
        sec = Box(
            left=base.left,
            top=round(base.top, 2),
            width=base.width,
            height=0.5,
            font_name=base.font_name or prof.title_font,
            font_size=prof.size("section", 10.0),
            bold=True,
            color=base.color,
        )
        sub = Box(
            left=base.left,
            top=round(base.top + 0.6, 2),
            width=base.width,
            height=0.7,
            font_name=base.font_name or prof.title_font,
            font_size=prof.size("subsection", 13.0),
            bold=True,
            color=base.color,
        )
        return sec, sub

    def _chapter_label_overlay(self, slide: Any, layout: Any) -> None:
        """장 전용 레이아웃이 없을 때 레이아웃에 고정된 장 이름·로마숫자를 현재 장으로 덮어쓴다."""
        if layout is not self._content_layout or not self.profile.chapter_label_boxes:
            return
        if not self._layout_numeral:
            return  # 장별 레이아웃(로마숫자 라벨)이 없는 템플릿은 덮어쓸 장 라벨이 없다
        if self._layout_numeral.get(self.profile.content_layout or "") == self.chapter_numeral:
            return
        band = self.profile.band_color
        text_color = None
        if band:
            red, green, blue = (int(band[i : i + 2], 16) for i in (0, 2, 4))
            luminance = 0.299 * red + 0.587 * green + 0.114 * blue
            text_color = "FFFFFF" if luminance < 140 else "000000"
        for box in self.profile.chapter_label_boxes:
            is_numeral = box.width < 2.0
            text = self.chapter_numeral if is_numeral else self.chapter_title
            if not text:
                continue
            target = box
            if not is_numeral and box.font_size:
                # 장 제목이 템플릿 라벨 상자 폭보다 길면 한 줄에 맞게 글꼴을 줄인다 (최소 10pt) — 넘침 방지 (Phase 18)
                width_pt = box.width / 2.54 * 72
                # 한글(전각) 글자 폭 ≈ 글꼴 크기, 영문 ≈ 0.6배. 여백 5%를 둔다.
                cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
                est_width_per_pt = (cjk * 1.0 + (len(text) - cjk) * 0.6) / max(1, len(text))
                fit = width_pt * 0.95 / (est_width_per_pt * max(1, len(text)))
                if fit < box.font_size:
                    target = box.model_copy(update={"font_size": max(9.0, round(fit, 1))})
            self._text(
                slide,
                target,
                text,
                fill=band,
                color=text_color,
                anchor=MSO_ANCHOR.MIDDLE,
                align=PP_ALIGN.CENTER if is_numeral else None,
            )

    def _content_slide(
        self, subsection_title: str, *, continued: bool, page: tuple[int, int] | None = None
    ) -> tuple[Any, Box]:
        """본문 슬라이드 머리글. 2단 양식: '절' + '절.소절 소절', 1단 양식(발표용): '절번호 소절 제목'."""
        layout = self._layout_for_chapter()
        slide = self._new_slide(layout)
        self._chapter_label_overlay(slide, layout)
        prof = self.profile
        fmt = prof.section_format
        marker = ""
        fraction = "{i}" in prof.continued_format
        if fraction and page and page[1] > 1:
            marker = " " + prof.continued_format.format(i=page[0], n=page[1])  # 모든 쪽에 (i/n)
        elif continued and not fraction:
            marker = " " + prof.continued_format  # 이어지는 쪽에만 (계속)
        default_pt = 16.0 if prof.orientation == "landscape" else 10.0
        if len(prof.headers) == 1:
            sec_box = prof.headers[0]
            text = (
                fmt.format(no=self.section_no, title=subsection_title)
                if self.section_no
                else subsection_title
            )
            self._text(
                slide,
                sec_box,
                (text + marker)[:80],
                size=sec_box.font_size or prof.size("section", default_pt),
                bold=True,
                anchor=MSO_ANCHOR.MIDDLE,
            )
            return slide, prof.body
        sec_box, sub_box = self._header_boxes()
        sec_label = (
            fmt.format(no=self.section_no, title=self.section_title)
            if self.section_no
            else self.section_title
        )
        sub_label = (
            f"{self.section_no}.{self.sub_no} {subsection_title}"
            if self.section_no
            else subsection_title
        )
        self._text(
            slide,
            sec_box,
            sec_label[:80],
            size=sec_box.font_size or prof.size("section", default_pt),
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        self._text(
            slide,
            sub_box,
            (sub_label + marker)[:80],
            size=sub_box.font_size or prof.size("subsection", default_pt + 3),
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        return slide, prof.body

    def _lead(self, slide: Any, text: str) -> float:
        """리드 메시지 상자를 그리고 그 아래 y(cm)를 돌려준다."""
        prof = self.profile
        box = prof.lead or Box(
            left=prof.body.left,
            top=prof.body.top,
            width=prof.body.width,
            height=1.5,
            font_name=prof.title_font,
            font_size=prof.size("lead", max(self.body_font_pt + 2, 12.0)),
            bold=True,
        )
        shape = self._text(
            slide,
            box,
            text[:240],
            bold=True,
            color=prof.colors.get("lead") or prof.colors.get("primary"),
            anchor=MSO_ANCHOR.MIDDLE,
        )
        shape.line.color.rgb = _rgb(prof.colors.get("primary"))
        return box.bottom + 0.3

    def _footnotes(self, slide: Any, notes: Sequence[str]) -> None:
        if not notes:
            return
        prof = self.profile
        box = prof.footnote or Box(
            left=prof.body.left,
            top=prof.body.bottom - 1.0,
            width=prof.body.width,
            height=1.0,
            font_name=prof.body_font,
            font_size=max(self.body_font_pt - 1, 7.0),
        )
        text = "\n".join(n if n.startswith("※") else f"※ {n}" for n in notes[:3])
        self._text(slide, box, text[:300], bold=False)

    def _notes(self, slide: Any, notes: str) -> None:
        if notes:
            slide.notes_slide.notes_text_frame.text = notes[:2000]

    # --- 구조 --------------------------------------------------------------------------------
    def begin_chapter(self, numeral: str, title: str, sections: Sequence[str]) -> None:
        self.chapter_numeral, self.chapter_title = numeral, title
        self.section_no, self.sub_no = 0, 0
        self.chapter_slide(numeral, title, sections)

    def begin_section(self, title: str, number: int | None = None) -> None:
        self.section_no = number if number is not None else self.section_no + 1
        self.section_title = title
        self.sub_no = 0

    def chapter_slide(self, numeral: str, title: str, sections: Sequence[str]) -> None:
        prof = self.profile
        layout = self._chapter_layout or self._content_layout
        slide = self._new_slide(layout)
        self.chapter_slides.append((numeral, self.slide_count))
        w, h = prof.slide_width_cm, prof.slide_height_cm
        tbox = prof.chapter_title_box or Box(
            left=w * 0.25,
            top=h * 0.2,
            width=w * 0.65,
            height=1.6,
            font_size=prof.size("chapter", 32.0),
        )
        wide = Box(
            left=tbox.left,
            top=tbox.top,
            width=max(tbox.width, w * 0.6),
            height=max(tbox.height, 1.6),
            font_name=tbox.font_name,
            font_size=tbox.font_size,
            color=tbox.color,
        )
        self._text(
            slide,
            wide,
            title[:60],
            size=prof.size("chapter", tbox.font_size or 32.0),
            bold=True,
            color=prof.colors.get("primary"),
            font=prof.title_font,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        if numeral:
            nbox = prof.chapter_numeral_box or Box(
                left=w * 0.1,
                top=tbox.top,
                width=w * 0.12,
                height=tbox.height,
                font_size=tbox.font_size,
            )
            self._text(
                slide,
                nbox,
                numeral,
                size=prof.size("chapter", nbox.font_size or 32.0),
                bold=True,
                color=nbox.color or "FFFFFF",
                font=prof.title_font,
                anchor=MSO_ANCHOR.MIDDLE,
                align=PP_ALIGN.CENTER,
            )
        if sections:
            lbox = prof.chapter_list_box or Box(
                left=w * 0.22,
                top=tbox.bottom + 1.5,
                width=w * 0.6,
                height=min(h * 0.4, 0.9 * len(sections) + 0.5),
            )
            shown = sections[:12]
            # 절이 많으면 상자 높이에 맞춰 글꼴을 줄인다 (줄 높이 ≈ 1.5em)
            fit_pt = lbox.height * 28.35 / (1.5 * max(len(shown), 1))
            self._text(
                slide,
                lbox,
                "\n".join(
                    f"{i + 1}. {s}" if not SECTION_RE.match(s) else s for i, s in enumerate(shown)
                ),
                size=max(8.0, min(prof.size("subsection", 13.0), fit_pt)),
                bold=True,
                font=prof.title_font,
                color=prof.colors.get("primary"),
            )
        self.section_no, self.sub_no = 0, 0

    # --- DeckBuilder 호환 ---------------------------------------------------------------------
    def title_slide(self, title: str, subtitle: str, footer: str) -> None:
        prof = self.profile
        layout = self._chapter_layout or self._content_layout
        slide = self._new_slide(layout)
        w, h = prof.slide_width_cm, prof.slide_height_cm
        box = prof.chapter_title_box or Box(left=w * 0.1, top=h * 0.3, width=w * 0.8, height=2.2)
        width = max(box.width, w * 0.6)
        size = prof.size("chapter", 30.0)
        # 긴 제목은 두 줄까지 허용: 글꼴을 폭에 맞춰 줄이고 상자를 두 줄 높이로
        per_line = width * 28.35 / (size * 0.75)
        if len(title) > per_line * 2:
            size = max(18.0, size * (per_line * 2) / len(title))
        title_h = max(box.height, size * 2.6 / 28.35)  # 두 줄 높이
        self._text(
            slide,
            Box(
                left=box.left, top=box.top, width=width, height=max(box.height, size * 2.6 / 28.35)
            ),
            title[:80],
            size=size,
            bold=True,
            color=prof.colors.get("primary"),
            font=prof.title_font,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        self._text(
            slide,
            Box(left=box.left, top=box.top + title_h + 0.4, width=width, height=1.2),
            subtitle[:120],
            size=prof.size("subsection", 13.0),
            font=prof.body_font,
            color=prof.colors.get("primary"),
        )

    def section_slide(self, title: str, footer: str) -> None:
        self.begin_chapter("", title, [])

    def bullet_slides(
        self,
        title: str,
        bullets: Sequence[str],
        footer: str,
        *,
        notes: str = "",
        lead: str = "",
        footnotes: Sequence[str] = (),
    ) -> int:
        self.sub_no += 1
        items = [b.strip()[: self.max_chars] for b in bullets if b and b.strip()]
        if not items:
            items = ["(해당 데이터 없음 — 검토 필요)"]
        first_cap = max(2, self.max_bullets - (3 if lead else 0))
        pages = [items[:first_cap]] + [
            items[i : i + self.max_bullets] for i in range(first_cap, len(items), self.max_bullets)
        ]
        prof = self.profile
        for i, page in enumerate(pages):
            slide, body = self._content_slide(title, continued=i > 0, page=(i + 1, len(pages)))
            top = body.top
            if lead and i == 0:
                top = self._lead(slide, lead)
            bottom = body.bottom - (1.1 if footnotes and i == len(pages) - 1 else 0.0)
            box = slide.shapes.add_textbox(
                Cm(body.left), Cm(top), Cm(body.width), Cm(max(bottom - top, 1.0))
            )
            tf = box.text_frame
            tf.word_wrap = True
            for j, b in enumerate(page):
                p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                p.text = f"• {b}"
                p.font.size = Pt(self.body_font_pt)
                p.font.name = prof.body_font
                p.space_after = Pt(4)
            if footnotes and i == len(pages) - 1:
                self._footnotes(slide, footnotes)
            self._notes(slide, notes)
        return len(pages)

    def table_slides(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
        footer: str,
        *,
        rows_per_slide: int | None = None,
        col_widths: Sequence[float] | None = None,
        notes: str = "",
        lead: str = "",
        footnotes: Sequence[str] = (),
    ) -> int:
        self.sub_no += 1
        prof = self.profile
        per = rows_per_slide or self.rows_per_slide
        pages = [rows[i : i + per] for i in range(0, max(len(rows), 1), per)] or [[]]
        tsize = float(prof.table_style.get("font_size", max(self.body_font_pt - 1, 7)))
        for i, page in enumerate(pages):
            slide, body = self._content_slide(title, continued=i > 0, page=(i + 1, len(pages)))
            top = body.top
            if lead and i == 0:
                top = self._lead(slide, lead)
            n_rows = len(page) + 1
            height = min(body.bottom - top, 0.7 * n_rows)
            shape = slide.shapes.add_table(
                n_rows, len(headers), Cm(body.left), Cm(top), Cm(body.width), Cm(height)
            )
            table = shape.table
            if col_widths:
                total = sum(col_widths)
                for ci, cw in enumerate(col_widths):
                    table.columns[ci].width = int(Cm(body.width) * (cw / total))
            for ci, hd in enumerate(headers):
                cell = table.cell(0, ci)
                cell.text = str(hd)
                para = cell.text_frame.paragraphs[0]
                para.font.size = Pt(tsize)
                para.font.bold = True
                para.font.name = prof.title_font
                para.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(
                    prof.table_style.get("header_fill"), prof.colors.get("primary", "1F4E78")
                )
            for ri, row in enumerate(page, start=1):
                for ci, v in enumerate(row):
                    cell = table.cell(ri, ci)
                    cell.text = str(v if v is not None else "")[:120]
                    para = cell.text_frame.paragraphs[0]
                    para.font.size = Pt(tsize)
                    para.font.name = prof.body_font
            if footnotes and i == len(pages) - 1:
                self._footnotes(slide, footnotes)
            self._notes(slide, notes)
        return len(pages)

    def image_slide(
        self,
        title: str,
        image_path: str | Path,
        footer: str,
        *,
        caption: str = "",
        notes: str = "",
        lead: str = "",
        tag: str | None = None,
    ) -> None:
        pic_name = picture_name(tag, caption or Path(image_path).stem) if tag else None
        self.sub_no += 1
        from PIL import Image

        prof = self.profile
        slide, body = self._content_slide(title, continued=False)
        top = body.top
        if lead:
            top = self._lead(slide, lead)
        with Image.open(image_path) as im:
            w_px, h_px = im.size
        max_w, max_h = body.width, body.bottom - top - (0.8 if caption else 0.0)
        scale = min(max_w / w_px, max_h / h_px)
        w, h = w_px * scale, h_px * scale
        left = body.left + (body.width - w) / 2
        pic = slide.shapes.add_picture(
            str(image_path), Cm(left), Cm(top), width=Cm(w), height=Cm(h)
        )
        if (
            tag
        ):  # 허용 그림(사진·일러스트·장식·참고)은 '<태그>:<설명>' 이름으로 표시 — QA-FILE-12 예외
            pic.name = pic_name
        if caption:
            self._text(
                slide,
                Box(
                    left=body.left,
                    top=top + h + 0.1,
                    width=body.width,
                    height=0.6,
                    font_name=prof.body_font,
                    font_size=max(self.body_font_pt - 1, 7),
                ),
                caption[:150],
                bold=False,
                align=PP_ALIGN.CENTER,
            )
        self._notes(slide, notes)

    def canvas_slide(self, title: str, *, lead: str = "", notes: str = "") -> tuple[Any, Box]:
        """머리글(+리드) 아래 도형을 그릴 본문 영역(cm)."""
        self.sub_no += 1
        slide, body = self._content_slide(title, continued=False)
        top = body.top
        if lead:
            top = self._lead(slide, lead)
        self._notes(slide, notes)
        return slide, Box(
            left=body.left, top=top, width=body.width, height=max(body.bottom - top, 3.0)
        )

    def visual_slide(
        self,
        title: str,
        spec: dict[str, Any],
        footer: str,
        *,
        lead: str = "",
        bullets: Sequence[str] = (),
        notes: str = "",
    ) -> str:
        from proposal_agent.generators.pptx.shapes import draw_visual

        slide, box = self.canvas_slide(title, lead=lead, notes=notes)
        items = [b.strip()[: self.max_chars] for b in bullets if b and b.strip()][:5]
        line_h = self.body_font_pt * 1.6 / 28.35
        vis_h = box.height - (0.5 + line_h * len(items) if items else 0.0)
        kind = draw_visual(
            slide,
            Box(left=box.left, top=box.top, width=box.width, height=max(vis_h, 3.0)),
            spec,
            style=self.style,
        )
        if items:
            tb = slide.shapes.add_textbox(
                Cm(box.left),
                Cm(box.top + max(vis_h, 3.0) + 0.2),
                Cm(box.width),
                Cm(line_h * len(items) + 0.3),
            )
            tf = tb.text_frame
            tf.word_wrap = True
            for i, b in enumerate(items):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = f"• {b}"
                p.font.size = Pt(self.body_font_pt)
                p.font.name = self.profile.body_font
        return kind

    def key_message_slide(
        self, title: str, messages: Sequence[str], footer: str, *, notes: str = ""
    ) -> None:
        self.sub_no += 1
        prof = self.profile
        slide, body = self._content_slide(title, continued=False)
        msgs = [m[:90] for m in messages if m][:4] or ["(핵심 메시지 없음 — 검토 필요)"]
        n = len(msgs)
        gap = 0.4
        box_w = (body.width - gap * (n - 1)) / n
        for i, m in enumerate(msgs):
            shape = slide.shapes.add_shape(
                1,
                Cm(body.left + i * (box_w + gap)),
                Cm(body.top + 0.5),
                Cm(box_w),
                Cm(min(5.0, body.height * 0.4)),
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor(0xEE, 0xF3, 0xF9)
            shape.line.color.rgb = _rgb(prof.colors.get("primary"))
            tf = shape.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            p.text = m
            p.font.size = Pt(prof.size("lead", self.body_font_pt + 4))
            p.font.bold = True
            p.font.name = prof.title_font
            p.font.color.rgb = _rgb(prof.colors.get("primary"))
            p.alignment = PP_ALIGN.CENTER
        self._notes(slide, notes)

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


__all__ = [
    "Box",
    "TemplateChapter",
    "TemplateDeckBuilder",
    "TemplateProfile",
    "profile_template",
]
