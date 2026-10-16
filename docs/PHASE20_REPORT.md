# Phase 20 보고서 — 편집 가능 객체 강화: 네이티브 차트·UI 목업 컴포넌트·그룹화·참고 그림 (2026-10-16)

[개선 계획](IMPROVEMENT_PLAN_2026-10.md) 20단계. 요청서 §10(편집 가능 산출물: 차트·목업 개별 객체·그룹 해제·사진 허용)·§12(python-pptx 지원 범위 활용)에 해당한다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| 네이티브 차트 | 새 모듈 `charts.py`: `add_category_chart`(막대·세로 막대·누적·선·원·도넛, 계열 색·데이터 레이블·축 글꼴), `add_gantt_chart`(누적 가로 막대 간트: 첫 계열 = 착수일 기준 시작 offset(투명), 둘째 = 기간(일), 범주 축 역순, 값 축 '일' 서식·제목), `chart_from_spec`(VisualSpec `kind=chart`: headers=[범주, 계열…], rows=[[범주, 값…]]). 덱: **역할별 공수**(가로 막대, 제출용·발표용), **요구사항 통계**(유형별 필수/선택 누적 세로 막대, 제출용 요구사항 표 뒤), **제출용 일정(간트)**(네이티브 간트; 발표용은 월 라벨이 있는 도형 일정 축 유지). 차트 데이터는 PowerPoint 데이터 시트에서 직접 수정 가능 | `generators/pptx/charts.py`(신규), `generators/pptx/decks.py` |
| UI 목업 컴포넌트 | `draw_screen` 재작성: `VisualItem.kind`(section/input/button/menu/tab/message/table/list/chart)에 따라 입력 필드(라벨+상자)·버튼·좌측 메뉴 항목(개별 상자, 첫 항목 선택 상태)·상단 탭·안내/오류 메시지 띠·목록 표(머리글 열+행 띠)·목록·차트 영역(막대 자리표시)을 **개별 도형**으로 그린다 | `generators/pptx/shapes.py`, `agents/schemas.py` |
| 그룹화 | `shapes.group()` 도우미(`add_group_shape`). 화면 목업 전체, 카드마다, 수치 카드마다, 데이터 모델 엔티티마다 그룹으로 묶어 PowerPoint에서 통째로 이동·크기 조정하고 **그룹 해제**로 개별 편집 가능. 표·차트·그림은 그룹 밖 | `generators/pptx/shapes.py` |
| 도식 종류 | 에이전트 선택 도식 **14종**(`AGENT_VISUAL_KINDS`: Phase 19의 13종 + `chart`). `VisualSpec.chart_type`, 프롬프트 규칙 10에 chart·screen 컴포넌트 지정 추가 | `shapes.py`, `schemas.py`, `prompts/proposal_writer.md` |
| 참고 그림 삽입 경로 | 문서 종류 **`참고 그림(사진·일러스트)`**(`DocumentKind.PICTURE`, PNG/JPG, 제안 단계 선택 입력, 추출 대상 아님). 파일명 `<태그>__<설명>.ext`(UI가 그림 종류 선택·설명 입력으로 붙여 줌; 태그 없으면 reference). `GenerationContext.pictures`로 덱에 전달되어 제안 문안 소절 `picture`가 참조한 소절 뒤에 "— 참고 그림" 슬라이드(태그 달린 그림, `image_slide`)로, 참조되지 않은 그림은 제출용 부록 '참고 그림'으로 들어간다(발표용은 참조된 것만). 제안 문안 브리프 `<data>.pictures`에 목록 제공, 프롬프트 규칙 17 | `models/enums.py`, `services/document_service.py`, `ingest/service.py`, `generators/base.py`(`parse_picture_name`), `generators/service.py`, `decks.py`, `ui/app_pages/project.py` |
| QA·명세 | `check_pptx`가 그룹 안 도형까지 평탄화해 넘침·겹침·경계를 검사. 슬라이드 명세가 차트·그룹 수를 세고 `rendered_layout`에 `chart` 추가 | `validation/deliverables.py`, `generators/pptx/slide_spec.py` |
| 대행 스크립트 | 자리표시 사진(Pillow 생성, `photo__…png`) 등록과 '사업 이해' 소절 `picture` 참조 | `scripts/run_manual_agents.py` |

## 2. 실제 확인 결과

- pytest **274 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase20_editable_objects.py` 4건: 네이티브 차트 객체(종류·범주·계열 값·간트 offset/기간·역순 축·VisualSpec chart·숫자 파싱), 화면 목업(탭·메뉴·입력·버튼·메시지·표·차트 영역이 개별 도형 20개 이상, 그룹 1개, 그림 0; 카드 그룹), 덱(제출용에 간트·공수·통계 차트 3종, 참조 그림 1장만 삽입·부록 중복 없음, 명세 chart/picture 집계, QA-FILE-12 예외 통과, 발표용 참조 그림·공수 차트), 참고 그림 문서 종류(허용·추출 제외·컨텍스트 목록). Phase 13·19 도식 테스트는 그룹 평탄화로 조정. `ruff check/format`, `mypy src`(114 파일) 통과.
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답·대행 승인, 프로젝트 `(객체 20)`): 제출용 30장 — 네이티브 차트 3개(8장 요구사항 통계 누적 세로 막대, 21장 간트 누적 가로 막대, 23장 역할별 공수 가로 막대), 그룹 8개, 태그 달린 사진 1장(6장 '사업 이해 — 참고 그림'); 발표용 22장 — 차트 1개(공수), 그룹 10개, 사진 1장. 통합 QA **38항목 중 37 실행·33 통과·0 실패·4 검토 필요**(QA-TECH-01/02/05/07, 기존과 동일)·1 미실행(QA-RFP-07), gate3·gate4 PASS, **QA-FILE-12 통과(사진 예외 2건 기록)**, QA-FILE-03/04(넘침·겹침, 그룹 안 도형 포함) 통과. 슬라이드 명세 `rendered_layouts`에 chart 3·picture 1(제출용) 집계.
- 실제 Claude 모델로 `screen` 컴포넌트·`chart` 도식·`picture` 참조를 쓴 결과는 없다(크레딧 부족). 대행 fixture는 차트 도식을 쓰지 않았으므로 VisualSpec `chart`는 단위 테스트로만 확인했다.

## 3. 한계·다음 작업

- 네이티브 간트의 값 축은 날짜가 아니라 '착수일 기준 경과 일수'다(python-pptx 범주형 차트 제약). 월 단위 눈금이 필요하면 발표용의 도형 일정 축이나 Excel 간트를 쓴다.
- 차트 글꼴·색은 코드 값(테마 색 아님)이며 템플릿 테마와 자동으로 맞지 않는다. 그룹의 좌표·크기는 python-pptx가 자식 도형으로 재계산한다.
- 참고 그림은 등록 파일명 규칙(`<태그>__<설명>`)에 의존한다. 그림 크기는 슬라이드 본문 영역에 맞춰 비율 유지로 줄일 뿐 자르기·배치 지정은 없다.
- 다음: 21단계(PowerPoint COM 렌더링·재열기 QA, QA-EDIT-01~10 편집 가능성 체크리스트, QA-FILE-13 페이지 제한, 회귀 테스트 보강, 최종 보고서 §18 13항목).
