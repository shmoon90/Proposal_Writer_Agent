"""FLOW_DIAGRAM.md의 흐름도를 PNG(Pillow)와 PPTX(python-pptx)로 렌더링한다.

외부 렌더러(mermaid-cli·브라우저) 없이 코드가 직접 그린다. 결과:
  docs/diagrams/flow_01_overall.png            전체 구조 (UI → 서비스 → 에이전트 → CLI → API/MCP/웹 → 저장소)
  docs/diagrams/flow_02_agent_call.png         에이전트 1회 호출 시퀀스
  docs/diagrams/flow_03_proposal_pipeline.png  제안 단계 파이프라인·게이트
  docs/diagrams/flow_04_build_changes.png      구축 단계 변경관리 흐름
  docs/diagrams/flow_05_role_tool_matrix.png   역할 ↔ 도구 ↔ MCP 매트릭스
  docs/FLOW_DIAGRAM.pptx                       위 5장 + 표지 (16:9)

실행: .venv\\Scripts\\python scripts\\render_flow_diagrams.py
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Emu, Inches, Pt

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "diagrams"
FONT_PATH = r"C:\Windows\Fonts\malgun.ttf"
FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"

# 색상 (역할별 구분)
C_UI = "#DDEBF7"
C_CODE = "#E2EFDA"
C_AGENT = "#FCE4D6"
C_EXT = "#EDEDED"
C_MCP = "#FFF2CC"
C_STORE = "#E4DFEC"
C_GATE = "#FFD966"
C_HUMAN = "#F8CBAD"
C_LINE = "#404040"
C_TEXT = "#1F1F1F"
WHITE = "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


@dataclass
class Canvas:
    img: Image.Image
    draw: ImageDraw.ImageDraw

    @classmethod
    def new(cls, w: int, h: int) -> Canvas:
        img = Image.new("RGB", (w, h), WHITE)
        return cls(img, ImageDraw.Draw(img))

    # --- 기본 도형 --------------------------------------------------------------------------
    def text_center(
        self,
        cx: float,
        cy: float,
        text: str,
        size: int = 22,
        bold: bool = False,
        fill: str = C_TEXT,
    ) -> None:
        f = font(size, bold)
        lines = text.split("\n")
        lh = size + 6
        total = lh * len(lines)
        for i, line in enumerate(lines):
            w = self.draw.textlength(line, font=f)
            self.draw.text((cx - w / 2, cy - total / 2 + i * lh), line, font=f, fill=fill)

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        text: str,
        fill: str = C_CODE,
        size: int = 22,
        bold_first: bool = True,
        radius: int = 14,
        outline: str = C_LINE,
        width: int = 3,
    ) -> tuple[float, float, float, float]:
        self.draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=radius, fill=fill, outline=outline, width=width
        )
        lines = text.split("\n")
        f0 = font(size, bold_first)
        f1 = font(size - 2)
        lh = size + 6
        total = lh * len(lines)
        for i, line in enumerate(lines):
            f = f0 if i == 0 else f1
            tw = self.draw.textlength(line, font=f)
            self.draw.text(
                (x + w / 2 - tw / 2, y + h / 2 - total / 2 + i * lh), line, font=f, fill=C_TEXT
            )
        return (x, y, x + w, y + h)

    def diamond(
        self,
        cx: float,
        cy: float,
        w: float,
        h: float,
        text: str,
        fill: str = C_GATE,
        size: int = 20,
    ) -> tuple[float, float, float, float]:
        pts = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
        self.draw.polygon(pts, fill=fill, outline=C_LINE, width=3)
        self.text_center(cx, cy, text, size=size, bold=True)
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    def group(
        self, x: float, y: float, w: float, h: float, title: str, fill: str = "#FAFAFA"
    ) -> None:
        self.draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=18, fill=fill, outline="#9E9E9E", width=2
        )
        self.draw.text((x + 16, y + 10), title, font=font(24, True), fill="#555555")

    def arrow(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        label: str = "",
        dashed: bool = False,
        width: int = 3,
        color: str = C_LINE,
        label_size: int = 18,
        label_offset: tuple[float, float] = (0, 0),
    ) -> None:
        x1, y1 = p1
        x2, y2 = p2
        if dashed:
            dx, dy = x2 - x1, y2 - y1
            length = max((dx**2 + dy**2) ** 0.5, 1)
            n = int(length // 14)
            for i in range(0, n, 2):
                a = (x1 + dx * i / n, y1 + dy * i / n)
                b = (x1 + dx * min(i + 1, n) / n, y1 + dy * min(i + 1, n) / n)
                self.draw.line([a, b], fill=color, width=width)
        else:
            self.draw.line([p1, p2], fill=color, width=width)
        # 화살촉
        import math

        ang = math.atan2(y2 - y1, x2 - x1)
        size = 16
        left = (x2 - size * math.cos(ang - math.pi / 7), y2 - size * math.sin(ang - math.pi / 7))
        right = (x2 - size * math.cos(ang + math.pi / 7), y2 - size * math.sin(ang + math.pi / 7))
        self.draw.polygon([p2, left, right], fill=color)
        if label:
            mx, my = (x1 + x2) / 2 + label_offset[0], (y1 + y2) / 2 + label_offset[1]
            f = font(label_size)
            tw = self.draw.textlength(label, font=f)
            self.draw.rectangle(
                (
                    mx - tw / 2 - 6,
                    my - label_size / 2 - 4,
                    mx + tw / 2 + 6,
                    my + label_size / 2 + 6,
                ),
                fill=WHITE,
            )
            self.draw.text((mx - tw / 2, my - label_size / 2), label, font=f, fill="#333333")

    def elbow(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        label: str = "",
        dashed: bool = False,
        via: str = "h",
    ) -> None:
        """ㄱ자 연결: via='h'면 수평 먼저, 'v'면 수직 먼저."""
        x1, y1 = p1
        x2, y2 = p2
        mid = (x2, y1) if via == "h" else (x1, y2)
        if dashed:
            self._dash([p1, mid])
        else:
            self.draw.line([p1, mid], fill=C_LINE, width=3)
        self.arrow(mid, p2, label=label, dashed=dashed)

    def _dash(self, pts: list[tuple[float, float]]) -> None:
        (x1, y1), (x2, y2) = pts
        dx, dy = x2 - x1, y2 - y1
        length = max((dx**2 + dy**2) ** 0.5, 1)
        n = max(int(length // 14), 1)
        for i in range(0, n, 2):
            a = (x1 + dx * i / n, y1 + dy * i / n)
            b = (x1 + dx * min(i + 1, n) / n, y1 + dy * min(i + 1, n) / n)
            self.draw.line([a, b], fill=C_LINE, width=3)

    def title(self, text: str, sub: str = "") -> None:
        self.draw.text((40, 24), text, font=font(36, True), fill=C_TEXT)
        if sub:
            self.draw.text((40, 72), sub, font=font(20), fill="#555555")

    def legend(self, x: float, y: float, items: list[tuple[str, str]]) -> None:
        f = font(18)
        for i, (color, label) in enumerate(items):
            yy = y + i * 30
            self.draw.rounded_rectangle(
                (x, yy, x + 34, yy + 22), radius=5, fill=color, outline=C_LINE, width=2
            )
            self.draw.text((x + 44, yy - 2), label, font=f, fill=C_TEXT)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.save(path, "PNG", optimize=True)


def mid_bottom(b: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, b[3])


def mid_top(b: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, b[1])


def mid_right(b: tuple[float, float, float, float]) -> tuple[float, float]:
    return (b[2], (b[1] + b[3]) / 2)


def mid_left(b: tuple[float, float, float, float]) -> tuple[float, float]:
    return (b[0], (b[1] + b[3]) / 2)


LEGEND = [
    (C_UI, "Streamlit 화면"),
    (C_CODE, "Python 코드(결정적)"),
    (C_AGENT, "에이전트(LLM)"),
    (C_MCP, "MCP 서버·도구"),
    (C_EXT, "외부 프로세스·API"),
    (C_STORE, "저장소"),
    (C_GATE, "게이트(코드 판정)"),
    (C_HUMAN, "사람 결정"),
]


# --- 1. 전체 구조 ----------------------------------------------------------------------------
def diagram_overall() -> Canvas:
    c = Canvas.new(2400, 1560)
    c.title(
        "1. 전체 구조 — 누가 누구를 호출하는가",
        "UI → 서비스(코드) → 에이전트 실행 → Claude Code CLI → API / MCP / 웹 → 저장소. 스킬·서브에이전트는 사용하지 않음",
    )
    # UI
    c.group(40, 110, 2320, 150, "Streamlit UI (ui/app_pages, 8 화면)", "#F3F8FD")
    ui_names = [
        "시작·프로젝트",
        "문서 추출",
        "요구사항",
        "에이전트·조사",
        "산출물",
        "구축: 기준 문서",
        "구축: 변경 관리",
    ]
    ui_boxes = []
    for i, n in enumerate(ui_names):
        ui_boxes.append(c.box(70 + i * 325, 150, 300, 80, n, fill=C_UI, size=22))
    # 서비스
    c.group(40, 300, 1560, 420, "서비스 · 오케스트레이터 (Python 코드)", "#F5FAF2")
    svc = {}
    row1 = [
        ("StepRunner", "단계 실행·StepRun 기록"),
        ("GateService", "Gate 0~5 코드 판정·사람 승인"),
        ("ExtractionService", "DOCX/TXT/PDF/OCR → 블록"),
        ("RequirementService", "ID 발급·출처 검증·Gate 1"),
        ("ResearchService", "주제 식별·출처 신뢰도"),
    ]
    row2 = [
        ("PlanningService", "영업일 일정·공수·인력"),
        ("GenerationService", "Excel 4·PPT 2·PNG"),
        ("QaService", "독립 검증 30항목·자동 재생성"),
        ("BaselineService", "기존 Excel 적재·Revision"),
        ("ChangeService", "의미 비교·영향 분석·반영"),
    ]
    for i, (n, d) in enumerate(row1):
        svc[n] = c.box(70 + i * 305, 345, 280, 90, f"{n}\n{d}", fill=C_CODE, size=20)
    for i, (n, d) in enumerate(row2):
        svc[n] = c.box(70 + i * 305, 460, 280, 90, f"{n}\n{d}", fill=C_CODE, size=20)
    svc["AgentStepService"] = c.box(
        70,
        590,
        1500,
        100,
        "AgentStepService\n역할 정의 조회 · 이전 역할 출력 재사용(<prior>) · pwa MCP를 프로젝트별로 조립 · 결과 JSON 저장 · 감사",
        fill=C_CODE,
        size=22,
    )
    # 에이전트 실행
    c.group(1640, 300, 720, 420, "에이전트 실행 (agents/)", "#FDF6F1")
    c.box(
        1670,
        345,
        660,
        110,
        "ClaudeAgentRunner\nClaudeSDKClient · 구조화 출력(JSON 스키마)\n예산/턴/시간/취소/재시도 · 실패 분류",
        fill=C_AGENT,
        size=20,
    )
    c.box(
        1670,
        475,
        320,
        95,
        "hooks\nPreToolUse 거부 · PostToolUse 기록\ncan_use_tool 폴백",
        fill=C_AGENT,
        size=19,
    )
    c.box(
        2010,
        475,
        320,
        95,
        "prompts/*.md (10)\n+ schemas.py\n역할별 시스템 프롬프트·출력 스키마",
        fill=C_AGENT,
        size=19,
    )
    c.box(
        1670,
        590,
        660,
        100,
        "roles.py — 역할 10종\nrfp_analyst · requirement_extractor · requirement_verifier · tech_researcher · architect\nplanner · proposal_writer · document_generator · qa_reviewer · semantic_differ",
        fill=C_AGENT,
        size=19,
    )
    # 외부·MCP
    c.group(40, 790, 2320, 330, "외부 프로세스 · MCP 서버 · 웹", "#F7F7F7")
    cli = c.box(
        1000,
        840,
        520,
        100,
        "Claude Code CLI (claude-agent-sdk 번들 프로세스)\npermission_mode=dontAsk · allowed_tools만 · env ANTHROPIC_API_KEY",
        fill=C_EXT,
        size=20,
    )
    api = c.box(
        1700,
        840,
        620,
        100,
        "Anthropic API\n모델: claude-opus-5-5 / claude-sonnet-5-5\n(2026-10-15 현재 크레딧 부족으로 응답 미검증)",
        fill=C_EXT,
        size=20,
    )
    pwa = c.box(
        70,
        980,
        1000,
        120,
        "pwa 인프로세스 MCP 서버 (읽기 전용 도구 10종)\nget_project · list_requirements · get_requirement · search_source_text · get_source_block\nlist_research · list_findings · list_gates · get_prior_output · verify_deliverable_file",
        fill=C_MCP,
        size=20,
    )
    c.box(
        1150,
        980,
        560,
        120,
        "내장 WebSearch / WebFetch\ntech_researcher 역할에만 허용\n내부·사설 IP URL 차단 · URL 감사 기록",
        fill=C_MCP,
        size=20,
    )
    c.box(
        1760,
        980,
        560,
        120,
        "외부 MCP 서버 (선택)\nPWA_MCP_EXTERNAL JSON · 예: claude-code-docs(HTTP)\n역할이 선언한 서버만 연결",
        fill=C_MCP,
        size=20,
    )
    # 저장소
    c.group(40, 1190, 2320, 150, "저장소", "#F6F3F9")
    c.box(
        70,
        1230,
        1100,
        90,
        "SQLite workspace/pwa.sqlite3 (마이그레이션 0001~0006)\n프로젝트·문서·요구사항·계획·변경 요청·게이트·QA·감사 (엔티티 JSON + 인덱스 컬럼)",
        fill=C_STORE,
        size=20,
    )
    c.box(
        1230,
        1230,
        1090,
        90,
        "Output/<프로젝트>/00_~13_ (FileStore)\n원본 보존 · 덮어쓰기 금지 · 버전 파일명(_vX.Y, _YYYYMMDDHHMM, _n) · ensure_within 경로 제한",
        fill=C_STORE,
        size=20,
    )
    # 화살표
    for b in ui_boxes:
        c.arrow(mid_bottom(b), ((b[0] + b[2]) / 2, 300), width=2)
    c.arrow(
        mid_right(svc["AgentStepService"]),
        (1670, 640),
        label="AgentRequest",
        label_offset=(0, -34),
    )
    c.draw.text(
        (1250, 724),
        "AgentRequest = 역할·프롬프트·허용 도구·MCP 서버·예산·턴·시간 제한",
        font=font(17),
        fill="#555555",
    )
    c.arrow((1980, 455), (1980, 475), width=2)
    c.arrow((2170, 455), (2170, 475), width=2)
    c.arrow((1900, 690), (1900, 710), width=2)
    c.draw.line([(1900, 710), (1900, 760), (1260, 760)], fill=C_LINE, width=3)
    c.arrow((1260, 760), (1260, 840), label="ClaudeSDKClient.query()")
    c.arrow(
        mid_right(cli), mid_left(api), label="메시지·도구 결과 / 구조화 출력", label_offset=(0, 36)
    )
    c.arrow((1150, 940), (900, 980), label="mcp__pwa__* 호출")
    c.arrow((1330, 940), (1430, 980), label="tech_researcher만", dashed=True)
    c.arrow((1480, 940), (1960, 980), label="선언된 역할만", dashed=True)
    c.arrow(mid_bottom(pwa), (570, 1230), label="조회(읽기 전용) · 파일 검증")
    c.arrow((800, 720), (800, 790), width=2)
    c.draw.line([(800, 790), (800, 1150)], fill=C_LINE, width=3)
    c.arrow((800, 1150), (800, 1230), label="서비스가 쓰기")
    c.draw.line([(1500, 720), (1500, 760), (1800, 760)], fill=C_LINE, width=3)
    c.draw.line([(1800, 760), (1800, 1150)], fill=C_LINE, width=3)
    c.arrow((1800, 1150), (1800, 1230), label="산출물·JSON·스냅샷 저장")
    c.legend(1660, 1370, LEGEND[:4])
    c.legend(2010, 1370, LEGEND[4:])
    c.draw.text(
        (40, 1370),
        "※ 에이전트는 파일을 만들지 않는다. 파일·ID·일정·QA·게이트는 코드가 수행하고, 사람 승인(Gate 0·1·5, 변경 승인)은 UI에서 기록된다.",
        font=font(20),
        fill="#555555",
    )
    return c


# --- 2. 에이전트 호출 시퀀스 -------------------------------------------------------------------
def diagram_sequence() -> Canvas:
    c = Canvas.new(2400, 1560)
    c.title(
        "2. 에이전트 1회 호출 시퀀스 (AgentStepService.run_role → ClaudeAgentRunner)",
        "도구 호출마다 훅이 허용 목록을 검사하고, 결과는 스키마 검증 후 JSON 파일·DB·감사 이벤트로 남는다",
    )
    lanes = [
        ("서비스\n(RequirementService 등)", C_CODE),
        ("AgentStepService", C_CODE),
        ("ClaudeAgentRunner", C_AGENT),
        ("Claude Code CLI", C_EXT),
        ("PreToolUse 훅 /\ncan_use_tool", C_AGENT),
        ("pwa MCP 서버", C_MCP),
        ("Anthropic API", C_EXT),
        ("SQLite / Output", C_STORE),
    ]
    xs = []
    for i, (name, color) in enumerate(lanes):
        x = 120 + i * 300
        xs.append(x)
        c.box(x - 120, 120, 240, 80, name, fill=color, size=20)
        c.draw.line([(x, 200), (x, 1480)], fill="#9E9E9E", width=2)

    def msg(y: float, a: int, b: int, text: str, dashed: bool = False) -> None:
        x1, x2 = xs[a], xs[b]
        c.arrow((x1, y), (x2, y), label=text, dashed=dashed, label_size=18)

    def note(y: float, lane: int, text: str, w: int = 300) -> None:
        x = xs[lane]
        c.box(
            x - w / 2,
            y - 24,
            w,
            48,
            text,
            fill="#FFFFE0",
            size=17,
            bold_first=False,
            radius=6,
            width=2,
        )

    msg(250, 0, 1, "run_role(project, role_key, prompt)")
    note(300, 1, "roles.py 조회 · <prior role> 재사용 · pwa 서버 조립", 420)
    msg(360, 1, 2, "AgentRequest(allowed_tools, mcp_servers, 예산·턴·시간)")
    msg(420, 2, 3, "ClaudeSDKClient(options: tools·hooks·dontAsk·JSON schema·env)")
    msg(480, 3, 6, "메시지 + 도구 목록")
    # loop box
    c.draw.rectangle((xs[2] - 160, 530, xs[7] - 40, 1010), outline="#7F7F7F", width=3)
    c.draw.rectangle(
        (xs[2] - 160, 530, xs[2] + 560, 566), fill="#EEEEEE", outline="#7F7F7F", width=2
    )
    c.draw.text(
        (xs[2] - 150, 536),
        "loop  턴 반복 (max_turns · max_budget_usd · timeout_s · 취소 토큰)",
        font=font(18, True),
        fill="#333333",
    )
    msg(620, 6, 3, "도구 호출 요청 (tool_use)")
    msg(680, 3, 4, "PreToolUse(tool_name, input)")
    note(740, 4, "허용 목록 밖 · 금지 도구(Bash/Write/Edit…) · 내부 URL → deny + 감사 기록", 560)
    msg(800, 3, 5, "mcp__pwa__get_requirement 등 (허용 시)")
    msg(850, 5, 7, "조회(읽기 전용) · 경로 제한")
    msg(900, 5, 3, "도구 결과", dashed=True)
    msg(950, 3, 4, "PostToolUse → ToolCallRecorder(비밀값 마스킹)")
    msg(990, 3, 6, "도구 결과 전달")
    msg(1060, 6, 3, "ResultMessage(structured_output, cost, turns)", dashed=True)
    msg(1120, 3, 2, "결과", dashed=True)
    note(1180, 2, "Pydantic 스키마 검증 · 실패 분류(credit/auth/budget/rate_limit/schema…)", 560)
    msg(1250, 2, 1, "AgentResponse(output, cost_usd, num_turns, tool_calls)", dashed=True)
    msg(1310, 1, 7, "Output/<subdir>/<stem>_vX.Y.json · AgentOutput · 감사 이벤트")
    msg(1370, 1, 0, "RoleRunResult", dashed=True)
    c.draw.text(
        (40, 1430),
        "실패 처리: 일시 오류(rate_limit·overloaded·connection·process)만 retries 횟수 재시도. 크레딧·인증·예산·스키마 오류는 즉시 AgentRunError → StepRun failed. 시간 초과·취소는 interrupt().",
        font=font(20),
        fill="#555555",
    )
    return c


# --- 3. 제안 단계 파이프라인 ---------------------------------------------------------------------
def diagram_proposal() -> Canvas:
    c = Canvas.new(2400, 1560)
    c.title(
        "3. 제안 단계 파이프라인 — 코드 단계·에이전트 단계·게이트",
        "주황=에이전트(LLM), 초록=코드, 노랑=게이트(코드 판정), 분홍=사람 승인",
    )
    W, H = 300, 110
    # row 1
    y1 = 150
    b_up = c.box(60, y1, W, H, "RFP 업로드\n01_RFP_Original 보존", fill=C_CODE, size=20)
    b_ex = c.box(
        420,
        y1,
        W,
        H,
        "추출 (코드)\npdfplumber·docx·txt·OCR\n블록·위치·신뢰도",
        fill=C_CODE,
        size=20,
    )
    c.diamond(930, y1 + H / 2, 220, 120, "Gate 0\n추출 품질", size=20)
    b_ra = c.box(
        1120,
        y1,
        W,
        H,
        "rfp_analyst (에이전트)\npwa: search_source_text\nget_source_block",
        fill=C_AGENT,
        size=20,
    )
    b_re = c.box(
        1480,
        y1,
        W,
        H,
        "requirement_extractor\n(에이전트, 도구 없음)\n청크 프롬프트",
        fill=C_AGENT,
        size=20,
    )
    b_id = c.box(
        1840,
        y1,
        W,
        H,
        "ID 발급·출처 검증 (코드)\nFR-/NFR-/CON-/EVA-/SUB-\n인용이 원문에 없으면 제외",
        fill=C_CODE,
        size=19,
    )
    c.arrow(mid_right(b_up), mid_left(b_ex))
    c.arrow(mid_right(b_ex), (820, y1 + H / 2))
    c.arrow((1040, y1 + H / 2), mid_left(b_ra))
    c.arrow(
        mid_right(b_ra), mid_left(b_re), label="분석 결과 재사용", dashed=True, label_offset=(0, 80)
    )
    c.arrow(mid_right(b_re), mid_left(b_id))
    # row 2
    y2 = 400
    b_rv = c.box(
        1840,
        y2,
        W,
        H,
        "requirement_verifier\n(에이전트, 별도 세션)\n누락·중복·왜곡·출처·범위",
        fill=C_AGENT,
        size=19,
    )
    c.diamond(1620, y2 + H / 2, 240, 130, "Gate 1\n요구사항 기준선", size=20)
    h1 = c.box(
        1270, y2, 230, H, "사람 승인\n검토 의견 필수\nFAIL은 승인 불가", fill=C_HUMAN, size=19
    )
    b_tr = c.box(
        820,
        y2,
        W + 60,
        H,
        "tech_researcher (에이전트)\nWebSearch · WebFetch\npwa: get_requirement, list_research",
        fill=C_AGENT,
        size=19,
    )
    b_src = c.box(
        420,
        y2,
        W,
        H,
        "출처 신뢰도 재분류 (코드)\n공식 문서 우선 · 미확인 강등\nFeasibilityStudy 저장",
        fill=C_CODE,
        size=19,
    )
    b_ar = c.box(
        60, y2, W, H, "architect (에이전트)\npwa 읽기 9종\n구성 요소·연결", fill=C_AGENT, size=20
    )
    c.arrow(mid_bottom(b_id), mid_top(b_rv))
    c.arrow(mid_left(b_rv), (1740, y2 + H / 2))
    c.arrow((1500, y2 + H / 2), mid_right(h1))
    c.arrow(mid_left(h1), mid_right(b_tr))
    c.arrow(mid_left(b_tr), mid_right(b_src))
    c.arrow(
        mid_left(b_src),
        mid_right(b_ar),
        label="조사 결과 재사용",
        dashed=True,
        label_offset=(0, 80),
    )
    # row 3
    y3 = 650
    b_pl = c.box(
        60,
        y3,
        W,
        H,
        "planner (에이전트)\npwa 읽기 9종\n공수·근거·순서만 (날짜 금지)",
        fill=C_AGENT,
        size=19,
    )
    b_sch = c.box(
        420,
        y3,
        W + 40,
        H,
        "일정·공수·인력 계산 (코드)\n영업일 FS/SS/FF/SF · 롤업\n월별 MM·인원 · 단가 시 비용",
        fill=C_CODE,
        size=19,
    )
    b_gen = c.box(
        820,
        y3,
        W + 60,
        H,
        "산출물 생성 (코드)\n구성도 3·차트 2 PNG · Excel 4\n제출용·발표용 PPT (_vX.Y)",
        fill=C_CODE,
        size=19,
    )
    b_iq = c.box(
        1250,
        y3,
        360,
        H,
        "통합 QA (코드, independent_qa)\nRFP 적합성·기술·일관성·파일 30항목\n재생성 자동 수정 ≤ N회 → 재검증",
        fill=C_CODE,
        size=19,
    )
    b_qr = c.box(
        1680,
        y3,
        300,
        H,
        "qa_reviewer (에이전트, 선택)\npwa 읽기 + verify_deliverable_file\n결과는 사람 검토 항목으로만",
        fill=C_AGENT,
        size=18,
    )
    c.arrow(mid_bottom(b_ar), mid_top(b_pl))
    c.arrow(mid_right(b_pl), mid_left(b_sch))
    c.arrow(mid_right(b_sch), mid_left(b_gen))
    c.arrow(mid_right(b_gen), mid_left(b_iq))
    c.arrow(mid_right(b_iq), mid_left(b_qr), dashed=True)
    c.arrow(
        (1830, y3 + H),
        (1500, y3 + H + 70),
        dashed=True,
        label="QA-AI-nn (사람 검토 항목)",
        label_offset=(130, 10),
    )
    # row 4: gates
    y4 = 950
    g2 = c.diamond(700, y4 + 60, 220, 120, "Gate 2\n기술 타당성", size=19)
    g3 = c.diamond(980, y4 + 60, 220, 120, "Gate 3\n계획 일관성", size=19)
    g4 = c.diamond(1260, y4 + 60, 220, 120, "Gate 4\n파일 무결성", size=19)
    g5 = c.diamond(1620, y4 + 60, 260, 130, "Gate 5\n최종 독립 QA", size=20)
    h5 = c.box(
        1860, y4 + 10, 260, 100, "사람 승인 (필수)\n필수 검증 FAIL이면 불가", fill=C_HUMAN, size=19
    )
    b_fin = c.box(
        2180, y4 + 10, 180, 100, "최종본 복사\n13_Final_\nDeliverables", fill=C_CODE, size=18
    )
    c.arrow(mid_bottom(b_iq), (1430, y4 - 40))
    c.draw.line([(1430, y4 - 40), (700, y4 - 40), (700, y4)], fill=C_LINE, width=3)
    c.draw.line([(1430, y4 - 40), (1260, y4 - 40), (1260, y4)], fill=C_LINE, width=3)
    c.draw.line([(980, y4 - 40), (980, y4)], fill=C_LINE, width=3)
    bus_y = y4 + 160
    for g in (g2, g3, g4):
        c.draw.line([mid_bottom(g), ((g[0] + g[2]) / 2, bus_y)], fill=C_LINE, width=3)
    c.draw.line([(700, bus_y), (1620, bus_y)], fill=C_LINE, width=3)
    c.arrow((1620, bus_y), mid_bottom(g5), label="세 게이트 결과 합산", label_offset=(150, 0))
    c.arrow(mid_right(g5), mid_left(h5))
    c.arrow(mid_right(h5), mid_left(b_fin))
    c.draw.text(
        (60, y4 + 200),
        "점선 = 기본값 대체 가능: architect·planner 결과가 없으면 코드 기본 구성('미정'·기본 공수, 검토 필요 표시)으로 산출물을 만든다.\nproposal_writer·document_generator 역할도 run_role_step으로 호출 가능하며 문안·문서 계획만 제공한다(파일은 코드).",
        font=font(19),
        fill="#555555",
    )
    c.draw.text(
        (60, y4 + 270),
        "모든 게이트는 코드가 판정한다. NEEDS_HUMAN_REVIEW는 검토 의견을 적은 사람 승인으로만 통과하고, FAIL은 승인으로 통과시킬 수 없다.",
        font=font(19),
        fill="#555555",
    )
    c.legend(60, y4 + 330, LEGEND[:4])
    c.legend(600, y4 + 330, LEGEND[4:])
    return c


# --- 4. 구축 단계 변경관리 ----------------------------------------------------------------------
def diagram_build() -> Canvas:
    c = Canvas.new(2400, 1560)
    c.title(
        "4. 구축 단계 변경관리 흐름 — 승인 전 기준 데이터 불변",
        "B1(구조 분석)·B3(영향 분석)·B4(문서 갱신)는 코드가 수행하고, 에이전트는 semantic_differ 1종만 선택적으로 덧붙는다",
    )
    W, H = 330, 110
    y1 = 150
    b_up = c.box(
        60,
        y1,
        W,
        H,
        "기존 Excel 업로드\n정의서·추적표·WBS (필수)\n투입계획·기타 (선택)",
        fill=C_CODE,
        size=19,
    )
    b_mp = c.box(
        450,
        y1,
        W,
        H,
        "구조 분석·컬럼 매핑 제안 (코드)\nexcel_reader: 표준 시트·동의어·유사도\n품질 검사(중복 ID·날짜·수식)",
        fill=C_CODE,
        size=18,
    )
    h_mp = c.box(
        840,
        y1,
        260,
        H,
        "사용자 매핑 확정\n확인 필요 컬럼 열 번호 지정\n(user vs 규칙 구분 저장)",
        fill=C_HUMAN,
        size=18,
    )
    b_ld = c.box(
        1160,
        y1,
        W,
        H,
        "기준 적재 (코드)\n기존 ID 유지 · 추적·화면·테스트\nWBS·의존·역할 · Revision v1.0",
        fill=C_CODE,
        size=18,
    )
    b_cr = c.box(
        1550,
        y1,
        W,
        H,
        "변경 요청 등록\n자연어 · 추가/수정/삭제 버튼\n문서 업로드(발췌) · 요청자·사유",
        fill=C_UI,
        size=18,
    )
    b_sem = c.box(
        1940,
        y1,
        400,
        H,
        "규칙 의미 비교 (코드, semantic.py)\nADD / MODIFY / DELETE_REQUEST\nNO_CHANGE / AMBIGUOUS + 근거·신뢰도",
        fill=C_CODE,
        size=18,
    )
    for a, b in ((b_up, b_mp), (b_mp, h_mp), (h_mp, b_ld), (b_ld, b_cr), (b_cr, b_sem)):
        c.arrow(mid_right(a), mid_left(b))
    y2 = 400
    b_sd = c.box(
        1940,
        y2,
        400,
        H,
        "semantic_differ (에이전트, 선택)\npwa: list_requirements, get_requirement\n규칙과 불일치 → AMBIGUOUS로 낮춤",
        fill=C_AGENT,
        size=18,
    )
    b_imp = c.box(
        1440,
        y2,
        440,
        H,
        "영향 분석 (코드, impact.py)\n전후 일정(여유 보존) · Task 재사용/수정/신규/제거\n공수 범위 · 인력 시나리오 1~6 · 단가 시 비용",
        fill=C_CODE,
        size=17,
    )
    h_dec = c.box(
        1060,
        y2,
        320,
        H,
        "후보별 수락/거절\n분류·대상 ID·내용·공수 입력\n(사용자 입력 별도 저장)",
        fill=C_HUMAN,
        size=18,
    )
    c.diamond(800, y2 + H / 2, 300, 140, "승인 / 반려\n(Approval 기록)", fill=C_HUMAN, size=19)
    b_keep = c.box(
        300, y2, 300, H, "반려 · 철회\n기준 데이터 불변\n사유 필수 기록", fill=C_CODE, size=19
    )
    c.arrow(mid_bottom(b_sem), mid_top(b_sd), dashed=True)
    c.arrow(
        mid_left(b_sd), mid_right(b_imp), label="의견 덧붙임", dashed=True, label_offset=(0, 80)
    )
    c.arrow((1990, y1 + H), (1700, y2), label="후보", width=2)
    c.arrow(mid_left(b_imp), mid_right(h_dec))
    c.arrow(mid_left(h_dec), (950, y2 + H / 2))
    c.arrow((650, y2 + H / 2), mid_right(b_keep), label="반려", label_offset=(0, -30))
    y3 = 680
    b_apply = c.box(
        60,
        y3,
        600,
        130,
        "트랜잭션 반영 (코드, service.apply)\n새 ID는 기존 체계로 승인 후 발급 · 수정은 이전 버전 보존·이력\n삭제는 상태 표시(물리 삭제 없음) · 추적 링크 재검토 · WBS·일정 갱신\nRevision vN.0 + 스냅샷(12_Revision_History)",
        fill=C_CODE,
        size=17,
    )
    b_regen = c.box(
        700,
        y3,
        460,
        130,
        "문서 재생성 (코드)\nRequirements_Definition_YYYYMMDDHHMM.xlsx\nTraceability_Matrix · WBS_Gantt · (Staffing_Plan)\n같은 이름이면 _1, _2 · 변경관리대장 시트",
        fill=C_CODE,
        size=18,
    )
    b_pqa = c.box(
        1220,
        y3,
        420,
        130,
        "변경 후 통합 QA (코드)\n변경 이력↔기준 데이터 · 정의서↔추적표\nWBS↔일정 · 파일 품질 (RFP·PPT 검사는 해당 없음)",
        fill=C_CODE,
        size=18,
    )
    g5 = c.diamond(1850, y3 + 65, 260, 130, "Gate 5\n최종 독립 QA", size=20)
    h5 = c.box(
        2040, y3 + 15, 300, 100, "사람 승인\n변경관리대장·Revision 조회", fill=C_HUMAN, size=18
    )
    b_err = c.box(
        60,
        y3 + 200,
        600,
        90,
        "반영 중 오류 → 롤백 · 상태 error · 재시도 가능\n(파일 생성은 트랜잭션 밖: 재시도 시 새 타임스탬프 파일)",
        fill="#FDE9E9",
        size=18,
    )
    c.arrow((800, y2 + H / 2 + 70), (340, y3), label="승인")
    c.arrow(mid_right(b_apply), mid_left(b_regen))
    c.arrow(mid_right(b_regen), mid_left(b_pqa))
    c.arrow(mid_right(b_pqa), (1720, y3 + 65))
    c.arrow(mid_right(g5), mid_left(h5))
    c.arrow(mid_bottom(b_apply), mid_top(b_err), dashed=True)
    c.draw.text(
        (60, 1020),
        "원칙: 승인 전에는 요구사항·WBS·추적·인력 데이터가 바뀌지 않는다(분석 결과는 ChangeRequest 안에만). 사용자가 입력한 값(user_decision·user_override)과 규칙/AI 추론(source)은 분리 저장한다.\n투입계획이 업로드되지 않으면 인력 자동 갱신을 주장하지 않고 시나리오 6(사용자 판단)으로 둔다. 순환 의존 등 계산 불가 사유는 error로 표시하고 승인을 막는다.",
        font=font(19),
        fill="#555555",
    )
    c.legend(60, 1130, LEGEND[:4])
    c.legend(600, 1130, LEGEND[4:])
    return c


# --- 5. 역할 ↔ 도구 ↔ MCP 매트릭스 -------------------------------------------------------------
MATRIX_HEADERS = [
    "역할",
    "내장 도구",
    "pwa MCP 도구",
    "출력 스키마",
    "호출하는 코드",
    "결과를 쓰는 코드",
]
MATRIX_ROWS = [
    [
        "rfp_analyst",
        "—",
        "search_source_text, get_source_block",
        "RfpAnalysis",
        "StepRunner.run_rfp_analysis",
        "조사 주제·기간 힌트·목차 결정",
    ],
    [
        "requirement_extractor",
        "—",
        "—",
        "RequirementExtraction",
        "RequirementService.extract",
        "ID 발급·출처 검증",
    ],
    [
        "requirement_verifier",
        "—",
        "—",
        "VerificationReport",
        "RequirementService.verify",
        "지적 사항 → Gate 1",
    ],
    [
        "tech_researcher",
        "WebSearch, WebFetch",
        "get_requirement, list_research",
        "ResearchReport",
        "ResearchService.run",
        "출처 재분류·FeasibilityStudy·QA-TECH",
    ],
    [
        "architect",
        "—",
        "읽기 9종",
        "ArchitectureDraft",
        "StepRunner.run_role_step",
        "GenerationService 구성도",
    ],
    [
        "planner",
        "—",
        "읽기 9종",
        "WBSDraft",
        "StepRunner.run_role_step",
        "PlanningService.build_plan (일정은 코드)",
    ],
    [
        "proposal_writer",
        "—",
        "읽기 9종",
        "ProposalContent",
        "StepRunner.run_role_step",
        "PPT 문안·목차",
    ],
    [
        "document_generator",
        "—",
        "읽기 9종",
        "DocumentPlan",
        "StepRunner.run_role_step",
        "문서 계획 (파일은 코드)",
    ],
    [
        "qa_reviewer",
        "—",
        "읽기 9종 + verify_deliverable_file",
        "QaReport",
        "QaService (qa_use_agent)",
        "QA-AI-nn 사람 검토 항목",
    ],
    [
        "semantic_differ",
        "—",
        "list_requirements, get_requirement",
        "SemanticDiffDraft",
        "ChangeService.analyze (use_agent)",
        "규칙 분류에 덧붙임 (불일치 시 AMBIGUOUS)",
    ],
]
COMMON_CONTROL = "공통 통제: 금지 도구 Bash·Write·Edit·NotebookEdit·Agent·Skill·KillShell / permission_mode=dontAsk / 허용 목록 밖 도구는 PreToolUse 훅이 거부 / 내부·사설 IP URL 차단 / 도구 호출 기록 비밀값 마스킹 / 역할별 턴·예산·시간·재시도 상한"


def diagram_matrix() -> Canvas:
    c = Canvas.new(2400, 1100)
    c.title(
        "5. 역할 ↔ 도구 ↔ MCP 매트릭스 (roles.py 기준)",
        "스킬·서브에이전트 없음. 읽기 9종 = get_project, list_requirements, get_requirement, search_source_text, get_source_block, list_research, list_findings, list_gates, get_prior_output",
    )
    widths = [300, 260, 460, 300, 480, 520]
    x0, y0, rh = 40, 130, 64
    f_h, f_b = font(21, True), font(19)
    x = x0
    for w, h in zip(widths, MATRIX_HEADERS, strict=True):
        c.draw.rectangle((x, y0, x + w, y0 + rh), fill="#BDD7EE", outline=C_LINE, width=2)
        c.draw.text((x + 12, y0 + 18), h, font=f_h, fill=C_TEXT)
        x += w
    for r, row in enumerate(MATRIX_ROWS):
        y = y0 + rh * (r + 1)
        x = x0
        for i, (w, cell) in enumerate(zip(widths, row, strict=True)):
            fill = C_AGENT if i == 0 else (C_MCP if i in (1, 2) else WHITE)
            c.draw.rectangle((x, y, x + w, y + rh), fill=fill, outline=C_LINE, width=1)
            c.draw.text((x + 12, y + 18), cell, font=f_b, fill=C_TEXT)
            x += w
    c.draw.text((40, y0 + rh * 12 + 20), COMMON_CONTROL, font=font(19), fill="#555555")
    return c


# --- PPTX ----------------------------------------------------------------------------------------
def build_pptx(images: list[tuple[str, Path]]) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)
    tb = s.shapes.add_textbox(Inches(0.8), Inches(2.3), Inches(11.7), Inches(2.5))
    tf = tb.text_frame
    tf.text = "Proposal Writer Agent — 에이전트 · MCP · 도구 · 코드 흐름"
    tf.paragraphs[0].runs[0].font.size = Pt(36)
    tf.paragraphs[0].runs[0].font.bold = True
    p = tf.add_paragraph()
    p.text = "구현 기준 2026-10-15 · 원본: docs/FLOW_DIAGRAM.md · 렌더링: scripts/render_flow_diagrams.py (Pillow)"
    p.runs[0].font.size = Pt(18)
    p = tf.add_paragraph()
    p.text = "스킬·서브에이전트는 사용하지 않음. 에이전트가 쓰는 것은 pwa MCP 읽기 도구 10종과 tech_researcher의 WebSearch/WebFetch뿐이며, 파일·ID·일정·QA·게이트는 코드가 수행한다."
    p.runs[0].font.size = Pt(16)
    for title, path in images:
        s = prs.slides.add_slide(blank)
        tb = s.shapes.add_textbox(Inches(0.4), Inches(0.15), Inches(12.5), Inches(0.6))
        tb.text_frame.text = title
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(22)
        tb.text_frame.paragraphs[0].runs[0].font.bold = True
        with Image.open(path) as im:
            w, h = im.size
        max_w, max_h = Inches(12.7), Inches(6.5)
        scale = min(max_w / w, max_h / h)
        pw, ph = int(w * scale), int(h * scale)
        s.shapes.add_picture(
            str(path),
            Emu(int((prs.slide_width - pw) / 2)),
            Inches(0.85),
            width=Emu(pw),
            height=Emu(ph),
        )
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("flow_01_overall.png", "1. 전체 구조", diagram_overall),
        ("flow_02_agent_call.png", "2. 에이전트 1회 호출 시퀀스", diagram_sequence),
        ("flow_03_proposal_pipeline.png", "3. 제안 단계 파이프라인·게이트", diagram_proposal),
        ("flow_04_build_changes.png", "4. 구축 단계 변경관리 흐름", diagram_build),
        ("flow_05_role_tool_matrix.png", "5. 역할 ↔ 도구 ↔ MCP 매트릭스", diagram_matrix),
    ]
    images: list[tuple[str, Path]] = []
    for name, title, fn in jobs:
        path = OUT_DIR / name
        fn().save(path)
        images.append((title, path))
        print("wrote", path)
    pptx_path = REPO / "docs" / "FLOW_DIAGRAM.pptx"
    pptx_path.write_bytes(build_pptx(images))
    print("wrote", pptx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
