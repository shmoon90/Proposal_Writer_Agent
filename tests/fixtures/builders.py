"""테스트용 **모의 문서** 생성기.

실제 고객 RFP가 아니라 자체 작성한 가상 RFP 본문(``SAMPLE_SECTIONS``)으로 DOCX/TXT/PDF/스캔 PDF를 만든다.
실제 문서로 검증한 항목이 아니므로 보고 시 "모의 문서"로 구분한다.
PDF 생성은 reportlab(텍스트 PDF), Pillow(이미지 전용 스캔 PDF), pypdf(병합·암호화)를 쓴다.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KOREAN_FONT = Path(r"C:\Windows\Fonts\malgun.ttf")


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    table: list[list[str]] | None = None


SAMPLE_TITLE = "차세대 민원 통합 플랫폼 구축 사업 제안요청서"

SAMPLE_SECTIONS: list[Section] = [
    Section(
        "제1장 사업 개요",
        [
            "본 사업은 분산된 민원 시스템을 통합하여 대민 서비스 품질을 높이는 것을 목적으로 한다.",
            "사업 기간은 계약일로부터 10개월이며, 사업 예산은 부가세 포함 12억 원이다.",
        ],
    ),
    Section(
        "제2장 기능 요구사항",
        ["다음 기능 요구사항은 모두 필수 구현 대상이다."],
        [
            "FR-A. 시스템은 사용자 인증을 공공기관 통합인증(SSO)으로 처리해야 한다.",
            "FR-B. 민원 접수 화면에서 첨부파일을 최대 5개, 각 20MB까지 업로드할 수 있어야 한다.",
            "FR-C. 처리 상태 변경 시 신청인에게 SMS와 이메일로 자동 통보해야 한다.",
            "FR-D. 관리자는 민원 유형별 처리 통계를 기간별로 조회하고 Excel로 내려받을 수 있어야 한다.",
        ],
    ),
    Section(
        "제3장 비기능 요구사항",
        [],
        [
            "NFR-A. 평균 응답 시간은 2초 이내, 동시 사용자 1,000명을 지원해야 한다.",
            "NFR-B. 서비스 가용성은 연 99.9% 이상이어야 하며 이중화 구성을 갖춘다.",
            "NFR-C. 개인정보는 암호화 저장하고 접근 이력을 3년간 보관해야 한다.",
        ],
        table=[
            ["항목", "기준", "비고"],
            ["응답 시간", "2초 이내", "피크 시간 기준"],
            ["가용성", "99.9%", "월 단위 측정"],
            ["동시 사용자", "1,000명", "부하 시험으로 검증"],
        ],
    ),
    Section(
        "제4장 제약사항 및 연계",
        [
            "CON-A. 시스템은 기관 표준 프레임워크(전자정부 표준프레임워크 4.x) 기반으로 개발해야 한다.",
            "CON-B. 기존 행정정보공동이용 시스템과 연계 인터페이스를 유지해야 한다.",
        ],
    ),
    Section(
        "제5장 평가 기준",
        ["기술 평가 90점, 가격 평가 10점으로 평가한다."],
        table=[
            ["평가 항목", "배점"],
            ["사업 이해도", "20"],
            ["기술 및 기능", "40"],
            ["수행 역량", "30"],
        ],
    ),
    Section(
        "제6장 제출 조건",
        [],
        [
            "SUB-A. 제안서는 2026년 11월 30일 15:00까지 전자 제출해야 한다.",
            "SUB-B. 제안서 본문은 100쪽 이내로 작성한다.",
        ],
    ),
]

SAMPLE_REQUIREMENT_KEYS = [
    "FR-A",
    "FR-B",
    "FR-C",
    "FR-D",
    "NFR-A",
    "NFR-B",
    "NFR-C",
    "CON-A",
    "CON-B",
    "SUB-A",
    "SUB-B",
]


def sample_text() -> str:
    lines: list[str] = [
        SAMPLE_TITLE,
        "",
        "목차",
        "제1장 사업 개요 ........ 1",
        "제2장 기능 요구사항 ........ 2",
        "",
    ]
    for s in SAMPLE_SECTIONS:
        lines.append(s.heading)
        lines.append("")
        for p in s.paragraphs:
            lines.append(p)
            lines.append("")
        for b in s.bullets:
            lines.append(f"- {b}")
        if s.bullets:
            lines.append("")
        if s.table:
            for row in s.table:
                lines.append(" | ".join(row))
            lines.append("")
    return "\n".join(lines)


def build_txt() -> bytes:
    return sample_text().encode("utf-8")


def build_docx(*, sections: list[Section] | None = None, title: str = SAMPLE_TITLE) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(title, level=0)
    doc.add_paragraph("목차")
    doc.add_paragraph("제1장 사업 개요 ........ 1")
    for s in sections or SAMPLE_SECTIONS:
        doc.add_heading(s.heading, level=1)
        for p in s.paragraphs:
            doc.add_paragraph(p)
        for b in s.bullets:
            doc.add_paragraph(b, style="List Bullet")
        if s.table:
            table = doc.add_table(rows=len(s.table), cols=len(s.table[0]))
            table.style = "Table Grid"
            for r, row in enumerate(s.table):
                for c, val in enumerate(row):
                    table.cell(r, c).text = val
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _register_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if KOREAN_FONT.exists():
        if "Malgun" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Malgun", str(KOREAN_FONT)))
        return "Malgun"
    return "Helvetica"


def build_text_pdf(
    *, sections: list[Section] | None = None, title: str = SAMPLE_TITLE, pad_pages: int = 0
) -> bytes:
    """텍스트 레이어와 괘선 표가 있는 PDF (reportlab platypus). ``pad_pages``만큼 본문 페이지를 늘린다."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font = _register_font()
    body = ParagraphStyle("body", fontName=font, fontSize=10.5, leading=15)
    head = ParagraphStyle(
        "head", fontName=font, fontSize=14, leading=18, spaceBefore=8, spaceAfter=6
    )
    title_style = ParagraphStyle("title", fontName=font, fontSize=18, leading=22, spaceAfter=12)
    story: list = [Paragraph(title, title_style)]
    for s in sections or SAMPLE_SECTIONS:
        story.append(Paragraph(s.heading, head))
        for p in s.paragraphs:
            story.append(Paragraph(p, body))
        for b in s.bullets:
            story.append(Paragraph(f"- {b}", body))
        if s.table:
            t = Table(s.table)
            t.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                        ("FONTNAME", (0, 0), (-1, -1), font),
                    ]
                )
            )
            story.append(Spacer(1, 6))
            story.append(t)
        story.append(Spacer(1, 8))
    for i in range(pad_pages):
        story.append(PageBreak())
        story.append(
            Paragraph(
                f"부록 {i + 1}. 추가 설명 페이지입니다. 본문 요구사항과 무관한 참고 내용을 담는다.",
                body,
            )
        )
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50
    ).build(story)
    return buf.getvalue()


