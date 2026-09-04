from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "creator_hub.sqlite"
DEFAULT_SETTINGS = ROOT / "config" / "settings.json"
DEFAULT_BRANDS = ROOT / "creator_hub" / "compat" / "cloud_phone_brands.json"
DEFAULT_QUERY_PACKS = ROOT / "config" / "query_packs.json"
DEFAULT_OUTPUT = ROOT / "output" / "dashboard"
DEFAULT_METRIC_CONFIG = ROOT / "data" / "secondary_metrics_v4.json"
LEGACY_METRIC_CONFIG = ROOT / "data" / "secondary_metrics_v3.json"


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_SETTINGS
    return json.loads(p.read_text(encoding="utf-8"))


def load_brands(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_BRANDS
    return json.loads(p.read_text(encoding="utf-8"))


def load_query_packs(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_QUERY_PACKS
    return json.loads(p.read_text(encoding="utf-8"))

# V4.3 generic-discovery: config
