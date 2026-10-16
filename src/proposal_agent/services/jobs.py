"""긴 작업의 백그라운드 실행·진행률·중단 (지시문 §15·§16, 단계 1, 결정 D-16).

- 동기 경로(`st.status` 안에서 호출) 는 그대로 두고, 선택적으로 작업을 스레드에서 실행한다.
- 작업 상태는 ``StepRun``(진행률·현재 일·중단 요청·생존 신호·재개 지점) 에 기록되므로 화면은 DB 를 폴링해
  진행을 본다. 프로세스가 죽어도 레코드가 남아 "중단된 작업" 으로 식별·재실행할 수 있다.
- 같은 단계의 중복 실행은 ``PipelineService.start_step`` 이 거부한다. 중단은 ``CancellationToken`` 으로
  협조적으로 이뤄지며(에이전트 러너·청크 루프가 확인), 강제 종료는 하지 않는다.
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from proposal_agent.agents.control import CancellationToken
from proposal_agent.config.errors import PWAError
from proposal_agent.config.logging import get_logger
from proposal_agent.models import Project, StepRun, StepStatus, utcnow
from proposal_agent.storage.repositories import Repositories

log = get_logger("services.jobs")

STALE_AFTER = timedelta(minutes=10)  # 생존 신호가 이보다 오래되면 '응답 없음' 으로 표시


@dataclass
class Job:
    run_id: str
    project_id: str
    step_key: str
    cancel: CancellationToken
    thread: threading.Thread | None = None
    result: Any = None
    error: BaseException | None = None
    done: bool = False
    started_at: Any = field(default_factory=utcnow)

    @property
    def alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class JobManager:
    """프로세스 안의 백그라운드 작업 레지스트리. 작업 함수는 ``fn(cancel: CancellationToken) -> Any``."""

    def __init__(self, repos: Repositories) -> None:
        self._repos = repos
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._record_lock = threading.Lock()  # StepRun 레코드 읽기-고치기-쓰기 직렬화

    # --- 실행 ------------------------------------------------------------------------------
    def submit(
        self,
        project: Project,
        run: StepRun | None,
        fn: Callable[[CancellationToken], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> Job:
        """작업을 스레드에서 수행한다. ``run`` 이 있으면 그 레코드에 백그라운드·생존 신호를 표시하고, 없으면(여러 단계
        묶음) 안에서 생기는 StepRun 이 각자 기록된다. 완료·실패 처리는 콜백이 맡는다."""
        cancel = CancellationToken()
        job = Job(
            run_id=run.id if run is not None else f"batch_{utcnow():%Y%m%d%H%M%S}",
            project_id=project.id,
            step_key=run.step_key if run is not None else "batch",
            cancel=cancel,
        )
        if run is not None:
            run.background = True
            run.heartbeat_at = utcnow()
            self._repos.step_runs.update(run)

        def target() -> None:
            try:
                job.result = fn(cancel)
                if on_done is not None:
                    on_done(job.result)
            except BaseException as exc:  # noqa: BLE001 — 스레드 안 예외는 레코드로 남긴다
                job.error = exc
                log.error("백그라운드 작업 실패 %s/%s: %s", job.step_key, job.run_id, exc)
                if not isinstance(exc, PWAError):
                    log.debug(traceback.format_exc())
                if on_error is not None:
                    try:
                        on_error(exc)
                    except Exception as exc2:  # noqa: BLE001
                        log.error("실패 처리 중 오류: %s", exc2)
            finally:
                job.done = True

        thread = threading.Thread(
            target=target, name=f"job-{job.step_key}-{job.run_id[-6:]}", daemon=True
        )
        job.thread = thread
        with self._lock:
            self._jobs[job.run_id] = job
        thread.start()
        return job

    # --- 조회·제어 --------------------------------------------------------------------------
    def get(self, run_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(run_id)

    def running(self, project_id: str | None = None) -> list[Job]:
        with self._lock:
            return [
                j
                for j in self._jobs.values()
                if j.alive and (project_id is None or j.project_id == project_id)
            ]

    def request_cancel(self, run: StepRun, *, actor: str = "user") -> StepRun:
        """중단 요청: DB 최신 레코드에 표시하고(다른 스레드·프로세스도 봄) 메모리의 토큰도 세운다."""
        with self._record_lock:
            fresh = self._repos.step_runs.get(run.id)
            fresh.cancel_requested = True
            if "중단 요청됨" not in fresh.progress_note:
                fresh.progress_note = (
                    fresh.progress_note + " · " if fresh.progress_note else ""
                ) + "중단 요청됨"
            self._repos.step_runs.update(fresh)
        run.cancel_requested, run.progress_note = True, fresh.progress_note
        job = self.get(run.id)
        if job is not None:
            job.cancel.cancel()
        log.info("중단 요청 %s/%s by %s", run.step_key, run.id, actor)
        return fresh

    def is_cancel_requested(self, run: StepRun) -> bool:
        fresh = self._repos.step_runs.get(run.id)
        return bool(fresh.cancel_requested)

    def heartbeat(
        self, run: StepRun, *, progress: float | None = None, note: str | None = None
    ) -> StepRun:
        """진행률·현재 일·생존 신호 갱신. 작업 함수가 주기적으로 호출한다.

        항상 DB 의 최신 레코드를 읽어 갱신한다 — 작업 스레드가 가진 옛 복사본으로 덮어쓰면 다른 쪽(화면)이
        기록한 중단 요청이 지워진다. 중단 요청 표시는 보존하고, 호출자의 객체에도 되돌려 준다.
        """
        with (
            self._record_lock
        ):  # 중단 요청과 같은 레코드를 읽고-고치고-쓰므로 잃어버린 갱신을 막는다
            fresh = self._repos.step_runs.get(run.id)
            if progress is not None:
                fresh.progress = max(0.0, min(1.0, float(progress)))
            if note is not None:
                fresh.progress_note = note[:200]
            if fresh.cancel_requested and "중단 요청됨" not in fresh.progress_note:
                fresh.progress_note = (
                    fresh.progress_note + " · " if fresh.progress_note else ""
                ) + "중단 요청됨"
            fresh.heartbeat_at = utcnow()
            self._repos.step_runs.update(fresh)
        run.progress, run.progress_note = fresh.progress, fresh.progress_note
        run.cancel_requested, run.heartbeat_at = fresh.cancel_requested, fresh.heartbeat_at
        return fresh

    def set_resume_point(self, run: StepRun, point: dict[str, Any]) -> StepRun:
        """재개 지점 기록. 작업 스레드의 옛 복사본으로 덮어쓰지 않도록 DB 최신 레코드에 쓴다(중단 요청 보존)."""
        with self._record_lock:
            fresh = self._repos.step_runs.get(run.id)
            fresh.resume_point = dict(point)
            self._repos.step_runs.update(fresh)
        run.resume_point = dict(point)
        run.cancel_requested = run.cancel_requested or fresh.cancel_requested
        return run

    def stale_runs(self, project: Project) -> list[StepRun]:
        """'실행 중' 인데 생존 신호가 오래된(또는 스레드가 없는) 작업 — 프로세스 재시작 등으로 끊긴 것."""
        now = utcnow()
        out: list[StepRun] = []
        for run in self._repos.step_runs.find(project.id, status=str(StepStatus.RUNNING)):
            job = self.get(run.id)
            if job is not None and job.alive:
                continue
            last = run.heartbeat_at or run.started_at
            if last is None or now - last > STALE_AFTER:
                out.append(run)
        return out

    def mark_interrupted(self, project: Project, run: StepRun, *, actor: str = "system") -> StepRun:
        """끊긴 작업을 실패로 정리해 재실행할 수 있게 한다 (진행 레코드는 보존)."""
        from proposal_agent.config.errors import ValidationError

        if run.status != StepStatus.RUNNING:
            return run
        run.status = StepStatus.FAILED
        run.finished_at = utcnow()
        run.error = ValidationError(
            "작업이 중단되었습니다 (프로세스 종료 또는 응답 없음).",
            cause=f"마지막 생존 신호 {run.heartbeat_at or run.started_at}",
            resolution="'실패한 작업 재실행' 으로 다시 실행하십시오. 재개 지점이 있으면 이어서 처리합니다.",
        ).to_dict()
        self._repos.step_runs.update(run)
        log.warning("중단 작업 정리 %s/%s by %s", run.step_key, run.id, actor)
        return run


__all__ = ["STALE_AFTER", "Job", "JobManager"]
