from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BANNED = re.compile(
    r"ugphone|ldcloud|redfinger|vsphone|cloud\s*phone|cloudphone|云手机|"
    r"partnered_ugphone|unpartnered_ugphone|ugphone_and_competitor|"
    r"role:ugphone|brand:ugphone|role:other_cloud_phone",
    re.I,
)
EMPTY_METRICS = {"schema_version": 1, "metrics": [], "rules": [], "activeRule": "", "filters": []}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _replace(text: str, old: str, new: str, label: str, *, required: bool = True) -> str:
    if old not in text:
        if required:
            raise RuntimeError(f"neutral-surface patch anchor missing: {label}")
        return text
    return text.replace(old, new)


def _sub(text: str, pattern: str, repl: str, label: str, *, flags: int = 0, required: bool = True) -> str:
    out, count = re.subn(pattern, repl, text, flags=flags)
    if required and count == 0:
        raise RuntimeError(f"neutral-surface regex anchor missing: {label}")
    return out


def patch_workspace(path: Path) -> None:
    text = _read(path)
    if "# V4.2 neutral-surface: workspace" in text:
        return
    text = _replace(
        text,
        '<div class="note"><b>V4 核心原则：</b>Core 不再把特定品牌、竞品、行业或商业指标写死。特定业务知识由 Workspace / Template 提供。原有云手机能力被迁移为 <b>Cloud Phone Growth</b> 兼容 Workspace。</div>',
        '<div class="note"><b>Workspace 原则：</b>Core 只提供通用 Creator / Video 事实与 Workspace primitives。品牌、行业、关系、商业指标和分类语义均由当前 Workspace 配置提供；兼容 Pack 默认隐藏，只有显式启用时才进入工作区。</div>',
        "workspace public note",
    )
    old = '''    def templates(self) -> list[dict[str, Any]]:\n        return list(_templates(self.templates_path).get("templates") or [])\n\n    def _template(self, template_id: str) -> dict[str, Any]:\n        for t in self.templates():\n            if str(t.get("id")) == str(template_id):\n                return t\n        raise ValueError(f"workspace template not found: {template_id}")\n'''
    new = '''    def _all_templates(self) -> list[dict[str, Any]]:\n        return list(_templates(self.templates_path).get("templates") or [])\n\n    def templates(self) -> list[dict[str, Any]]:\n        """Public template catalog. Compatibility packs are opt-in and hidden by default."""\n        return [t for t in self._all_templates() if str(t.get("visibility") or "public") != "compatibility"]\n\n    def _template(self, template_id: str) -> dict[str, Any]:\n        # Internal/explicit installs may still resolve hidden compatibility templates.\n        for t in self._all_templates():\n            if str(t.get("id")) == str(template_id):\n                return t\n        raise ValueError(f"workspace template not found: {template_id}")\n'''
    text = _replace(text, old, new, "workspace hidden templates")

    old = '''        active = self.active_id()\n        if not active:\n            active = (cloud or general).get("id")\n            self.set_active(str(active))\n        elif legacy_score and active == "general" and cloud:\n            self.set_active(str(cloud.get("id")))\n\n        if cloud:\n'''
    new = '''        active = self.active_id()\n        if not active:\n            # Public/default surface is always generic. Legacy evidence may create a hidden\n            # compatibility Workspace, but it must never become active automatically.\n            active = general.get("id")\n            self.set_active(str(active))\n\n        if cloud:\n'''
    text = _replace(text, old, new, "workspace no compat auto-activation")
    text += "\n# V4.2 neutral-surface: workspace\n"
    _write(path, text)


