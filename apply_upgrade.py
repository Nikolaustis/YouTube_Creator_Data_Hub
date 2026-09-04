from __future__ import annotations

import json
import re
from pathlib import Path

VERSION = "4.4.0"
ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = [
        ROOT / "creator_hub" / "api" / "app.py",
        ROOT / "creator_hub" / "portfolio" / "demo.py",
        ROOT / "creator_hub" / "portfolio" / "benchmark.py",
        ROOT / "creator_hub" / "portfolio" / "ai_eval.py",
        ROOT / "creator_hub" / "static" / "creator_detail.js",
        ROOT / "scripts" / "neutralize_public_surface.py",
        ROOT / "scripts" / "check_public_surface_neutrality.py",
        ROOT / "scripts" / "neutralize_discovery_surface.py",
        ROOT / "scripts" / "query_pack_editor.py",
        ROOT / "config" / "query_packs.json",
        ROOT / "creator_hub" / "ai" / "prompts.py",
        ROOT / "creator_hub" / "compat" / "cloud_phone_workspace.json",
        ROOT / "creator_hub" / "compat" / "cloud_phone_brands.json",
        ROOT / "tests" / "test_public_surface_neutrality.py",
        ROOT / "README.md",
        ROOT / "SKILL.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        print("[ERROR] Neutral-surface overlay incomplete:", ", ".join(missing))
        return 2

    # Patch the large legacy Dashboard/metric files first. The overlay intentionally keeps
    # these as an idempotent source migration instead of shipping opaque full-file replacements.
    from scripts.neutralize_public_surface import patch_sources
    from scripts.neutralize_discovery_surface import patch_sources as patch_discovery_sources
    from scripts.query_pack_editor import patch_sources as patch_query_pack_sources

    changed_sources = sorted(set(patch_sources(ROOT) + patch_discovery_sources(ROOT) + patch_query_pack_sources(ROOT)))

    (ROOT / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    init_file = ROOT / "creator_hub" / "__init__.py"
    text = init_file.read_text(encoding="utf-8") if init_file.exists() else ""
    if "__version__" in text:
        text = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{VERSION}"', text)
    else:
        text += f'\n__version__ = "{VERSION}"\n'
    init_file.write_text(text.lstrip(), encoding="utf-8")

    settings = ROOT / "config" / "settings.json"
    if settings.exists():
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["version"] = VERSION
        settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    from scripts.repo_hygiene import clean

    removed = clean()
    from creator_hub.config import DEFAULT_DB
    from creator_hub.db import init_db

    init_db(DEFAULT_DB)

    # The schema remains unchanged. This is a presentation/config-scoping migration:
    # compatibility workspaces and their data are retained, but generic workspaces are cleaned
    # and the public/default active workspace is never compatibility-specific.
    from scripts.neutralize_public_surface import sanitize_database
    from scripts.neutralize_discovery_surface import sanitize_database as sanitize_discovery_database
    from scripts.query_pack_editor import sanitize_database as sanitize_query_pack_database

    migration = sanitize_database(Path(DEFAULT_DB))
    discovery_migration = sanitize_discovery_database(Path(DEFAULT_DB))
    query_pack_migration = sanitize_query_pack_database(Path(DEFAULT_DB), ROOT / "config" / "query_packs.json")

    print(f"[OK] Creator Intelligence Hub neutral surface -> {VERSION}")
    print("[OK] Database schema remains 18")
    print(f"[OK] Source modules neutralized: {len(changed_sources)}")
    print(f"[OK] Active Workspace: {migration.get('active_workspace_id')}")
    print(f"[OK] Switched away from compatibility default: {bool(migration.get('switched_from_compatibility'))}")
    print(f"[OK] Historical metric backups created: {migration.get('metric_backups_created', 0)}")
    print(f"[OK] Legacy Query Profiles reset: {discovery_migration.get('query_profiles_reset', 0)}")
    print(f"[OK] Query Profile backups created: {discovery_migration.get('query_profile_backups_created', 0)}")
    print(f"[OK] Query Profiles upgraded to editable schema: {query_pack_migration.get('query_profiles_upgraded', 0)}")
    print(f"[OK] Query Pack editor backups created: {query_pack_migration.get('query_profile_editor_backups_created', 0)}")
    print(f"[OK] Repository hygiene removed {len(removed)} legacy/cache paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
