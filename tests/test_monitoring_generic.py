from datetime import datetime, timezone

from creator_hub.monitoring import suspected_inactive_relationship


def test_generic_relationship_inactivity():
    settings = {"refresh_policy": {"normal": {"new_video_hours": 24, "metric_hours": 24}}}
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    result = suspected_inactive_relationship(
        settings,
        monitoring_enabled=True,
        priority="normal",
        last_synced_at="2026-09-03T00:00:00Z",
        relationship_evidence_count=3,
        latest_relationship_evidence_at="2026-07-01T00:00:00Z",
        inactive_days=30,
        now=now,
    )
    assert result is True
