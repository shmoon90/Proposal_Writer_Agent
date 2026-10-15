# TEST_STRATEGY — 테스트 전략

문서 버전 0.1 · 2026-10-15 · 관련: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

---

## 1. 목표와 원칙

- **결정적 코드는 100% 자동 테스트**: ID 발급, 날짜·공수, 의존 검증, 파일 경로·버전, 필수 컬럼 검사, 상태 전이.
- **LLM 호출은 계층 분리**: 에이전트 호출을 `AgentRunner` 인터페이스 뒤에 두고, 테스트에서는 `FakeAgentRunner`가 고정된 구조화 출력을 돌려준다. 실제 호출 테스트는 `@pytest.mark.llm`로 분리하고 기본 실행에서 제외한다.
- **실행하지 않은 테스트는 보고하지 않는다**: Phase 보고서에 `pytest` 실제 출력(통과/실패/건너뜀 수)을 첨부한다.
- **골든 파일**: 문서 생성과 일정 계산은 고정 입력 → 고정 출력(golden)을 비교한다. 바이너리(xlsx/pptx)는 재오픈 후 구조 비교.

## 2. 테스트 피라미드

| 계층 | 위치 | 대상 | 실행 빈도 |
|---|---|---|---|
| 단위 | `tests/unit/` | models, config, storage, requirements, planning, validation, generators(구조), changes | 매 커밋 |
| 통합(모의 LLM) | `tests/integration/` | 파이프라인 단계 연결, 승인 게이트, DB↔파일, UI 상태 전이(Streamlit `AppTest`) | 매 Phase / PR |
| LLM 계약 | `tests/integration/llm/` (`-m llm`) | 각 에이전트 프롬프트 + 스키마가 실제로 유효한 `structured_output`을 반환하는지 | 수동, API 키 필요 |
| E2E | `tests/e2e/` (Phase 5·6) | 샘플 RFP → 최종 산출물, 샘플 산출물 업로드 → 변경 → 새 버전 | Phase 종료 |
| 사람 검토 | 체크리스트 | 생성 PPT/Excel 가독성, 구성도 품질 | Phase 4·7 |

## 3. 영역별 핵심 테스트 케이스

### config / storage
- `ProjectPaths`: 동일 프로젝트명 2회 생성 시 두 번째 폴더에 식별자 접미사. 14개 하위 폴더 생성.
- `files.save()`: 기존 파일 존재 시 `FileExistsConflict` 발생, 덮어쓰기 없음. 버전 파일명 증가 규칙.
- 마이그레이션 멱등성(2회 적용 동일 스키마).
- 리포지토리: 삭제 호출이 행을 제거하지 않고 `status=deleted`로 바꾸고 `AuditEvent`를 남김.

### requirements
- `id_policy`: `REQ-F-001` 순차, 기능/비기능 별도 시퀀스, 삭제된 ID 재사용 금지, 재추출 시 매칭된 항목은 ID 유지.
- 상태 전이: 허용되지 않은 전이(`draft→baseline` 직행) 거부.
- `diff`: 필드별 before/after, 유사 후보 정규화(공백·대소문자·구두점).
- `trace`: 피벗 행·열 개수, 미추적 요구사항 목록.

### planning (골든)
- 영업일: 주말·공휴일 제외, 월말 경계.
- 의존: FS/SS/FF/SF + lag 계산, 순환 의존 `ValueError`, 자기 참조 거부.
- CPM: 전진 계산 결과 고정값, 기간 제약 초과 시 warning 결과.
- 공수: 하위 합계 = 상위, Decimal 정밀도, 배정 합 ≠ 공수 → error.
- 인력: 월별 M/M 분배(기간 걸침), 비용 = Σ(M/M × 단가).

### generators / validation
- 각 Excel 생성 후 openpyxl 재오픈: 필수 시트 존재, 헤더 컬럼 일치, 행 수 = 데이터 수, 변경이력 시트.
- PPT: 슬라이드 수 ≥ 최소, 제목 슬라이드 텍스트, 이미지 참조 파일 존재.
- 다이어그램: PNG 생성·크기 > 0, 컴포넌트 수 = 박스 수(라벨 텍스트 검사는 생략).
- `consistency`: 요구사항 정의서 ID 집합 == DB baseline ID 집합, 추적표 누락 탐지.
- `file_integrity`: sha256 기록값과 재계산 일치.

### changes
- 승인 전 `Requirement` 불변(변경 요청·분석 후 DB 조회 값 동일).
- 승인→적용: `RequirementChange.status=applied`, `Revision` 생성, 스냅샷 JSON 존재, 새 버전 파일명.
- 반려: 어떤 기준 데이터도 변하지 않음.
- 영향 식별: 추적 그래프에서 결정적 집합이 정확히 도출되고 에이전트 제안과 라벨로 구분.

### agents (모의)
- `FakeAgentRunner`: 역할별 고정 JSON → Pydantic 검증 통과.
- 스키마 draft-07 호환: 모든 `*Draft.model_json_schema()`가 `$schema` 2020-12 키워드를 포함하지 않음(SDK가 draft-07로 검증).
- 훅: workspace 밖 `Write` 호출 입력에 대해 deny 결과 반환.
- 실패 매핑: `subtype=error_max_budget_usd` → `AgentRunError` + AuditEvent error 기록.

### UI (Streamlit AppTest)
- 모드 선택 → 메뉴 구성 차이.
- 게이트에서 반려 사유 미입력 시 제출 불가.
- 에러 발생 시 원인·해결 방안 메시지 표시.

## 4. LLM 계약 테스트 (`-m llm`)

- 각 프롬프트에 대해 소형 고정 입력(샘플 RFP 2~3페이지)으로 1회 호출, 조건: `subtype == success`, `structured_output` Pydantic 검증 통과, 비용 ≤ 상한.
- 결과 JSON을 `tests/fixtures/llm_snapshots/`에 저장(수동 검토용, 자동 비교하지 않음 — 비결정적).
- 실행 명령:

```bash
pytest -m llm tests/integration/llm -v
```

- API 키가 없으면 `skip` 처리되며, 보고서에는 "실행하지 않음"으로 기록한다.

## 5. 도구 및 설정

- `pytest` + `pytest-asyncio`(`asyncio_mode=auto`), 기본 `addopts="-m 'not llm'"`.
- `ruff check`, `ruff format --check`를 테스트 전 실행.
- `mypy src`는 Phase 3부터 CI 조건에 포함(초기엔 경고만).
- 커버리지: `pytest-cov` 도입은 Phase 2, 결정적 모듈 목표 90%.

## 6. 테스트 데이터

- `tests/fixtures/sample_rfp.pdf`, `sample_rfp.docx`: 자체 작성 가상 RFP(10~15페이지, 기능/비기능 혼합, 표 포함).
- `tests/fixtures/scanned_page.pdf`: OCR 판정용 이미지 PDF 1장.
- `tests/fixtures/legacy_requirements.xlsx` 등: 구축 단계 업로드 샘플(다른 컬럼명 2종).
- 실제 고객 문서는 저장소에 넣지 않는다.

## 7. Phase별 보고 형식

```
Phase N 테스트 결과 (YYYY-MM-DD)
- 명령: pytest -q
- 결과: passed=NN failed=0 skipped=M (skipped 사유: llm 마커)
- 미실행: tests/integration/llm (API 키 없음)
- 수동 확인: <항목> — <확인자> — <결과>
```
