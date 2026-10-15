# ERROR_HANDLING — 오류 종류·메시지·조치

문서 버전 1.0 · 2026-10-15 · 구현: `config/errors.py`, `services/audit.py`, `agents/runner.py`, `ui/state.py`

---

## 1. 메시지 형식

업무 오류는 모두 `PWAError`를 상속하며 화면·로그에 같은 형식으로 나온다.

```
<메시지> (원인: <cause>; 조치: <resolution>)
```

- `to_dict()`로 `step_runs.error`·`change_requests.error`·감사 이벤트에 저장된다(비밀값 마스킹).
- 예상하지 못한 예외(`Exception`)는 타입·메시지로 기록되고 기술 로그(`workspace\logs\app.log`)에 스택이 남는다.
- 모든 입력은 LLM이 아니라 코드가 검증한다. 에이전트가 "통과"라고 답해도 게이트·검증 결과에는 영향이 없다.

## 2. 오류 종류

| 클래스 | 언제 | 기본 조치 |
|---|---|---|
| `ConfigError` | `.env`·환경변수 오류, `prod`에서 API 키 없음, 모델·MCP 설정 형식 오류 | `.env` 또는 환경변수를 확인 |
| `IngestError` | 지원하지 않는 형식(HWP 등), 손상·암호화된 PDF/XLSX, 텍스트 없는 문서, OCR 실패 | 형식·내용 확인, 변환 후 재업로드 |
| `AgentRunError(subtype)` | 에이전트 실행 실패. `detail.category`: `credit`(크레딧 부족), `auth`, `budget`(예산 초과), `rate_limit`, `overloaded`, `connection`, `process`, `schema`(구조화 출력 검증 실패), `timeout`, `cancelled`, `no_responder` | 일시 오류는 자동 재시도(역할별 `retries`). 크레딧·인증·예산·스키마는 즉시 실패 → 원인 해결 후 재실행 |
| `ValidationError` | 데이터 규칙 위반: 게이트 미통과 상태에서 승인, 사유 없는 반려, 필수 문서 누락, 매핑 미확정, 모호 후보 수락, 산정 근거 없는 WBS, 기간 없음 등 | 메시지에 적힌 항목을 수정 |
| `GateBlockedError` | 앞 게이트가 PASS가 아닌데 다음 단계 실행 | 게이트 사유 해결·재평가, 검토 필요면 사람 승인 |
| `StorageError` | DB 제약 위반(중복 ID·해시), 파일 저장 실패 | 경로·권한·중복 확인 |
| `NotFoundError` | 존재하지 않는 ID 조회 | ID 확인 |
| `PathSecurityError` | 프로젝트 폴더 밖 경로 접근 시도 | 프로젝트 내부 상대 경로만 사용 |
| `FileExistsConflict` | 같은 이름으로 저장 시도 | 새 버전 파일명 사용(코드가 자동 부여). 덮어쓰기는 지원하지 않음 |

## 3. 단계 실행과 상태

- 단계 실행은 `StepRun(status: pending→running→approved/needs_review/failed)`으로 기록된다. 실패하면 `error`에 원인·조치가 남고 같은 단계를 다시 실행하면 `attempt`가 증가한 새 레코드가 생긴다.
- 실행 중(`running`)인 단계는 중복 시작이 거부된다. 앱이 강제 종료되어 `running`으로 남은 경우 프로젝트 화면에서 실패 처리 후 재실행한다.
- 변경 반영(구축)은 DB 트랜잭션 안에서 수행되어 오류 시 롤백되고 요청은 `error` 상태로 남아 **반영 재시도**가 가능하다. 파일 생성은 트랜잭션 밖이므로 재시도 시 새 타임스탬프 파일이 생긴다(기존 파일 덮어쓰기 없음).
- 산출물 생성은 종류별로 독립 실행되어 한 종류가 실패해도 나머지는 생성되고, 실패 종류는 `errors`로 보고되며 단계는 `failed`로 기록된다. 재실행하면 실패한 종류만이 아니라 전체가 새 버전으로 다시 생성된다.

## 4. 게이트 판정과 사람 검토

| 상태 | 의미 | 가능한 조치 |
|---|---|---|
| `PASS` | 코드 조건 충족 | 다음 단계 진행 |
| `NEEDS_HUMAN_REVIEW` | 자동으로 확정할 수 없음 | 검토 의견(필수)을 적고 승인 → PASS 취급 / 반려 → FAIL |
| `FAIL` | 필수 조건 미충족 | 승인으로 통과시킬 수 없음. 원인 해결 후 재평가 |

Gate 5(최종 독립 QA)는 필수 검증 실패가 없어도 항상 사람 승인이 필요하다.

## 5. 자주 보는 메시지

| 메시지 | 원인 | 조치 |
|---|---|---|
| `Credit balance is too low` | Anthropic 계정 크레딧 부족 | 콘솔에서 충전. 코드 설정으로 해결 불가 |
| `ANTHROPIC_API_KEY가 설정되지 않았습니다` | 키 없음 | `.env` 입력 후 재시작 |
| `Gate 1: … 미통과 (NEEDS_HUMAN_REVIEW)` | 요구사항 검토 미완료 | 지적 사항 해소 → 재평가 → 승인 |
| `컬럼 매핑 확인이 필요한 문서가 있습니다` | 기준 Excel 헤더가 표준과 다름 | 구조 분석 화면에서 열 번호 지정 후 확정 |
| `승인 조건을 만족하지 않습니다 (미결정 후보 …)` | 변경 후보 결정 누락 | 후보별 수락/거절 |
| `WBS 재계산 실패: 순환 의존성` | WBS 의존 관계 순환 | 의존 관계 수정 후 재분석 |
| `같은 내용의 문서가 이미 등록되어 있습니다` | 해시 동일 | 다른 문서를 올리거나 기존 문서 사용 |
| `최종본이 이미 존재합니다` | 같은 버전 재확정 | 새 버전 생성 후 확정 |
| `ImportError … DLL` | 앱 제어 정책의 네이티브 DLL 차단 | PyMuPDF·matplotlib은 미사용. 다른 패키지면 정책 예외 요청 |

## 6. 로그 확인 방법

```powershell
Get-Content workspace\logs\app.log -Tail 100
Select-String -Path workspace\logs\app.log -Pattern "ERROR|failed"
```

감사 이벤트는 DB에서 확인한다(비밀값은 `***`).

```powershell
python -c "import sqlite3; c=sqlite3.connect('workspace/pwa.sqlite3'); [print(r) for r in c.execute('select created_at, action, entity_id from audit_events order by created_at desc limit 20')]"
```