def render_text_image(
    lines: list[str], *, width: int = 1240, height: int = 1754, font_size: int = 30
) -> object:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = (
        ImageFont.truetype(str(KOREAN_FONT), font_size)
        if KOREAN_FONT.exists()
        else ImageFont.load_default()
    )
    y = 80
    for line in lines:
        draw.text((80, y), line, font=font, fill="black")
        y += int(font_size * 1.8)
    return img


SCAN_LINES = [
    "제2장 기능 요구사항",
    "FR-A. 시스템은 사용자 인증을 SSO로 처리해야 한다.",
    "FR-C. 처리 상태 변경 시 SMS와 이메일로 통보해야 한다.",
]


def build_scanned_pdf(lines: list[str] | None = None, *, pages: int = 1) -> bytes:
    """텍스트 레이어 없이 이미지만 있는 PDF (Pillow가 이미지 전용 PDF를 만든다)."""
    img = render_text_image(lines or SCAN_LINES)
    buf = io.BytesIO()
    extra = [img.copy() for _ in range(pages - 1)]
    img.save(buf, format="PDF", resolution=150.0, save_all=bool(extra), append_images=extra)
    return buf.getvalue()


def build_mixed_pdf() -> bytes:
    """1쪽 텍스트 + 1쪽 스캔."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for src in (build_text_pdf(sections=SAMPLE_SECTIONS[:1]), build_scanned_pdf()):
        for page in PdfReader(io.BytesIO(src)).pages:
            writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def build_encrypted_pdf() -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(
        clone_from=PdfReader(io.BytesIO(build_text_pdf(sections=SAMPLE_SECTIONS[:1])))
    )
    writer.encrypt(user_password="secret", owner_password="owner", algorithm="AES-256")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def build_corrupted_bytes(seed: int = 7, size: int = 4096) -> bytes:
    rng = random.Random(seed)
    return b"%PDF-1.7\n" + bytes(rng.getrandbits(8) for _ in range(size))


def build_corrupted_docx() -> bytes:
    return b"PK\x03\x04" + b"\x00" * 64 + b"not-a-zip"


# --- 구조화 RFP (공공 SI 표준 형식 모사) ------------------------------------------------------
# 실제 고객 RFP가 아닌 가상 문서. Ⅰ~Ⅵ 로마숫자 장, 요구사항 목록·상세 표(세로 병합 라벨 포함),
# 제안서 목차 표, 평가 배점 표, 제출 서류 목록을 담아 ingest.rfp_profile 의 구조 인식을 검증한다.
STRUCTURED_RFP_TITLE = "가상 민원 사건관리 시스템 구축 제안요청서"
STRUCTURED_RFP_IDS = ["PER-001", "SER-001", "SFR-001", "SFR-002"]
STRUCTURED_RFP_TOC = ["제안 개요", "사업 수행 방안", "사업 관리 방안", "지원 방안"]
STRUCTURED_RFP_TOC_SECTIONS: dict[str, list[str]] = {
    "제안 개요": ["사업 이해도", "추진 전략"],
    "사업 수행 방안": ["시스템 구성 방안", "요구사항 대응 방안"],
    "사업 관리 방안": ["조직 및 인력", "추진 일정"],
    "지원 방안": ["교육 훈련", "유지보수"],
}

_STRUCTURED_DETAILS: list[tuple[str, str, str, list[str]]] = [
    (
        "SFR-001",
        "사건 접수 관리",
        "민원 사건을 접수·배정·종결까지 관리한다.",
        [
            "1) 사건 접수 화면에서 제보 내용과 첨부 파일을 등록해야 한다.",
            "2) 담당자 배정 시 배정 알림을 발송해야 한다.",
        ],
    ),
    (
        "SFR-002",
        "통계 조회",
        "사건 처리 현황을 기간·유형별로 조회한다.",
        ["1) 월별·유형별 처리 건수를 조회하고 엑셀로 내려받을 수 있어야 한다."],
    ),
    (
        "SER-001",
        "접근 통제",
        "사용자 권한에 따른 접근 통제를 적용한다.",
        ["1) 역할 기반 권한을 적용하고 접근 이력을 3년간 보관해야 한다."],
    ),
    (
        "PER-001",
        "응답 시간",
        "주요 화면의 응답 시간 기준을 만족한다.",
        ["1) 평균 응답 시간은 3초 이내여야 한다."],
    ),
]


def build_structured_rfp_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(STRUCTURED_RFP_TITLE, level=0)
    doc.add_heading("Ⅰ. 사업 개요", level=1)
    doc.add_paragraph("1. 사업명 : 가상 민원 사건관리 시스템 구축")
    doc.add_paragraph("2. 사업 기간 : 계약일로부터 8개월")
    doc.add_paragraph("3. 사업 예산 : 금 500,000,000원 (부가세 포함)")
    doc.add_heading("Ⅱ. 사업 범위", level=1)
    doc.add_paragraph("민원 민원 민원 사건 접수·배정·종결 관리 시스템 신규 구축", style="List Bullet")
    doc.add_paragraph("통계 조회 및 접근 통제 기능 구축", style="List Bullet")
    doc.add_heading("Ⅲ. 요구사항", level=1)
    doc.add_paragraph("1. 요구사항 요약")
    _add_table(
        doc, [["구분", "요구사항 수"], ["기능(SFR)", "2"], ["보안(SER)", "1"], ["성능(PER)", "1"]]
    )
    doc.add_paragraph("2. 요구사항 목록")
    _add_table(
        doc,
        [["고유번호", "요구사항명", "정의"]]
        + [[rid, name, definition] for rid, name, definition, _ in _STRUCTURED_DETAILS],
    )
    doc.add_paragraph("3. 요구사항 상세")
    for rid, name, definition, details in _STRUCTURED_DETAILS:
        _add_table(
            doc,
            [
                ["요구사항", "고유번호", rid],
                ["요구", "명칭", name],
                ["사항", "정의", definition],
                ["세부", "내용", "\n".join(details)],
                ["", "설명", "세부 내용은 제안서에 구현 방안을 기술한다."],
            ],
        )
    doc.add_heading("Ⅳ. 제안서 작성 요령", level=1)
    doc.add_paragraph("제안서는 아래 목차 순서로 작성한다.")
    _add_table(
        doc,
        [["목차", "작성 내용"]]
        + [
            [
                f"{r}. {t}",
                "\n".join(
                    f"{i + 1}. {sec} ○ {sec}에 대해 기술"
                    for i, sec in enumerate(STRUCTURED_RFP_TOC_SECTIONS[t])
                ),
            ]
            for r, t in zip("ⅠⅡⅢⅣ", STRUCTURED_RFP_TOC, strict=True)
        ],
    )
    doc.add_heading("Ⅴ. 제안서 평가 기준", level=1)
    doc.add_paragraph("기술 능력 평가와 가격 평가를 합산한다.")
    _add_table(doc, [["평가 항목", "배점"], ["기술 능력", "90"], ["가격", "10"], ["합계", "100"]])
    doc.add_heading("Ⅵ. 제안 안내사항", level=1)
    doc.add_paragraph("1. 제출서류")
    doc.add_paragraph("○ 제안서 7부")
    doc.add_paragraph("○ 제안요약서 1부 및 USB 1본")
    doc.add_paragraph("2. 제안서 제출기한 : 2026년 12월 1일 15:00까지")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _add_table(doc: Any, rows: list[list[str]]) -> None:
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            table.cell(r, c).text = val


# --- 제안서 템플릿 PPTX (가상 고객 양식) ------------------------------------------------------
# A4 세로, 장 표지(로마숫자·장 제목·절 목록) + 본문 슬라이드(머리글 2단·리드·본문·표·※ 주석).
TEMPLATE_FONT = "맑은 고딕"
TEMPLATE_HEADER_TOPS = (3.8, 4.5)


def build_template_pptx(*, portrait: bool = True) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Cm, Pt

    prs = Presentation()
    if portrait:
        prs.slide_width, prs.slide_height = Cm(21.0), Cm(29.7)
    else:
        prs.slide_width, prs.slide_height = Cm(33.867), Cm(19.05)
    chapter_layout, content_layout = prs.slide_layouts[0], prs.slide_layouts[6]

    def clear(slide: Any) -> None:
        for ph in list(slide.placeholders):
            ph._element.getparent().remove(ph._element)  # noqa: SLF001

    def text(
        slide: Any,
        left: float,
        top: float,
        w: float,
        h: float,
        value: str,
        size: float,
        *,
        bold: bool = False,
        color: str | None = None,
    ) -> Any:
        box = slide.shapes.add_textbox(Cm(left), Cm(top), Cm(w), Cm(h))
        tf = box.text_frame
        tf.word_wrap = True
        for i, line in enumerate(value.split("\n")):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            run = para.add_run()
            run.text = line
            run.font.name = TEMPLATE_FONT
            run.font.size = Pt(size)
            run.font.bold = bold
            if color:
                run.font.color.rgb = RGBColor.from_string(color)
        return box

    s = prs.slides.add_slide(chapter_layout)
    clear(s)
    text(s, 2.5, 6.5, 1.6, 1.8, "Ⅰ", 36, bold=True, color="FFFFFF")
    text(s, 6.0, 6.5, 10.0, 1.5, "제안 개요", 34, bold=True, color="313D83")
    text(s, 4.8, 10.5, 8.0, 4.0, "1. 사업 이해도\n2. 추진 전략", 13, bold=True)
    pages = [
        ("1. 사업 이해도", "1.1 사업의 개요", False),
        ("1. 사업 이해도", "1.1 사업의 개요", True),
        ("1. 사업 이해도", "1.2 사업의 범위", False),
        ("2. 추진 전략", "2.1 추진 전략", False),
        ("2. 추진 전략", "2.2 핵심 성공 요소", False),
        ("2. 추진 전략", "2.2 핵심 성공 요소", True),
    ]
    h1, h2 = TEMPLATE_HEADER_TOPS
    body_top = 7.5 if portrait else 5.5
    for i, (sec, sub, cont) in enumerate(pages):
        s = prs.slides.add_slide(content_layout)
        text(s, 2.0, h1, 17.5, 0.4, sec, 10, bold=True)
        text(s, 2.0, h2, 17.5, 0.6, sub + (" (계속)" if cont else ""), 13, bold=True)
        text(
            s, 2.0, 5.5, 17.5, 1.6, f"리드 메시지 {i + 1}: 요약 문장", 11, bold=True, color="0070C0"
        )
        text(s, 2.0, body_top, 17.5, 12.0, "\n".join(f"- 본문 글머리 {k}" for k in range(1, 7)), 9)
        if i == 2:
            shape = s.shapes.add_table(3, 3, Cm(2.0), Cm(20.0), Cm(17.5), Cm(2.4))
            for ci, hd in enumerate(("구분", "위험요소", "대처 방안")):
                cell = shape.table.cell(0, ci)
                cell.text = hd
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor.from_string("1F4E78")
                cell.text_frame.paragraphs[0].runs[0].font.size = Pt(9)
                cell.text_frame.paragraphs[0].runs[0].font.name = TEMPLATE_FONT
            for ri in (1, 2):
                for ci in range(3):
                    cell = shape.table.cell(ri, ci)
                    cell.text = f"r{ri}c{ci}"
                    cell.text_frame.paragraphs[0].runs[0].font.size = Pt(9)
        if portrait:
            text(s, 2.0, 27.3, 17.5, 0.8, "※ 발주처와 협의하여 조정", 8)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
