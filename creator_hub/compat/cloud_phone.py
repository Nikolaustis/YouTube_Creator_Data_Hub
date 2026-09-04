from __future__ import annotations

from typing import Any


LEGACY_ROLE_KEYS = {"ugphone", "competitor", "daily", "multi_brand", "other_cloud_phone", "pending"}
LEGACY_BRAND_KEYS = {"ugphone", "ldcloud", "redfinger", "vsphone"}


def legacy_metric_aliases() -> dict[str, str]:
    """Compatibility aliases retained for historical saved metrics and filters."""
    return {
        "ugphone_video_count": "taxonomy_count__content_relationship__own_brand",
        "competitor_video_count": "taxonomy_count__content_relationship__competitor",
        "partnered_ugphone": "relationship__partnership__known",
        "suspected_inactive_partner": "relationship_health__partnership__inactive",
    }


def is_cloud_phone_workspace(context: dict[str, Any] | None) -> bool:
    ws = (context or {}).get("workspace") or {}
    return str(ws.get("template_id") or "") == "cloud_phone_growth"


def suspected_inactive_partner(
    settings: dict[str, Any],
    *,
    monitoring_enabled: bool | int,
    priority: str | None,
    last_synced_at: str | None,
    ugphone_video_count: int | float | None,
    latest_ugphone_upload: str | None,
    inactive_days: float = 30.0,
    now=None,
) -> bool:
    """Historical compatibility signature backed by the domain-neutral heuristic."""
    from ..monitoring import suspected_inactive_relationship

    return suspected_inactive_relationship(
        settings,
        monitoring_enabled=monitoring_enabled,
        priority=priority,
        last_synced_at=last_synced_at,
        relationship_evidence_count=ugphone_video_count,
        latest_relationship_evidence_at=latest_ugphone_upload,
        inactive_days=inactive_days,
        now=now,
    )
