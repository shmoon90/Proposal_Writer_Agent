# Phase 19 보고서 — 슬라이드별 명세·기술 구체성·비전문가 표현·QA-CON-10/11 (2026-10-16)

[개선 계획](IMPROVEMENT_PLAN_2026-10.md) 19단계. 요청서 §5(슬라이드 단위 설계)·§6(기술 구체성·대안 비교)·§7(비전문가 표현·용어 설명)·§13(근거 없는 수치·추상 표현 검출)에 해당한다. Phase 18에서 확정한 브리프 형식·승인 화면·차단 범위는 바꾸지 않았다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| 슬라이드별 명세 | `ProposalSection`에 `key_message`(결론형 제목), `purpose`, `audience`(evaluator/business/technical/executive), `evidence[]`(`EvidenceRef`: kind/ref/text), `links_prev/next`, `layout_type`(9종), `tech_detail`, `terms` 추가. `ProposalContent.glossary[]`(`GlossaryTerm`). 코드는 **key_message를 리드 상자에**, lead_message·목적·독자·연결을 **발표자 노트**에, 근거를 하단 **※ 주석**(제출용 2줄, 발표용 1줄)에 넣는다 | `agents/schemas.py`, `generators/pptx/decks.py` |
| 슬라이드 디자인 명세 산출 | 덱 생성 중 소절마다 슬라이드 범위를 기록(`GenerationContext.slide_specs`)하고, 생성된 PPTX를 다시 열어 슬라이드별 제목·계획 레이아웃/실제 렌더링(text/table/visual/visual_table/picture)·도식 종류·근거·요구사항 ID·연결·노트 유무·도형 수를 합친 JSON을 저장: `07_Submission_Proposal_PPT/슬라이드명세_제출용_vX.Y.json`, `08_Presentation_PPT/슬라이드명세_발표용_vX.Y.json`. 요약에 결론형 제목·근거·목적이 없는 소절 목록을 넣고 생성 검토 항목에도 올린다. manifest `extra_files`에 기록. 산출물 화면에 "슬라이드 명세" 패널 | `generators/pptx/slide_spec.py`(신규), `generators/service.py`, `ui/app_pages/deliverables.py` |
| 시각화 13종 | 에이전트 선택 가능 도식 `AGENT_VISUAL_KINDS` 13종 = 기존 8(cards/flow/process/two_column/dataflow/screen/kpis/compare) + **raci**(책임 분담표, R/A/C/I 셀 색), **data_model**(엔티티 상자·관계 화살표 1:N), **procedure**(담당별 레인 절차), **security_layers**(네트워크→서버→응용→데이터→관리 띠), **layers**(계층 구성). 모두 자동 도형·연결선·네이티브 표(그림 없음). 코드 전용 architecture/timeline/bars는 그대로 | `generators/pptx/shapes.py` |
| 기술 소절 템플릿·대안 비교 | `TechDetail`(components/interfaces/data/operations/security/alternatives/selection_reason), `AlternativeOption`(**commercial/open_source/in_house**, 장점·단점·비용 관점·선정·근거). 제출용은 "기술 상세" 카드 슬라이드(5구분) + "대안 비교 (상용/공개/자체)" 표, 발표용은 축약 표만(셀 글꼴이 커서 항목 2개·30자·비용 열 생략) | `generators/pptx/decks.py` `_render_tech_detail` |
| 용어집 소절 | `glossary`가 있으면 제출용 부록·발표용 마무리에 "용어 설명" 표(용어·풀이·비전문가용 설명·첫 등장) | `decks.py` `_render_glossary` |
| 프롬프트 | `proposal_writer.md` 규칙 12~16: 결론형 제목(명사형 주제 금지, 40자 내외), 근거(evidence) 필수·단위 붙은 수치는 데이터에 있는 값만·과장 표현 금지, 글머리 제한(한 줄 한 사실, 하위 목록 금지), 기술 소절 템플릿과 상용/공개/자체 대안, 비전문가 표현·용어집. 규칙 10 도식 13종. 제안 문안 브리프 끝 문장도 같은 요구 | `agents/prompts/proposal_writer.md`, `generators/service.py` |
| QA | **QA-CON-10 제안 문안 추상 표현·근거 없는 수치**(gate5, 비필수): 과장 표현 16종 검출, 단위 붙은 수치(%·배·초·건·명·개월 등)가 기준 데이터 숫자 토큰(요구사항·조사·RFP 본문·WBS·인력·기간·범위/유형별 건수)이나 소절 evidence에 없으면 검토. 제안 문안이 없으면 제출용 PPT 본문의 추상 표현만. **QA-CON-11 약어·전문 용어 설명**(gate5, 비필수): 영문 약어(2~8자)가 glossary에 있거나 본문에 "약어(풀이)"/"풀이(약어)"로 설명되지 않으면 검토(RFP·WBS·PM 등 일반 약어·요구사항 ID·로마 숫자 제외). 총 **38항목** | `validation/independent_qa.py` |
| 기타 | 대행 스크립트 fixture에 결론형 제목·근거·tech_detail(상용/공개/자체)·layers 도식·용어집 5건 추가, Windows 콘솔(cp949) 출력 오류 방지 | `scripts/run_manual_agents.py` |

