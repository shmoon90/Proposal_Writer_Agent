# RISK_REGISTER — 위험, 외부 의존성, 비용, 미확정 사항

문서 버전 0.1 · 2026-10-15

---

## 1. 위험 목록

| ID | 위험 | 영향 | 가능성 | 대응 | 상태 |
|---|---|---|---|---|---|
| R-01 | `ANTHROPIC_API_KEY` 미설정. claude.ai 구독 로그인은 서드파티 앱에 허용되지 않음(공식 문서) | 런타임 에이전트 실행 불가 | 확실(현재) | Phase 1 전 Console에서 API 키 발급, `.env` + `python-dotenv` 로드. 키 없으면 LLM 테스트 skip | 열림 |
| R-02 | Agent SDK는 0.x 버전으로 API 변경이 잦음 (0.2.165 설치, 0.2.167 최신) | 업그레이드 시 호환 깨짐 | 중 | `claude-agent-sdk>=0.2.165,<0.3` 고정, `runner.py` 한 곳에만 SDK 의존, 변경 로그 확인 후 업그레이드 | 열림 |
| R-03 | LLM 비용 초과 (긴 RFP, 서브에이전트 폭주) | 예산 초과 | 중 | `max_budget_usd`/`max_turns`/깊이 1/동시 4 제한, 단계별 비용 기록·UI 표시, 섹션 분할은 sonnet | 열림 |
| R-04 | 내장 `WebSearch`는 Claude API·Foundry에서 제공, Bedrock 미제공 | Bedrock 전환 시 기술 조사 불가 | 낮음 | 1차는 Claude API. Bedrock 필요 시 외부 검색 MCP(예: Brave/Tavily) 어댑터를 `research/`에 추가 | 열림 |
| R-05 | 에이전트가 입력 문서 안의 지시문을 명령으로 오인(프롬프트 인젝션) | 잘못된 출력, 도구 오남용 | 중 | 문서는 `<document>` 데이터 블록으로 전달, 쓰기 도구 전면 금지, 훅으로 경로 제한, 출력은 스키마 검증만 수용 | 열림 |
| R-06 | Streamlit 동기 실행 모델과 Agent SDK asyncio 충돌, 긴 작업 중 rerun | 작업 중단·중복 실행 | 중 | `jobs.py`에서 별도 스레드 이벤트 루프 + 작업 테이블(SQLite)로 상태 공유, 진행률 폴링. `st.fragment`/`st.status` 활용. Phase 1에서 스파이크 | 열림 |
| R-07 | OCR 엔진 미확정: Tesseract 미설치, `rapidocr-onnxruntime` 한국어 모델은 별도 확인 필요 | 스캔 RFP 처리 불가 | 중 | Phase 2 스파이크로 두 후보 비교(한국어 인식률·설치 난이도). 미결정 시 "스캔 PDF 미지원" 명시 | 열림 |
| R-08 | HWP 형식 RFP (공공 RFP 다수) | 입력 불가 | 높음 | 1차: 사용자가 PDF 변환 후 업로드(안내 문구). 2차: `pyhwp`/`hwp5txt` 검토(Phase 7) | 열림 |
| R-09 | pandas 3.x(최신 3.0.6) 변경점(Copy-on-Write, 문자열 dtype) + streamlit 1.66 호환 | 예기치 않은 동작 | 중 | Phase 1에서 pandas 2.x 고정 테스트. pandas 의존 최소화(openpyxl 직접 사용 우선) | 열림 |
| R-10 | 한글 폰트: matplotlib 기본 폰트에 한글 없음, PPT 폰트 임베딩 불가 | 다이어그램 글자 깨짐 | 높음 | Windows `malgun.ttf` 경로를 설정으로 지정, 없으면 경고. 폰트 설정은 `generators/diagrams/fonts.py` 한 곳 | 열림 |
| R-11 | 구축 단계 업로드 Excel 양식이 고객사마다 다름 | 파싱 실패 | 높음 | B1 매핑 제안 + 사용자 확정 + 템플릿 프로파일 저장. 필수 필드 누락 행은 오류 목록으로 보고 | 열림 |
| R-12 | 구조화 출력 실패(`error_max_structured_output_retries`) 또는 빈 결과 | 단계 실패 | 중 | 스키마 단순화(필수 필드 최소), 오류 첨부 1회 재시도, 입력 분할 | 열림 |
| R-13 | 요구사항 추출 누락·과잉 (LLM 품질) | 제안 품질 저하 | 중 | 독립 검증 에이전트 + 사람 승인 게이트 + 원문 출처 필수 | 열림 |
| R-14 | 공수·일정 산정 근거 부실 | 신뢰도 저하 | 중 | `estimate_basis` 필수 검증, 산정근거 시트 자동 생성 | 열림 |
| R-15 | 동일 Output 경로 덮어쓰기·수동 편집 충돌 | 데이터 손실 | 낮음 | 덮어쓰기 금지, 버전 파일명, sha256 대조, 수동 편집 파일은 기준 데이터로 쓰지 않음 | 열림 |
| R-16 | Windows 경로 길이(260자) 초과, 한글 파일명 인코딩 | 저장 실패 | 낮음 | slug 길이 제한, 긴 경로 허용 레지스트리 안내, UTF-8 고정 | 열림 |
| R-17 | Agent SDK 번들 `claude.exe`가 Windows Defender·사내 보안 정책에 차단 | 에이전트 기동 실패 | 낮음 | `CLINotFoundError`/`ProcessError` 포착 후 원인·조치 안내, `cli_path` 옵션으로 수동 지정 | 열림 |
| R-18 | API 데이터 보존 정책·보안: RFP가 외부 API로 전송됨 | 고객 보안 요건 위반 가능 | 중 | 프로젝트 생성 시 외부 전송 고지, 민감 문서는 사용자 책임으로 마스킹, 필요 시 Bedrock/Vertex 경로(R-04 연계) | 열림 |
| R-19 | **PyMuPDF DLL이 개발 PC의 애플리케이션 제어 정책(WDAC/AppLocker)에 차단됨** (`_mupdf.pyd` 로드 실패, 2026-10-15 확인) | PDF 처리 불가 | 확실(현재) | PDF 스택을 순수 Python 조합으로 교체: 텍스트·표 `pdfplumber`, 암호화·손상 판별 `pypdf`, 스캔 페이지 렌더링 `pypdfium2`(DLL 로드 확인됨), 실패 시 `pypdf` 내장 이미지 추출로 대체. 다른 PC에서도 같은 정책이면 onnxruntime·pypdfium2도 차단될 수 있으므로 설치 후 `python -c "import pypdfium2, onnxruntime"`로 확인 | 완화됨 |
| R-20 | OCR 결과의 띄어쓰기 누락·오탈자 (rapidocr 한국어 모델) | 요구사항 수치·용어 오류 | 중 | OCR 블록은 신뢰도와 `ocr="1"` 태그를 달아 에이전트에 전달, 저신뢰 페이지는 검토 필요로 표시, OCR 비율이 높으면 Gate 0 NEEDS_HUMAN_REVIEW | 열림 |
| R-21 | Anthropic 계정 크레딧 부족으로 에이전트 응답·웹 검색 실행 품질을 검증하지 못함 (2026-10-15, `Credit balance is too low`) | LLM 의존 기능 전부 미검증 | 확실(현재) | 러너가 오류를 분류해 충전 조치를 표시. 크레딧 충전 후 `scripts/run_phase2_llm.py`, `pytest -m llm` 실행 | 열림 |
| R-22 | Agent SDK 세션 중단(interrupt)이 스트리밍 모드에서만 동작, 시간 제한은 SDK 옵션이 없어 워치독 태스크로 구현 | 긴 작업이 제때 멈추지 않을 수 있음 | 중 | `ClaudeSDKClient` 스트리밍 사용, 0.5초 워치독이 취소 토큰·시간 제한을 감시해 `interrupt()`; 실제 장시간 세션에서는 미검증 | 열림 |
| R-23 | 외부 MCP 서버(HTTP)는 네트워크·인증 상태에 따라 `failed`/`needs-auth` | 역할 실행 실패 | 중 | init 메시지 상태를 러너가 기록하고 실패 서버를 오류 원인에 포함. 연결 점검 UI/스크립트 제공 | 완화됨 |
| R-24 | 웹 검색 결과의 환각(존재하지 않는 문서·버전 인용) | 잘못된 기술 조사 | 중 | 프롬프트에 "열람한 URL만 인용" 지시, 코드가 출처 없는 사실을 미확인으로 강등하고 도메인 규칙으로 신뢰도 재분류, 사람 확인 플래그 | 열림 |
| R-25 | **matplotlib 렌더링 DLL(`_backend_agg`)이 앱 제어 정책에 차단** (2026-10-15) | 구성도·차트 생성 불가 | 확실(현재) | Pillow(동작 확인)로 도형·차트를 직접 그리도록 교체, matplotlib 제거. 다른 PC에서는 `python -c "import PIL.ImageDraw"`로 확인 | 완화됨 |
| R-26 | 산출물 기본값(공수·기술 스택·수용여부)이 사람 확정 없이 제안서에 들어감 | 근거 없는 수치·기술 제시 | 중 | 기본값은 "검토 필요/미정"으로 표기하고 QA review_items·Gate 4 사유에 포함. 발표용 PPT에 '미정' 과다 시 경고 | 열림 |
| R-27 | PPT 텍스트 넘침·겹침 검사가 글자 수 기반 추정 | 실제 렌더링 불일치 | 낮음 | 도형 경계·겹침은 좌표로 검사, 넘침은 추정 경고만. 최종 승인 전 PowerPoint에서 육안 확인 | 열림 |
| R-28 | 규칙 기반 의미 비교(문자 bigram·의도 키워드)가 복합 문장·영문 혼용에서 분류를 놓침 (Phase 6) | 수정/삭제 오분류 | 중 | 경계 구간은 AMBIGUOUS로 두고 사용자 확정 없이는 반영 불가. AI(`semantic_differ`) 결과는 덧붙임만 하고 불일치 시 AMBIGUOUS로 낮춤 | 열림 |
| R-29 | 변경 공수 추정이 유사도 비율 휴리스틱(0.2~0.6)·유사 Task 중앙값 | 일정·인력 영향 과소/과대 | 중 | '범위'와 근거를 함께 표시, 화면에서 공수 확정값 입력 시 '확정'으로 대체. 승인 전 사람이 검토 | 열림 |
| R-30 | 기존 산출물 양식이 표준과 크게 달라 헤더 매핑 실패 | 적재 불가·오매핑 | 중 | 동의어·유사도 제안 + 필수 컬럼은 사용자 확정 전 적재 거부, 품질 검사(중복 ID·날짜·수식) 경고 | 열림 |
| R-31 | 통합 QA의 RFP 적합성 검사가 키워드('하여야 한다' 등)·정규화 문자열 기반이라 누락·과잉 판정에 한계 (Phase 7) | 누락 요구사항을 못 잡거나 과다 지적 | 중 | 판정은 NEEDS_HUMAN_REVIEW로만 내고 FAIL은 출처 불일치·범위 오표기 같은 확정 가능한 경우에 한정. qa_reviewer 에이전트 검토는 보조(사람 확인 항목) | 열림 |
| R-32 | 자동 수정이 '재생성'뿐이라 데이터 기인 실패(요구사항↔WBS 누락, 공수 불일치)는 자동 해결 불가 | 반복 실패 → 사람 검토로 전환 | 낮음 | 설계 의도(기준 데이터는 자동 변경 금지). 수정 제안을 보고서에 적고 한도 도달 시 검토 대상으로 전환 | 수용 |
| R-33 | 기술 타당성 검사는 기술 조사 기록이 있어야 의미가 있음 — 조사 미실행(크레딧 부족) 시 전부 검토 필요로 표시 | Gate 2가 항상 NEEDS_HUMAN_REVIEW | 중 | 크레딧 확보 후 tech_researcher 실행, 또는 조사 결과를 수동 등록. 코드는 근거 없는 기술명을 지적만 함 | 열림 |

