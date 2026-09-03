(()=>{
'use strict';
const $=id=>document.getElementById(id);
async function post(path,body={}){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json();
  if(!r.ok||j.ok===false) throw new Error(j.error||j.message||`HTTP ${r.status}`);
  return j.data!==undefined?j.data:j;
}
function esc(v){return String(v??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]))}
function listHtml(items,fn){return items.length?`<ul>${items.map(x=>`<li>${fn(x)}</li>`).join('')}</ul>`:'<span class="small">未配置</span>'}
let state={workspaces:[],active:null,templates:[]};
async function load(){
  const data=await post('/api/v1/workspaces/list',{});
  state=data||state;
  const sel=$('workspaceSelect');
  sel.innerHTML=(state.workspaces||[]).map(w=>`<option value="${esc(w.id)}" ${state.active&&state.active.id===w.id?'selected':''}>${esc(w.name)}</option>`).join('');
  const ts=$('workspaceTemplate');
  ts.innerHTML=(state.templates||[]).map(t=>`<option value="${esc(t.id)}">${esc(t.name_zh||t.name||t.id)}</option>`).join('');
  renderActive();
}
async function renderActive(){
  const active=state.active;
  if(!active){$('workspaceActive').textContent='未配置';return}
  $('workspaceActive').textContent=active.name||active.id;
  const meta=active.metadata||{};
  $('workspaceActiveMeta').textContent=[`ID: ${active.id}`,`Template: ${active.template_id||'blank'}`,meta.description||''].filter(Boolean).join(' · ');
  const ctx=await post('/api/v1/workspaces/context',{workspace_id:active.id});
  $('workspaceBrands').innerHTML=listHtml(ctx.brands||[],b=>`<b>${esc(b.display_name||b.key)}</b> <span class="pill">${esc(b.role||'brand')}</span>`)+
    ((ctx.brand_groups||[]).length?'<hr>'+listHtml(ctx.brand_groups||[],g=>`<b>${esc(g.name)}</b>：${esc((g.members||[]).map(x=>x.display_name).join('、')||'—')}`):'');
  $('workspaceTaxonomies').innerHTML=listHtml(ctx.taxonomies||[],s=>`<b>${esc(s.name)}</b>：${esc((s.labels||[]).map(x=>x.name).join(' / ')||'—')}`);
  $('workspaceBusiness').innerHTML=listHtml(ctx.business_metrics||[],m=>`<b>${esc(m.name)}</b> · ${esc(m.value_type||'number')} ${esc(m.currency||m.unit||'')}`);
  $('workspaceDiscovery').innerHTML=listHtml(ctx.discovery_profiles||[],p=>`<b>${esc(p.name)}</b> ${p.enabled?'<span class="pill good">启用</span>':'<span class="pill">停用</span>'}`);
}
$('workspaceActivate')?.addEventListener('click',async()=>{
  const id=$('workspaceSelect').value;if(!id)return;
  $('workspaceStatus').textContent='正在切换并重建 Dashboard…';
  try{
    await post('/api/v1/workspaces/set-active',{workspace_id:id});
    $('workspaceStatus').textContent='已切换。正在刷新…';
    location.reload();
  }catch(e){$('workspaceStatus').textContent='切换失败：'+e.message}
});
$('workspaceCreate')?.addEventListener('click',async()=>{
  const name=$('workspaceName').value.trim();const template_id=$('workspaceTemplate').value||'blank';
  if(!name){$('workspaceStatus').textContent='请输入 Workspace 名称';return}
  $('workspaceStatus').textContent='正在创建…';
  try{
    const ws=await post('/api/v1/workspaces/create',{name,template_id});
    $('workspaceStatus').textContent=`已创建 ${ws.name||name}`;
    $('workspaceName').value='';
    await load();
  }catch(e){$('workspaceStatus').textContent='创建失败：'+e.message}
});
load().catch(e=>{$('workspaceStatus').textContent='读取 Workspace 失败：'+e.message});
})();
