from __future__ import annotations
import json,re,shutil
from pathlib import Path
VERSION="4.0.2"

def clean(root:Path):
    removed=[]
    for pat in ("apply_v*.py","README_V*.txt","V*_PATCH_MANIFEST.json"):
        for p in root.glob(pat):
            if p.is_file(): p.unlink();removed.append(p.name)
    patches=root/"patches"
    if patches.exists():
        for p in patches.iterdir():
            if p.is_file() and re.match(r"v\d",p.name,re.I): p.unlink();removed.append(p.relative_to(root).as_posix())
        try:
            if not any(patches.iterdir()): patches.rmdir()
        except OSError: pass
    overlay=root/"overlay"
    if overlay.exists() and overlay.is_dir(): shutil.rmtree(overlay);removed.append("overlay/")
    return removed

def main():
    root=Path(__file__).resolve().parent
    required=[root/"hub.py",root/"creator_hub/server.py",root/"start-dashboard.cmd",root/"creator_hub/dashboard.py",root/"creator_hub/static/export_tools.js",root/"README.md",root/"SKILL.md"]
    missing=[str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        print("[ERROR] V4.0.2 files incomplete:",", ".join(missing));return 2
    forbidden=('default=".1"','bind((".1"','http://.1:8765/','host: str=".1"','{".1","::1"}')
    bad=[]
    for rel in ("hub.py","creator_hub/server.py","start-dashboard.cmd","setup.cmd","creator_hub/dashboard.py","creator_hub/static/export_tools.js"):
        p=root/rel
        if p.exists() and any(x in p.read_text(encoding="utf-8") for x in forbidden): bad.append(rel)
    if bad:
        print("[ERROR] Legacy invalid localhost literal remains:",", ".join(bad));return 3
    (root/"VERSION").write_text(VERSION+"\n",encoding="utf-8")
    p=root/"creator_hub/__init__.py";t=p.read_text(encoding="utf-8");p.write_text(re.sub(r'__version__\s*=\s*"[^"]+"',f'__version__ = "{VERSION}"',t),encoding="utf-8")
    s=root/"config/settings.json"
    if s.exists():
        d=json.loads(s.read_text(encoding="utf-8"));d["version"]=VERSION;s.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    from creator_hub.config import DEFAULT_DB
    from creator_hub.db import init_db
    init_db(DEFAULT_DB)
    c=root/"CHANGELOG.md";old=c.read_text(encoding="utf-8") if c.exists() else "# Changelog\n\n"
    entry=("## v4.0.2\n\n"
           "- 修复交互 Dashboard 启动时 `socket.gaierror: [Errno 11001] getaddrinfo failed`：历史无效 Host `.1` 统一改为 `127.0.0.1`。\n"
           "- `hub.py serve`、Doctor、`serve_dashboard()`、`start-dashboard.cmd` 统一使用 `127.0.0.1:8765`。\n"
           "- 本机敏感 API 来源校验改为 `127.0.0.1` / `::1`；Setup、Dashboard、导出、安装与架构说明同步修正。\n"
           "- Schema 保持 18；保留 V4.0.1 Dashboard 批量构建与缓存优化。\n\n")
    old=re.sub(r"^## v4\.0\.2\b.*?(?=^## |\Z)","",old,flags=re.S|re.M)
    if old.startswith("# Changelog"):
        c.write_text("# Changelog\n\n"+entry+old[len("# Changelog"):].lstrip("\n"),encoding="utf-8")
    else:c.write_text(entry+old,encoding="utf-8")
    removed=clean(root)
    print(f"[OK] YouTube Creator Intelligence Hub -> V{VERSION}")
    print("[OK] Interactive host -> 127.0.0.1:8765")
    print("[OK] Schema remains 18; existing data preserved")
    print(f"[OK] Cleaned obsolete/versioned helpers: {len(removed)}")
    return 0
if __name__=="__main__": raise SystemExit(main())
