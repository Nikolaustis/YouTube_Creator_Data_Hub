from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VISIBLE_BANNED = ("UgPhone", "LDCloud", "RedFinger", "VSPhone", "Cloud Phone", "cloud phone", "云手机")


def scan_text(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [term for term in VISIBLE_BANNED if term in text]


def run_check() -> dict[str, object]:
    # Source-level UI assets: these strings can be rendered directly in generic surfaces.
    source_targets = [
        ROOT / "creator_hub" / "static" / "metrics_workspace.js",
        ROOT / "creator_hub" / "static" / "creator_detail.js",
    ]
    source_hits = {str(p.relative_to(ROOT)): scan_text(p) for p in source_targets if p.exists() and scan_text(p)}

    td = Path(tempfile.mkdtemp(prefix="creator_hub_neutral_"))
    try:
        from creator_hub.portfolio.demo import create_demo
        from creator_hub.workspace import WorkspaceService

        db = td / "neutral-demo.sqlite"
        out = td / "dashboard"
        result = create_demo(db, creators=8, videos=64, output_dir=out, build=True)

        ws = WorkspaceService(db)
        active = ws.active() or {}
        public_templates = ws.templates()
        if (active.get("metadata") or {}).get("compatibility_profile"):
            raise AssertionError("synthetic demo activated a compatibility workspace")
        if any(str(x.get("visibility") or "public") == "compatibility" for x in public_templates):
            raise AssertionError("compatibility template leaked into public template catalog")

        generated_targets = [
            out / "index.html",
            out / "metrics.html",
            out / "workspace.html",
            out / "assets" / "metrics_workspace.js",
            out / "assets" / "metrics_config.js",
            out / "assets" / "metric_base.js",
            out / "assets" / "creator_facts.js",
        ]
        generated_hits = {str(p.relative_to(out)): scan_text(p) for p in generated_targets if p.exists() and scan_text(p)}

        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            wid = str(active.get("id") or "")
            row = conn.execute(
                "SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='secondary_metrics'",
                (wid,),
            ).fetchone()
            # A new generic demo must not inherit global/historical metric state.
            if row and any(term in str(row["value_json"]) for term in VISIBLE_BANNED):
                raise AssertionError("generic workspace secondary_metrics contains compatibility presentation strings")

        if source_hits or generated_hits:
            raise AssertionError(f"neutral surface leak: source={source_hits}, generated={generated_hits}")
        return {
            "ok": True,
            "demo_creators": result.get("creators"),
            "demo_videos": result.get("videos"),
            "active_workspace": active.get("id"),
            "checked_generated_files": len(generated_targets),
        }
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main() -> int:
    result = run_check()
    print("PUBLIC_SURFACE_NEUTRAL_OK", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
