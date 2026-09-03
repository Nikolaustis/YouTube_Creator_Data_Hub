from __future__ import annotations

import json
import time

from creator_hub.db import connect, init_db
from creator_hub.jobs import JobEngine


def wait_terminal(engine: JobEngine, job_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = engine.get(job_id)
        if job and job.get("state") in engine.TERMINAL:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not reach terminal state")


def test_persistent_job_and_durability_health(tmp_path):
    db = tmp_path / "jobs.sqlite"
    init_db(db)
    engine = JobEngine(db, limits={"local": 1, "youtube": 1, "ai": 1, "maintenance": 1})
    job = engine.start(
        task="simple",
        title="Simple",
        resource_class="local",
        runner=lambda progress: {"value": 42},
    )
    final = wait_terminal(engine, job["job_id"])
    assert final["state"] == "complete"
    assert final["result"]["value"] == 42
    assert engine.durability_health()["status"] == "ok"
    with connect(db) as conn:
        assert conn.execute("SELECT state FROM job_runs WHERE job_id=?", (job["job_id"],)).fetchone()[0] == "complete"


def test_restart_recovers_from_checkpoint(tmp_path):
    db = tmp_path / "recover.sqlite"
    init_db(db)
    now = "2026-09-03T00:00:00Z"
    job_id = "resume-fixture"
    with connect(db) as conn:
        conn.execute(
            """INSERT INTO job_runs(
               job_id,task,title,state,stage,message,current_value,total_value,percent,started_at,updated_at,
               elapsed_seconds,result_json,payload_json,resource_class,cancel_requested,checkpoint_json,resumable,
               retry_count,parent_job_id,worker_id
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id, "resume-test", "Resume", "running", "work", "before restart", 3, 5, 60,
                now, now, 0, "{}", json.dumps({"items": [0, 1, 2, 3, 4]}), "local", 0,
                json.dumps({"current": 3, "total": 5}), 1, 0, None, "old-worker",
            ),
        )
        conn.commit()

    observed = {}

    def factory(task, payload):
        assert task == "resume-test"
        observed["checkpoint"] = payload.get("_resume_checkpoint")

        def runner(progress):
            start = int((payload.get("_resume_checkpoint") or {}).get("current") or 0)
            for current in range(start + 1, 6):
                progress(current=current, total=5, stage="resumed")
            return {"resumed_from": start}

        return runner

    engine = JobEngine(db, limits={"local": 1, "youtube": 1, "ai": 1, "maintenance": 1})
    engine.set_runner_factory(factory)
    final = wait_terminal(engine, job_id)
    assert observed["checkpoint"]["current"] == 3
    assert final["state"] == "complete"
    assert final["result"]["resumed_from"] == 3
    assert final["checkpoint"]["current"] == 5