def patch_metric_workspace(path: Path) -> None:
    text = _read(path)
    if "# V4.2 neutral-surface: metric-workspace" in text:
        return
    text = _replace(text, "例如：近90天UgPhone视频播放中位数", "例如：近90天教程视频播放中位数", "generic metric placeholder")
    text = _replace(text, "例如：高潜未合作博主", "例如：高潜成长型博主", "generic rule placeholder")
    old = '''def field_registry_payload()->dict[str,Any]:\n    cfg=load_metric_config(None) if False else {"metrics":[]}\n    return registry_payload(CREATOR_FACT_FIELDS,CREATOR_LABELS,VIDEO_FACT_FIELDS,[])\n'''
    new = '''def field_registry_payload()->dict[str,Any]:\n    # The static/default registry is domain-neutral. Workspace-specific fields are supplied\n    # by build_metric_base() at runtime.\n    return registry_payload(GENERIC_CREATOR_FACT_FIELDS,{},VIDEO_FACT_FIELDS,[])\n'''
    text = _replace(text, old, new, "generic static field registry")

    old = '''    row=conn.execute("SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='secondary_metrics'",(wid,)).fetchone() if wid else None\n    if not row:\n        row=conn.execute("SELECT value_json FROM app_settings WHERE key='secondary_metrics'").fetchone()\n    saved=json_load(row["value_json"],None) if row else load_metric_config()\n'''
    new = '''    row=conn.execute("SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='secondary_metrics'",(wid,)).fetchone() if wid else None\n    # V4.2: a Workspace with no metric configuration starts empty. Never inherit global\n    # V3-era app_settings or installation defaults into a generic Workspace. Compatibility\n    # migration is handled explicitly by WorkspaceService._scope_legacy_metric_config().\n    saved=json_load(row["value_json"],None) if row else {"schema_version":1,"metrics":[],"rules":[],"activeRule":"","filters":[]}\n'''
    text = _replace(text, old, new, "workspace-only metric config")
    for old_label,new_label in [("UgPhone","主品牌"),("LDCloud","竞品品牌 A"),("RedFinger","竞品品牌 B"),("VSPhone","竞品品牌 C"),("云手机","行业产品"),("Cloud Phone","Industry Product")]:
        text=text.replace(old_label,new_label)
    text += "\n# V4.2 neutral-surface: metric-workspace\n"
    _write(path, text)


