from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "creator_hub.sqlite"
BACKUPS = ROOT / "backups"


def main() -> int:
    if not DB.exists():
        print("No existing SQLite database; pre-upgrade backup skipped.")
        return 0
    BACKUPS.mkdir(parents=True, exist_ok=True)
    dest = BACKUPS / f"pre_upgrade_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite"
    source = sqlite3.connect(DB)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
        target.commit()
        check = target.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        target.close()
        source.close()
    if str(check).lower() != "ok":
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"pre-upgrade backup quick_check failed: {check}")
    print(f"Pre-upgrade backup created: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
