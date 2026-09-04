from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRICT_TARGETS = [
    ROOT / "creator_hub" / "api",
    ROOT / "creator_hub" / "portfolio",
    ROOT / "creator_hub" / "field_registry.py",
    ROOT / "creator_hub" / "ai" / "workspace_tools.py",
    ROOT / "creator_hub" / "ai" / "prompts.py",
]
BANNED = re.compile(r"\b(ugphone|ldcloud|redfinger|vsphone|cloud[ _-]?phone)\b", re.I)
LEGACY_BOUNDARY = [
    "creator_hub/compat/",
    "creator_hub/dashboard.py",
    "creator_hub/metric_workspace.py",
    "creator_hub/ai/local_tools.py",
    "creator_hub/server.py",
]


def iter_python(target: Path):
    if target.is_file():
        yield target
    elif target.exists():
        yield from target.rglob("*.py")


def check() -> list[str]:
    findings = []
    for target in STRICT_TARGETS:
        for path in iter_python(target):
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                if BANNED.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the new reusable Core surfaces are domain-neutral")
    parser.add_argument("--show-boundary", action="store_true")
    args = parser.parse_args()
    findings = check()
    if findings:
        print("CORE_PORTABILITY_FAILED")
        print("\n".join(findings))
        raise SystemExit(1)
    print("CORE_PORTABILITY_OK")
    if args.show_boundary:
        print("Legacy compatibility boundary:")
        for item in LEGACY_BOUNDARY:
            print(f"- {item}")


if __name__ == "__main__":
    main()