def patch_metrics_js(path: Path) -> None:
    text = _read(path)
    if "/* V4.2 neutral-surface: metrics-ui */" in text:
        return
    old = '''const KEY='cdh-secondary-metrics-v6';\nconst LEGACY_KEYS=['cdh-secondary-metrics-v5','cdh-secondary-metrics-v4','cdh-secondary-metrics-v3'];\nconst FACTS=window.CDH_CREATOR_FACTS||{creators:[]};\nconst BASE=window.CDH_METRIC_BASE||{cubes:{},creator_fact_fields:{},creator_labels:{},video_fact_fields:{},video_filters:{},windows:['all','7','30','60','90','180','365']};\n'''
    new = '''const FACTS=window.CDH_CREATOR_FACTS||{creators:[]};\nconst BASE=window.CDH_METRIC_BASE||{cubes:{},creator_fact_fields:{},creator_labels:{},video_fact_fields:{},video_filters:{},windows:['all','7','30','60','90','180','365']};\nconst WORKSPACE=BASE.workspace||{};\nconst IS_COMPAT=Boolean((WORKSPACE.metadata||{}).compatibility_profile);\nconst WORKSPACE_KEY=String(WORKSPACE.id||'general').replace(/[^a-zA-Z0-9_.:-]/g,'_');\nconst KEY='cdh-secondary-metrics-v7::'+WORKSPACE_KEY;\nconst LEGACY_KEYS=['cdh-secondary-metrics-v6','cdh-secondary-metrics-v5','cdh-secondary-metrics-v4','cdh-secondary-metrics-v3'];\n'''
    text = _replace(text, old, new, "workspace-scoped browser metric key")

    old = '''function load(){\n  try{\n    const current=localStorage.getItem(KEY);if(current)return migrateState(JSON.parse(current));\n    for(const k of LEGACY_KEYS){const v=localStorage.getItem(k);if(v){const s=migrateState(JSON.parse(v));localStorage.setItem(KEY,JSON.stringify(s));return s}}\n    if(window.CDH_SAVED_METRIC_CONFIG)return migrateState(window.CDH_SAVED_METRIC_CONFIG);\n  }catch(e){}\n  return emptyState();\n}\n'''
    new = '''function load(){\n  try{\n    const current=localStorage.getItem(KEY);if(current)return migrateState(JSON.parse(current));\n    // Only an explicitly active compatibility Workspace may inherit V3-V6 browser state.\n    if(IS_COMPAT){\n      for(const k of LEGACY_KEYS){const v=localStorage.getItem(k);if(v){const s=migrateState(JSON.parse(v));localStorage.setItem(KEY,JSON.stringify(s));return s}}\n    }else{\n      // Generic workspaces deliberately ignore and retire unscoped historical UI state.\n      for(const k of LEGACY_KEYS)localStorage.removeItem(k);\n    }\n    if(window.CDH_SAVED_METRIC_CONFIG)return migrateState(window.CDH_SAVED_METRIC_CONFIG);\n  }catch(e){}\n  return emptyState();\n}\n'''
    text = _replace(text, old, new, "generic browser state isolation")

    old_identity = '''function identityPills(c){const a=[c.partnered_ugphone?['合作过博主','identity-partnered']:['未合作博主','identity-unpartnered'],c.ldcloud_creator?['LDCloud合作博主','identity-competitor']:null,c.redfinger_creator?['RedFinger合作博主','identity-competitor']:null,c.vsphone_creator?['VSPhone合作博主','identity-competitor']:null,c.suspected_inactive_partner?['疑似不再合作','identity-suspected']:null].filter(Boolean);return a.map(([t,k])=>`<span class="pill ${k}">${esc(t)}</span>`).join('')}\n'''
    new_identity = '''function identityPills(c){const a=Object.entries(creatorLabels).filter(([k])=>Number(c[k]||0)).map(([,label])=>label);return a.length?a.map(t=>`<span class="pill identity-partnered">${esc(t)}</span>`).join(''):'<span class="small">—</span>'}\n'''
    text = _replace(text, old_identity, new_identity, "dynamic identity pills")

    old_fixed = '''function fixedKindForMetric(m){if(!m||m.type!=='constructed'||m.source_kind!=='video_fact'||m.source_field!=='current_views'||(m.window||'all')!=='all'||(m.aggregation||'count')!=='median')return '';const f=m.filter_label||'';if(!f)return 'all';if(f==='role:ugphone'||f==='brand:ugphone')return 'ugphone';if(f==='role:competitor')return 'competitor';return ''}\n'''
    new_fixed = '''function fixedKindForMetric(m){if(!m||m.type!=='constructed'||m.source_kind!=='video_fact'||m.source_field!=='current_views'||(m.window||'all')!=='all'||(m.aggregation||'count')!=='median')return '';return (m.filter_label||'')?'':'all'}\n'''
    text = _replace(text, old_fixed, new_fixed, "generic fixed metric recognition")

    # Replace the hard-coded three playback columns with one generic total-playback column.
    text = _sub(
        text,
        r'''  head\.innerHTML='<tr><th class="'\+hcls\('channel_title',sortKey==='channel_title'\)\+'" data-field="channel_title">博主</th>.*?<th class="'\+hcls\('last_synced_at',sortKey==='last_synced_at'\)\+'" data-field="last_synced_at">最近同步</th></tr>';''',
        '''  head.innerHTML='<tr><th class="'+hcls('channel_title',sortKey==='channel_title')+'" data-field="channel_title">博主</th><th class="'+hcls('country',sortKey==='country')+'" data-field="country">国家</th><th class="'+hcls('subscriber_count',sortKey==='subscriber_count')+'" data-field="subscriber_count">订阅数</th><th class="'+hcls('channel_view_count',sortKey==='channel_view_count')+'" data-field="channel_view_count">频道累计播放量</th><th class="'+hcls('stored_videos',sortKey==='stored_videos')+'" data-field="stored_videos">本地视频数</th><th class="'+(activeBase.has('identity')?'filter-sort-active':'')+'" data-field="identity">Workspace 关系</th><th class="fixed-playback '+(fixedSort==='all'?'sort-active':'')+'" title="全部时间 · Median">总视频播放量<div class="small">Median · 全部时间</div></th>'+filterHeads+(!sortIsFilter&&extraSortMetric?`<th class="sort-active" title="当前排序指标" data-field="metric:${esc(extraSortMetric.id)}">${esc(extraSortMetric.name)}</th>`:!sortIsFilter&&extraSortFact?`<th class="sort-active" title="当前排序指标" data-field="${esc(extraSortFact.key)}">${esc(extraSortFact.name)}</th>`:'')+'<th class="'+hcls('last_synced_at',sortKey==='last_synced_at')+'" data-field="last_synced_at">最近同步</th></tr>';''',
        "generic result headers",
        flags=re.S,
        required=False,
    )

    text = _sub(
        text,
        r'''  for\(const x of shown\)\{const c=x\.c,vals=x\.vals,channelUrl=.*?html\.push\(`<tr>.*?</tr>`\)\}\n''',
        '''  for(const x of shown){const c=x.c,vals=x.vals,channelUrl=`https://www.youtube.com/channel/${encodeURIComponent(c.channel_id)}`,localUrl=`creators/${encodeURIComponent(c.channel_id)}.html`,detail=c.detail_available===false?'':`<div class="small"><a class="link-local" href="${localUrl}">查看详情</a></div>`,all=fixedPlaybackValue(c,''),filterCells=filterExtras.map(z=>`<td>${fmt(z.kind==='metric'?vals[z.key]:c[z.key])}</td>`).join('');html.push(`<tr><td><a class="link-ext" target="_blank" rel="noopener" href="${channelUrl}"><b>${esc(c.channel_title||c.channel_id)}</b></a><div class="small mono">${esc(c.handle||c.channel_id)}</div>${detail}</td><td>${esc(c.country_resolved||c.country_api||'—')}</td><td>${fmt(c.subscriber_count)}</td><td>${fmt(c.channel_view_count)}</td><td>${fmt(c.stored_videos)}</td><td>${identityPills(c)}</td><td>${fmt(all)}</td>${filterCells}${!sortIsFilter&&extraSortMetric?`<td>${fmt(vals[extraSortMetric.id])}</td>`:!sortIsFilter&&extraSortFact?`<td>${fmt(c[extraSortFact.key])}</td>`:''}<td class="small">${esc(c.last_synced_at||'—')}</td></tr>`)}\n''',
        "generic result rows",
        flags=re.S,
        required=False,
    )

    # Export: drop legacy identity and primary/competitor playback fixed columns.
    text = _sub(
        text,
        r'''identity:\[c\.partnered_ugphone\?.*?\.filter\(Boolean\)\.join\('；'\),ugphone_playback_median:fixedPlaybackValue\(c,'role:ugphone'\),all_playback_median:fixedPlaybackValue\(c,''\),competitor_playback_median:fixedPlaybackValue\(c,'role:competitor'\)''',
        '''identity:Object.entries(creatorLabels).filter(([k])=>Number(c[k]||0)).map(([,label])=>label).join('；'),all_playback_median:fixedPlaybackValue(c,'')''',
        "generic result export payload",
        flags=re.S,
        required=False,
    )
    text = _replace(
        text,
        "{key:'identity',label:'身份标签'},{key:'ugphone_playback_median',label:'UgPhone视频播放量 Median'},{key:'all_playback_median',label:'总视频播放量 Median'},{key:'competitor_playback_median',label:'竞品视频播放量 Median'}",
        "{key:'identity',label:'Workspace 关系'},{key:'all_playback_median',label:'总视频播放量 Median'}",
        "generic result export columns",
        required=False,
    )
    # Last-resort presentation guard: legacy internal keys may remain for compatibility,
    # but generic UI literals must not expose historical product/domain names.
    for old_label,new_label in [("UgPhone","主品牌"),("LDCloud","竞品品牌 A"),("RedFinger","竞品品牌 B"),("VSPhone","竞品品牌 C"),("云手机","行业产品"),("Cloud Phone","Industry Product")]:
        text=text.replace(old_label,new_label)
    text += "\n/* V4.2 neutral-surface: metrics-ui */\n"
    _write(path, text)


