from datetime import datetime, timezone

from creator_hub.monitoring import suspected_inactive_relationship, suspected_inactive_partner


def test_generic_inactivity_and_legacy_alias_match():
    settings = {"refresh_policy": {"normal": {"new_video_hours": 24, "metric_hours": 24}}}
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    kwargs = dict(
        monitoring_enabled=True,
        priority="normal",
        last_synced_at="2026-09-03T00:00:00Z",
        inactive_days=30,
        now=now,
    )
    generic = suspected_inactive_relationship(
        settings,
        relationship_evidence_count=3,
        latest_relationship_evidence_at="2026-07-01T00:00:00Z",
        **kwargs,
    )
    legacy = suspected_inactive_partner(
        settings,
        ugphone_video_count=3,
        latest_ugphone_upload="2026-07-01T00:00:00Z",
        **kwargs,
    )
    assert generic is True
    assert legacy is generic
