# Phase 21 보고서 — 실제 렌더링·편집 가능성 QA·페이지 제한·회귀 테스트 (2026-10-16)

[개선 계획](IMPROVEMENT_PLAN_2026-10.md) 21단계(마지막). 요청서 §13(QA 분리·실제 렌더링·체크리스트 10항목)·§8(페이지 제한)·§14(회귀 테스트)·§18(최종 완료 보고)에 해당한다. 최종 완료 보고는 [FINAL_REPORT_IMPROVEMENT_2026-10.md](FINAL_REPORT_IMPROVEMENT_2026-10.md)에 13항목으로 정리했다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| 실제 렌더링·재열기 | 새 모듈 `validation/render.py`: `com_available()`(레지스트리로 PowerPoint COM·pywin32 확인, PowerPoint를 띄우지 않음), `render_pptx(path, out_dir)`(PowerPoint를 **읽기 전용·창 없이** 열어 슬라이드마다 PNG 1280px 내보내기 → COM 슬라이드 수 ↔ python-pptx 슬라이드 수 대조 → 저장 왕복(메모리) 후 재열기 → PNG 앞 3장 Pillow 검증). 원본은 수정하지 않는다. 엔진이 없으면 `available=False` | `validation/render.py`(신규) |
| QA-FILE-14 실제 렌더링·재열기 | 제출용·발표용 덱을 `11_QA_Validation_Reports/render/<덱 이름>/slide_NN.png`로 내보내고 결과를 판정. 설정 `qa_render_check`(`PWA_QA_RENDER_CHECK`, 기본 꺼짐)가 꺼져 있으면 **미실행·해당 없음**(게이트를 막지 않음), 켰는데 PowerPoint가 없으면 **미실행·검토 필요**(gate4 사람 확인). QA 보고서 범위(scope)에 렌더링 요약(장 수·시간) 기록 | `validation/independent_qa.py`, `validation/qa_service.py`, `config/settings.py` |
| QA-FILE-13 페이지 제한 | RFP 구조 프로파일(코드 파싱 `page_limit`) → RFP 분석(에이전트 `page_limit` 문구) 순으로 제한 쪽 수를 얻어 제출용 **본문 슬라이드 수**(표지·목차·장 구분 제외 추정)와 대조. 초과 = 실패, 90% 이상 = 검토, 제한 문구 없음 = 미실행 | `independent_qa.py`, `qa_service.py` |
| QA-EDIT-01~10 편집 가능성 체크리스트 | 새 범주 `QaCategory.EDITABILITY`(gate4). 01 텍스트 편집(글자 든 그림 없음·빈 상자 과다 아님) · 02 네이티브 표(제출용 1개 이상) · 03 도형·연결선(자유형 과다 아님) · 04 네이티브 차트(차트 이미지 없음, 제출용 차트 없으면 검토) · 05 그룹 해제 가능(자식 2개 이상·깊이 3 이하) · 06 그림 정책(허용 태그만, 예외 기록) · 07 글꼴(기본·템플릿 글꼴 집합) · 08 발표자 노트(발표용 본문 슬라이드 절반 이상) · 09 레이아웃·경계 · 10 재열기 안정성(저장 왕복 후 슬라이드·도형 수 동일). 01·02·04·06·10 필수(재생성으로 자동 수정 가능), 나머지는 검토. 그룹 안 도형까지 평탄화해 검사 | `independent_qa.py` `check_editability` |
| QA 범주 분리 실행 | `QaService.run(categories=…)`: 선택 범주만 실행하고 나머지는 "범주 선택으로 미실행"(통과로 세지 않음). 보고서 §3에 **범주별 집계**(내용 3범주 / 파일 품질·디자인·안정성 / 편집 가능성). `QaCategory.label` 추가, 보고서 scope 를 라벨로 표기 | `qa_service.py`, `models/qa.py` |
| 발표자 노트 보강 | 발표용 소절 슬라이드에 에이전트 노트가 없으면 `[발표 노트 초안] 제목: 본문 요약`을 코드가 채운다(QA-EDIT-08이 렌더링 QA 도입 전 대행 흐름에서 0/11로 검출한 것을 해소) | `generators/pptx/decks.py` `_fill_default_notes` |
| UI·스크립트 | 산출물 화면 QA 버튼 앞에 '실제 렌더링·재열기 검증' 체크(COM 있으면 기본 켬, 없으면 비활성·사유 표시)와 'QA 범주' 다중 선택. `StepRunner.run_qa(render_check, categories)`. `run_manual_agents.py`는 렌더링 켬, `run_regression.py --render` | `ui/app_pages/deliverables.py`, `orchestrator/runner.py`, `scripts/` |
| 템플릿 장 라벨 | 렌더링 PNG에서 장 제목("사업 관리 방안")이 템플릿 라벨 상자 안에서 두 줄로 꺾이는 것을 확인 → 라벨 덮어쓰기는 줄바꿈 끔·내부 여백 축소·여백을 뺀 폭으로 글꼴 맞춤 | `generators/pptx/template.py` |

