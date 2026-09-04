from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.3.0"
OLD_PACK_IDS = {"core", "farming", "afk", "active", "commercial"}
DISCOVERY_BANNED = re.compile(
    r"ugphone|ldcloud|redfinger|vsphone|cloud\s*phone|cloudphone|云手机|雲手機|"
    r"\bafk\b|auto\s*farm|\bfarming\b|\bgameplay\b|输入游戏名称|游戏\s*Creator|Anime Expeditions|"
    r"partnered_ugphone|unpartnered_ugphone|ldcloud_creator|redfinger_creator|vsphone_creator",
    re.I,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _replace(text: str, old: str, new: str, label: str, *, required: bool = True) -> str:
    if old not in text:
        if required:
            raise RuntimeError(f"generic-discovery patch anchor missing: {label}")
        return text
    return text.replace(old, new)


def _sub(text: str, pattern: str, repl: str, label: str, *, required: bool = True) -> str:
    out, count = re.subn(pattern, repl, text, flags=re.S)
    if required and count == 0:
        raise RuntimeError(f"generic-discovery regex anchor missing: {label}")
    return out


def patch_dashboard(path: Path) -> None:
    text = _read(path)
    if "# V4.3 generic-discovery: dashboard" in text:
        return
    text = _replace(
        text,
        'placeholder="输入游戏名称，例如 Anime Expeditions"',
        'placeholder="输入主题、产品、品牌或关键词，例如 AI productivity"',
        "discovery search placeholder",
    )
    # The relation column is Workspace-defined, not a fixed partnership identity.
    text = text.replace('<th data-field="identity">身份</th>', '<th data-field="identity">Workspace 关系</th>')
    text += "\n# V4.3 generic-discovery: dashboard\n"
    _write(path, text)


def patch_discovery_js(path: Path) -> None:
    text = _read(path)
    if "/* V4.3 generic-discovery */" in text:
        return

    text = _replace(
        text,
        "const QP_STORE='cdh-query-packs-v2',QP_OLD_STORE='cdh-query-packs-v1',QP_LANG_STORE='cdh-query-language-v1';",
        "const WORKSPACE_KEY=String((window.CDH_CREATOR_FACTS||{}).workspace_id||'general').replace(/[^a-zA-Z0-9_.:-]/g,'_');\n"
        "const QP_STORE='cdh-query-packs-v3::'+WORKSPACE_KEY,QP_OLD_STORES=['cdh-query-packs-v3','cdh-query-packs-v2','cdh-query-packs-v1'],QP_LANG_STORE='cdh-query-language-v2::'+WORKSPACE_KEY;",
        "query pack storage version",
    )

    text = _sub(
        text,
        r"function loadQueryState\(\)\{.*?\}\nfunction queryProfileValue\(\)\{.*?\}\nfunction saveQueryState",
        "function loadQueryState(){let saved=null;try{saved=JSON.parse(localStorage.getItem(QP_STORE)||'null');if(!saved){for(const k of QP_OLD_STORES)localStorage.removeItem(k)}}catch(e){}return mergeQueryState(saved,false)}\n"
        "function queryProfileValue(){return {schema_version:3,profile:'generic_creator_discovery_v1',language:currentQueryLang(),packs:queryState?.packs||{}}}\n"
        "function saveQueryState",
        "query profile local migration",
    )

    text = _sub(
        text,
        r"async function hydrateQueryProfile\(\)\{.*?\}\nfunction currentQueryLang",
        "async function hydrateQueryProfile(){if(!interactive)return;const x=await post('/api/settings/get',{key:'query_profile'});const compatible=Number(x.value?.schema_version||0)>=3&&x.value?.profile==='generic_creator_discovery_v1'&&x.value?.packs;if(compatible){queryState=mergeQueryState(x.value,false);const lang=document.getElementById('queryLanguage');if(x.value.language&&QP.languages?.[x.value.language])lang.value=x.value.language;localStorage.setItem(QP_STORE,JSON.stringify(queryState));localStorage.setItem(QP_LANG_STORE,lang.value)}else{queryState=freshQueryState();await post('/api/settings/set',{key:'query_profile',value:queryProfileValue()})}queryDbReady=true;renderQueryPacks();updateQueryPreview();const st=document.getElementById('queryProfileStatus');if(st)st.textContent='Query Expansion 配置已按当前 Workspace 保存到本地 SQLite'}\n"
        "function currentQueryLang",
        "query profile database migration",
    )

    text = _sub(
        text,
        r"function identity\(cid\)\{.*?\}\nfunction tierPill",
        "function relationshipCount(c){return Object.entries(c||{}).filter(([k,v])=>k.startsWith('relationship__')&&Number(v||0)).length}\n"
        "function identity(cid){const c=byId.get(cid);if(!c)return '<span class=\"pill\">尚未入库</span>';const n=relationshipCount(c);return n?`<div class=\"identity-stack\"><span class=\"pill identity-partnered\">Workspace 关系 × ${n}</span></div>`:'<span class=\"small\">—</span>'}\n"
        "function tierPill",
        "dynamic discovery relationship display",
    )

    text = _sub(
        text,
        r"function liveFilterOptions\(field\)\{.*?\}\nfunction liveConditionRow",
        "function liveFilterOptions(field){if(field==='tier')return ['A','B','C','D'].map(x=>[x,x]);if(field==='identity')return [['has_relationship','存在 Workspace 关系'],['no_relationship','无 Workspace 关系']];return []}\n"
        "function liveConditionRow",
        "generic discovery relationship filter",
    )
    text = text.replace('<option value="identity">身份标签</option>', '<option value="identity">Workspace 关系</option>')

    text = _sub(
        text,
        r"function liveCond\(c,x\)\{.*?\}\nfunction chain",
        "function liveCond(c,x){if(x.field==='geo'){const code=c.country_resolved||c.country_api||'',r=countryByCode.get(code);if(!r||r.group!==x.value)return false;return x.country?code===x.country:true}if(x.field==='tier')return (c.opportunity_tier||'')===x.value;const f=byId.get(c.channel_id),n=relationshipCount(f);if(x.value==='has_relationship')return n>0;if(x.value==='no_relationship')return n===0;return true}\n"
        "function chain",
        "generic discovery relationship predicate",
    )

    # Export the same generic Workspace relationship summary shown in the table.
    text = _sub(
        text,
        r"identity:\(\(\)=>\{const f=byId\.get\(c\.channel_id\);if\(!f\)return '尚未入库';return \[.*?\]\.filter\(Boolean\)\.join\(' \| '\)\}\)\(\)",
        "identity:(()=>{const f=byId.get(c.channel_id);if(!f)return '尚未入库';const n=relationshipCount(f);return n?`Workspace 关系 × ${n}`:'—'})()",
        "generic discovery export relationship",
    )

    text = text.replace('输入游戏名称后显示查询预览', '输入搜索主题后显示查询预览')
    text = text.replace("if(!q)return alert('请输入游戏名称')", "if(!q)return alert('请输入搜索主题或关键词')")

    # Old v1/v2 vocabulary must not be visible or executable after the migration.
    leftovers = DISCOVERY_BANNED.findall(text)
    if leftovers:
        sample = sorted({str(x) for x in leftovers})[:12]
        raise RuntimeError(f"discovery UI still contains legacy domain vocabulary after patch: {sample}")

    text += "\n/* V4.3 generic-discovery */\n"
    _write(path, text)



def patch_workspace_loader(path: Path) -> None:
    text = _read(path)
    if "# V4.3 generic-discovery: workspace-loader" in text:
        return
    old = '''    def _all_templates(self) -> list[dict[str, Any]]:
        return list(_templates(self.templates_path).get("templates") or [])
'''
    new = '''    def _all_templates(self) -> list[dict[str, Any]]:
        public = list(_templates(self.templates_path).get("templates") or [])
        compat_path = Path(__file__).resolve().parent / "compat" / "cloud_phone_workspace.json"
        if compat_path.exists():
            public.extend(list(_templates(compat_path).get("templates") or []))
        return public
'''
    text = _replace(text, old, new, "compat template loader")
    text += "\n# V4.3 generic-discovery: workspace-loader\n"
    _write(path, text)


def patch_config(path: Path) -> None:
    text = _read(path)
    if "# V4.3 generic-discovery: config" in text:
        return
    text = _replace(
        text,
        'DEFAULT_BRANDS = ROOT / "config" / "brands.json"',
        'DEFAULT_BRANDS = ROOT / "creator_hub" / "compat" / "cloud_phone_brands.json"',
        "compat brand config relocation",
    )
    text += "\n# V4.3 generic-discovery: config\n"
    _write(path, text)

def patch_workspace_templates(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    templates = data.get("templates") or []
    target = next((x for x in templates if str(x.get("id")) in {"gaming_creator", "creator_discovery"}), None)
    if target is None:
        raise RuntimeError("Creator discovery template not found")
    target.update({
        "id": "creator_discovery",
        "name": "Creator Discovery",
        "name_zh": "Creator 发现",
        "description_zh": "适合通用 Creator 发现、内容类型分类和持续创作判断，不预设具体行业或内容品类。",
        "brands": [],
        "brand_groups": [],
        "taxonomies": [{
            "key": "content_type",
            "name": "内容类型",
            "entity_type": "video",
            "multi_select": True,
            "labels": [
                {"key": "tutorial", "name": "教程 / 讲解"},
                {"key": "review", "name": "评测 / 比较"},
                {"key": "news", "name": "动态 / 资讯"},
                {"key": "livestream", "name": "直播"},
                {"key": "shorts", "name": "Shorts"},
            ],
        }],
        "business_metrics": [],
        "discovery_profiles": [{
            "key": "creator_general",
            "name": "Creator General",
            "profile": {
                "positive_terms": ["guide", "tutorial", "review", "how to"],
                "exclude_official_channels": True,
            },
        }],
        "presets": [],
    })
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_query_packs(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [str(x.get("id") or "") for x in data.get("packs") or []]
    expected = ["learn", "review", "use_case", "updates", "community", "custom"]
    if ids != expected:
        raise RuntimeError(f"generic query pack ids are not canonical: {ids}")
    raw = json.dumps(data, ensure_ascii=False)
    hit = DISCOVERY_BANNED.search(raw)
    if hit:
        raise RuntimeError(f"generic query packs contain legacy term: {hit.group(0)}")


def patch_sources(root: Path = ROOT) -> list[str]:
    validate_query_packs(root / "config" / "query_packs.json")
    targets = {
        "creator_hub/dashboard.py": patch_dashboard,
        "creator_hub/static/discovery.js": patch_discovery_js,
        "creator_hub/workspace.py": patch_workspace_loader,
        "creator_hub/config.py": patch_config,
        "config/workspace_templates.json": patch_workspace_templates,
    }
    changed: list[str] = []
    for rel, fn in targets.items():
        path = root / rel
        if not path.exists():
            raise RuntimeError(f"required generic-discovery source missing: {rel}")
        before = path.read_bytes()
        fn(path)
        if path.read_bytes() != before:
            changed.append(rel)
    return changed


def _is_compat_workspace(row: Any) -> bool:
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except Exception:
        meta = {}
    return str(row["template_id"] or "") == "cloud_phone_growth" or bool(meta.get("compatibility_profile"))


def _legacy_query_profile(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    if int(value.get("schema_version") or 0) >= 3 and value.get("profile") == "generic_creator_discovery_v1":
        return False
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    packs = set((value.get("packs") or {}).keys()) if isinstance(value.get("packs"), dict) else set()
    return bool(packs & OLD_PACK_IDS) or bool(DISCOVERY_BANNED.search(raw)) or int(value.get("schema_version") or 0) < 3


def sanitize_database(db_path: Path) -> dict[str, Any]:
    from creator_hub.db import connect, json_dump, json_load
    from creator_hub.util import now_utc

    reset = 0
    backups = 0
    with connect(db_path) as conn:
        workspaces = conn.execute("SELECT id,template_id,metadata_json FROM workspaces").fetchall()
        for ws in workspaces:
            if _is_compat_workspace(ws):
                continue
            wid = str(ws["id"])
            row = conn.execute(
                "SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='query_profile'",
                (wid,),
            ).fetchone()
            if not row:
                continue
            value = json_load(row["value_json"], {})
            if not _legacy_query_profile(value):
                continue
            backup_key = "query_profile_pre_neutral_4_3"
            exists = conn.execute(
                "SELECT 1 FROM workspace_settings WHERE workspace_id=? AND key=?",
                (wid, backup_key),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO workspace_settings(workspace_id,key,value_json,updated_at) VALUES(?,?,?,?)",
                    (wid, backup_key, row["value_json"], now_utc()),
                )
                backups += 1
            fresh = {"schema_version": 3, "profile": "generic_creator_discovery_v1", "language": "en", "packs": {}}
            conn.execute(
                "UPDATE workspace_settings SET value_json=?,updated_at=? WHERE workspace_id=? AND key='query_profile'",
                (json_dump(fresh), now_utc(), wid),
            )
            reset += 1
        conn.commit()
    return {"query_profiles_reset": reset, "query_profile_backups_created": backups}


def apply(root: Path = ROOT, db_path: Path | None = None, *, source_only: bool = False) -> dict[str, Any]:
    changed = patch_sources(root)
    db_result = None
    if not source_only:
        if db_path is None:
            from creator_hub.config import DEFAULT_DB
            db_path = Path(DEFAULT_DB)
        db_result = sanitize_database(Path(db_path))
    return {"changed_sources": changed, "database": db_result}


def main() -> int:
    ap = argparse.ArgumentParser(description="Remove legacy domain assumptions from Creator Discovery and Query Expansion.")
    ap.add_argument("--source-only", action="store_true")
    ap.add_argument("--db", default="")
    args = ap.parse_args()
    db = Path(args.db).resolve() if args.db else None
    result = apply(ROOT, db, source_only=args.source_only)
    print(json.dumps({"ok": True, "version": VERSION, **result}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
