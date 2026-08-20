from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .db import connect, json_dump, json_load


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class JobStore:
    """Persistent progress registry for the local interactive Dashboard.

    Running state is kept in memory for fast polling and mirrored to SQLite so page
    navigation, browser refreshes and later server sessions retain task history. A
    process restart cannot resume Python worker threads; unfinished persisted rows are
    therefore marked interrupted on the next server start instead of pretending to run.
    """

    def __init__(self, db_path: str | Path | None = None, max_jobs: int = 120):
        self.max_jobs = max(20, int(max_jobs))
        self.db_path = Path(db_path) if db_path else None
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        if self.db_path:
            self._mark_interrupted()

    def _mark_interrupted(self) -> None:
        try:
            with connect(self.db_path) as conn:
                rows=conn.execute("SELECT job_id FROM job_runs WHERE state IN ('queued','running')").fetchall()
                if rows:
                    at=_now()
                    conn.execute("""UPDATE job_runs SET state='failed',stage='已中断',message='Dashboard 服务曾关闭，后台线程无法跨进程恢复；请重新执行该任务。',error='interrupted_by_server_restart',finished_at=?,updated_at=? WHERE state IN ('queued','running')""",(at,at))
                    conn.commit()
        except Exception:
            pass

    def _persist(self, job: dict[str, Any]) -> None:
        if not self.db_path:
            return
        try:
            with connect(self.db_path) as conn:
                conn.execute("""INSERT INTO job_runs(job_id,task,title,state,stage,message,current_value,total_value,percent,started_at,updated_at,finished_at,elapsed_seconds,result_json,error)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(job_id) DO UPDATE SET task=excluded.task,title=excluded.title,state=excluded.state,stage=excluded.stage,message=excluded.message,current_value=excluded.current_value,total_value=excluded.total_value,percent=excluded.percent,started_at=excluded.started_at,updated_at=excluded.updated_at,finished_at=excluded.finished_at,elapsed_seconds=excluded.elapsed_seconds,result_json=excluded.result_json,error=excluded.error""",
                    (job.get('job_id'),job.get('task'),job.get('title'),job.get('state'),job.get('stage'),job.get('message'),job.get('current'),job.get('total'),job.get('percent'),job.get('started_at'),job.get('updated_at') or _now(),job.get('finished_at'),float(job.get('elapsed_seconds') or 0),json_dump(job.get('result')) if job.get('result') is not None else '{}',job.get('error')))
                conn.commit()
        except Exception:
            pass

    @staticmethod
    def _from_row(row: Any) -> dict[str, Any]:
        d=dict(row)
        return {
            'job_id':d.get('job_id'),'task':d.get('task'),'title':d.get('title'),'state':d.get('state'),
            'stage':d.get('stage'),'message':d.get('message'),'current':d.get('current_value'),
            'total':d.get('total_value'),'percent':d.get('percent'),'started_at':d.get('started_at'),
            'updated_at':d.get('updated_at'),'finished_at':d.get('finished_at'),
            'elapsed_seconds':d.get('elapsed_seconds') or 0,'result':json_load(d.get('result_json'),None),
            'error':d.get('error')
        }

    def _trim(self) -> None:
        if len(self._jobs) <= self.max_jobs:
            return
        finished = sorted(
            (j for j in self._jobs.values() if j.get('state') in {'complete', 'failed'}),
            key=lambda x: x.get('updated_at') or '',
        )
        for j in finished[: max(0, len(self._jobs) - self.max_jobs)]:
            self._jobs.pop(str(j['job_id']), None)

    def start(self, *, task: str, title: str, runner: Callable[[Callable[..., None]], Any]) -> dict[str, Any]:
        jid = uuid.uuid4().hex
        job: dict[str, Any] = {
            'job_id': jid, 'task': task, 'title': title or task, 'state': 'queued',
            'stage': '等待执行', 'message': '任务已进入本机执行队列',
            'current': 0, 'total': None, 'percent': None,
            'started_at': None, 'updated_at': _now(), 'finished_at': None,
            'elapsed_seconds': 0.0, 'result': None, 'error': None,
        }
        with self._lock:
            self._jobs[jid] = job
            self._trim()
            self._persist(job)

        def progress(*, stage: str | None = None, message: str | None = None,
                     current: int | float | None = None, total: int | float | None = None,
                     percent: float | None = None, **extra: Any) -> None:
            with self._lock:
                j = self._jobs.get(jid)
                if not j:
                    return
                if stage is not None: j['stage'] = str(stage)
                if message is not None: j['message'] = str(message)
                if current is not None: j['current'] = current
                if total is not None: j['total'] = total
                if percent is None and total not in (None, 0) and current is not None:
                    try: percent = 100.0 * float(current) / float(total)
                    except Exception: percent = None
                if percent is not None:
                    j['percent'] = round(max(0.0, min(100.0, float(percent))), 1)
                for k, v in extra.items():
                    if k not in {'result', 'error'}: j[k] = v
                j['updated_at'] = _now()
                if j.get('_started_monotonic') is not None:
                    j['elapsed_seconds'] = round(time.monotonic() - float(j['_started_monotonic']), 1)
                self._persist(j)

        def worker() -> None:
            with self._lock:
                j = self._jobs[jid]
                j.update(state='running', stage='开始执行', started_at=_now(), updated_at=_now(), _started_monotonic=time.monotonic())
                self._persist(j)
            try:
                result = runner(progress)
                with self._lock:
                    j = self._jobs[jid]
                    j.update(state='complete', result=result, stage='完成', percent=100.0, finished_at=_now(), updated_at=_now())
                    if not j.get('message'): j['message'] = '任务完成'
                    j['elapsed_seconds'] = round(time.monotonic() - float(j.get('_started_monotonic') or time.monotonic()), 1)
                    self._persist(j)
            except Exception as exc:
                with self._lock:
                    j = self._jobs[jid]
                    err = f'{type(exc).__name__}: {exc}'
                    j.update(state='failed', error=err, stage='失败', message=err, finished_at=_now(), updated_at=_now())
                    j['elapsed_seconds'] = round(time.monotonic() - float(j.get('_started_monotonic') or time.monotonic()), 1)
                    self._persist(j)

        threading.Thread(target=worker, name=f'cdh-job-{task}-{jid[:8]}', daemon=True).start()
        return self.get(jid) or job

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            j = self._jobs.get(str(job_id))
            if j:
                out = copy.deepcopy(j); out.pop('_started_monotonic', None); return out
        if self.db_path:
            try:
                with connect(self.db_path) as conn:
                    r=conn.execute('SELECT * FROM job_runs WHERE job_id=?',(str(job_id),)).fetchone()
                return self._from_row(r) if r else None
            except Exception:
                pass
        return None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        limit=max(1,min(100,int(limit)))
        merged: dict[str,dict[str,Any]]={}
        if self.db_path:
            try:
                with connect(self.db_path) as conn:
                    rows=conn.execute('SELECT * FROM job_runs ORDER BY updated_at DESC LIMIT ?',(limit,)).fetchall()
                for r in rows:
                    j=self._from_row(r); merged[str(j['job_id'])]=j
            except Exception:
                pass
        with self._lock:
            for raw in self._jobs.values():
                j=copy.deepcopy(raw);j.pop('_started_monotonic',None);merged[str(j['job_id'])]=j
        return sorted(merged.values(),key=lambda x:x.get('updated_at') or '',reverse=True)[:limit]
