# Phase 16 보고서 — 진행 기록·산출물 manifest·그림 정책·라이브러리 검토 (2026-10-16)

[개선 계획](IMPROVEMENT_PLAN_2026-10.md) 16단계. 요청서 §10.2(사진·일러스트 허용), §12(라이브러리 검토), §15(manifest), §16(진행 기록)에 해당한다.

## 1. 무엇을 바꿨나

| 요건 | 변경 | 위치 |
|---|---|---|
| §15 산출물 manifest | `Output/<프로젝트>/manifest.json`: 생성 실행(run)마다 산출물(종류·category submission/presentation/excel/qa/source·경로·버전·sha256·크기·ID)·보조 파일(구성도·차트 PNG)·오류·시각을 **누적** 기록. 통합 QA 완료 시 그 run에 판정·건수·게이트·보고서 경로·실패/검토/미실행 항목·그림 예외를 첨부. 구축 단계 재생성도 `regeneration` run으로 기록. manifest 기록 실패는 생성을 막지 않고 검토 메모로 남김 | `storage/manifest.py`(신규), `generators/service.py`, `validation/qa_service.py`, `changes/service.py` |
| §10.2 그림 정책 | 사진·일러스트·장식 배경·참고 이미지는 **허용 태그**(`photo` / `illustration` / `decoration` / `reference`)를 붙여 삽입(`image_slide(..., tag=)`, 도형 이름 `<태그>:<설명>`; 잘못된 태그는 삽입 전 거부). QA-FILE-12는 **태그 없는 그림**(표·구조도·차트·목업을 이미지로 넣은 것)만 실패시키고, 허용 그림은 `예외:` 메시지(INFO)로 판정을 바꾸지 않은 채 보고서·manifest `picture_exceptions`에 기록 | `generators/base.py`(`PICTURE_TAGS`·`picture_name`·`picture_tag`), `generators/pptx/builder.py`·`template.py`, `validation/deliverables.py`(`_pictures`), `validation/independent_qa.py` |
| §12 라이브러리 검토 | python-pptx(텍스트·표·도형·연결선·네이티브 차트·그림·그룹 지원, SVG·렌더링 미지원)·openpyxl·Pillow·PowerPoint COM(이 PC에 등록, pywin32 설치)을 확인해 유지/보완 결정 문서화 | `docs/LIBRARY_REVIEW.md`(신규) |
| §16 진행 기록 | `workspace/DEVELOPMENT_STATUS.md/.json`·`WORK_LOG.md` 신설(계획 단계에서 생성, 이번 단계부터 갱신). `scripts/record_test_status.py`가 pytest 요약을 JSON `tests`에 기록(해석 실패 시 기록하지 않음). `.gitignore`에 상태 파일 예외 | `workspace/`, `WORK_LOG.md`, `scripts/record_test_status.py`, `.gitignore` |

## 2. 실제 확인 결과

- pytest **257 passed, 1 skipped, 2 deselected**(전체). 신규 `tests/unit/test_phase16_manifest_pictures.py` 4건: manifest 생성 누적·QA 첨부·category·해시·파일 존재, 태그 없는 그림 실패/태그 그림 예외(INFO) 기록, `image_slide` 태그 이름·잘못된 태그 거부·QA 통과, 상태 기록 스크립트 요약 해석. `ruff check/format`, `mypy src` 통과.
- 실샘플 재검증(계산기 RFP + 고객 템플릿 2종, API 키 없이 대행 응답): `manifest.json`에 run 1건(산출물 9건, 보조 파일 5건), QA 첨부(35항목 중 34 실행·30 통과·0 실패·4 검토·1 미실행, gate3·gate4 PASS), 그림 예외 0건. 산출물 경로: `Output/Project_20261016_공학용_계산기_웹_개발_(manifest_16)/`.
- 연결 상태: Claude API 키 없음(실제 모델 호출 미검증), 인프로세스 MCP `pwa` 연결(2026-10-15 점검), PowerPoint COM 등록 확인(렌더링은 21단계에서 사용).
- 생성하지 않은 산출물·실행하지 않은 테스트는 없다. 렌더링 검증은 아직 미구현(미실행)이다.

## 3. 한계·다음 작업

- 허용 그림은 아직 덱 생성 로직에서 쓰이지 않는다(에이전트가 사진을 지정하는 필드는 19단계 `evidence`/시각화 명세와 함께 추가). 지금은 빌더 API와 QA 정책만 갖췄다.
- manifest는 생성·QA 시점에만 갱신되며 최종본 확정(`13_Final_Deliverables` 복사)은 기록하지 않는다 → 21단계 최종 보고와 함께 추가.
- 다음: 17단계(RFP 분석 항목 확장·추적표 대응 페이지·근거 구분).
