from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def offenders() -> list[Path]:
    found: list[Path] = []
    for path in ROOT.rglob("__pycache__"):
        if path.is_dir():
            found.append(path)
    for pattern in ("*.pyc", "*.pyo"):
        found.extend(path for path in ROOT.rglob(pattern) if path.is_file())
    patches = ROOT / "patches"
    if patches.exists():
        found.append(patches)
    old_release = ROOT / "docs" / "RELEASE_NOTES_4.1.0.md"
    if old_release.exists():
        found.append(old_release)
    return sorted(set(found), key=lambda p: p.as_posix())


def clean() -> list[str]:
    removed = []
    for path in offenders():
        if not path.exists():
            continue
        removed.append(path.relative_to(ROOT).as_posix())
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        bad = offenders()
        if bad:
            print("REPO_HYGIENE_FAILED")
            for path in bad:
                print(path.relative_to(ROOT).as_posix())
            raise SystemExit(1)
        print("REPO_HYGIENE_OK")
        return
    removed = clean()
    print(f"REPO_HYGIENE_CLEANED {len(removed)}")
    for item in removed:
        print(f"- {item}")


if __name__ == "__main__":
    main()
