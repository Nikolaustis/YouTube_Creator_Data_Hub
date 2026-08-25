from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

VERSION = "3.10.5"
PATCH_FILE = Path("patches") / "v3_10_5_ui_patch.js"
TARGET_JS = Path("creator_hub") / "static" / "metrics_workspace.js"

OLD_PATCH_RE = re.compile(
    r"/\* CDH V3\.10\.(?:1|2|3|4|5) UI PATCH START \*/.*?/\* CDH V3\.10\.(?:1|2|3|4|5) UI PATCH END \*/\s*",
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
        "addRuleCondition",
        "saveRule",
        "clearRule",
    )
    absent = [x for x in required_tokens if x not in js]
    if absent:
        print("[ERROR] 当前源码与 V3.10.x 预期结构不兼容：", ", ".join(absent))
        return 3

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "_upgrade_backups" / f"v3.10.5_{stamp}"
    backup_targets = [
        TARGET_JS,
        Path("creator_hub") / "__init__.py",
        Path("config") / "settings.json",
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

    js = OLD_PATCH_RE.sub("", js)
    if not js.endswith("\n"):
        js += "\n"
    patch = patch_path.read_text(encoding="utf-8").strip() + "\n"
    js_path.write_text(js + patch, encoding="utf-8")

    # Align version declarations.
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
        "## v3.10.5\n\n"
        "- 扩展“规则 / 标签构建器”的桌面端内部结构：规则元数据、条件设置、保存 Footer 三段式布局，避免一条规则时 Card 过度收缩。\n"
        "- 规则说明区域加高；条件区增加标题、提示、独立“添加条件”区域；保存 / 清空移动到独立 Footer。\n"
        "- 规则构建器桌面端最小高度约 500px；规则列表继续跟随左侧 Builder 高度，并保持 10 条/页与 Card 内纵向滚动。\n"
        "- V3.10.4 的高度归属原则保持不变：右侧列表不能反向撑高左侧 Builder。\n"
        "- Schema 不变，不修改 SQLite 业务数据。\n\n"
    )
    old = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Changelog\n\n"
    old = re.sub(r"^## v3\.10\.5\b.*?(?=^## |\Z)", "", old, flags=re.S | re.M)
    if old.startswith("# Changelog"):
        rest = old[len("# Changelog"):].lstrip("\n")
        changelog.write_text("# Changelog\n\n" + entry + rest, encoding="utf-8")
    else:
        changelog.write_text(entry + old, encoding="utf-8")

    print(f"[OK] YouTube Creator Data Hub -> V{VERSION}")
    print("[OK] 规则 / 标签构建器：三段式纵向结构 + 桌面端 min-height 500px")
    print("[OK] 规则列表：继续匹配左侧高度 + 10 条/页 + 内部滚动")
    print("[OK] 右侧列表不会反向撑高 Builder")
    print(f"[OK] 升级前源码备份：{backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
