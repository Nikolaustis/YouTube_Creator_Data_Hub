from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VISIBLE_BANNED = (
    "UgPhone", "LDCloud", "RedFinger", "VSPhone", "Cloud Phone", "cloud phone", "云手机", "雲手機",
    "AFK", "auto farm", "Auto Farm", "Farming /", "gameplay", "Gameplay",
    "输入游戏名称", "游戏 Creator", "Anime Expeditions",
)
EXPECTED_QUERY_PACKS = ["learn", "review", "use_case", "updates", "community", "custom"]
EXPECTED_QUERY_PROFILE_SCHEMA = 4
EXPECTED_QUERY_PROFILE = "generic_creator_discovery_v2"


def scan_text(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [term for term in VISIBLE_BANNED if term in text]


def _check_query_pack_source() -> None:
    path = ROOT / "config" / "query_packs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [str(x.get("id") or "") for x in data.get("packs") or []]
    if int(data.get("schema_version") or 0) != EXPECTED_QUERY_PROFILE_SCHEMA or data.get("profile") != EXPECTED_QUERY_PROFILE:
        raise AssertionError("public Query Pack template is not on editable schema 4")
    if ids != EXPECTED_QUERY_PACKS:
        raise AssertionError(f"unexpected public Query Pack catalog: {ids}")
    hits = scan_text(path)
    if hits:
        raise AssertionError(f"legacy discovery vocabulary leaked into public Query Packs: {hits}")


def _check_public_templates() -> None:
    path = ROOT / "config" / "workspace_templates.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    public = [x for x in data.get("templates") or [] if str(x.get("visibility") or "public") != "compatibility"]
    raw = json.dumps(public, ensure_ascii=False)
    hits = [term for term in VISIBLE_BANNED if term in raw]
    if hits:
        raise AssertionError(f"legacy vocabulary leaked into public Workspace templates: {hits}")
    ids = {str(x.get("id") or "") for x in public}
    if "creator_discovery" not in ids:
        raise AssertionError("generic creator_discovery template missing")
    if "gaming_creator" in ids:
        raise AssertionError("legacy gaming_creator template still public")


def run_check() -> dict[str, object]:
    _check_query_pack_source()
    _check_public_templates()

    # These files can directly drive generic/default UI or AI discovery behavior.
    source_targets = [
        ROOT / "creator_hub" / "static" / "metrics_workspace.js",
        ROOT / "creator_hub" / "static" / "creator_detail.js",
        ROOT / "creator_hub" / "static" / "discovery.js",
        ROOT / "creator_hub" / "ai" / "prompts.py",
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
            out / "discovery.html",
            out / "assets" / "metrics_workspace.js",
            out / "assets" / "discovery.js",
            out / "assets" / "query_packs.js",
            out / "assets" / "metrics_config.js",
            out / "assets" / "metric_base.js",
            out / "assets" / "creator_facts.js",
        ]
        generated_hits = {str(p.relative_to(out)): scan_text(p) for p in generated_targets if p.exists() and scan_text(p)}
        discovery_html = (out / "discovery.html").read_text(encoding="utf-8", errors="ignore")
        discovery_js = (out / "assets" / "discovery.js").read_text(encoding="utf-8", errors="ignore")
        for token in ("queryAddPack", "queryResetLanguageDefaults", "恢复系统默认 Query Packs"):
            if token not in discovery_html:
                raise AssertionError(f"Query Pack editor control missing from generated discovery page: {token}")
        for token in ("V4.4 query-pack-editor", "generic_creator_discovery_v2", "data-qe-copy", "data-qe-delete", "data-qe-save-meta"):
            if token not in discovery_js:
                raise AssertionError(f"Query Pack editor behavior missing from generated discovery JS: {token}")

        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            wid = str(active.get("id") or "")
            metric_row = conn.execute(
                "SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='secondary_metrics'",
                (wid,),
            ).fetchone()
            if metric_row and any(term in str(metric_row["value_json"]) for term in VISIBLE_BANNED):
                raise AssertionError("generic workspace secondary_metrics contains legacy presentation strings")
            query_row = conn.execute(
                "SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='query_profile'",
                (wid,),
            ).fetchone()
            if query_row and any(term in str(query_row["value_json"]) for term in VISIBLE_BANNED):
                raise AssertionError("generic workspace query_profile contains legacy discovery vocabulary")

        if source_hits or generated_hits:
            raise AssertionError(f"neutral surface leak: source={source_hits}, generated={generated_hits}")
        return {
            "ok": True,
            "demo_creators": result.get("creators"),
            "demo_videos": result.get("videos"),
            "active_workspace": active.get("id"),
            "query_packs": EXPECTED_QUERY_PACKS,
            "query_profile_schema": EXPECTED_QUERY_PROFILE_SCHEMA,
            "query_profile": EXPECTED_QUERY_PROFILE,
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
