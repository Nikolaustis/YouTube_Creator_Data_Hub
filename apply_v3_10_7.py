from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

VERSION = "3.10.7"
PATCH_FILE = Path("patches") / "v3_10_7_ui_patch.js"
TARGET_JS = Path("creator_hub") / "static" / "metrics_workspace.js"

OLD_PATCH_RE = re.compile(
    r"/\* CDH V3\.10\.(?:1|2|3|4|5|6|7) UI PATCH START \*/.*?/\* CDH V3\.10\.(?:1|2|3|4|5|6|7) UI PATCH END \*/\s*",
    re.S,
)

def main() -> int:
    root = Path(__file__).resolve().parent
    patch_path = root / PATCH_FILE
    js_path = root / TARGET_JS
    required = [
        patch_path, js_path, root/"creator_hub"/"__init__.py",
        root/"config"/"settings.json", root/"README.md"
    ]
    missing=[str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        print("[ERROR] 覆盖包或项目结构不完整：", ", ".join(missing))
        return 2

    js=js_path.read_text(encoding="utf-8")
    needed=("metrics-rule-builder","metrics-rules","ruleConditions","ruleList","addRuleCondition","saveRule","clearRule")
    absent=[x for x in needed if x not in js]
    if absent:
        print("[ERROR] 当前源码与 V3.10.x 预期结构不兼容：", ", ".join(absent))
        return 3

    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    backup=root/"_upgrade_backups"/f"v3.10.7_{stamp}"
    for rel in (
        TARGET_JS, Path("creator_hub")/"__init__.py", Path("config")/"settings.json",
        Path("README.md"), Path("VERSION"), Path("CHANGELOG.md"), Path("upgrade.cmd")
    ):
        src=root/rel
        if src.exists():
            dst=backup/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)

    js=OLD_PATCH_RE.sub("",js)
    if not js.endswith("\n"): js+="\n"
    js_path.write_text(js+patch_path.read_text(encoding="utf-8").strip()+"\n",encoding="utf-8")

    init=root/"creator_hub"/"__init__.py"
    t=init.read_text(encoding="utf-8")
    if re.search(r'__version__\s*=\s*"[^"]+"',t):
        t=re.sub(r'__version__\s*=\s*"[^"]+"',f'__version__ = "{VERSION}"',t)
    else:t=f'__version__ = "{VERSION}"\n'+t
    init.write_text(t,encoding="utf-8")

    sp=root/"config"/"settings.json"
    s=json.loads(sp.read_text(encoding="utf-8"));s["version"]=VERSION
    sp.write_text(json.dumps(s,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (root/"VERSION").write_text(VERSION+"\n",encoding="utf-8")

    cp=root/"CHANGELOG.md"
    entry=(
        "## v3.10.7\n\n"
        "- 修复规则条件行被 flex 压缩导致新增条件无法正常显示的问题：每条条件固定自然行高且禁止 shrink。\n"
        "- ruleConditions 成为唯一滚动 viewport：约三条条件高度，overflow-y:scroll；第 4 条及以后内部纵向滚动。\n"
        "- 删除每条条件各自的横向滚动条；窄宽度时仅保留条件 viewport 的共享横向滚动。\n"
        "- 删除 Rule Footer 的 margin-top:auto 空白；添加条件、保存/清空与说明紧随条件区。\n"
        "- 规则外壳根据结构化内容测量一次后冻结，条件数量变化不再改变左右 Card 高度。\n"
        "- README.md 同步更新；Schema 与 SQLite 业务数据不变。\n\n"
    )
    old=cp.read_text(encoding="utf-8") if cp.exists() else "# Changelog\n\n"
    old=re.sub(r"^## v3\.10\.7\b.*?(?=^## |\Z)","",old,flags=re.S|re.M)
    if old.startswith("# Changelog"):
        rest=old[len("# Changelog"):].lstrip("\n");cp.write_text("# Changelog\n\n"+entry+rest,encoding="utf-8")
    else:cp.write_text(entry+old,encoding="utf-8")

    print("[OK] V3.10.7 applied")
    print("[OK] 3-row non-shrinking condition viewport + visible vertical scroll")
    print("[OK] No per-row horizontal scrollbars; no footer filler gap")
    print(f"[OK] Backup: {backup}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