def patch_dashboard(path: Path) -> None:
    text = _read(path)
    if "# V4.2 neutral-surface: dashboard" in text:
        return
    text = _replace(
        text,
        'ROLE_NAMES={"ugphone":"UgPhone","competitor":"竞品","daily":"日常视频","multi_brand":"多品牌云手机","other_cloud_phone":"其他云手机","pending":"待复核"}',
        'ROLE_NAMES={"ugphone":"主品牌内容","competitor":"竞品内容","daily":"自然内容","multi_brand":"多品牌内容","other_cloud_phone":"其他品牌内容","pending":"待复核"}',
        "generic legacy role labels",
    )
    # Detail source ordering must be neutral: no hidden primary-brand priority.
    text = _sub(
        text,
        r'''                        ORDER BY v\.channel_id,\n                          CASE WHEN COALESCE\(l\.human_role,s\.suggested_role,'pending'\)='ugphone'\n                                    OR instr\(lower\(COALESCE\(l\.brands_json,s\.brands_json,''\)\),'ugphone'\)>0\n                               THEN 0 ELSE 1 END,\n                          COALESCE\(v\.current_views,0\) DESC,v\.published_at DESC''',
        '''                        ORDER BY v.channel_id,COALESCE(v.current_views,0) DESC,v.published_at DESC''',
        "neutral detail ordering",
    )

    # Runtime relationship labels for the active Workspace.
    anchor = "        last_sync=dict(conn.execute('SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1').fetchone() or {})\n\n        rows=[]\n"
    insert = '''        last_sync=dict(conn.execute('SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1').fetchone() or {})\n        workspace_id=str(active_workspace.get("id") or "")\n        relationship_labels=defaultdict(list)\n        if workspace_id:\n            for rel in conn.execute("""SELECT r.channel_id,r.relationship_type,r.status,b.display_name\n                                      FROM creator_relationships r\n                                      LEFT JOIN workspace_brands b ON b.id=r.brand_id\n                                      WHERE r.workspace_id=?\n                                      ORDER BY r.channel_id,b.display_name,r.relationship_type,r.status""",(workspace_id,)).fetchall():\n                bits=[str(rel["display_name"] or "").strip(),str(rel["relationship_type"] or "").strip(),str(rel["status"] or "").strip()]\n                label=" · ".join(x for x in bits if x)\n                if label and label not in relationship_labels[str(rel["channel_id"])]: relationship_labels[str(rel["channel_id"])].append(label)\n        workspace_brand_choices=[(str(b.get("key") or ""),str(b.get("display_name") or b.get("key") or "")) for b in workspace_ctx.get("brands") or [] if b.get("key")]\n\n        rows=[]\n'''
    text = _replace(text, anchor, insert, "workspace relationship overview index")

    old_identity = '''            identity=['合作过博主' if c.get('identified_ugphone',0)>0 else '未合作博主']\n            if c.get('ldcloud_videos',0)>0: identity.append('LDCloud合作博主')\n            if c.get('redfinger_videos',0)>0: identity.append('RedFinger合作博主')\n            if c.get('vsphone_videos',0)>0: identity.append('VSPhone合作博主')\n            if c.get('suspected_inactive_partner'): identity.append('疑似不再合作')\n            search=(c.get('channel_title') or '')+' '+(c.get('handle') or '')+' '+country+' '+c['channel_id']+' '+' '.join(identity)\n            tags='<div class="identity-stack">'+''.join('<span class="pill '+('identity-partnered' if x=='合作过博主' else 'identity-unpartnered' if x=='未合作博主' else 'identity-suspected' if x=='疑似不再合作' else 'identity-competitor')+'">'+esc(x)+'</span>' for x in identity)+'</div>'\n'''
    new_identity = '''            identity=list(relationship_labels.get(str(c['channel_id']),[]))\n            search=(c.get('channel_title') or '')+' '+(c.get('handle') or '')+' '+country+' '+c['channel_id']+' '+' '.join(identity)\n            tags=('<div class="identity-stack">'+''.join('<span class="pill identity-partnered">'+esc(x)+'</span>' for x in identity)+'</div>') if identity else '<span class="small">—</span>'\n'''
    text = _replace(text, old_identity, new_identity, "generic overview relationships")

    text = _sub(
        text,
        r'''            biz_html=\(\(.*?\) if biz_count else '<span class="small">商业数据未采集（不代表0）</span>'\)\n''',
        '''            biz_html=(f'<div><b>商业指标记录 {biz_count} 条</b></div><div class="small">最近更新 {esc(str(c.get("business_metric_updated_at") or "—")[:19])}</div>' if biz_count else '<span class="small">当前 Workspace 尚无商业指标记录</span>')\n''',
        "generic overview business summary",
        flags=re.S,
    )
    text = _replace(text, '<td class="identity-cell">{tags}</td><td>{fmt_int(c.get(\'identified_ugphone\'))}</td><td class="metric-cell">{biz_html}</td>', '<td class="identity-cell">{tags}</td><td class="metric-cell">{biz_html}</td>', "remove legacy overview count")

    text = _sub(
        text,
        r'''<div class="section anchor-section" id="overview-identity"><div class="note"><b>身份口径：</b>.*?<br><b>监控口径：</b>''',
        '''<div class="section anchor-section" id="overview-identity"><div class="note"><b>关系口径：</b>身份与关系只来自当前 Workspace 的 Creator Relationship；Core 不根据特定客户、品牌或行业自动定义“已合作 / 未合作”。品牌内容语义由 Workspace Taxonomy 管理。<br><b>监控口径：</b>''',
        "generic overview note",
        flags=re.S,
    )

    text = _sub(
        text,
        r'''<select id="ovSort" class="select"><option value="ugphone_video_count" selected>UgPhone视频数</option>.*?</select><select id="ovSortDir"''',
        '''<select id="ovSort" class="select"><option value="subscriber_count" selected>订阅数</option><option value="channel_title">博主名称</option><option value="country">国家</option><option value="channel_view_count">频道累计播放量</option><option value="stored_videos">已存视频数</option><option value="latest_upload">最近发布</option></select><select id="ovSortDir"''',
        "generic overview sort menu",
        flags=re.S,
    )
    text = _replace(text, '<th data-field="identity creator_label">身份标签</th><th data-field="ugphone_video_count">UgPhone视频数</th><th data-field="gmv_total new_users_total business_metrics">商业表现</th>', '<th data-field="identity creator_label">Workspace 关系</th><th data-field="business_metrics">商业表现</th>', "generic overview headers")

    # Creator detail cards: no fixed customer metric names.
    text = _sub(
        text,
        r'''                facts=f''' + "'''" + r'''<div class="facts">.*?</div><div class="section note"><b>数据新鲜度：</b>''',
        '''                facts=f''' + "'''" + '''<div class="facts"><div class="card fact"><span class="small">订阅数</span><b>{fmt_int(c.get('subscriber_count'))}</b></div><div class="card fact"><span class="small">频道累计播放量</span><b>{fmt_int(c.get('channel_view_count'))}</b></div><div class="card fact"><span class="small">YouTube视频总数</span><b>{fmt_int(c.get('channel_video_count'))}</b></div><div class="card fact"><span class="small">国家（API）</span><b>{esc(c.get('country_api') or '—')}</b></div><div class="card fact"><span class="small">商业指标记录</span><b>{int(c.get('business_metric_count') or 0)}</b><span class="small">按当前 Workspace 定义解释</span></div></div><div class="section note"><b>数据新鲜度：</b>''',
        "generic creator detail facts",
        flags=re.S,
        required=False,
    )
    text = _replace(text, '<option value="priority_views" selected>UgPhone优先 + 播放量</option><option value="views">播放量</option>', '<option value="views" selected>播放量</option>', "neutral creator detail sort")
    text = _replace(text, '<th data-field="views priority_views">播放量 / 历史</th>', '<th data-field="views">播放量 / 历史</th>', "neutral detail view field")
    text = _replace(text, '<th data-field="role brand priority_views">有效分类（人工优先）</th>', '<th data-field="role brand">有效分类（人工优先）</th>', "neutral detail role field")
    text = _replace(text, "                    is_ugphone='1' if role=='ugphone' or 'ugphone' in brand_text else '0'\n", "", "remove legacy detail priority flag")
    text = _replace(text, ' data-ugphone="{is_ugphone}"', '', "remove legacy detail data attribute")

    old_checks = '''            checks=' '.join(f'<label class="small"><input class="review-brand" type="checkbox" value="{b}" {"checked" if b in brands else ""}> {name}</label>' for b,name in [('ugphone','UgPhone'),('ldcloud','LDCloud'),('redfinger','RedFinger'),('vsphone','VSPhone')])\n'''
    new_checks = '''            checks=' '.join(f'<label class="small"><input class="review-brand" type="checkbox" value="{b}" {"checked" if b in brands else ""}> {name}</label>' for b,name in workspace_brand_choices)\n'''
    text = _replace(text, old_checks, new_checks, "dynamic classification brand choices")
    for old_label,new_label in [("UgPhone","主品牌"),("LDCloud","竞品品牌 A"),("RedFinger","竞品品牌 B"),("VSPhone","竞品品牌 C"),("云手机","行业产品"),("Cloud Phone","Industry Product")]:
        text=text.replace(old_label,new_label)
    text += "\n# V4.2 neutral-surface: dashboard\n"
    _write(path, text)


