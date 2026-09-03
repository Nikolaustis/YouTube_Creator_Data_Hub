from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_public_surface_neutrality import run_check

ROOT = Path(__file__).resolve().parents[1]


def test_public_default_surface_is_domain_neutral() -> None:
    result = run_check()
    assert result["ok"] is True
    assert int(result["demo_creators"] or 0) == 8
    assert int(result["demo_videos"] or 0) == 64


def test_neutrality_checker_is_runnable_by_file_path() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_public_surface_neutrality.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "PUBLIC_SURFACE_NEUTRAL_OK" in proc.stdout