## 2. 실제 확인 결과

- pytest **270 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase19_slide_spec.py` 5건: 도식 5종이 그림 없이 도형·표로 그려지는지, 스키마 확장, 제출용·발표용 덱에 결론형 제목(리드)·발표자 노트(목적·독자·연결·리드)·기술 상세·대안 비교·용어 설명이 들어가고 슬라이드 명세가 범위·레이아웃·요구사항 ID·요약을 내는지, QA-CON-10(추상 표현·근거 없는 수치, evidence 수치는 통과)·QA-CON-11(용어집·괄호 풀이·일반 약어·ID 제외) 판정. 기존 E2E는 QA 실행 수 34 → 36으로 조정. `ruff check/format`, `mypy src`(113 파일) 통과.
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, 대행 응답·대행 승인, 프로젝트 `(명세 19b)`): 제출용 28장·발표용 21장, 그림 0. 슬라이드 명세 2건 저장(제출용 소절 17·에이전트 7, 도식 layers, 레이아웃 text 17/visual 6/table 5; 발표용 소절 9, visual 9/text 9/table 3), 용어 5건. 통합 QA **38항목 중 37 실행·33 통과·0 실패·4 검토 필요**(QA-TECH-01/02/05/07, 기존과 동일)·1 미실행(QA-RFP-07), gate3·gate4 PASS, gate2·gate5 NEEDS_HUMAN_REVIEW, **QA-CON-10·11 통과**. manifest `extra_files`에 `slide_spec_submission/presentation` 기록.
- 첫 실행(`(명세 19)`)에서 발견해 고친 것: ① QA-CON-10이 "부가 제안 2건"을 근거 없는 수치로 봄 → 범위 분류·유형·수용 상태별 건수를 기준 숫자에 포함. ② QA-CON-11이 HTTPS·JSON 미설명을 검출(정상 동작) → 대행 fixture 용어집에 추가. ③ 발표용 대안 비교 슬라이드의 ※ 주석 2줄이 템플릿 주석 상자를 넘침(QA-FILE-03) → 발표용은 근거 주석 1줄·대안 표 주석 없음·셀 축약. ④ 슬라이드 명세 제목이 템플릿의 장 라벨("Ⅱ")·장 머리글("사업 수행 방안")을 집음 → 소절 제목이 든 상자 우선, 2자 이하 라벨 제외. ⑤ 대행 스크립트가 cp949 콘솔에서 '—' 출력 시 예외 → UTF-8 재설정.
- 실제 Claude 모델로 `proposal_writer`를 실행한 결과는 없다(크레딧 부족). 결론형 제목·근거·용어집의 품질은 실제 실행 후 프롬프트를 보정해야 한다. 대행 fixture는 시스템 구성 소절 1건에만 명세를 채웠으므로 요약의 "결론형 제목 없음 6건"은 fixture 한계다.

## 3. 한계·다음 작업

- QA-CON-10의 수치 대조는 숫자 토큰 일치(쉼표 제거)라 단위 환산(개월↔주)·반올림은 잡지 못하며, 한 자리 수는 기준 데이터에 흔해 통과하기 쉽다. 추상 표현 목록은 16종 고정이다. QA-CON-11은 영문 대문자 약어만 본다(한글 전문 용어는 제외).
- `layout_type`은 에이전트 계획값이며 코드는 참고만 한다(실제 레이아웃은 명세의 `rendered_layout`). 슬라이드 명세는 소절 범위 기록 + 파일 재열기로 만들며, 템플릿 머리글 구조에 따라 제목 추출이 휴리스틱이다.
- 다음: 20단계(네이티브 차트 `add_chart`, UI 목업 컴포넌트, 그룹화, RACI·데이터 모델·운영·보안 도식 고도화, 허용 그림 삽입), 21단계(PowerPoint COM 렌더링 QA, QA-EDIT-01~10, QA-FILE-13 페이지 제한, 회귀 테스트, 최종 보고).
