from __future__ import annotations

import json
from pathlib import Path

from scripts.neutralize_discovery_surface import _legacy_query_profile, validate_query_packs

ROOT = Path(__file__).resolve().parents[1]


def test_public_query_pack_catalog_is_generic() -> None:
    path = ROOT / "config" / "query_packs.json"
    validate_query_packs(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["profile"] == "generic_creator_discovery_v2"
    assert data["schema_version"] == 4
    assert [p["id"] for p in data["packs"]] == ["learn", "review", "use_case", "updates", "community", "custom"]


def test_legacy_query_profiles_are_reset_but_generic_profiles_are_not_reclassified_as_legacy() -> None:
    legacy = {"language": "en", "packs": {"core": {"enabled": True}, "afk": {"enabled": True}}}
    generic_v3 = {"schema_version": 3, "profile": "generic_creator_discovery_v1", "language": "en", "packs": {}}
    generic_v4 = {"schema_version": 4, "profile": "generic_creator_discovery_v2", "language": "en", "packs": {}}
    assert _legacy_query_profile(legacy) is True
    assert _legacy_query_profile(generic_v3) is False
    assert _legacy_query_profile(generic_v4) is False