## 2. 실제 확인 결과

- pytest **279 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase21_render_qa.py` 5건: COM 렌더링(PowerPoint 없으면 `skip`=미실행; 이 PC에서는 3장 PNG·재열기 성공), 엔진 없음 결과, 생성 덱의 QA-EDIT 10항목 실행·필수 통과·사진 예외 기록·구축 모드 미실행, 페이지 제한 초과/통과, 범주 필터. E2E(`test_phase7_qa.py`)는 총 50항목·47 실행·3 미실행(RFP-07·FILE-11·FILE-14 꺼짐)·FILE-13 통과(모의 RFP '100쪽 이내')·EDIT 10항목 실행으로 조정. `ruff check/format`, `mypy src`(115 파일) 통과.
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답·대행 승인, 렌더링 켬, 프로젝트 `(렌더링 21)`): 통합 QA **50항목 중 48 실행·44 통과·0 실패·4 검토 필요**(QA-TECH-01/02/05/07, 기존과 동일)·2 미실행(QA-RFP-07, QA-FILE-13 제한 문구 없음), gate3·gate4 PASS. **QA-FILE-14 통과 — 제출용 30/30장·발표용 22/22장 PNG 내보내기, 재열기 성공(13.5s·5.5s)**, PNG는 `11_QA_Validation_Reports/render/`. QA-EDIT-01~10 전부 통과(EDIT-06 사진 예외 2건 기록). 렌더링 PNG를 열어 간트 차트·사진·카드가 PowerPoint에서 실제로 그려짐을 확인했고, 장 라벨 줄바꿈 문제를 발견해 수정했다(수정 후 재실행 결과는 아래).
- 장 라벨 수정(줄바꿈 끔·여백 반영·덮개 30% 확장) 후 재실행 (렌더링 21b)·(렌더링 21c) 모두 QA 50항목 중 48 실행·44 통과·0 실패·4 검토·2 미실행, gate3·gate4 PASS, QA-FILE-14 PASS(제출용 30/30·발표용 22/22 PNG, 재열기 성공, 9.4s·3.8s). 21c PNG에서 장 라벨이 한 줄로 들어가고 레이아웃 잔여 글자가 사라진 것을 육안 확인
- 실제 Claude 모델 호출은 여전히 없다(크레딧 부족). 렌더링 검증은 이 PC(PowerPoint 16.0)에서만 수행했다.

## 3. 한계

- QA-FILE-14는 "열리고 그려지며 장 수가 맞고 다시 열린다"까지만 판정한다. 글자 깨짐·겹침 같은 **모양 품질은 PNG를 사람이 봐야 한다**(보고서에 PNG 경로 기록).
- PowerPoint가 없는 PC(서버·CI)에서는 항상 미실행이며, LibreOffice 대체 경로는 없다.
- QA-EDIT는 객체 구조 휴리스틱이다(글꼴 집합·노트 비율·그룹 깊이). 페이지 제한의 본문 슬라이드 수는 표지·목차·장 구분 제외 추정값이다.
