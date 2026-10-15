"""python-pptx 슬라이드 빌더 (16:9, 자체 도형·표·이미지만 사용).

텍스트가 넘치지 않도록 글머리 수와 글자 수를 제한하고, 긴 목록은 자동으로 다음 슬라이드로 나눈다.
모든 도형은 슬라이드 경계 안에 배치한다 (QA가 경계·겹침을 다시 검사).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

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
        self, title: str, bullets: Sequence[str], footer: str, *, notes: str = "", lead: str = ""
    ) -> int:
        """글머리가 많으면 여러 슬라이드로 나눈다. 만든 슬라이드 수를 돌려준다."""
        items = [b.strip()[: self.max_chars] for b in bullets if b and b.strip()]
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
    ) -> int:
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
        self, title: str, image_path: str | Path, footer: str, *, caption: str = "", notes: str = ""
    ) -> None:
        slide = self._new_slide()
        self._title(slide, title)
        from PIL import Image

        with Image.open(image_path) as im:
            w_px, h_px = im.size
        max_w, max_h = BODY_W, BODY_H - Inches(0.4)
        scale = min(max_w / w_px, max_h / h_px)
        w, h = int(w_px * scale), int(h_px * scale)
        left = MARGIN + int((BODY_W - w) / 2)
        slide.shapes.add_picture(str(image_path), left, BODY_TOP, width=w, height=h)
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
