from __future__ import annotations

from scripts.check_public_surface_neutrality import run_check


def test_public_default_surface_is_domain_neutral() -> None:
    result = run_check()
    assert result["ok"] is True
    assert int(result["demo_creators"] or 0) == 8
    assert int(result["demo_videos"] or 0) == 64
