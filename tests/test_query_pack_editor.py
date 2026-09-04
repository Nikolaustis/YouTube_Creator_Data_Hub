from __future__ import annotations

import json
from pathlib import Path

from scripts.query_pack_editor import PROFILE, SCHEMA_VERSION, default_profile, upgrade_profile

ROOT = Path(__file__).resolve().parents[1]


def template() -> dict:
    return json.loads((ROOT / "config" / "query_packs.json").read_text(encoding="utf-8"))


def test_default_query_profile_is_editable_schema() -> None:
    state = default_profile(template())
    assert state["schema_version"] == SCHEMA_VERSION == 4
    assert state["profile"] == PROFILE == "generic_creator_discovery_v2"
    assert state["order"] == ["learn", "review", "use_case", "updates", "community", "custom"]
    assert state["packs"]["learn"]["system"] is True


def test_v3_profile_migration_preserves_user_term_edits() -> None:
    old = {
        "schema_version": 3,
        "profile": "generic_creator_discovery_v1",
        "language": "en",
        "packs": {
            "learn": {
                "enabled": True,
                "terms": {"en": ["guide", "my custom keyword"]},
                "active": {"en": ["my custom keyword"]},
            },
            "review": {"enabled": True},
        },
    }
    state = upgrade_profile(old, template())
    assert state["schema_version"] == 4
    assert state["packs"]["learn"]["terms"]["en"] == ["guide", "my custom keyword"]
    assert state["packs"]["learn"]["active"]["en"] == ["my custom keyword"]
    assert state["packs"]["review"]["enabled"] is True


def test_v4_custom_groups_survive_normalization() -> None:
    state = default_profile(template())
    state["packs"]["my_pack"] = {
        "id": "my_pack",
        "name": "High Intent",
        "description": "User-defined strategy",
        "enabled": True,
        "system": False,
        "terms": {"en": ["buying guide"]},
        "active": {"en": ["buying guide"]},
    }
    state["order"] = ["my_pack", *state["order"]]
    normalized = upgrade_profile(state, template())
    assert normalized["order"][0] == "my_pack"
    assert normalized["packs"]["my_pack"]["name"] == "High Intent"
    assert normalized["packs"]["my_pack"]["terms"]["en"] == ["buying guide"]
    assert normalized["packs"]["my_pack"]["system"] is False


def test_v4_system_pack_can_intentionally_have_empty_language_terms() -> None:
    state = default_profile(template())
    state["packs"]["learn"]["terms"]["en"] = []
    state["packs"]["learn"]["active"]["en"] = []
    normalized = upgrade_profile(state, template())
    assert normalized["packs"]["learn"]["terms"]["en"] == []
    assert normalized["packs"]["learn"]["active"]["en"] == []
