from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

VERSION = "3.10.4"
PATCH_FILE = Path("patches") / "v3_10_4_ui_patch.js"

TARGET_JS = Path("creator_hub") / "static" / "metrics_workspace.js"
TARGET_INIT = Path("creator_hub") / "__init__.py"
TARGET_SETTINGS = Path("config") / "settings.json"

OLD_PATCH_RE = re.compile(
    r"/\* CDH V3\.10\.(?:1|2|3|4) UI PATCH START \*/.*?/\* CDH V3\.10\.(?:1|2|3|4) UI PATCH END \*/\s*",
    re.S,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    patch_path = root / PATCH_FILE
    js_path = root / TARGET_JS

    required = [patch_path, js_path, root / TARGET_INIT, root / TARGET_SETTINGS]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        print("[ERROR] 覆盖包或项目结构不完整：")
        for p in missing:
            print("       ", p)
        return 2

    js = js_path.read_text(encoding="utf-8")
    required_tokens = ("metrics-builder", "metrics-saved", "metrics-rule-builder", "metrics-rules", "metricList", "ruleList")
    absent = [x for x in required_tokens if x not in js]
    if absent:
        print("[ERROR] 当前 metrics_workspace.js 与 V3.10.x 预期结构不兼容：", ", ".join(absent))
        return 3

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "_upgrade_backups" / f"v3.10.4_{stamp}"
    for rel in (TARGET_JS, TARGET_INIT, TARGET_SETTINGS, Path("VERSION"), Path("CHANGELOG.md"), Path("upgrade.cmd")):
        src = root / rel
        if src.exists():
            dst = backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Replace any previous V3.10.x UI overlay with exactly one V3.10.4 overlay.
    js = OLD_PATCH_RE.sub("", js)
    if not js.endswith("\n"):
        js += "\n"
    patch = patch_path.read_text(encoding="utf-8").strip() + "\n"
    js_path.write_text(js + patch, encoding="utf-8")

    # Keep all visible/internal version declarations aligned.
    init_path = root / TARGET_INIT
    init_text = init_path.read_text(encoding="utf-8")
    if re.search(r'__version__\s*=\s*"[^"]+"', init_text):
        init_text = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{VERSION}"', init_text)
    else:
        init_text = f'__version__ = "{VERSION}"\n' + init_text
    init_path.write_text(init_text, encoding="utf-8")

    settings_path = root / TARGET_SETTINGS
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["version"] = VERSION
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (root / "VERSION").write_text(VERSION + "\n", encoding="utf-8")

    changelog = root / "CHANGELOG.md"
    entry = (
        "## v3.10.4\n\n"
        "- 修复二次指标四面板的高度归属：左侧“指标构建器 / 规则标签构建器”使用自然内容高度，右侧“已构建指标 / 规则列表”只能跟随左侧高度，不能反向撑高 Builder。\n"
        "- 已构建指标与规则列表继续保持 10 条/页，并在受约束的 Card Body 内使用纵向滚动；搜索、排序、翻页不再改变外层 Card 高度。\n"
        "- 新增 Builder ResizeObserver：切换指标类型、条件数量或窗口尺寸后自动重新同步右侧高度。\n"
        "- Schema 不变，不修改 SQLite 业务数据。\n\n"
    )
    old = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Changelog\n\n"
    old = re.sub(r"^## v3\.10\.4\b.*?(?=^## |\Z)", "", old, flags=re.S | re.M)
    changelog.write_text(entry + old.lstrip(), encoding="utf-8")

    print(f"[OK] 已升级到 V{VERSION}")
    print("[OK] 高度锚点：指标构建器 / 规则标签构建器（自然高度）")
    print("[OK] 右侧列表：跟随左侧高度 + 内部纵向滚动 + 10 条/页")
    print(f"[OK] 源码备份：{backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
