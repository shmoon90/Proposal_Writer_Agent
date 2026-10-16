"""python-pptx 슬라이드 빌더 (16:9, 자체 도형·표·이미지만 사용).

텍스트가 넘치지 않도록 글머리 수와 글자 수를 제한하고, 긴 목록은 자동으로 다음 슬라이드로 나눈다.
모든 도형은 슬라이드 경계 안에 배치한다 (QA가 경계·겹침을 다시 검사).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Emu, Inches, Pt

from proposal_agent.generators.base import picture_name
from proposal_agent.generators.pptx.shapes import ShapeStyle, draw_visual
from proposal_agent.generators.pptx.template import Box

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.5)
TITLE_H = Inches(0.9)
BODY_TOP = MARGIN + TITLE_H + Inches(0.15)
BODY_H = SLIDE_H - BODY_TOP - Inches(0.6)
BODY_W = SLIDE_W - 2 * MARGIN
PRIMARY = RGBColor(0x1F, 0x4E, 0x78)
ACCENT = RGBColor(0x5B, 0x9B, 0xD5)
GREY = RGBColor(0x59, 0x59, 0x59)
FONT = "맑은 고딕"


class DeckBuilder:
    def __init__(
        self, *, max_bullets: int = 8, max_chars: int = 110, body_font_pt: int = 16
    ) -> None:
        self.prs = Presentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self._blank = self.prs.slide_layouts[6]
        self.max_bullets = max_bullets
        self.max_chars = max_chars
        self.body_font_pt = body_font_pt
        self.slide_count = 0
        self.style = ShapeStyle(
            font=FONT,
            primary="1F4E78",
            accent="5B9BD5",
            base_pt=float(max(min(body_font_pt - 4, 12), 8)),
        )

    # --- 기본 요소 --------------------------------------------------------------------------
    def _new_slide(self):
        slide = self.prs.slides.add_slide(self._blank)
        self.slide_count += 1
        return slide

    def _title(self, slide, text: str, *, size: int = 26) -> None:
        box = slide.shapes.add_textbox(MARGIN, MARGIN, BODY_W, TITLE_H)
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = text[:70]
        p.font.size = Pt(size)
        p.font.bold = True
        p.font.name = FONT
        p.font.color.rgb = PRIMARY
        line = slide.shapes.add_shape(
            1, MARGIN, MARGIN + TITLE_H, BODY_W, Emu(28000)
        )  # MSO_SHAPE.RECTANGLE
        line.fill.solid()
        line.fill.fore_color.rgb = ACCENT
        line.line.fill.background()
        line.text_frame.text = ""

    def _footer(self, slide, text: str) -> None:
        box = slide.shapes.add_textbox(MARGIN, SLIDE_H - Inches(0.5), BODY_W, Inches(0.35))
        p = box.text_frame.paragraphs[0]
        p.text = f"{text}  ·  {self.slide_count}"
        p.font.size = Pt(9)
        p.font.color.rgb = GREY
        p.font.name = FONT
        p.alignment = PP_ALIGN.RIGHT

    def _notes(self, slide, notes: str) -> None:
        if notes:
            slide.notes_slide.notes_text_frame.text = notes[:2000]

    # --- 슬라이드 유형 ------------------------------------------------------------------------
    def title_slide(self, title: str, subtitle: str, footer: str) -> None:
        slide = self._new_slide()
        band = slide.shapes.add_shape(1, 0, Inches(2.4), SLIDE_W, Inches(2.6))
        band.fill.solid()
        band.fill.fore_color.rgb = PRIMARY
        band.line.fill.background()
        tf = band.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = title[:80]
        p.font.size = Pt(34)
        p.font.bold = True
        p.font.name = FONT
        p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.alignment = PP_ALIGN.CENTER
        p2 = tf.add_paragraph()
        p2.text = subtitle[:120]
        p2.font.size = Pt(16)
        p2.font.name = FONT
        p2.font.color.rgb = RGBColor(0xDD, 0xEB, 0xF7)
        p2.alignment = PP_ALIGN.CENTER
        self._footer(slide, footer)

    def begin_chapter(self, numeral: str, title: str, sections: Sequence[str]) -> None:
        """장 표지 (기본 양식: 제목 슬라이드 + 절 목록)."""
        label = f"{numeral}. {title}" if numeral else title
        slide = self._new_slide()
        box = slide.shapes.add_textbox(MARGIN, Inches(1.6), BODY_W, Inches(1.2))
        p = box.text_frame.paragraphs[0]
        p.text = label[:60]
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.name = FONT
        p.font.color.rgb = PRIMARY
        if sections:
            lst = slide.shapes.add_textbox(
                MARGIN + Inches(0.4), Inches(3.0), BODY_W - Inches(0.8), Inches(3.6)
            )
            tf = lst.text_frame
            tf.word_wrap = True
            for i, s in enumerate(sections[:10]):
                para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                para.text = f"{i + 1}. {s}"
                para.font.size = Pt(18)
                para.font.name = FONT
                para.font.color.rgb = GREY
        self._footer(slide, "")

    def begin_section(self, title: str, number: int | None = None) -> None:
        """기본 양식은 절 번호를 머리글에 쓰지 않는다 (템플릿 빌더만 사용)."""
        return None

    def section_slide(self, title: str, footer: str) -> None:
        slide = self._new_slide()
        box = slide.shapes.add_textbox(MARGIN, Inches(3.0), BODY_W, Inches(1.2))
        p = box.text_frame.paragraphs[0]
        p.text = title[:60]
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.name = FONT
        p.font.color.rgb = PRIMARY
        self._footer(slide, footer)

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
        """글머리가 많으면 여러 슬라이드로 나눈다. 만든 슬라이드 수를 돌려준다."""
        items = [b.strip()[: self.max_chars] for b in bullets if b and b.strip()]
        items += [n if n.startswith("※") else f"※ {n}" for n in footnotes if n]
        if not items:
            items = ["(해당 데이터 없음 — 검토 필요)"]
        pages = [items[i : i + self.max_bullets] for i in range(0, len(items), self.max_bullets)]
        for i, page in enumerate(pages):
            slide = self._new_slide()
            self._title(slide, title if i == 0 else f"{title} (계속)")
            box = slide.shapes.add_textbox(MARGIN, BODY_TOP, BODY_W, BODY_H)
            tf = box.text_frame
            tf.word_wrap = True
            first = True
            if lead and i == 0:
                p = tf.paragraphs[0]
                p.text = lead[:200]
                p.font.size = Pt(self.body_font_pt)
                p.font.name = FONT
                p.font.color.rgb = GREY
                first = False
            for b in page:
                p = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                p.text = f"• {b}"
                p.font.size = Pt(self.body_font_pt)
                p.font.name = FONT
                p.space_after = Pt(6)
            self._footer(slide, footer)
            self._notes(slide, notes)
        return len(pages)

    def table_slides(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
        footer: str,
        *,
        rows_per_slide: int = 12,
        col_widths: Sequence[float] | None = None,
        notes: str = "",
        lead: str = "",
        footnotes: Sequence[str] = (),
    ) -> int:
        if lead or footnotes:
            notes = "\n".join(x for x in (lead, notes, *footnotes) if x)
        pages = [
            rows[i : i + rows_per_slide] for i in range(0, max(len(rows), 1), rows_per_slide)
        ] or [[]]
        for i, page in enumerate(pages):
            slide = self._new_slide()
            self._title(slide, title if i == 0 else f"{title} (계속)")
            n_rows = len(page) + 1
            height = min(BODY_H, Inches(0.38) * n_rows)
            shape = slide.shapes.add_table(n_rows, len(headers), MARGIN, BODY_TOP, BODY_W, height)
            table = shape.table
            if col_widths:
                total = sum(col_widths)
                for ci, w in enumerate(col_widths):
                    table.columns[ci].width = int(BODY_W * (w / total))
            for ci, h in enumerate(headers):
                cell = table.cell(0, ci)
                cell.text = str(h)
                para = cell.text_frame.paragraphs[0]
                para.font.size = Pt(11)
                para.font.bold = True
                para.font.name = FONT
                para.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                cell.fill.solid()
                cell.fill.fore_color.rgb = PRIMARY
            for ri, row in enumerate(page, start=1):
                for ci, v in enumerate(row):
                    cell = table.cell(ri, ci)
                    cell.text = str(v if v is not None else "")[:120]
                    para = cell.text_frame.paragraphs[0]
                    para.font.size = Pt(10)
                    para.font.name = FONT
            self._footer(slide, footer)
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
        """이미지 슬라이드. ``tag``(photo/illustration/decoration/reference)를 주면 허용 그림으로 이름을 붙인다.

        태그 없는 그림은 정보성 자료 이미지로 간주되어 QA-FILE-12가 실패시키므로, 표·구조도·차트·목업은 도형으로 그린다.
        """
        if lead:
            caption = f"{lead} · {caption}" if caption else lead
        pic_name = picture_name(tag, caption or Path(image_path).stem) if tag else None
        slide = self._new_slide()
        self._title(slide, title)
        from PIL import Image

        with Image.open(image_path) as im:
            w_px, h_px = im.size
        max_w, max_h = BODY_W, BODY_H - Inches(0.4)
        scale = min(max_w / w_px, max_h / h_px)
        w, h = int(w_px * scale), int(h_px * scale)
        left = MARGIN + int((BODY_W - w) / 2)
        pic = slide.shapes.add_picture(str(image_path), left, BODY_TOP, width=w, height=h)
        if pic_name:
            pic.name = pic_name
        if caption:
            box = slide.shapes.add_textbox(
                MARGIN, BODY_TOP + h + Inches(0.05), BODY_W, Inches(0.35)
            )
            p = box.text_frame.paragraphs[0]
            p.text = caption[:150]
            p.font.size = Pt(10)
            p.font.name = FONT
            p.font.color.rgb = GREY
            p.alignment = PP_ALIGN.CENTER
        self._footer(slide, footer)
        self._notes(slide, notes)

    def canvas_slide(self, title: str, *, lead: str = "", notes: str = "") -> tuple[Any, Box]:
        """제목(+리드) 아래 도형을 그릴 빈 영역(cm)을 돌려준다. 도식은 shapes.draw_* 로 그린다."""
        slide = self._new_slide()
        self._title(slide, title)
        left, top = Emu(MARGIN).cm, Emu(BODY_TOP).cm
        width, height = Emu(BODY_W).cm, Emu(BODY_H).cm
        if lead:
            box = slide.shapes.add_textbox(Cm(left), Cm(top), Cm(width), Cm(1.0))
            p = box.text_frame.paragraphs[0]
            p.text = lead[:200]
            p.font.size = Pt(self.body_font_pt - 2)
            p.font.bold = True
            p.font.name = FONT
            p.font.color.rgb = PRIMARY
            top += 1.1
            height -= 1.1
        self._footer(slide, "")
        self._notes(slide, notes)
        return slide, Box(left=left, top=top, width=width, height=height)

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
        """에이전트 지정 도식(VisualSpec) 슬라이드. 글머리가 있으면 도식 아래에 요점 4개까지."""
        slide, box = self.canvas_slide(title, lead=lead, notes=notes)
        items = [b.strip()[: self.max_chars] for b in bullets if b and b.strip()][:4]
        vis_h = box.height - (0.8 + 0.55 * len(items) if items else 0.0)
        kind = draw_visual(
            slide,
            Box(left=box.left, top=box.top, width=box.width, height=max(vis_h, 3.0)),
            spec,
            style=self.style,
        )
        if items:
            tb = slide.shapes.add_textbox(
                Cm(box.left),
                Cm(box.top + max(vis_h, 3.0) + 0.3),
                Cm(box.width),
                Cm(0.55 * len(items) + 0.4),
            )
            tf = tb.text_frame
            tf.word_wrap = True
            for i, b in enumerate(items):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = f"• {b}"
                p.font.size = Pt(self.body_font_pt - 2)
                p.font.name = FONT
        return kind

    def key_message_slide(
        self, title: str, messages: Sequence[str], footer: str, *, notes: str = ""
    ) -> None:
        """발표용: 큰 글씨 핵심 메시지 3~4개를 박스로."""
        slide = self._new_slide()
        self._title(slide, title)
        msgs = [m[:90] for m in messages if m][:4] or ["(핵심 메시지 없음 — 검토 필요)"]
        n = len(msgs)
        gap = Inches(0.25)
        box_w = int((BODY_W - gap * (n - 1)) / n)
        for i, m in enumerate(msgs):
            shape = slide.shapes.add_shape(
                1, MARGIN + i * (box_w + gap), BODY_TOP + Inches(0.5), box_w, Inches(3.2)
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = (
                RGBColor(0xDD, 0xEB, 0xF7) if i % 2 == 0 else RGBColor(0xE2, 0xF0, 0xD9)
            )
            shape.line.color.rgb = ACCENT
            tf = shape.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            p.text = m
            p.font.size = Pt(18)
            p.font.bold = True
            p.font.name = FONT
            p.font.color.rgb = PRIMARY
            p.alignment = PP_ALIGN.CENTER
        self._footer(slide, footer)
        self._notes(slide, notes)

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()
