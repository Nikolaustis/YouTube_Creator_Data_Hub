from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.4.0"
PROFILE = "generic_creator_discovery_v2"
SCHEMA_VERSION = 4


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _replace(text: str, old: str, new: str, label: str, *, required: bool = True) -> str:
    if old not in text:
        if required:
            raise RuntimeError(f"query-pack-editor patch anchor missing: {label}")
        return text
    return text.replace(old, new)


def _sub(text: str, pattern: str, repl: str, label: str, *, required: bool = True) -> str:
    out, count = re.subn(pattern, repl, text, flags=re.S)
    if required and count == 0:
        raise RuntimeError(f"query-pack-editor regex anchor missing: {label}")
    return out


def _template(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _languages(template: dict[str, Any]) -> list[str]:
    return list((template.get("languages") or {}).keys())


def _uniq(xs: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in xs or []:
        value = str(raw or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _default_pack_record(pack: dict[str, Any], languages: list[str]) -> dict[str, Any]:
    terms: dict[str, list[str]] = {}
    active: dict[str, list[str]] = {}
    for lang in languages:
        vals = _uniq((pack.get("terms") or {}).get(lang) or [])
        terms[lang] = vals
        active[lang] = list(vals)
    return {
        "id": str(pack.get("id") or ""),
        "name": str(pack.get("name_zh") or pack.get("name") or pack.get("id") or "Query Pack"),
        "description": str(pack.get("description_zh") or pack.get("description") or ""),
        "enabled": bool(pack.get("default_enabled")),
        "system": True,
        "terms": terms,
        "active": active,
    }


def default_profile(template: dict[str, Any]) -> dict[str, Any]:
    languages = _languages(template)
    packs: dict[str, Any] = {}
    order: list[str] = []
    for pack in template.get("packs") or []:
        pid = str(pack.get("id") or "").strip()
        if not pid:
            continue
        order.append(pid)
        packs[pid] = _default_pack_record(pack, languages)
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "language": str(template.get("default_language") or "en"),
        "order": order,
        "packs": packs,
    }


def upgrade_profile(value: Any, template: dict[str, Any]) -> dict[str, Any]:
    """Upgrade Query Pack state without overwriting user customizations.

    v3 profiles could modify enable state and per-language terms for the fixed default
    packs. v4 retains those edits and adds pack metadata/order/custom pack support.
    Existing v4 profiles are normalized but never reset to template defaults.
    """
    base = default_profile(template)
    languages = _languages(template)
    defaults = {str(p.get("id") or ""): p for p in template.get("packs") or []}
    if not isinstance(value, dict):
        return base

    if int(value.get("schema_version") or 0) >= SCHEMA_VERSION and value.get("profile") == PROFILE:
        raw_packs = value.get("packs") if isinstance(value.get("packs"), dict) else {}
        raw_order = value.get("order") if isinstance(value.get("order"), list) else list(raw_packs)
        order: list[str] = []
        packs: dict[str, Any] = {}
        for raw_id in [*raw_order, *[x for x in raw_packs if x not in raw_order]]:
            pid = str(raw_id or "").strip()
            if not pid or pid in packs:
                continue
            source = raw_packs.get(pid)
            if not isinstance(source, dict):
                continue
            default_pack = defaults.get(pid)
            fallback = _default_pack_record(default_pack, languages) if default_pack else None
            rec = {
                "id": pid,
                "name": str(source.get("name") or (fallback or {}).get("name") or pid),
                "description": str(source.get("description") or (fallback or {}).get("description") or ""),
                "enabled": bool(source.get("enabled")),
                "system": bool(default_pack is not None),
                "terms": {},
                "active": {},
            }
            for lang in languages:
                source_terms = source.get("terms") if isinstance(source.get("terms"), dict) else {}
                if lang in source_terms and isinstance(source_terms.get(lang), list):
                    vals = _uniq(source_terms.get(lang) or [])
                else:
                    vals = list((fallback.get("terms") or {}).get(lang) or []) if fallback else []
                source_active = source.get("active") if isinstance(source.get("active"), dict) else {}
                active = _uniq(source_active.get(lang) if lang in source_active and isinstance(source_active.get(lang), list) else vals)
                allowed = {x.casefold(): x for x in vals}
                rec["terms"][lang] = vals
                rec["active"][lang] = [allowed[x.casefold()] for x in active if x.casefold() in allowed]
            order.append(pid)
            packs[pid] = rec
        return {
            "schema_version": SCHEMA_VERSION,
            "profile": PROFILE,
            "language": str(value.get("language") or base["language"]),
            "order": order,
            "packs": packs,
        }

    # v3 generic profile: preserve all fixed-pack term/enable edits.
    if int(value.get("schema_version") or 0) >= 3 and value.get("profile") == "generic_creator_discovery_v1":
        old_packs = value.get("packs") if isinstance(value.get("packs"), dict) else {}
        for pid in list(base["order"]):
            old = old_packs.get(pid)
            if not isinstance(old, dict):
                continue
            rec = base["packs"][pid]
            rec["enabled"] = bool(old.get("enabled"))
            for lang in languages:
                if isinstance(old.get("terms"), dict) and isinstance(old["terms"].get(lang), list):
                    rec["terms"][lang] = _uniq(old["terms"][lang])
                if isinstance(old.get("active"), dict) and isinstance(old["active"].get(lang), list):
                    allowed = {x.casefold(): x for x in rec["terms"][lang]}
                    rec["active"][lang] = [allowed[x.casefold()] for x in _uniq(old["active"][lang]) if x.casefold() in allowed]
                else:
                    rec["active"][lang] = list(rec["terms"][lang])
        base["language"] = str(value.get("language") or base["language"])
    return base


def patch_dashboard(path: Path) -> None:
    text = _read(path)
    if "# V4.4 query-pack-editor: dashboard" in text:
        return
    old = '<select id="queryLanguage" class="select"></select><button class="btn" id="queryResetDefaults">恢复当前语言默认词</button>'
    new = (
        '<select id="queryLanguage" class="select"></select>'
        '<button class="btn primary" id="queryAddPack">新增组</button>'
        '<button class="btn" id="queryResetLanguageDefaults">恢复当前语言默认词</button>'
        '<button class="btn" id="queryResetDefaults">恢复系统默认 Query Packs</button>'
    )
    text = _replace(text, old, new, "Query Expansion toolbar")
    text += "\n# V4.4 query-pack-editor: dashboard\n"
    _write(path, text)


EDITOR_BLOCK = r'''function defaultPackRecord(p){const terms={},active={};for(const lang of Object.keys(QP.languages||{})){const vals=uniqTerms((p.terms||{})[lang]||[]);terms[lang]=vals;active[lang]=[...vals]}return {id:String(p.id||''),name:String(p.name_zh||p.name||p.id||'Query Pack'),description:String(p.description_zh||p.description||''),enabled:!!p.default_enabled,system:true,terms,active}}
function defaultPackById(id){return (QP.packs||[]).find(p=>String(p.id||'')===String(id||''))||null}
function freshQueryState(){const packs={},order=[];for(const p of QP.packs||[]){const rec=defaultPackRecord(p);if(!rec.id)continue;order.push(rec.id);packs[rec.id]=rec}return {schema_version:4,profile:'generic_creator_discovery_v2',order,packs}}
function normalizePackId(raw){let s=String(raw||'').trim().replace(/[^a-zA-Z0-9_.:-]+/g,'_').replace(/^_+|_+$/g,'');if(!s)s='pack';return s.slice(0,80)}
function normalizePackRecord(id,src={},fallback=null){const terms={},active={};for(const lang of Object.keys(QP.languages||{})){let vals=uniqTerms(src?.terms?.[lang]||fallback?.terms?.[lang]||[]);const allow=new Map(vals.map(x=>[termKey(x),x]));let on=uniqTerms(src?.active?.[lang]||vals).map(x=>allow.get(termKey(x))).filter(Boolean);terms[lang]=vals;active[lang]=on}return {id,name:String(src.name||fallback?.name||id).trim()||id,description:String(src.description||fallback?.description||''),enabled:!!src.enabled,system:!!fallback,terms,active}}
function mergeQueryState(saved){const fresh=freshQueryState();if(!saved||typeof saved!=='object'||!saved.packs)return fresh;if(Number(saved.schema_version||0)>=4&&saved.profile==='generic_creator_discovery_v2'){
 const packs={},order=[],raw=saved.packs||{},requested=Array.isArray(saved.order)?saved.order:Object.keys(raw);for(const rid of [...requested,...Object.keys(raw).filter(x=>!requested.includes(x))]){const id=normalizePackId(rid);if(!id||packs[id]||!raw[rid])continue;const def=defaultPackById(id),fb=def?defaultPackRecord(def):null;packs[id]=normalizePackRecord(id,raw[rid],fb);order.push(id)}return {schema_version:4,profile:'generic_creator_discovery_v2',order,packs}}
 // v3 -> v4: preserve fixed-pack terms and enabled state instead of resetting user edits.
 for(const id of fresh.order){const old=saved.packs?.[id];if(!old)continue;const rec=fresh.packs[id];rec.enabled=!!old.enabled;for(const lang of Object.keys(QP.languages||{})){if(Array.isArray(old.terms?.[lang]))rec.terms[lang]=uniqTerms(old.terms[lang]);const allow=new Map(rec.terms[lang].map(x=>[termKey(x),x]));rec.active[lang]=Array.isArray(old.active?.[lang])?uniqTerms(old.active[lang]).map(x=>allow.get(termKey(x))).filter(Boolean):[...rec.terms[lang]]}}return fresh}
function loadQueryState(){let saved=null;try{saved=JSON.parse(localStorage.getItem(QP_STORE)||'null');if(!saved){saved=JSON.parse(localStorage.getItem(QP_PREV_STORE)||'null')}}catch(e){}return mergeQueryState(saved)}
function queryProfileValue(){return {schema_version:4,profile:'generic_creator_discovery_v2',language:currentQueryLang(),order:[...(queryState?.order||[])],packs:queryState?.packs||{}}}
function saveQueryState(){localStorage.setItem(QP_STORE,JSON.stringify(queryState));try{localStorage.setItem(QP_LANG_STORE,currentQueryLang())}catch(e){}if(interactive&&queryDbReady){clearTimeout(querySaveTimer);querySaveTimer=setTimeout(()=>post('/api/settings/set',{key:'query_profile',value:queryProfileValue()}).catch(()=>{}),180)}}
async function hydrateQueryProfile(){if(!interactive)return;const x=await post('/api/settings/get',{key:'query_profile'});const v=x.value||null;queryState=mergeQueryState(v);const lang=document.getElementById('queryLanguage');if(v?.language&&QP.languages?.[v.language])lang.value=v.language;localStorage.setItem(QP_STORE,JSON.stringify(queryState));localStorage.setItem(QP_LANG_STORE,lang.value);if(Number(v?.schema_version||0)<4||v?.profile!=='generic_creator_discovery_v2')await post('/api/settings/set',{key:'query_profile',value:queryProfileValue()});queryDbReady=true;renderQueryPacks();updateQueryPreview();const st=document.getElementById('queryProfileStatus');if(st)st.textContent='Query Pack 组、顺序与多语言词库已按当前 Workspace 保存到本地 SQLite'}
function currentQueryLang(){return document.getElementById('queryLanguage').value||QP.default_language||'en'}
function activeSet(st,lang){return new Set((st?.active?.[lang]||[]).map(termKey))}
function packList(){return (queryState?.order||[]).map(id=>queryState.packs?.[id]).filter(Boolean)}
function buildExpandedQueries(base){const q=normTerm(base),out=[],seen=new Set();function add(x){x=normTerm(x);const k=termKey(x);if(x&&!seen.has(k)){seen.add(k);out.push(x)}}add(q);const lang=currentQueryLang();for(const st of packList()){if(!st?.enabled)continue;const active=activeSet(st,lang);for(const term of st.terms?.[lang]||[]){if(active.has(termKey(term)))add(`${q} ${term}`)}}return out.slice(0,Number(QP.max_queries_per_search||80))}
function queryTermChip(packId,term,index,checked){return `<span class="qe-term ${checked?'':'inactive'}"><label title="勾选后本次搜索使用该扩展词"><input type="checkbox" data-qe-term-toggle="${esc(packId)}" data-qe-index="${index}" ${checked?'checked':''}> <span>${esc(term)}</span></label><button type="button" data-qe-remove="${esc(packId)}" data-qe-index="${index}" title="从当前语言词库删除">×</button></span>`}
function uniquePackId(seed='pack'){let base=normalizePackId(seed),id=base,n=2;while(queryState.packs[id])id=`${base}_${n++}`;return id}
function addPack(){const id=uniquePackId('custom_'+Date.now().toString(36)),terms={},active={};for(const lang of Object.keys(QP.languages||{})){terms[lang]=[];active[lang]=[]}queryState.packs[id]={id,name:'新建扩展组',description:'',enabled:false,system:false,terms,active};queryState.order.push(id);saveQueryState();renderQueryPacks();updateQueryPreview();setTimeout(()=>document.querySelector(`[data-qe-edit="${CSS.escape(id)}"]`)?.click(),0)}
function duplicatePack(id){const src=queryState.packs[id];if(!src)return;const nid=uniquePackId(id+'_copy'),copy=JSON.parse(JSON.stringify(src));copy.id=nid;copy.name=(src.name||id)+' · 副本';copy.system=false;queryState.packs[nid]=copy;const at=Math.max(0,queryState.order.indexOf(id));queryState.order.splice(at+1,0,nid);saveQueryState();renderQueryPacks();updateQueryPreview()}
function deletePack(id){const p=queryState.packs[id];if(!p)return;if(!confirm(`删除 Query Pack「${p.name||id}」？组内多语言词库也会从当前 Workspace 配置中删除。`))return;delete queryState.packs[id];queryState.order=queryState.order.filter(x=>x!==id);saveQueryState();renderQueryPacks();updateQueryPreview()}
function movePack(id,delta){const i=queryState.order.indexOf(id),j=i+delta;if(i<0||j<0||j>=queryState.order.length)return;[queryState.order[i],queryState.order[j]]=[queryState.order[j],queryState.order[i]];saveQueryState();renderQueryPacks();updateQueryPreview()}
function resetPack(id){const def=defaultPackById(id);if(!def)return alert('该组为自定义组，没有系统默认值。');if(!confirm(`恢复「${queryState.packs[id]?.name||id}」的系统默认名称、说明、启用状态和全部语言词库？`))return;queryState.packs[id]=defaultPackRecord(def);saveQueryState();renderQueryPacks();updateQueryPreview()}
function renderQueryPacks(){const lang=currentQueryLang(),grid=document.getElementById('queryPackGrid'),items=packList();grid.innerHTML=items.map((p,pos)=>{const terms=p?.terms?.[lang]||[],active=activeSet(p,lang),activeCount=terms.filter(t=>active.has(termKey(t))).length;return `<div class="qe-card ${p?.enabled?'enabled':''}" data-qe-card="${esc(p.id)}"><div class="qe-head"><div style="min-width:0"><div class="qe-title"><label><input type="checkbox" data-qe-enable="${esc(p.id)}" ${p?.enabled?'checked':''}> ${esc(p.name||p.id)}</label></div><div class="qe-desc">${esc(p.description||'')}</div></div><div style="text-align:right"><span class="small">${activeCount}/${terms.length} 词启用</span><div class="toolbar" style="justify-content:flex-end;margin:6px 0 0;gap:5px"><button class="btn" data-qe-edit="${esc(p.id)}">编辑</button><button class="btn" data-qe-copy="${esc(p.id)}">复制</button><button class="btn" data-qe-up="${esc(p.id)}" ${pos===0?'disabled':''}>↑</button><button class="btn" data-qe-down="${esc(p.id)}" ${pos===items.length-1?'disabled':''}>↓</button>${p.system?`<button class="btn" data-qe-reset-pack="${esc(p.id)}">恢复默认</button>`:''}<button class="btn danger" data-qe-delete="${esc(p.id)}">删除</button></div></div></div><div class="qe-pack-edit" data-qe-editor="${esc(p.id)}" style="display:none;margin:10px 0;padding:10px;border:1px solid var(--line);border-radius:8px;background:#fafbfc"><div class="form-row"><label>组名称</label><input class="input" data-qe-name="${esc(p.id)}" value="${esc(p.name||'')}"></div><div class="form-row top"><label>组说明</label><textarea class="input" rows="2" data-qe-desc="${esc(p.id)}">${esc(p.description||'')}</textarea></div><div class="toolbar" style="justify-content:flex-end;margin:8px 0 0"><button class="btn primary" data-qe-save-meta="${esc(p.id)}">保存组信息</button><button class="btn" data-qe-cancel-edit="${esc(p.id)}">取消</button></div></div><div class="qe-terms">${terms.map((t,i)=>queryTermChip(p.id,t,i,active.has(termKey(t)))).join('')||'<span class="small">当前语言暂无长尾词</span>'}</div><div class="qe-add"><input class="input" data-qe-input="${esc(p.id)}" placeholder="新增当前语言长尾词"><button class="btn" data-qe-add="${esc(p.id)}">添加</button></div></div>`}).join('')||'<div class="note">当前 Workspace 暂无 Query Pack。原始搜索主题仍会执行；可点击“新增组”创建扩展策略。</div>';
 grid.querySelectorAll('[data-qe-enable]').forEach(x=>x.onchange=()=>{queryState.packs[x.dataset.qeEnable].enabled=x.checked;saveQueryState();renderQueryPacks();updateQueryPreview()});grid.querySelectorAll('[data-qe-term-toggle]').forEach(x=>x.onchange=()=>{const st=queryState.packs[x.dataset.qeTermToggle],arr=st.terms[lang]||[],term=arr[Number(x.dataset.qeIndex)];if(!term)return;const active=activeSet(st,lang);if(x.checked)active.add(termKey(term));else active.delete(termKey(term));st.active[lang]=arr.filter(t=>active.has(termKey(t)));saveQueryState();renderQueryPacks();updateQueryPreview()});grid.querySelectorAll('[data-qe-remove]').forEach(x=>x.onclick=()=>{const st=queryState.packs[x.dataset.qeRemove],arr=st.terms[lang]||[],idx=Number(x.dataset.qeIndex),removed=arr[idx];arr.splice(idx,1);st.terms[lang]=arr;if(removed)st.active[lang]=(st.active[lang]||[]).filter(t=>termKey(t)!==termKey(removed));saveQueryState();renderQueryPacks();updateQueryPreview()});grid.querySelectorAll('[data-qe-add]').forEach(b=>b.onclick=()=>{const inp=grid.querySelector(`[data-qe-input="${CSS.escape(b.dataset.qeAdd)}"]`),v=normTerm(inp.value);if(!v)return;const st=queryState.packs[b.dataset.qeAdd],arr=st.terms[lang]||[];if(!arr.some(x=>termKey(x)===termKey(v))){arr.push(v);st.terms[lang]=arr;st.active[lang]=[...(st.active[lang]||[]),v]}saveQueryState();renderQueryPacks();updateQueryPreview()});grid.querySelectorAll('[data-qe-input]').forEach(inp=>inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();grid.querySelector(`[data-qe-add="${CSS.escape(inp.dataset.qeInput)}"]`)?.click()}});grid.querySelectorAll('[data-qe-edit]').forEach(b=>b.onclick=()=>{const ed=grid.querySelector(`[data-qe-editor="${CSS.escape(b.dataset.qeEdit)}"]`);if(ed)ed.style.display=ed.style.display==='none'?'block':'none'});grid.querySelectorAll('[data-qe-cancel-edit]').forEach(b=>b.onclick=()=>{const ed=grid.querySelector(`[data-qe-editor="${CSS.escape(b.dataset.qeCancelEdit)}"]`);if(ed)ed.style.display='none'});grid.querySelectorAll('[data-qe-save-meta]').forEach(b=>b.onclick=()=>{const id=b.dataset.qeSaveMeta,p=queryState.packs[id],name=grid.querySelector(`[data-qe-name="${CSS.escape(id)}"]`)?.value.trim()||'',desc=grid.querySelector(`[data-qe-desc="${CSS.escape(id)}"]`)?.value.trim()||'';if(!name)return alert('组名称不能为空');p.name=name;p.description=desc;saveQueryState();renderQueryPacks();updateQueryPreview()});grid.querySelectorAll('[data-qe-copy]').forEach(b=>b.onclick=()=>duplicatePack(b.dataset.qeCopy));grid.querySelectorAll('[data-qe-delete]').forEach(b=>b.onclick=()=>deletePack(b.dataset.qeDelete));grid.querySelectorAll('[data-qe-up]').forEach(b=>b.onclick=()=>movePack(b.dataset.qeUp,-1));grid.querySelectorAll('[data-qe-down]').forEach(b=>b.onclick=()=>movePack(b.dataset.qeDown,1));grid.querySelectorAll('[data-qe-reset-pack]').forEach(b=>b.onclick=()=>resetPack(b.dataset.qeResetPack))}
function updateQueryPreview(){const qs=buildExpandedQueries(document.getElementById('discoverQuery').value),box=document.getElementById('queryPreview');box.innerHTML=qs.map((q,i)=>`<div>${i+1}. ${esc(q)}</div>`).join('')||'<span class="muted">输入搜索主题后显示查询预览</span>';const max=Number(document.getElementById('discoverMax').value||50),source=document.getElementById('discoverSource').value,cost=document.getElementById('queryCost');if(source==='api'){const units=qs.length*Math.ceil(max/50)*100;cost.textContent=`共 ${qs.length} 个 Query · 每个 Query 最多 ${max} 个视频 · API search.list 预计最多约 ${units.toLocaleString('zh-CN')} quota units${units>9500?'（超过默认每日软上限，可能只完成部分 Query）':''}`;cost.style.color=units>9500?'#b42318':''}else{cost.textContent=`共 ${qs.length} 个 Query · 每个 Query 最多 ${max} 个视频 · 网页搜索会跟随 continuation 深度加载；频道/视频指标补全仍会调用 YouTube API。`;cost.style.color=''}}
function setupQueryExpansion(){queryState=loadQueryState();const lang=document.getElementById('queryLanguage');lang.innerHTML=Object.entries(QP.languages||{}).map(([k,v])=>`<option value="${esc(k)}">${esc(v.name||k)}</option>`).join('');const savedLang=localStorage.getItem(QP_LANG_STORE),initial=(savedLang&&QP.languages?.[savedLang])?savedLang:(QP.default_language||'en');lang.value=initial;lang.onchange=()=>{saveQueryState();renderQueryPacks();updateQueryPreview()};document.getElementById('queryAddPack').onclick=addPack;document.getElementById('queryResetLanguageDefaults').onclick=()=>{const l=currentQueryLang();for(const id of queryState.order){const p=queryState.packs[id],def=defaultPackById(id);if(!p||!def)continue;const vals=uniqTerms((def.terms||{})[l]||[]);p.terms[l]=vals;p.active[l]=[...vals]}saveQueryState();renderQueryPacks();updateQueryPreview()};document.getElementById('queryResetDefaults').onclick=()=>{if(!confirm('恢复系统默认 Query Packs？当前 Workspace 的自定义组、组名、说明、排序与词库修改都会被替换。'))return;queryState=freshQueryState();saveQueryState();renderQueryPacks();updateQueryPreview()};document.getElementById('discoverQuery').oninput=updateQueryPreview;document.getElementById('discoverSource').onchange=updateQueryPreview;document.getElementById('discoverMax').onchange=updateQueryPreview;renderQueryPacks();updateQueryPreview()}
'''


def patch_discovery_js(path: Path) -> None:
    text = _read(path)
    if "/* V4.4 query-pack-editor */" in text:
        return
    if "/* V4.3 generic-discovery */" not in text:
        raise RuntimeError("V4.4 query-pack-editor requires V4.3 generic discovery migration to run first")

    old_const = (
        "const WORKSPACE_KEY=String((window.CDH_CREATOR_FACTS||{}).workspace_id||'general').replace(/[^a-zA-Z0-9_.:-]/g,'_');\n"
        "const QP_STORE='cdh-query-packs-v3::'+WORKSPACE_KEY,QP_OLD_STORES=['cdh-query-packs-v3','cdh-query-packs-v2','cdh-query-packs-v1'],QP_LANG_STORE='cdh-query-language-v2::'+WORKSPACE_KEY;"
    )
    new_const = (
        "const WORKSPACE_KEY=String((window.CDH_CREATOR_FACTS||{}).workspace_id||'general').replace(/[^a-zA-Z0-9_.:-]/g,'_');\n"
        "const QP_STORE='cdh-query-packs-v4::'+WORKSPACE_KEY,QP_PREV_STORE='cdh-query-packs-v3::'+WORKSPACE_KEY,QP_OLD_STORES=['cdh-query-packs-v3','cdh-query-packs-v2','cdh-query-packs-v1'],QP_LANG_STORE='cdh-query-language-v3::'+WORKSPACE_KEY;"
    )
    text = _replace(text, old_const, new_const, "Workspace-scoped v4 storage")

    text = _sub(
        text,
        r"function freshQueryState\(\)\{.*?\n\nfunction savedFilterOptions",
        EDITOR_BLOCK + "\n\nfunction savedFilterOptions",
        "Query Pack state/editor block",
    )

    text += "\n/* V4.4 query-pack-editor */\n"
    _write(path, text)


def patch_query_pack_template(path: Path) -> None:
    data = _template(path)
    data["schema_version"] = SCHEMA_VERSION
    data["profile"] = PROFILE
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_sources(root: Path = ROOT) -> list[str]:
    targets = {
        "creator_hub/dashboard.py": patch_dashboard,
        "creator_hub/static/discovery.js": patch_discovery_js,
        "config/query_packs.json": patch_query_pack_template,
    }
    changed: list[str] = []
    for rel, fn in targets.items():
        path = root / rel
        if not path.exists():
            raise RuntimeError(f"required Query Pack editor source missing: {rel}")
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


def sanitize_database(db_path: Path, template_path: Path | None = None) -> dict[str, Any]:
    from creator_hub.db import connect, json_dump, json_load
    from creator_hub.util import now_utc

    template = _template(template_path or (ROOT / "config" / "query_packs.json"))
    upgraded = 0
    backups = 0
    with connect(db_path) as conn:
        rows = conn.execute("SELECT id,template_id,metadata_json FROM workspaces").fetchall()
        for ws in rows:
            if _is_compat_workspace(ws):
                continue
            wid = str(ws["id"])
            row = conn.execute(
                "SELECT value_json FROM workspace_settings WHERE workspace_id=? AND key='query_profile'",
                (wid,),
            ).fetchone()
            if not row:
                continue
            old = json_load(row["value_json"], {})
            if isinstance(old, dict) and int(old.get("schema_version") or 0) >= SCHEMA_VERSION and old.get("profile") == PROFILE:
                continue
            backup_key = "query_profile_pre_editor_4_4"
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
            new_value = upgrade_profile(old, template)
            conn.execute(
                "UPDATE workspace_settings SET value_json=?,updated_at=? WHERE workspace_id=? AND key='query_profile'",
                (json_dump(new_value), now_utc(), wid),
            )
            upgraded += 1
        conn.commit()
    return {"query_profiles_upgraded": upgraded, "query_profile_editor_backups_created": backups}


def apply(root: Path = ROOT, db_path: Path | None = None, *, source_only: bool = False) -> dict[str, Any]:
    changed = patch_sources(root)
    db_result = None
    if not source_only:
        if db_path is None:
            from creator_hub.config import DEFAULT_DB
            db_path = Path(DEFAULT_DB)
        db_result = sanitize_database(Path(db_path), root / "config" / "query_packs.json")
    return {"changed_sources": changed, "database": db_result}


def main() -> int:
    ap = argparse.ArgumentParser(description="Enable editable Workspace-scoped Query Pack groups.")
    ap.add_argument("--source-only", action="store_true")
    ap.add_argument("--db", default="")
    args = ap.parse_args()
    db = Path(args.db).resolve() if args.db else None
    result = apply(ROOT, db, source_only=args.source_only)
    print(json.dumps({"ok": True, "version": VERSION, **result}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
