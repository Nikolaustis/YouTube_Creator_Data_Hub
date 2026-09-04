from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .db import connect, json_dump, json_load
from .util import now_utc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATES = ROOT / "config" / "workspace_templates.json"

WORKSPACE_BODY = r"""
<div class="title">
  <div>
    <h1>工作区</h1>
    <div class="sub">Creator / Video 基础事实全局共享；品牌、标签、关系、商业指标、规则与发现策略按 Workspace 隔离。</div>
  </div>
</div>
<div class="note"><b>Workspace 原则：</b>Core 只提供通用 Creator / Video 事实与 Workspace primitives。品牌、行业、关系、商业指标和分类语义均由当前 Workspace 配置提供；兼容 Pack 默认隐藏，只有显式启用时才进入工作区。</div>

<div class="grid two section anchor-section" id="workspace-overview">
  <div class="card">
    <h2>当前 Workspace</h2>
    <div id="workspaceActive" class="metric">读取中…</div>
    <div id="workspaceActiveMeta" class="small"></div>
    <div class="toolbar section">
      <select id="workspaceSelect" class="select"></select>
      <button class="btn primary" id="workspaceActivate">切换并重建 Dashboard</button>
    </div>
    <div id="workspaceStatus" class="small"></div>
  </div>
  <div class="card">
    <h2>创建 / 安装模板</h2>
    <div class="toolbar">
      <input id="workspaceName" class="input" placeholder="新 Workspace 名称">
      <select id="workspaceTemplate" class="select"></select>
      <button class="btn" id="workspaceCreate">创建</button>
    </div>
    <div class="small">Blank 不预置业务语义；其他模板只安装配置，不复制 Creator / Video 基础事实。</div>
  </div>
</div>

<div class="section anchor-section" id="workspace-model">
  <div class="grid two">
    <div class="card"><h2>品牌与品牌组</h2><div id="workspaceBrands" class="small">—</div></div>
    <div class="card"><h2>Taxonomy / 标签体系</h2><div id="workspaceTaxonomies" class="small">—</div></div>
    <div class="card"><h2>商业指标定义</h2><div id="workspaceBusiness" class="small">—</div></div>
    <div class="card"><h2>Discovery Profiles</h2><div id="workspaceDiscovery" class="small">—</div></div>
  </div>
</div>
<script src="assets/workspace.js"></script>
"""


