from __future__ import annotations

import copy
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .db import connect, json_dump, json_load


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JobCancelled(RuntimeError):
    pass


class JobPersistenceError(RuntimeError):
    pass


class JobProgress:
    def __init__(self, engine: "JobEngine", jid: str):
        self.engine = engine
        self.jid = jid

    def __call__(
        self,
        *,
        stage: str | None = None,
        message: str | None = None,
        current: float | int | None = None,
        total: float | int | None = None,
        percent: float | None = None,
        checkpoint: dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        self.raise_if_cancelled()
        self.engine._progress(
            self.jid,
            stage=stage,
            message=message,
            current=current,
            total=total,
            percent=percent,
            checkpoint=checkpoint,
            **extra,
        )

    def cancelled(self) -> bool:
        return self.engine.is_cancel_requested(self.jid)

    def raise_if_cancelled(self) -> None:
        if self.cancelled():
            raise JobCancelled("cancel_requested")

    def checkpoint(self, value: dict[str, Any]) -> None:
        self.raise_if_cancelled()
        self.engine._progress(self.jid, checkpoint=value, _checkpoint_explicit=True)


class JobEngine:
    """Persistent local Job Engine with explicit durability health.

    Resumable jobs treat checkpoint persistence as critical: if a checkpoint cannot be
    written after bounded retries, the job fails loudly rather than pretending it can
    recover after a restart.
    """

    DEFAULT_LIMITS = {"youtube": 1, "ai": 1, "local": 2, "maintenance": 1}
    TERMINAL = {"complete", "failed", "cancelled"}

    def __init__(
        self,
        db_path: str | Path | None = None,
        max_jobs: int = 200,
        limits: dict[str, int] | None = None,
        persist_retries: int = 3,
    ):
        self.max_jobs = max(30, int(max_jobs))
        self.db_path = Path(db_path) if db_path else None
        self.limits = {**self.DEFAULT_LIMITS, **(limits or {})}
        self.persist_retries = max(1, int(persist_retries))
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._runners: dict[str, Callable[[JobProgress], Any] | None] = {}
        self._queues = {key: queue.Queue() for key in self.limits}
        self._factory: Callable[[str, dict[str, Any]], Callable[[JobProgress], Any]] | None = None
        self._stop = False
        self._workers: list[threading.Thread] = []
        self._durability = {
            "status": "memory_only" if not self.db_path else "ok",
            "last_error": None,
            "last_error_at": None,
            "consecutive_failures": 0,
            "last_success_at": None,
        }
        for resource_class, count in self.limits.items():
            for index in range(max(1, int(count))):
                worker = threading.Thread(
                    target=self._worker,
                    args=(resource_class,),
                    name=f"cdh-job-{resource_class}-{index + 1}",
                    daemon=True,
                )
                worker.start()
                self._workers.append(worker)

    def durability_health(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._durability)

    def _mark_persist_success(self) -> None:
        with self._lock:
            self._durability.update(
                status="ok",
                last_error=None,
                consecutive_failures=0,
                last_success_at=_now(),
            )

    def _mark_persist_failure(self, exc: Exception) -> None:
        with self._lock:
            failures = int(self._durability.get("consecutive_failures") or 0) + 1
            self._durability.update(
                status="degraded",
                last_error=f"{type(exc).__name__}: {exc}",
                last_error_at=_now(),
                consecutive_failures=failures,
            )

    def set_runner_factory(
        self,
        factory: Callable[[str, dict[str, Any]], Callable[[JobProgress], Any]],
    ) -> None:
        self._factory = factory
        self._recover_persisted()

    @staticmethod
    def _from_row(row: Any) -> dict[str, Any]:
        raw = dict(row)
        return {
            "job_id": raw.get("job_id"),
            "task": raw.get("task"),
            "title": raw.get("title"),
            "state": raw.get("state"),
            "stage": raw.get("stage"),
            "message": raw.get("message"),
            "current": raw.get("current_value"),
            "total": raw.get("total_value"),
            "percent": raw.get("percent"),
            "started_at": raw.get("started_at"),
            "updated_at": raw.get("updated_at"),
            "finished_at": raw.get("finished_at"),
            "elapsed_seconds": raw.get("elapsed_seconds") or 0,
            "result": json_load(raw.get("result_json"), {}),
            "error": raw.get("error"),
            "payload": json_load(raw.get("payload_json"), {}),
            "resource_class": raw.get("resource_class") or "local",
            "cancel_requested": bool(raw.get("cancel_requested")),
            "checkpoint": json_load(raw.get("checkpoint_json"), {}),
            "resumable": bool(raw.get("resumable")),
            "retry_count": int(raw.get("retry_count") or 0),
            "parent_job_id": raw.get("parent_job_id"),
            "worker_id": raw.get("worker_id"),
        }

    def _persist(self, job: dict[str, Any], *, critical: bool = False) -> bool:
        if not self.db_path:
            return False
        last_exc: Exception | None = None
        for attempt in range(self.persist_retries):
            try:
                with connect(self.db_path) as conn:
                    conn.execute(
                        """INSERT INTO job_runs(
                            job_id,task,title,state,stage,message,current_value,total_value,percent,
                            started_at,updated_at,finished_at,elapsed_seconds,result_json,error,payload_json,
                            resource_class,cancel_requested,checkpoint_json,resumable,retry_count,parent_job_id,worker_id
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(job_id) DO UPDATE SET
                            task=excluded.task,title=excluded.title,state=excluded.state,stage=excluded.stage,
                            message=excluded.message,current_value=excluded.current_value,total_value=excluded.total_value,
                            percent=excluded.percent,started_at=excluded.started_at,updated_at=excluded.updated_at,
                            finished_at=excluded.finished_at,elapsed_seconds=excluded.elapsed_seconds,
                            result_json=excluded.result_json,error=excluded.error,payload_json=excluded.payload_json,
                            resource_class=excluded.resource_class,cancel_requested=excluded.cancel_requested,
                            checkpoint_json=excluded.checkpoint_json,resumable=excluded.resumable,
                            retry_count=excluded.retry_count,parent_job_id=excluded.parent_job_id,worker_id=excluded.worker_id""",
                        (
                            job.get("job_id"), job.get("task"), job.get("title"), job.get("state"),
                            job.get("stage"), job.get("message"), job.get("current"), job.get("total"),
                            job.get("percent"), job.get("started_at"), job.get("updated_at") or _now(),
                            job.get("finished_at"), float(job.get("elapsed_seconds") or 0),
                            json_dump(job.get("result") or {}), job.get("error"),
                            json_dump(job.get("payload") or {}), job.get("resource_class") or "local",
                            int(bool(job.get("cancel_requested"))), json_dump(job.get("checkpoint") or {}),
                            int(bool(job.get("resumable"))), int(job.get("retry_count") or 0),
                            job.get("parent_job_id"), job.get("worker_id"),
                        ),
                    )
                    conn.commit()
                self._mark_persist_success()
                return True
            except Exception as exc:  # persistence errors must remain visible
                last_exc = exc
                self._mark_persist_failure(exc)
                if attempt + 1 < self.persist_retries:
                    time.sleep(0.05 * (attempt + 1))
        if critical and last_exc is not None:
            raise JobPersistenceError(
                f"durable job state could not be persisted after {self.persist_retries} attempts: {last_exc}"
            ) from last_exc
        return False

    def _recover_persisted(self) -> None:
        if not self.db_path:
            return
        try:
            with connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT * FROM job_runs WHERE state IN ('queued','running') ORDER BY updated_at"
                ).fetchall()
        except Exception as exc:
            self._mark_persist_failure(exc)
            raise JobPersistenceError(f"cannot recover persisted jobs: {exc}") from exc

        for row in rows:
            job = self._from_row(row)
            jid = str(job["job_id"])
            if job.get("resumable"):
                job.update(
                    state="queued",
                    stage="恢复排队",
                    message="服务重启后根据持久化任务规格与 checkpoint 重新排队",
                    worker_id=None,
                    updated_at=_now(),
                )
                with self._lock:
                    self._jobs[jid] = job
                self._persist(job, critical=True)
                resource_class = str(job.get("resource_class") or "local")
                self._queues.setdefault(resource_class, queue.Queue()).put(jid)
            else:
                job.update(
                    state="failed",
                    stage="已中断",
                    message="服务关闭；该任务未声明可恢复，请重新执行。",
                    error="interrupted_by_server_restart",
                    finished_at=_now(),
                    updated_at=_now(),
                )
                self._persist(job, critical=True)

    def _worker(self, resource_class: str) -> None:
        work_queue = self._queues[resource_class]
        while not self._stop:
            try:
                jid = work_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._execute(jid, resource_class)
            except Exception as exc:
                # Worker threads must survive a single task/persistence failure.
                with self._lock:
                    job = self._jobs.get(jid)
                    if job and job.get("state") not in self.TERMINAL:
                        error = f"{type(exc).__name__}: {exc}"
                        job.update(
                            state="failed",
                            stage="Job Engine failure",
                            message=error,
                            error=error,
                            finished_at=_now(),
                            updated_at=_now(),
                            worker_id=None,
                        )
                        self._persist(job, critical=False)
            finally:
                work_queue.task_done()

    def _execute(self, jid: str, resource_class: str) -> None:
        with self._lock:
            job = self._jobs.get(jid) or self.get(jid)
            if not job:
                return
            if job.get("state") == "cancelled" or job.get("cancel_requested"):
                job.update(state="cancelled", stage="已取消", finished_at=_now(), updated_at=_now())
                self._jobs[jid] = job
                self._persist(job, critical=bool(job.get("resumable")))
                return

            runner = self._runners.get(jid)
            if runner is None and self._factory:
                payload = dict(job.get("payload") or {})
                payload["_resume_checkpoint"] = dict(job.get("checkpoint") or {})
                try:
                    runner = self._factory(str(job.get("task")), payload)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    job.update(
                        state="failed",
                        stage="无法恢复",
                        error=error,
                        message="无法根据持久化任务规格恢复",
                        finished_at=_now(),
                        updated_at=_now(),
                    )
                    self._persist(job, critical=False)
                    return
            if runner is None:
                return

            job.update(
                state="running",
                stage="开始执行",
                started_at=job.get("started_at") or _now(),
                updated_at=_now(),
                worker_id=threading.current_thread().name,
                _started_monotonic=time.monotonic(),
            )
            self._jobs[jid] = job
            self._persist(job, critical=bool(job.get("resumable")))

        progress = JobProgress(self, jid)
        try:
            result = runner(progress)
            progress.raise_if_cancelled()
            with self._lock:
                job = self._jobs[jid]
                job.update(
                    state="complete",
                    result=result,
                    stage="完成",
                    percent=100.0,
                    finished_at=_now(),
                    updated_at=_now(),
                    worker_id=None,
                )
                job["elapsed_seconds"] = round(
                    time.monotonic() - float(job.get("_started_monotonic") or time.monotonic()), 1
                )
                self._persist(job, critical=bool(job.get("resumable")))
        except JobCancelled:
            with self._lock:
                job = self._jobs[jid]
                job.update(
                    state="cancelled",
                    stage="已取消",
                    message="用户请求取消；已完成的批次数据保留。",
                    finished_at=_now(),
                    updated_at=_now(),
                    worker_id=None,
                )
                self._persist(job, critical=bool(job.get("resumable")))
        except Exception as exc:
            with self._lock:
                job = self._jobs[jid]
                error = f"{type(exc).__name__}: {exc}"
                job.update(
                    state="failed",
                    error=error,
                    stage="失败",
                    message=error,
                    finished_at=_now(),
                    updated_at=_now(),
                    worker_id=None,
                )
                self._persist(job, critical=False)

    def _progress(
        self,
        jid: str,
        *,
        stage: str | None = None,
        message: str | None = None,
        current: float | int | None = None,
        total: float | int | None = None,
        percent: float | None = None,
        checkpoint: dict[str, Any] | None = None,
        _checkpoint_explicit: bool = False,
        **extra: Any,
    ) -> None:
        with self._lock:
            job = self._jobs.get(jid)
            if not job:
                return
            if stage is not None:
                job["stage"] = str(stage)
            if message is not None:
                job["message"] = str(message)
            if current is not None:
                job["current"] = current
            if total is not None:
                job["total"] = total
            if checkpoint is not None:
                job["checkpoint"] = dict(checkpoint)
            elif current is not None and job.get("resumable"):
                job["checkpoint"] = {
                    **dict(job.get("checkpoint") or {}),
                    "current": current,
                    "total": total if total is not None else job.get("total"),
                }
            if percent is None and job.get("total") not in (None, 0) and current is not None:
                try:
                    percent = 100 * float(current) / float(job["total"])
                except (TypeError, ValueError, ZeroDivisionError):
                    percent = None
            if percent is not None:
                job["percent"] = round(max(0, min(100, float(percent))), 1)
            for key, value in extra.items():
                job[key] = value
            job["updated_at"] = _now()
            if job.get("_started_monotonic") is not None:
                job["elapsed_seconds"] = round(
                    time.monotonic() - float(job["_started_monotonic"]), 1
                )
            critical = bool(job.get("resumable")) and (
                checkpoint is not None or current is not None or _checkpoint_explicit
            )
            self._persist(job, critical=critical)

    def start(
        self,
        *,
        task: str,
        title: str,
        runner: Callable[[JobProgress], Any] | None = None,
        payload: dict[str, Any] | None = None,
        resource_class: str = "local",
        resumable: bool = False,
        parent_job_id: str | None = None,
    ) -> dict[str, Any]:
        rc = resource_class if resource_class in self._queues else "local"
        jid = uuid.uuid4().hex
        job: dict[str, Any] = {
            "job_id": jid,
            "task": task,
            "title": title or task,
            "state": "queued",
            "stage": "等待执行",
            "message": f"任务已进入 {rc} 队列",
            "current": 0,
            "total": None,
            "percent": None,
            "started_at": None,
            "updated_at": _now(),
            "finished_at": None,
            "elapsed_seconds": 0,
            "result": None,
            "error": None,
            "payload": dict(payload or {}),
            "resource_class": rc,
            "cancel_requested": False,
            "checkpoint": {},
            "resumable": bool(resumable),
            "retry_count": 0,
            "parent_job_id": parent_job_id,
            "worker_id": None,
        }
        with self._lock:
            self._jobs[jid] = job
            self._runners[jid] = runner
            self._persist(job, critical=bool(resumable))
        self._queues[rc].put(jid)
        return self.get(jid) or job

    def is_cancel_requested(self, jid: str) -> bool:
        with self._lock:
            job = self._jobs.get(str(jid))
            if job:
                return bool(job.get("cancel_requested"))
        if self.db_path:
            try:
                with connect(self.db_path) as conn:
                    row = conn.execute(
                        "SELECT cancel_requested FROM job_runs WHERE job_id=?", (str(jid),)
                    ).fetchone()
                self._mark_persist_success()
                return bool(row and row[0])
            except Exception as exc:
                self._mark_persist_failure(exc)
        return False

    def cancel(self, jid: str) -> dict[str, Any]:
        job = self.get(jid)
        if not job:
            raise ValueError("job not found")
        if job.get("state") in self.TERMINAL:
            return job
        with self._lock:
            current = self._jobs.get(jid, job)
            current["cancel_requested"] = True
            current["message"] = "已请求取消；将在当前安全检查点停止"
            current["updated_at"] = _now()
            if current.get("state") == "queued":
                current.update(state="cancelled", stage="已取消", finished_at=_now())
            self._jobs[jid] = current
            self._persist(current, critical=bool(current.get("resumable")))
        return self.get(jid) or current

    def retry(self, jid: str) -> dict[str, Any]:
        job = self.get(jid)
        if not job:
            raise ValueError("job not found")
        if not self._factory:
            raise RuntimeError("runner factory unavailable")
        payload = dict(job.get("payload") or {})
        runner = self._factory(str(job.get("task")), payload)
        output = self.start(
            task=str(job.get("task")),
            title=str(job.get("title")),
            runner=runner,
            payload=payload,
            resource_class=str(job.get("resource_class") or "local"),
            resumable=bool(job.get("resumable")),
            parent_job_id=jid,
        )
        with self._lock:
            created = self._jobs[output["job_id"]]
            created["retry_count"] = int(job.get("retry_count") or 0) + 1
            self._persist(created, critical=bool(created.get("resumable")))
        return self.get(output["job_id"]) or created

    def get(self, jid: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(str(jid))
            if job:
                output = copy.deepcopy(job)
                output.pop("_started_monotonic", None)
                return output
        if self.db_path:
            try:
                with connect(self.db_path) as conn:
                    row = conn.execute("SELECT * FROM job_runs WHERE job_id=?", (str(jid),)).fetchone()
                self._mark_persist_success()
                return self._from_row(row) if row else None
            except Exception as exc:
                self._mark_persist_failure(exc)
        return None

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(200, int(limit)))
        merged: dict[str, dict[str, Any]] = {}
        if self.db_path:
            try:
                with connect(self.db_path) as conn:
                    rows = conn.execute(
                        "SELECT * FROM job_runs ORDER BY updated_at DESC LIMIT ?", (limit,)
                    ).fetchall()
                self._mark_persist_success()
                for row in rows:
                    job = self._from_row(row)
                    merged[str(job["job_id"])] = job
            except Exception as exc:
                self._mark_persist_failure(exc)
        with self._lock:
            for raw in self._jobs.values():
                job = copy.deepcopy(raw)
                job.pop("_started_monotonic", None)
                merged[str(job["job_id"])] = job
        return sorted(
            merged.values(),
            key=lambda item: item.get("updated_at") or "",
            reverse=True,
        )[:limit]


JobStore = JobEngine
