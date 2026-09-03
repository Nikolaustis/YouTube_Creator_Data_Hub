from __future__ import annotations

from datetime import datetime
from typing import Any

from .util import now_utc, parse_iso


def due_hours(settings: dict[str, Any], priority: str | None = None, mode: str = "incremental") -> float:
    """Return the configured refresh interval for a creator priority/mode."""
    policy = (settings.get("refresh_policy") or {}).get(priority or "normal", {})
    new_h = float(policy.get("new_video_hours") or 24)
    metric_h = float(policy.get("metric_hours") or new_h)
    if mode in {"metrics-only", "metrics"}:
        return metric_h
    if mode in {"channel-only", "channel", "full-history"}:
        return new_h
    return min(new_h, metric_h)


def monitoring_data_fresh(
    settings: dict[str, Any],
    *,
    priority: str | None,
    last_synced_at: str | None,
    now: datetime | None = None,
    scheduler_grace_hours: float = 6.0,
) -> bool:
    """Whether the latest successful sync is fresh enough for status inference."""
    last = parse_iso(last_synced_at)
    current = now or parse_iso(now_utc())
    if not last or not current:
        return False
    age_hours = max(0.0, (current - last).total_seconds() / 3600.0)
    return age_hours <= due_hours(settings, priority, "incremental") + float(scheduler_grace_hours)


def suspected_inactive_relationship(
    settings: dict[str, Any],
    *,
    monitoring_enabled: bool | int,
    priority: str | None,
    last_synced_at: str | None,
    relationship_evidence_count: int | float | None,
    latest_relationship_evidence_at: str | None,
    inactive_days: float = 30.0,
    now: datetime | None = None,
) -> bool:
    """Domain-neutral inactivity heuristic for an evidenced Creator relationship.

    The warning is deliberately conservative: the Creator must still be monitored, the
    relationship must have historical evidence, the monitoring data must be fresh, and
    the most recent relationship evidence must be older than the configured threshold.
    """
    if not bool(monitoring_enabled) or float(relationship_evidence_count or 0) <= 0:
        return False
    current = now or parse_iso(now_utc())
    latest = parse_iso(latest_relationship_evidence_at)
    if not current or not latest:
        return False
    if not monitoring_data_fresh(
        settings,
        priority=priority,
        last_synced_at=last_synced_at,
        now=current,
    ):
        return False
    return (current - latest).total_seconds() >= float(inactive_days) * 86400.0


def suspected_inactive_partner(
    settings: dict[str, Any],
    *,
    monitoring_enabled: bool | int,
    priority: str | None,
    last_synced_at: str | None,
    ugphone_video_count: int | float | None,
    latest_ugphone_upload: str | None,
    inactive_days: float = 30.0,
    now: datetime | None = None,
) -> bool:
    """Backward-compatible cloud-phone alias.

    New Core code should call :func:`suspected_inactive_relationship`. The legacy
    signature remains so existing Dashboard and saved metric behavior do not break.
    """
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