def _templates(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_TEMPLATES
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {"schema_version": 1, "templates": []}
    if not isinstance(data, dict):
        return {"schema_version": 1, "templates": []}
    data["templates"] = [x for x in list(data.get("templates") or []) if isinstance(x, dict) and x.get("id")]
    return data


def _slug(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return s or "workspace"


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_") or "item"


class WorkspaceService:
    def __init__(self, db_path: str | Path, templates_path: str | Path | None = None):
        self.db_path = str(db_path)
        self.templates_path = Path(templates_path) if templates_path else DEFAULT_TEMPLATES

    def _all_templates(self) -> list[dict[str, Any]]:
        public = list(_templates(self.templates_path).get("templates") or [])
        compat_path = Path(__file__).resolve().parent / "compat" / "cloud_phone_workspace.json"
        if compat_path.exists():
            public.extend(list(_templates(compat_path).get("templates") or []))
        return public

    def templates(self) -> list[dict[str, Any]]:
        """Public template catalog. Compatibility packs are opt-in and hidden by default."""
        return [t for t in self._all_templates() if str(t.get("visibility") or "public") != "compatibility"]

    def _template(self, template_id: str) -> dict[str, Any]:
        # Internal/explicit installs may still resolve hidden compatibility templates.
        for t in self._all_templates():
            if str(t.get("id")) == str(template_id):
                return t
        raise ValueError(f"workspace template not found: {template_id}")

    def _workspace_id(self, name: str, requested: str = "") -> str:
        base = _safe_key(requested or name)
        with connect(self.db_path) as conn:
            if not conn.execute("SELECT 1 FROM workspaces WHERE id=?", (base,)).fetchone():
                return base
        return f"{base}_{uuid.uuid4().hex[:8]}"

    def list(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id,name,slug,template_id,status,is_default,metadata_json,created_at,updated_at FROM workspaces ORDER BY is_default DESC,name"
            ).fetchall()]
        for r in rows:
            r["metadata"] = json_load(r.pop("metadata_json", None), {})
        return rows

    def active_id(self) -> str:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT value_json FROM app_settings WHERE key='active_workspace_id'").fetchone()
            wid = str(json_load(row["value_json"], "") if row else "").strip()
            if wid and conn.execute("SELECT 1 FROM workspaces WHERE id=?", (wid,)).fetchone():
                return wid
            row = conn.execute("SELECT id FROM workspaces ORDER BY is_default DESC,created_at LIMIT 1").fetchone()
            return str(row["id"]) if row else ""

    def active(self) -> dict[str, Any] | None:
        wid = self.active_id()
        return self.get(wid) if wid else None

    def get(self, workspace_id: str) -> dict[str, Any] | None:
        wid = str(workspace_id or "").strip()
        if not wid:
            return None
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE id=?", (wid,)).fetchone()
            if not row:
                return None
            out = dict(row)
            out["metadata"] = json_load(out.pop("metadata_json", None), {})
            out["brands"] = [dict(r) | {"aliases": json_load(r["aliases_json"], []), "metadata": json_load(r["metadata_json"], {})}
                             for r in conn.execute("SELECT * FROM workspace_brands WHERE workspace_id=? ORDER BY role,display_name", (wid,)).fetchall()]
            groups = [dict(r) for r in conn.execute("SELECT * FROM brand_groups WHERE workspace_id=? ORDER BY name", (wid,)).fetchall()]
            for g in groups:
                g["members"] = [dict(r) for r in conn.execute(
                    """SELECT b.id,b.key,b.display_name,b.role FROM brand_group_members m
                       JOIN workspace_brands b ON b.id=m.brand_id WHERE m.group_id=? ORDER BY b.display_name""",
                    (g["id"],)
                ).fetchall()]
            out["brand_groups"] = groups
            schemes = [dict(r) for r in conn.execute("SELECT * FROM taxonomy_schemes WHERE workspace_id=? ORDER BY name", (wid,)).fetchall()]
            for s in schemes:
                s["labels"] = [dict(r) | {"metadata": json_load(r["metadata_json"], {})}
                               for r in conn.execute("SELECT * FROM taxonomy_labels WHERE scheme_id=? ORDER BY sort_order,name", (s["id"],)).fetchall()]
            out["taxonomies"] = schemes
            out["business_metrics"] = [dict(r) | {"metadata": json_load(r["metadata_json"], {})}
                                       for r in conn.execute("SELECT * FROM business_metric_definitions WHERE workspace_id=? ORDER BY name", (wid,)).fetchall()]
            out["discovery_profiles"] = [dict(r) | {"profile": json_load(r["profile_json"], {})}
                                         for r in conn.execute("SELECT * FROM discovery_profiles WHERE workspace_id=? ORDER BY name", (wid,)).fetchall()]
        return out

    def context(self, workspace_id: str = "") -> dict[str, Any]:
        ws = self.get(workspace_id or self.active_id())
        if not ws:
            return {"workspace": None, "brands": [], "brand_groups": [], "taxonomies": [], "business_metrics": [], "discovery_profiles": []}
        return {
            "workspace": {k: ws.get(k) for k in ("id","name","slug","template_id","status","is_default","metadata")},
            "brands": ws.get("brands") or [],
            "brand_groups": ws.get("brand_groups") or [],
            "taxonomies": ws.get("taxonomies") or [],
            "business_metrics": ws.get("business_metrics") or [],
            "discovery_profiles": ws.get("discovery_profiles") or [],
        }

    def install_template(self, template_id: str, *, name: str = "", workspace_id: str = "", is_default: bool = False) -> dict[str, Any]:
        tpl = self._template(template_id)
        ws_name = str(name or tpl.get("name_zh") or tpl.get("name") or template_id).strip()
        wid = self._workspace_id(ws_name, workspace_id or (template_id if workspace_id else ""))
        at = now_utc()
        metadata = {
            "description": tpl.get("description_zh") or tpl.get("description") or "",
            "compatibility_profile": tpl.get("compatibility_profile") or "",
            "primary_brand_key": tpl.get("primary_brand_key") or "",
        }
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO workspaces(id,name,slug,template_id,status,is_default,metadata_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (wid, ws_name, _slug(ws_name), template_id, "active", 1 if is_default else 0, json_dump(metadata), at, at),
            )
            brand_ids: dict[str, str] = {}
            for b in list(tpl.get("brands") or []):
                key = _safe_key(b.get("key") or b.get("name"))
                bid = f"{wid}:brand:{key}"
                brand_ids[key] = bid
                conn.execute(
                    """INSERT OR REPLACE INTO workspace_brands(id,workspace_id,key,display_name,role,aliases_json,metadata_json,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (bid,wid,key,str(b.get("name") or key),str(b.get("role") or "brand"),json_dump(list(b.get("aliases") or [])),json_dump(dict(b.get("metadata") or {})),at,at)
                )
            for g in list(tpl.get("brand_groups") or []):
                gkey = _safe_key(g.get("key") or g.get("name"))
                gid = f"{wid}:group:{gkey}"
                conn.execute("INSERT OR REPLACE INTO brand_groups(id,workspace_id,key,name,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                             (gid,wid,gkey,str(g.get("name") or gkey),at,at))
                for member in list(g.get("members") or []):
                    bid = brand_ids.get(_safe_key(member))
                    if bid:
                        conn.execute("INSERT OR IGNORE INTO brand_group_members(group_id,brand_id) VALUES(?,?)",(gid,bid))
            for s in list(tpl.get("taxonomies") or []):
                skey = _safe_key(s.get("key") or s.get("name"))
                sid = f"{wid}:taxonomy:{skey}"
                conn.execute(
                    """INSERT OR REPLACE INTO taxonomy_schemes(id,workspace_id,key,name,entity_type,multi_select,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (sid,wid,skey,str(s.get("name") or skey),str(s.get("entity_type") or "video"),1 if s.get("multi_select") else 0,at,at)
                )
                for pos,lbl in enumerate(list(s.get("labels") or []),1):
                    lkey = _safe_key(lbl.get("key") or lbl.get("name"))
                    lid = f"{sid}:label:{lkey}"
                    conn.execute(
                        """INSERT OR REPLACE INTO taxonomy_labels(id,scheme_id,key,name,parent_label_id,sort_order,metadata_json)
                           VALUES(?,?,?,?,?,?,?)""",
                        (lid,sid,lkey,str(lbl.get("name") or lkey),None,pos,json_dump(dict(lbl.get("metadata") or {})))
                    )
            for m in list(tpl.get("business_metrics") or []):
                key = _safe_key(m.get("key") or m.get("name"))
                mid = f"{wid}:metric:{key}"
                conn.execute(
                    """INSERT OR REPLACE INTO business_metric_definitions
                       (id,workspace_id,key,name,value_type,unit,currency,aggregation,metadata_json,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (mid,wid,key,str(m.get("name") or key),str(m.get("value_type") or "number"),str(m.get("unit") or ""),
                     str(m.get("currency") or ""),str(m.get("aggregation") or "sum"),json_dump(dict(m.get("metadata") or {})),at,at)
                )
            for p in list(tpl.get("discovery_profiles") or []):
                key = _safe_key(p.get("key") or p.get("name"))
                pid = f"{wid}:discovery:{key}"
                conn.execute(
                    """INSERT OR REPLACE INTO discovery_profiles(id,workspace_id,key,name,profile_json,enabled,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (pid,wid,key,str(p.get("name") or key),json_dump(dict(p.get("profile") or {})),1,at,at)
                )
            for p in list(tpl.get("presets") or []):
                key = _safe_key(p.get("key") or p.get("name"))
                pid = f"{wid}:preset:{_safe_key(p.get('type') or 'preset')}:{key}"
                conn.execute(
                    """INSERT OR REPLACE INTO workspace_presets(id,workspace_id,preset_type,key,name,payload_json,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (pid,wid,str(p.get("type") or "preset"),key,str(p.get("name") or key),json_dump(dict(p.get("payload") or {})),at,at)
                )
            conn.commit()
        return self.get(wid) or {"id":wid,"name":ws_name}

    def create_blank(self, name: str) -> dict[str, Any]:
        if not str(name or "").strip():
            raise ValueError("workspace name is required")
        return self.install_template("blank", name=str(name).strip())

    def set_active(self, workspace_id: str) -> dict[str, Any]:
        wid = str(workspace_id or "").strip()
        if not self.get(wid):
            raise ValueError("workspace not found")
        at = now_utc()
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO app_settings(key,value_json,updated_at) VALUES('active_workspace_id',?,?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
                (json_dump(wid),at)
            )
            conn.commit()
        return self.get(wid) or {}

    def get_setting(self, key: str, default: Any = None, workspace_id: str = "") -> Any:
        wid = workspace_id or self.active_id()
        if not wid:
            return default
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key=?", (wid,key)).fetchone()
        return json_load(row["value_json"], default) if row else default

    def set_setting(self, key: str, value: Any, workspace_id: str = "") -> dict[str, Any]:
        wid = workspace_id or self.active_id()
        if not wid:
            raise ValueError("no active workspace")
        at = now_utc()
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO workspace_settings(workspace_id,key,value_json,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(workspace_id,key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
                (wid,key,json_dump(value),at)
            )
            conn.commit()
        return {"workspace_id":wid,"key":key,"value":value,"updated_at":at}

    def classifier_config(self, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
        ws = self.active()
        if not ws:
            return fallback or {"rule_version":"workspace-v1","classification":{},"brands":[]}
        meta = ws.get("metadata") or {}
        if meta.get("compatibility_profile") == "cloud_phone_v1" and fallback:
            return fallback
        brands = []
        for b in ws.get("brands") or []:
            brands.append({
                "key":b.get("key"),"role":"target" if b.get("role")=="primary" else b.get("role") or "brand",
                "display_name":b.get("display_name"),"aliases":b.get("aliases") or [],
                "official_domains":(b.get("metadata") or {}).get("official_domains") or [],
                "web_patterns":[],"referral_patterns":[],"app_ids":[],"known_short_links":[]
            })
        return {"rule_version":"workspace-v1","classification":{"cta_terms":[],"community_domains":[],"app_domains":[],"shortener_domains":[],"cloud_entity_terms":[],"use_case_terms":[],"product_link_terms":[]},"brands":brands}

    def bootstrap(self) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'").fetchone()
        if not table:
            return {"ready":False}

        existing = {x["template_id"]: x for x in self.list()}
        if "blank" not in existing:
            general = self.install_template("blank", name="General Creator Intelligence", workspace_id="general", is_default=True)
        else:
            general = existing["blank"]

        legacy_score = 0
        with connect(self.db_path) as conn:
            try:
                legacy_score += int(conn.execute(
                    """SELECT COUNT(*) FROM label_suggestions
                       WHERE suggested_role IN ('ugphone','competitor','multi_brand','other_cloud_phone')
                          OR lower(brands_json) LIKE '%ugphone%' OR lower(brands_json) LIKE '%ldcloud%'
                          OR lower(brands_json) LIKE '%redfinger%' OR lower(brands_json) LIKE '%vsphone%'"""
                ).fetchone()[0] or 0)
                legacy_score += int(conn.execute(
                    "SELECT COUNT(*) FROM creator_business_metrics WHERE metric_key IN ('gmv','new_users')"
                ).fetchone()[0] or 0)
            except Exception:
                pass

        cloud = existing.get("cloud_phone_growth")
        if legacy_score and not cloud:
            cloud = self.install_template("cloud_phone_growth", name="Cloud Phone Growth", workspace_id="cloud_phone_growth")
        active = self.active_id()
        if not active:
            # Public/default surface is always generic. Legacy evidence may create a hidden
            # compatibility Workspace, but it must never become active automatically.
            active = general.get("id")
            self.set_active(str(active))

        if cloud:
            self._migrate_legacy_cloud(str(cloud.get("id")))
            self._scope_legacy_saved_views(str(cloud.get("id")))
            self._scope_legacy_metric_config(str(cloud.get("id")))

        return {"ready":True,"active_workspace_id":self.active_id(),"legacy_cloud_rows":legacy_score}

    def _scope_legacy_saved_views(self, workspace_id: str) -> None:
        prefix = f"{workspace_id}:"
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT id,page_key FROM saved_views").fetchall()
            for r in rows:
                key = str(r["page_key"] or "")
                if ":" not in key:
                    conn.execute("UPDATE saved_views SET page_key=? WHERE id=?", (prefix+key,int(r["id"])))
            conn.commit()

    def _scope_legacy_metric_config(self, workspace_id: str) -> None:
        with connect(self.db_path) as conn:
            old = conn.execute("SELECT value_json FROM app_settings WHERE key='secondary_metrics'").fetchone()
            exists = conn.execute("SELECT 1 FROM workspace_settings WHERE workspace_id=? AND key='secondary_metrics'",(workspace_id,)).fetchone()
            if old and not exists:
                conn.execute(
                    "INSERT INTO workspace_settings(workspace_id,key,value_json,updated_at) VALUES(?,?,?,?)",
                    (workspace_id,"secondary_metrics",old["value_json"],now_utc())
                )
                conn.commit()

    def _migrate_legacy_cloud(self, workspace_id: str) -> None:
        ctx = self.get(workspace_id)
        if not ctx:
            return
        scheme = next((s for s in ctx.get("taxonomies") or [] if s.get("key")=="content_relationship"),None)
        if not scheme:
            return
        labels = {l["key"]: l["id"] for l in scheme.get("labels") or []}
        brands = {b["key"]: b["id"] for b in ctx.get("brands") or []}
        role_map = {
            "ugphone":"own_brand","competitor":"competitor","multi_brand":"multi_brand",
            "daily":"organic","other_cloud_phone":"other_brand","pending":"review"
        }
        at = now_utc()
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT video_id,suggested_role,brands_json FROM label_suggestions").fetchall()
            for r in rows:
                role = role_map.get(str(r["suggested_role"] or "pending"),"review")
                lid = labels.get(role)
                if lid:
                    conn.execute(
                        """INSERT OR IGNORE INTO video_taxonomy_assignments
                           (workspace_id,video_id,scheme_id,label_id,layer,source_ref,assigned_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (workspace_id,str(r["video_id"]),scheme["id"],lid,"derived","legacy:label_suggestions",at)
                    )
            rows = conn.execute("SELECT video_id,human_role,brands_json FROM video_labels").fetchall()
            for r in rows:
                role = role_map.get(str(r["human_role"] or "pending"),"review")
                lid = labels.get(role)
                if lid:
                    conn.execute(
                        """INSERT OR IGNORE INTO video_taxonomy_assignments
                           (workspace_id,video_id,scheme_id,label_id,layer,source_ref,assigned_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (workspace_id,str(r["video_id"]),scheme["id"],lid,"human","legacy:video_labels",at)
                    )
            video_rows = conn.execute(
                """SELECT v.channel_id,
                          COALESCE(l.human_role,s.suggested_role,'pending') role,
                          COALESCE(l.brands_json,s.brands_json,'[]') brands_json
                   FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id
                   LEFT JOIN video_labels l ON l.video_id=v.video_id"""
            ).fetchall()
            seen=set()
            for r in video_rows:
                cid=str(r["channel_id"])
                role=str(r["role"] or "")
                bset={str(x).lower() for x in json_load(r["brands_json"],[]) or []}
                if role=="ugphone": bset.add("ugphone")
                for bk in bset:
                    bid=brands.get(bk)
                    if not bid: continue
                    key=(cid,bid,"partnership","known")
                    if key in seen: continue
                    seen.add(key)
                    conn.execute(
                        """INSERT OR IGNORE INTO creator_relationships
                           (workspace_id,channel_id,brand_id,relationship_type,status,source_ref,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (workspace_id,cid,bid,"partnership","known","legacy:video_brand_evidence",at,at)
                    )
            conn.commit()


def active_workspace_context(conn) -> dict[str, Any]:
    row = conn.execute("SELECT value_json FROM app_settings WHERE key='active_workspace_id'").fetchone()
    wid = str(json_load(row["value_json"], "") if row else "").strip()
    if not wid:
        row = conn.execute("SELECT id FROM workspaces ORDER BY is_default DESC,created_at LIMIT 1").fetchone()
        wid = str(row["id"]) if row else ""
    if not wid:
        return {"workspace":None,"brands":[],"brand_groups":[],"taxonomies":[],"business_metrics":[],"discovery_profiles":[]}
    row = conn.execute("SELECT id,name,slug,template_id,status,is_default,metadata_json FROM workspaces WHERE id=?", (wid,)).fetchone()
    if not row:
        return {"workspace":None,"brands":[],"brand_groups":[],"taxonomies":[],"business_metrics":[],"discovery_profiles":[]}
    ws=dict(row);ws["metadata"]=json_load(ws.pop("metadata_json",None),{})
    brands=[dict(r) for r in conn.execute("SELECT id,key,display_name,role,aliases_json,metadata_json FROM workspace_brands WHERE workspace_id=? ORDER BY display_name",(wid,)).fetchall()]
    for b in brands:
        b["aliases"]=json_load(b.pop("aliases_json",None),[])
        b["metadata"]=json_load(b.pop("metadata_json",None),{})
    groups=[dict(r) for r in conn.execute("SELECT id,key,name FROM brand_groups WHERE workspace_id=? ORDER BY name",(wid,)).fetchall()]
    for g in groups:
        g["members"]=[dict(r) for r in conn.execute(
            "SELECT b.id,b.key,b.display_name,b.role FROM brand_group_members m JOIN workspace_brands b ON b.id=m.brand_id WHERE m.group_id=? ORDER BY b.display_name",
            (g["id"],)
        ).fetchall()]
    schemes=[dict(r) for r in conn.execute("SELECT id,key,name,entity_type,multi_select FROM taxonomy_schemes WHERE workspace_id=? ORDER BY name",(wid,)).fetchall()]
    for s in schemes:
        s["labels"]=[dict(r) for r in conn.execute("SELECT id,key,name,sort_order FROM taxonomy_labels WHERE scheme_id=? ORDER BY sort_order,name",(s["id"],)).fetchall()]
    metrics=[dict(r) for r in conn.execute("SELECT id,key,name,value_type,unit,currency,aggregation FROM business_metric_definitions WHERE workspace_id=? ORDER BY name",(wid,)).fetchall()]
    profiles=[dict(r) for r in conn.execute("SELECT id,key,name,enabled,profile_json FROM discovery_profiles WHERE workspace_id=? ORDER BY name",(wid,)).fetchall()]
    for p in profiles:p["profile"]=json_load(p.pop("profile_json",None),{})
    return {"workspace":ws,"brands":brands,"brand_groups":groups,"taxonomies":schemes,"business_metrics":metrics,"discovery_profiles":profiles}

# V4.2 neutral-surface: workspace

# V4.3 generic-discovery: workspace-loader