## 2. 외부 의존성

| 의존성 | 용도 | 상태 | 대안 |
|---|---|---|---|
| Anthropic Claude API (API 키) | 모든 에이전트 | 키 미설정 | Bedrock/Vertex/Foundry(SDK 지원, WebSearch 제약) |
| claude-agent-sdk 0.2.x + 번들 claude.exe | 에이전트 런타임 | 설치됨 | 없음 (설계 전제) |
| mcp 2.3 | 외부 MCP 서버 필요 시 | 설치됨 | 인프로세스 SDK MCP로 충분 |
| Node.js 24 | npx 기반 외부 MCP 서버 | 설치됨 | 현재 계획엔 외부 MCP 없음 |
| OCR 엔진 | 스캔 PDF | 미확정 | R-07 |
| 한글 폰트(malgun) | 다이어그램 | Windows 기본 제공 | 나눔고딕 번들 |
| PyMuPDF | PDF | PyPI 1.28.2 | pypdf(텍스트만) |

## 3. 비용 추정 (가정치, 측정 후 갱신)

가정: 모델 `claude-opus-5-5` 입력 $4/MTok·출력 $20/MTok, 보조 `claude-sonnet-5-5` $2/$10 (2026-10 기준 요율표). RFP 100페이지(약 150K 토큰) 기준.