def patch_field_registry(path: Path) -> None:
    text = _read(path)
    if "# V4.2 neutral-surface: field-registry" in text:
        return
    text = _sub(text, r'''\n\s*\{"id": "compatibility", "name": "历史兼容字段", "order": 90\},''', '', "remove compatibility group", required=False)
    text = _sub(text, r'''\nLEGACY_COMPAT_KEYS = \{.*?\}\n''', '\n', "remove legacy compat key catalog", flags=re.S, required=False)
    text = _sub(text, r'''\n    if key in LEGACY_COMPAT_KEYS:\n        return "compatibility"''', '', "remove legacy label group", required=False)
    # Older 4.0-style file variants.
    text = _sub(text, r'''\n    if key in \{"partnered_ugphone","unpartnered_ugphone","suspected_inactive_partner"\}: return "partnership"\n    if key in \{"ldcloud_creator","redfinger_creator","vsphone_creator","ugphone_and_competitor"\}: return "competitor_partnership"''', '', "remove old legacy grouping", required=False)
    text += "\n# V4.2 neutral-surface: field-registry\n"
    _write(path, text)


def patch_templates(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for template in data.get("templates") or []:
        if str(template.get("id")) == "cloud_phone_growth":
            template["visibility"] = "compatibility"
            changed = True
    if not changed:
        # V4.3+ relocates the compatibility template under creator_hub/compat so the
        # public top-level template catalog remains domain-neutral.
        compat_path = ROOT / "creator_hub" / "compat" / "cloud_phone_workspace.json"
        if not compat_path.exists():
            raise RuntimeError("cloud compatibility template not found")
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_sources(root: Path = ROOT) -> list[str]:
    targets = {
        "creator_hub/workspace.py": patch_workspace,
        "creator_hub/metric_workspace.py": patch_metric_workspace,
        "creator_hub/static/metrics_workspace.js": patch_metrics_js,
        "creator_hub/dashboard.py": patch_dashboard,
        "creator_hub/field_registry.py": patch_field_registry,
        "config/workspace_templates.json": patch_templates,
    }
    changed = []
    for rel, fn in targets.items():
        path = root / rel
        if not path.exists():
            raise RuntimeError(f"required neutral-surface source missing: {rel}")
        before = path.read_bytes()
        fn(path)
        if path.read_bytes() != before:
            changed.append(rel)
    return changed


def _compat_workspace(row: Any) -> bool:
    meta = json.loads(row["metadata_json"] or "{}") if row["metadata_json"] else {}
    return str(row["template_id"] or "") == "cloud_phone_growth" or bool(meta.get("compatibility_profile"))


def _contains_legacy(value: Any) -> bool:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        raw = str(value)
    return bool(BANNED.search(raw))


def _sanitize_metric_config(value: Any) -> tuple[dict[str, Any], dict[str, int]]:
    if not isinstance(value, dict):
        return dict(EMPTY_METRICS), {"metrics": 0, "rules": 0, "filters": 0}
    metrics = [m for m in list(value.get("metrics") or []) if isinstance(m, dict)]
    kept_metrics = [m for m in metrics if not _contains_legacy(m)]
    removed_ids = {str(m.get("id")) for m in metrics if m not in kept_metrics and m.get("id")}

    # Cascading ratio dependencies.
    changed = True
    while changed:
        changed = False
        next_metrics = []
        for m in kept_metrics:
            refs = [m.get("numerator_ref"), m.get("denominator_ref")]
            bad = any(isinstance(r, dict) and r.get("kind") == "constructed" and str(r.get("key")) in removed_ids for r in refs)
            if bad:
                if m.get("id"):
                    removed_ids.add(str(m.get("id")))
                changed = True
            else:
                next_metrics.append(m)
        kept_metrics = next_metrics

    rules = [r for r in list(value.get("rules") or []) if isinstance(r, dict)]
    kept_rules = []
    removed_rule_ids = set()
    for rule in rules:
        conditions = list(rule.get("conditions") or [])
        bad = _contains_legacy(rule) or any(
            isinstance(c, dict) and (
                _contains_legacy(c)
                or (str(c.get("metric_type") or "") in {"constructed", "ratio"} and str(c.get("metric_key") or "") in removed_ids)
            )
            for c in conditions
        )
        if bad:
            if rule.get("id"):
                removed_rule_ids.add(str(rule.get("id")))
        else:
            kept_rules.append(rule)

    filters = [f for f in list(value.get("filters") or []) if isinstance(f, dict)]
    kept_filters = [
        f for f in filters
        if not _contains_legacy(f)
        and not (str(f.get("metric_type") or "") in {"constructed", "ratio"} and str(f.get("metric_key") or "") in removed_ids)
    ]
    active = str(value.get("activeRule") or "")
    if active in removed_rule_ids:
        active = ""
    result = {**value, "schema_version": 1, "metrics": kept_metrics, "rules": kept_rules, "filters": kept_filters, "activeRule": active}
    return result, {
        "metrics": len(metrics) - len(kept_metrics),
        "rules": len(rules) - len(kept_rules),
        "filters": len(filters) - len(kept_filters),
    }


def sanitize_database(db_path: Path) -> dict[str, Any]:
    from creator_hub.db import connect, json_dump, json_load
    from creator_hub.util import now_utc
    from creator_hub.workspace import WorkspaceService

    service = WorkspaceService(db_path)
    boot = service.bootstrap()
    switched = False
    backup_rows = 0
    sanitized = {"metrics": 0, "rules": 0, "filters": 0}

    with connect(db_path) as conn:
        workspaces = conn.execute("SELECT id,template_id,metadata_json,is_default,created_at FROM workspaces ORDER BY is_default DESC,created_at").fetchall()
        generic = [r for r in workspaces if not _compat_workspace(r)]
        current_id = service.active_id()
        current = next((r for r in workspaces if str(r["id"]) == current_id), None)
        if current is not None and _compat_workspace(current):
            target = next((r for r in generic if str(r["id"]) == "general"), generic[0] if generic else None)
            if target is None:
                conn.commit()
            else:
                conn.execute(
                    """INSERT INTO app_settings(key,value_json,updated_at) VALUES('active_workspace_id',?,?)
                       ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
                    (json_dump(str(target["id"])), now_utc()),
                )
                switched = True

        # Generic workspaces never inherit compatibility metrics. Preserve a backup before sanitation.
        for ws in generic:
            wid = str(ws["id"])
            row = conn.execute("SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='secondary_metrics'", (wid,)).fetchone()
            if not row:
                continue
            original = json_load(row["value_json"], EMPTY_METRICS)
            clean, counts = _sanitize_metric_config(original)
            if clean != original:
                backup_key = "secondary_metrics_pre_neutral_4_2"
                exists = conn.execute("SELECT 1 FROM workspace_settings WHERE workspace_id=? AND key=?", (wid, backup_key)).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO workspace_settings(workspace_id,key,value_json,updated_at) VALUES(?,?,?,?)",
                        (wid, backup_key, row["value_json"], now_utc()),
                    )
                    backup_rows += 1
                conn.execute(
                    "UPDATE workspace_settings SET value_json=?,updated_at=? WHERE workspace_id=? AND key='secondary_metrics'",
                    (json_dump(clean), now_utc(), wid),
                )
                for k in sanitized:
                    sanitized[k] += counts[k]
        conn.commit()

    return {
        "bootstrap": boot,
        "active_workspace_id": service.active_id(),
        "switched_from_compatibility": switched,
        "metric_backups_created": backup_rows,
        "removed": sanitized,
    }


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
    ap = argparse.ArgumentParser(description="Make the default/public Creator Intelligence surface domain-neutral.")
    ap.add_argument("--source-only", action="store_true", help="patch source files only; do not open the production database")
    ap.add_argument("--db", default="", help="optional SQLite path")
    args = ap.parse_args()
    db = Path(args.db).resolve() if args.db else None
    out = apply(ROOT, db, source_only=args.source_only)
    print(json.dumps({"ok": True, **out}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
