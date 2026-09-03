from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from creator_hub.ai.workspace_tools import workspace_creator_indexes
from creator_hub.dashboard import build_dashboard, creator_facts_payload, metric_base_payload
from creator_hub.service import CreatorHub

from .demo import create_demo

PROFILES = {
    "small": {"creators": 40, "videos": 400},
    "medium": {"creators": 150, "videos": 3000},
    "large": {"creators": 500, "videos": 15000},
}


def _measure(fn: Callable[[], Any], repeats: int = 3) -> dict[str, Any]:
    samples = []
    last = None
    for _ in range(max(1, repeats)):
        started = time.perf_counter()
        last = fn()
        samples.append(time.perf_counter() - started)
    return {
        "samples_seconds": [round(x, 6) for x in samples],
        "median_seconds": round(statistics.median(samples), 6),
        "min_seconds": round(min(samples), 6),
        "max_seconds": round(max(samples), 6),
        "result_hint": _hint(last),
    }


def _hint(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: value[k] for k in list(value)[:6]}
    if isinstance(value, list):
        return {"rows": len(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return type(value).__name__


def run(profile: str = "small", *, repeats: int = 3, workdir: str | Path | None = None) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"unknown benchmark profile: {profile}")
    cfg = PROFILES[profile]
    temp_root = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="creator_hub_bench_"))
    temp_root.mkdir(parents=True, exist_ok=True)
    db = temp_root / f"benchmark_{profile}_demo.sqlite"
    output = temp_root / "dashboard"

    dataset_started = time.perf_counter()
    demo = create_demo(db, creators=cfg["creators"], videos=cfg["videos"], build=False)
    dataset_seconds = time.perf_counter() - dataset_started
    hub = CreatorHub(db)

    cold = _measure(lambda: build_dashboard(db, output, hub.settings), repeats=1)
    warm = _measure(lambda: build_dashboard(db, output, hub.settings), repeats=max(1, repeats))
    creators = _measure(lambda: hub.list_creators(False, 5000), repeats=repeats)
    creator_facts = _measure(lambda: creator_facts_payload(db, hub.settings), repeats=repeats)
    metric_cube = _measure(lambda: metric_base_payload(db, hub.settings), repeats=repeats)
    workspace_index = _measure(lambda: workspace_creator_indexes(hub), repeats=repeats)

    return {
        "benchmark_version": 1,
        "profile": profile,
        "dataset": {**cfg, "generation_seconds": round(dataset_seconds, 6), "db_bytes": db.stat().st_size},
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "measurements": {
            "dashboard_cold_build": cold,
            "dashboard_warm_build": warm,
            "creator_list": creators,
            "creator_facts_payload": creator_facts,
            "metric_base_payload": metric_cube,
            "workspace_creator_indexes": workspace_index,
        },
        "synthetic_only": True,
        "note": "Benchmark numbers are valid only with the recorded profile and environment.",
        "demo": demo,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproducible synthetic benchmark")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="small")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", dest="json_path", default="")
    parser.add_argument("--workdir", default="")
    args = parser.parse_args()
    result = run(args.profile, repeats=args.repeats, workdir=args.workdir or None)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
