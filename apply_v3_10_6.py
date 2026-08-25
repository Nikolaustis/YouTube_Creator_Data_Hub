from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

VERSION = "3.10.6"
PATCH_FILE = Path("patches") / "v3_10_6_ui_patch.js"
TARGET_JS = Path("creator_hub") / "static" / "metrics_workspace.js"

OLD_PATCH_RE = re.compile(
    r"/\* CDH V3\.10\.(?:1|2|3|4|5|6) UI PATCH START \*/.*?/\* CDH V3\.10\.(?:1|2|3|4|5|6) UI PATCH END \*/\s*",
    re.S,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    patch_path = root / PATCH_FILE
    js_path = root / TARGET_JS

    required = [
        patch_path,
        js_path,
        root / "creator_hub" / "__init__.py",
        root / "config" / "settings.json",
        root / "README.md",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        print("[ERROR] 覆盖包或项目结构不完整：")
        for p in missing:
            print("       ", p)
        return 2

    js = js_path.read_text(encoding="utf-8")
    required_tokens = (
        "metrics-rule-builder",
        "metrics-rules",
        "ruleConditions",
        "ruleList",
        "addRuleCondition",
        "saveRule",
        "clearRule",
    )
    absent = [x for x in required_tokens if x not in js]
    if absent:
        print("[ERROR] 当前源码与 V3.10.x 预期结构不兼容：", ", ".join(absent))
        return 3

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "_upgrade_backups" / f"v3.10.6_{stamp}"
    backup_targets = [
        TARGET_JS,
        Path("creator_hub") / "__init__.py",
        Path("config") / "settings.json",
        Path("README.md"),
        Path("VERSION"),
        Path("CHANGELOG.md"),
        Path("upgrade.cmd"),
    ]
    for rel in backup_targets:
        src = root / rel
        if src.exists():
            dst = backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Exactly one current UI overlay.
    js = OLD_PATCH_RE.sub("", js)
    if not js.endswith("\n"):
        js += "\n"
    patch = patch_path.read_text(encoding="utf-8").strip() + "\n"
    js_path.write_text(js + patch, encoding="utf-8")

    # Version declarations.
    init_path = root / "creator_hub" / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8")
    if re.search(r'__version__\s*=\s*"[^"]+"', init_text):
        init_text = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{VERSION}"', init_text)
    else:
        init_text = f'__version__ = "{VERSION}"\n' + init_text
    init_path.write_text(init_text, encoding="utf-8")

    settings_path = root / "config" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["version"] = VERSION
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "VERSION").write_text(VERSION + "\n", encoding="utf-8")

    changelog = root / "CHANGELOG.md"
    entry = (
        "## v3.10.6\n\n"
        "- 规则 / 标签构建器改为桌面端固定外壳高度；条件数量不再改变 Card 高度。\n"
        "- 条件 viewport 固定为约三条条件高度，第 4 条及以后只在条件区内部垂直滚动。\n"
        "- 规则列表使用与规则构建器相同的固定外壳；只有 ruleList Body 滚动。\n"
        "- 禁止规则卡片 flex-grow / stretch，消除少量规则时卡片下方被拉出的巨大空白。\n"
        "- 规则列表继续 10 条/页；指标构建器 / 已构建指标的现有高度逻辑保持不变。\n"
        "- README.md 同步更新到 V3.10.6；Schema 不变，不修改 SQLite 业务数据。\n\n"
    )
    old = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Changelog\n\n"
    old = re.sub(r"^## v3\.10\.6\b.*?(?=^## |\Z)", "", old, flags=re.S | re.M)
    if old.startswith("# Changelog"):
        rest = old[len("# Changelog"):].lstrip("\n")
        changelog.write_text("# Changelog\n\n" + entry + rest, encoding="utf-8")
    else:
        changelog.write_text(entry + old, encoding="utf-8")

    print(f"[OK] YouTube Creator Data Hub -> V{VERSION}")
    print("[OK] Rule Builder / Rule List: fixed 690px desktop shells")
    print("[OK] Rule Conditions: fixed three-row viewport + vertical scrolling")
    print("[OK] Rule cards: natural height; flex-grow/stretch disabled")
    print("[OK] README.md -> V3.10.6")
    print(f"[OK] 升级前源码备份：{backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