| 단계 | 호출 | 추정 비용(USD) | 비고 |
|---|---|---|---|
| RFP 분석 + 추출(섹션 서브에이전트 sonnet) | 1 + N | 3 ~ 8 | 청크 재읽기 횟수에 좌우 |
| 독립 검증 | 1 | 2 ~ 5 | |
| 기술 조사 (WebSearch 포함) | 1 + N | 2 ~ 6 | 웹 검색 사용량 별도 과금 가능 |
| 아키텍처 + 계획 | 2 | 1 ~ 3 | |
| 문안 작성 ×2 | 2 + N | 2 ~ 5 | |
| QA | 1 | 1 ~ 2 | |
| **제안 단계 합계** | | **11 ~ 29** | 프로젝트당 |
| 구축 단계 변경 1건 | 3~4 | 0.5 ~ 2 | |

- 단계별 `max_budget_usd` 기본값: 추출 10, 검증 6, 조사 8, 기타 4. 설정으로 조정.
- Phase 2·3 완료 시 실측치로 표를 갱신한다.

## 4. 미확정 사항 (결정 필요)

| ID | 항목 | 선택지 | 결정 시점 | 담당 |
|---|---|---|---|---|
| D-01 | API 키 발급·보관 방식 | `.env` 로컬 / OS 환경변수 | Phase 1 시작 전 | 사용자 |
| D-02 | OCR 엔진 | **확정: `rapidocr` 3.10 + `onnxruntime`, 한국어 인식 모델 `korean_PP-OCRv5_rec_mobile`(첫 실행 시 12.9MB 다운로드). 모의 한국어 이미지 신뢰도 0.94~0.97 확인(2026-10-15)** | Phase 2 완료 | 개발 |
| D-03 | pandas 버전 | **확정: 2.x 고정 (`pandas>=2.2,<3`)** | Phase 1 완료 | 개발 |
| D-11 | PDF 라이브러리 | **확정: pdfplumber + pypdf + pypdfium2 (PyMuPDF는 R-19로 제외)** | Phase 2 완료 | 개발 |
| D-04 | 역할별 모델 | opus/sonnet/haiku 조합 | Phase 2 실측 후 | 사용자+개발 |
| D-05 | 다이어그램 렌더링 | **확정: Pillow 직접 드로잉 (matplotlib은 R-25로 제외, Mermaid 외부 도구 불필요)** | Phase 4 완료 | 개발 |
| D-06 | PPT 템플릿 | 기본 생성 / 사용자 .pptx 템플릿 | Phase 4 | 사용자 |
| D-07 | 인력 단가·공휴일 데이터 | 설정 파일 입력 방식 | Phase 3 | 사용자 |
| D-08 | HWP 지원 | 미지원(안내) / 변환 라이브러리 | Phase 7 | 사용자 |
| D-09 | 승인자 식별 | 단일 사용자 입력 / 로그인 | Phase 5 | 사용자 |
| D-10 | 외부 전송 고지 문구·마스킹 정책 | — | Phase 2 | 사용자 |

## 5. 설계 단계에서 확인된 사실 (가정이 아님)

- Agent SDK Python 0.2.165의 공개 API 목록과 `ClaudeAgentOptions`/`AgentDefinition` 필드 전체를 설치 패키지에서 직접 확인했다.
- 공식 문서에서 구조화 출력(`output_format` + `ResultMessage.structured_output`, draft-07 검증), 서브에이전트(`agents`, 깊이·동시성 환경변수, `max_budget_usd`), MCP 설정(stdio/http/sdk, `mcp__server__tool` 명명, `allowed_tools` 우선), 인증(API 키 필수, 구독 로그인 불허), 내장 도구 목록(WebSearch/WebFetch 포함)을 확인했다.
- MCP Python SDK 2.x에서 `FastMCP`가 `MCPServer`로 개명되었음을 설치 패키지 오류 메시지와 공식 마이그레이션 가이드에서 확인했다.
- Streamlit 1.66.0은 Python ≥3.11, pandas <4를 요구한다(wheel 메타데이터 확인).
