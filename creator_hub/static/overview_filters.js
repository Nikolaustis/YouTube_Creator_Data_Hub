(()=>{
'use strict';
const KEYS=['cdh-secondary-metrics-v6','cdh-secondary-metrics-v5','cdh-secondary-metrics-v4','cdh-secondary-metrics-v3'];
const F=window.CDH_CREATOR_FACTS||{creators:[]},B=window.CDH_METRIC_BASE||{cubes:{},creator_fact_fields:{},creator_labels:{}},GEO=window.CDH_GEOGRAPHY||{groups:[],countries:[]};
const geoCountry=new Map((GEO.countries||[]).map(x=>[x.code,x]));
const creatorFactFields=B.creator_fact_fields||B.objective_fields||{},creatorLabels=B.creator_labels||B.aggregate_labels||{};
let S=window.CDH_SAVED_METRIC_CONFIG||{metrics:[]};if(!window.CDH_SAVED_METRIC_CONFIG){for(const k of KEYS){try{const x=JSON.parse(localStorage.getItem(k)||'null');if(x){S={...S,...x};break}}catch(e){}}}
const byId=new Map((F.creators||[]).map(x=>[x.channel_id,x]));
async function post(path,payload={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),x=await r.json();if(!r.ok||x.ok===false)throw new Error(x.error||`HTTP ${r.status}`);return x}
const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]||c));
const fmt=n=>Number(n||0).toLocaleString('zh-CN');
const priorityName={high:'高',normal:'普通',low:'低',archive:'归档'};
let interactive=false;
let fieldRegistry=[];function refreshFieldRegistry(){fieldRegistry=window.CDHFieldRegistry?CDHFieldRegistry.build(B,S.metrics||[]):[]}
function overviewSortEntries(){refreshFieldRegistry();return fieldRegistry.filter(e=>e.grain==='creator'&&e.sortable&&e.kind==='creator_fact').concat([{id:'country',key:'country',kind:'geography',label:'国家',group:'geography',grain:'creator',sortable:true},{id:'latest_upload',key:'latest_upload',kind:'creator_fact',label:'最近发布',group:'data_health',grain:'creator',sortable:true}]).filter((x,i,a)=>a.findIndex(y=>y.id===x.id)===i)}
function mountPicker(select,entriesFn,ns,placeholder='选择字段'){if(!window.CDHFieldRegistry||!select)return;const root=select.nextElementSibling?.classList?.contains('field-picker')?select.nextElementSibling:null;const api=root?root._fieldPicker:CDHFieldRegistry.mount(select,{entries:entriesFn,namespace:ns,placeholder});api?.refresh()}

function markDataChanged(){try{localStorage.setItem('cdh-data-revision',String(Date.now()))}catch(e){}}
function bucket(c,s,v,w){return (((((B.cubes||{})[c.channel_id]||{})[s]||{})[v]||{})[w]||{})}
function pl(k){const a=String(k||'').split(':');return {s:a[0],v:a[1]}}
function side(c,spec){let b=bucket(c,'all','all',spec.window||'all');if(spec.filter_label){const z=pl(spec.filter_label);b=bucket(c,z.s,z.v,spec.window||'all')}const a=spec.aggregation||'count';if(a==='count'||spec.source_field==='video_count')return a==='count'?Number(b.count||0):null;return Number(((b[spec.source_field]||{})[a])??NaN)}
function findMetric(id){return (S.metrics||[]).find(x=>x.id===id)}
function refv(c,r,seen){if(!r)return null;if(r.kind==='creator_fact')return Number(c[r.key]??0);if(r.kind==='constructed')return cv(c,findMetric(r.key),seen);return null}
function cv(c,m,seen=new Set()){
 if(!m)return null;if(m.custom_values&&Object.prototype.hasOwnProperty.call(m.custom_values,c.channel_id))return m.custom_values[c.channel_id];if(seen.has(m.id))return null;seen.add(m.id);
 if(m.type==='constructed'){
   if(m.source_kind==='aggregate_label')return Number(c[m.source_field]??0); // legacy only
   if(m.source_kind==='label'){const z=pl(m.source_field),w=m.window||'all',a=m.aggregation||'count',match=Number(bucket(c,z.s,z.v,w).count||0),total=Number(bucket(c,'all','all',w).count||0);return a==='count'||a==='sum'?match:a==='avg'?(total?match/total:0):a==='median'?(total&&match*2>=total?1:0):a==='max'?(match>0?1:0):(total>0&&match===total?1:0)}
   return side(c,m);
 }
 if(m.type==='ratio'){
   if(m.numerator_ref&&m.denominator_ref){const a=refv(c,m.numerator_ref,new Set(seen)),d=refv(c,m.denominator_ref,new Set(seen));return d!==null&&Number(d)!==0?Number(a||0)/Number(d):null}
   if(m.numerator_spec&&m.denominator_spec){const a=side(c,m.numerator_spec),d=side(c,m.denominator_spec);return d?a/d:null}
 }
 return null;
}
function cmp(v,o,t){v=Number(v);t=Number(t);if(!Number.isFinite(v)||!Number.isFinite(t))return false;return o==='gt'?v>t:o==='gte'?v>=t:o==='lt'?v<t:o==='lte'?v<=t:o==='eq'?v===t:v!==t}
function normType(t){return t==='objective'?'creator_fact':t==='aggregate_label'?'creator_label':t}
function options(cat){cat=normType(cat);if(cat==='creator_fact')return Object.entries(creatorFactFields);if(cat==='creator_label')return Object.entries(creatorLabels);return (S.metrics||[]).filter(m=>m.type===cat&&!m.internal&&!(cat==='constructed'&&m.source_kind==='aggregate_label')).map(m=>[m.id,m.name])}
function overviewFieldEntries(cat){cat=normType(cat);refreshFieldRegistry();if(cat==='creator_fact')return fieldRegistry.filter(e=>e.kind==='creator_fact'&&e.grain==='creator').map(e=>({...e,id:e.key}));if(cat==='creator_label')return fieldRegistry.filter(e=>e.kind==='creator_label').map(e=>({...e,id:e.key}));if(cat==='constructed'||cat==='ratio')return fieldRegistry.filter(e=>e.kind===cat).map(e=>({...e,id:e.key}));return []}
function value(c,type,key){type=normType(type);if(type==='creator_fact'||type==='creator_label')return Number(c[key]??0);return cv(c,findMetric(key))}
function passCond(c,x){const type=normType(x.type);if(type==='geography'){const code=c.country_resolved||c.country_api||'',row=geoCountry.get(code);if(!row||row.group!==x.key)return false;return x.country?code===x.country:true}const v=value(c,type,x.key);if(type==='creator_label')return x.op==='falsy'?!Number(v):!!Number(v);return cmp(v,x.op,x.value)}
function chain(c,conds){if(!conds.length)return true;let a=passCond(c,conds[0]);for(let i=1;i<conds.length;i++){const b=passCond(c,conds[i]),j=conds[i].join||'AND';a=j==='OR'?(a||b):j==='NOT'?(a&&!b):(a&&b)}return a}
const q=document.getElementById('q'),sort=document.getElementById('ovSort'),dir=document.getElementById('ovSortDir'),ps=document.getElementById('ovPageSize'),psOk=document.getElementById('ovPageSizeConfirm'),summary=document.getElementById('ovSummary'),tbody=document.getElementById('rows'),box=document.getElementById('ovFilterConditions'),filterStatus=document.getElementById('ovFilterStatus');
let rows=[...tbody.querySelectorAll('tr')];let page=1,size=30,active=[];ps.value='30';
refreshFieldRegistry();if(window.CDHFieldRegistry){const cur=sort.value||'ugphone_video_count';CDHFieldRegistry.optionGroups(sort,overviewSortEntries(),cur);if([...sort.options].some(o=>o.value===cur))sort.value=cur;mountPicker(sort,overviewSortEntries,'creator-library-sort','选择排序字段')}
function identityPills(c){const a=[c.partnered_ugphone?['合作过博主','identity-partnered']:['未合作博主','identity-unpartnered'],c.ldcloud_creator?['LDCloud合作博主','identity-competitor']:null,c.redfinger_creator?['RedFinger合作博主','identity-competitor']:null,c.vsphone_creator?['VSPhone合作博主','identity-competitor']:null,c.suspected_inactive_partner?['疑似不再合作','identity-suspected']:null].filter(Boolean);return `<div class="identity-stack">${a.map(([t,k])=>`<span class="pill ${k}">${esc(t)}</span>`).join('')}</div>`}
function liveRow(c,selected=false){const country=c.country_resolved||c.country_api||'—',identity=[c.partnered_ugphone?'合作过博主':'未合作博主',c.ldcloud_creator?'LDCloud合作博主':'',c.redfinger_creator?'RedFinger合作博主':'',c.vsphone_creator?'VSPhone合作博主':'',c.suspected_inactive_partner?'疑似不再合作':''].filter(Boolean),search=`${c.channel_title||''} ${c.handle||''} ${country} ${c.channel_id||''} ${identity.join(' ')}`,channel=c.channel_url||`https://www.youtube.com/channel/${encodeURIComponent(c.channel_id)}`,mon=c.monitoring_enabled?'<span class="pill monitor-on">监控中</span>':'<span class="pill monitor-off">未监控</span>',biz=Number(c.business_metric_count||0)?`${c.gmv_total!=null?`<div><b>GMV $${Number(c.gmv_total).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}</b></div>`:'<div><b>GMV 未采集</b></div>'}${c.gmv_snapshot_at?`<div class="small">截至 ${esc(String(c.gmv_snapshot_at).slice(0,10))}</div>`:''}${c.new_users_total!=null?`<div class="small">拉新 ${Number(c.new_users_total).toLocaleString('zh-CN')}${c.new_users_snapshot_at?' · 截至 '+esc(String(c.new_users_snapshot_at).slice(0,10)):''}</div>`:''}`:'<span class="small">商业数据未采集（不代表0）</span>';return `<tr data-cid="${esc(c.channel_id)}" data-search="${esc(search)}"><td><input type="checkbox" class="ov-select creator-select" value="${esc(c.channel_id)}" ${selected?'checked':''}></td><td class="entity-cell"><a class="link-ext" target="_blank" rel="noopener" href="${esc(channel)}"><b>${esc(c.channel_title||c.channel_id)}</b></a><div class="small mono">${esc(c.handle||c.channel_id)}</div><button class="btn" data-inspect-creator="${esc(c.channel_id)}" data-creator-title="${esc(c.channel_title||c.channel_id)}" data-priority="${esc(priorityName[c.priority]||c.priority||'—')}" data-monitoring="${c.monitoring_enabled?'监控中':'未监控'}" data-sync-status="${esc(c.last_sync_status||'—')}" data-last-sync="${esc(c.last_synced_at||'—')}" data-next-sync="${esc(c.next_sync_at||'—')}" data-next-retry="${esc(c.next_retry_at||'—')}" data-failures="${fmt(c.consecutive_sync_failures)}" data-channel-data="${esc(c.channel_data_at||'—')}" data-video-metrics="${esc(c.video_metrics_at||'—')}" data-classification-data="${esc(c.classification_data_at||'—')}" data-contact-data="${esc(c.contact_scraped_at||'—')}">详情</button></td><td>${esc(country)}</td><td>${fmt(c.subscriber_count)}</td><td>${fmt(c.channel_view_count)}</td><td>${fmt(c.stored_videos)}</td><td class="identity-cell">${identityPills(c)}</td><td>${fmt(c.ugphone_video_count)}</td><td class="metric-cell">${biz}</td><td><div class="status-summary"><span class="pill priority-label">${esc(priorityName[c.priority]||c.priority||'—')}优先级</span>${mon}</div></td></tr>`}
async function refreshLiveData(includeMetrics=false){if(!interactive)return;const keep=new Set(selectedIds()),needMetrics=includeMetrics||active.some(x=>['constructed','ratio'].includes(normType(x.type)));const tasks=[post('/api/creators/facts',{}),post('/api/dashboard/stats',{})];if(needMetrics)tasks.push(post('/api/metrics/base',{}));const got=await Promise.all(tasks),f=got[0],stats=got[1],base=got[2];F.creators.splice(0,F.creators.length,...(f.creators||[]));byId.clear();for(const c of F.creators)byId.set(c.channel_id,c);if(base){B.cubes=base.cubes||{};B.brands=base.brands||B.brands;window.CDH_METRIC_BASE=B}window.CDH_CREATOR_FACTS=F;tbody.innerHTML=F.creators.map(c=>liveRow(c,keep.has(String(c.channel_id)))).join('')||'<tr><td colspan="10" class="empty">暂无博主</td></tr>';rows=[...tbody.querySelectorAll('tr[data-cid]')];const m=document.getElementById('overviewMonitoredCount'),v=document.getElementById('overviewVideoCount');if(m)m.textContent=fmt(stats.monitored);if(v)v.textContent=fmt(stats.videos);render()}

function conditionRow(c={},i=0){const d=document.createElement('div');d.className='condition-row';d.innerHTML=(i===0?'<span class="small">起始</span>':'<select class="f-join"><option>AND</option><option>OR</option><option>NOT</option></select>')+'<select class="f-type"><option value="creator_fact">博主客观数据</option><option value="creator_label">博主标签</option><option value="constructed">构建指标</option><option value="ratio">比值指标</option><option value="geography">地理位置</option></select><select class="f-key"></select><select class="f-op"></select><input class="f-value" type="number" step="any" placeholder="筛选值"><button class="btn danger">×</button>';const t=d.querySelector('.f-type'),key=d.querySelector('.f-key'),op=d.querySelector('.f-op'),val=d.querySelector('.f-value');t.value=normType(c.type||'creator_fact');
function fillCountry(selected=''){const g=key.value,arr=g?(GEO.countries||[]).filter(x=>x.group===g):[];op.innerHTML=(g?'<option value="">全部该区域</option>':'<option value="">请先选择区域</option>')+arr.map(x=>`<option value="${x.code}">${x.name_zh} (${x.code})</option>`).join('');if(selected&&arr.some(x=>x.code===selected))op.value=selected}
function fill(w='',country=''){if(t.value==='geography'){key.innerHTML='<option value="">选择区域</option>'+(GEO.groups||[]).map(g=>`<option value="${g.id}">${g.name}</option>`).join('');if(w&&(GEO.groups||[]).some(g=>g.id===w))key.value=w;fillCountry(country);key.onchange=()=>fillCountry('');val.style.display='none';return}key.onchange=null;const entries=overviewFieldEntries(t.value);if(entries.length&&window.CDHFieldRegistry)CDHFieldRegistry.optionGroups(key,entries,w,'请选择字段');else key.innerHTML='<option value="">暂无该类指标</option>';if(w&&entries.some(x=>x.id===w))key.value=w;mountPicker(key,()=>overviewFieldEntries(t.value),`creator-library-filter-${t.value}`,'选择字段');if(t.value==='creator_label'){op.innerHTML='<option value="truthy">存在 / 是</option><option value="falsy">不存在 / 否</option>';op.style.display='';val.style.display='none'}else{op.innerHTML='<option value="gte">≥</option><option value="gt">&gt;</option><option value="lte">≤</option><option value="lt">&lt;</option><option value="eq">=</option><option value="neq">≠</option>';op.style.display='';val.style.display=''}}
fill(c.key||'',c.country||'');t.onchange=()=>fill();if(c.join&&d.querySelector('.f-join'))d.querySelector('.f-join').value=c.join;if(t.value!=='geography'&&c.op)op.value=c.op;if(!['geography','creator_label'].includes(t.value))val.value=c.value??'';d.querySelector('button').onclick=()=>{d.remove();renumber()};return d}
function add(c={}){box.appendChild(conditionRow(c,box.children.length))}function renumber(){const a=read(true);box.innerHTML='';a.forEach(add);if(!a.length)add()}
function read(includeBlank=false){return [...box.children].map((d,i)=>{const type=d.querySelector('.f-type').value,key=d.querySelector('.f-key').value,join=i===0?'':(d.querySelector('.f-join')?.value||'AND');if(type==='geography')return {join,type,key,country:d.querySelector('.f-op').value,op:'geo',value:''};if(type==='creator_label')return {join,type,key,op:d.querySelector('.f-op').value||'truthy',value:''};return {join,type,key,op:d.querySelector('.f-op').value,value:d.querySelector('.f-value').value}}).filter(x=>includeBlank?x.key:(x.key&&(x.type==='creator_label'||x.type==='geography'||x.value!=='')))}
function sortValue(c,key){if(key==='channel_title')return c.channel_title||c.handle||c.channel_id||'';if(key==='country')return c.country_resolved||c.country_api||'';if(key==='latest_upload')return c.latest_upload||'';return Number(c[key]??0)}
function metricLabel(type,key){if(type==='geography')return '地理位置';const hit=options(type).find(x=>x[0]===key);return hit?hit[1]:key}
function syncExplainColumns(){const table=document.getElementById('overviewTable'),head=document.getElementById('overviewHead');if(!table||!head)return;table.querySelectorAll('.dynamic-explain').forEach(x=>x.remove());const baseFields=new Set();head.querySelectorAll('th').forEach(th=>String(th.dataset.field||'').split(/[|,\s]+/).filter(Boolean).forEach(x=>baseFields.add(x)));const specs=[],highlight=[],seen=new Set();for(const c of active){const type=normType(c.type),field=type==='geography'?'geography':type==='creator_label'?'creator_label':c.key;if(field)highlight.push(field);if(type==='geography'||type==='creator_label'||!c.key||baseFields.has(c.key))continue;const token=`${type}:${c.key}`;if(!seen.has(token)){seen.add(token);specs.push(c)}}const sk=sort.value;if(sk&&!baseFields.has(sk)&&!['channel_title','country'].includes(sk)){const token=`creator_fact:${sk}`;if(!seen.has(token))specs.push({type:'creator_fact',key:sk})}for(const c of specs.slice(0,2)){const th=document.createElement('th');th.className='dynamic-explain filter-sort-active';th.dataset.field=c.key;th.textContent=metricLabel(c.type,c.key);head.appendChild(th)}for(const r of rows){const c=byId.get(r.dataset.cid);if(!c)continue;for(const sp of specs.slice(0,2)){const td=document.createElement('td');td.className='dynamic-explain';const v=sp.key==='latest_upload'?(c.latest_upload||'—'):value(c,sp.type,sp.key);td.textContent=v==null?'—':(typeof v==='number'?v.toLocaleString('zh-CN',{maximumFractionDigits:4}):String(v));r.appendChild(td)}}highlight.unshift(sk);window.CDHTableTools?.highlightHeaders(table,highlight)}

function go(p){page=p;render()}
function filteredRows(){const qq=(q.value||'').toLowerCase(),filtered=[];for(const r of rows){const c=byId.get(r.dataset.cid);if(!c)continue;let ok=!qq||(r.dataset.search||'').toLowerCase().includes(qq);if(ok)ok=chain(c,active);if(ok)filtered.push({r,c})}return filtered}
function clearOvSelection(){tbody.querySelectorAll('.ov-select').forEach(x=>x.checked=false);updateSelectionStatus()}
function updateSelectionStatus(){const n=selectedIds().length,st=document.getElementById('ovSelectionStatus');if(st)st.textContent=`已选择 ${n} 条`;const cur=visibleCheckboxes(),toggle=document.getElementById('ovSelectVisible');if(toggle){toggle.checked=!!cur.length&&cur.every(x=>x.checked);toggle.indeterminate=cur.some(x=>x.checked)&&!toggle.checked}}
function render(){syncExplainColumns();const filtered=filteredRows();const key=sort.value,desc=dir.value==='desc';filtered.sort((a,b)=>{let av=sortValue(a.c,key),bv=sortValue(b.c,key),z=typeof av==='number'&&typeof bv==='number'?av-bv:String(av).localeCompare(String(bv),'zh-CN',{numeric:true,sensitivity:'base'});return desc?-z:z});const pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.max(1,Math.min(pages,page));const start=(page-1)*size,shown=new Set(filtered.slice(start,start+size).map(x=>x.r));rows.forEach(r=>r.style.display=shown.has(r)?'':'none');filtered.forEach(x=>tbody.appendChild(x.r));summary.textContent=`共 ${filtered.length} 条 · 当前显示 ${filtered.length?start+1:0}-${Math.min(start+size,filtered.length)}`;if(filterStatus)filterStatus.textContent=active.length?`已应用 ${active.length} 个筛选条件 · 命中 ${filtered.length} 条`:'';CDHTableTools.renderPager({page,pages,go,firstId:'ovFirst',prevId:'ovPrev',nextId:'ovNext',lastId:'ovLast',buttonsId:'ovPageButtons',inputId:'ovPageInput',jumpId:'ovJump',pageInfoId:'ovPageInfo'});updateSelectionStatus()}
function exportRows(){const qq=(q.value||'').toLowerCase(),a=[];for(const r of rows){const c=byId.get(r.dataset.cid);if(!c)continue;let ok=!qq||(r.dataset.search||'').toLowerCase().includes(qq);if(ok)ok=chain(c,active);if(ok)a.push(c)}const key=sort.value,desc=dir.value==='desc';a.sort((x,y)=>{const av=sortValue(x,key),bv=sortValue(y,key),z=typeof av==='number'&&typeof bv==='number'?av-bv:String(av).localeCompare(String(bv),'zh-CN',{numeric:true,sensitivity:'base'});return desc?-z:z});return a.map(c=>({channel_title:c.channel_title||'',channel_id:c.channel_id,handle:c.handle||'',country:c.country_resolved||c.country_api||'',subscriber_count:c.subscriber_count,channel_view_count:c.channel_view_count,stored_videos:c.stored_videos,latest_upload:c.latest_upload||'',identity:[c.partnered_ugphone?'合作过博主':'未合作博主',c.ldcloud_creator?'LDCloud合作博主':'',c.redfinger_creator?'RedFinger合作博主':'',c.vsphone_creator?'VSPhone合作博主':'',c.suspected_inactive_partner?'疑似不再合作':''].filter(Boolean).join('；'),ugphone_video_count:c.ugphone_video_count,ldcloud_video_count:c.ldcloud_video_count,redfinger_video_count:c.redfinger_video_count,vsphone_video_count:c.vsphone_video_count,gmv_total:c.gmv_total,gmv_snapshot_at:c.gmv_snapshot_at||'',new_users_total:c.new_users_total,new_users_snapshot_at:c.new_users_snapshot_at||'',gmv_currency:c.gmv_total!=null?'USD':'',last_synced_at:c.last_synced_at||''}))}
function selectedIds(){return [...tbody.querySelectorAll('.ov-select:checked')].map(x=>x.value)}
function visibleCheckboxes(){return [...tbody.querySelectorAll('tr')].filter(r=>r.style.display!=='none').map(r=>r.querySelector('.ov-select')).filter(Boolean)}
async function batch(action){const ids=selectedIds(),st=document.getElementById('ovBatchStatus');if(!ids.length)return alert('请先勾选博主');let value='';if(action==='priority')value=document.getElementById('ovBatchPriority').value;if(action==='tag')value=document.getElementById('ovBatchTag').value.trim();if(action==='tag'&&!value)return alert('请输入标签');try{st.textContent='正在批量处理…';const payload={channel_ids:ids,action,value};const x=window.CDHJobs?await CDHJobs.run('creator_batch',payload):await post('/api/creators/batch',payload);st.textContent=`已处理 ${x.processed}/${x.requested}${x.errors?.length?` · ${x.errors.length} 个错误`:''}`;if(x.errors?.length)console.warn(x.errors);markDataChanged();await refreshLiveData()}catch(e){st.textContent=e.message}}
function reset(){page=1;render()}q.oninput=()=>{clearOvSelection();reset()};sort.onchange=reset;dir.onchange=reset;psOk.onclick=()=>{size=CDHTableTools.pageSize(ps,size);ps.value=String(size);reset()};document.getElementById('ovAddFilter').onclick=()=>add();document.getElementById('ovApplyFilter').onclick=()=>{clearOvSelection();active=read();page=1;if(interactive&&active.some(x=>['constructed','ratio'].includes(normType(x.type))))refreshLiveData(true).catch(e=>{if(filterStatus)filterStatus.textContent=e.message});else render()};document.getElementById('ovClearFilter').onclick=()=>{clearOvSelection();active=[];q.value='';box.innerHTML='';add();reset()};document.getElementById('ovSelectVisible').onchange=e=>{visibleCheckboxes().forEach(x=>x.checked=e.target.checked);updateSelectionStatus()};document.getElementById('ovSelectAllResults').onclick=()=>{filteredRows().forEach(x=>{const c=x.r.querySelector('.ov-select');if(c)c.checked=true});updateSelectionStatus()};document.getElementById('ovClearSelection').onclick=clearOvSelection;tbody.addEventListener('change',e=>{if(e.target.matches('.ov-select'))updateSelectionStatus()});document.querySelectorAll('[data-ov-batch]').forEach(b=>b.onclick=()=>batch(b.dataset.ovBatch));document.getElementById('ovExport').onclick=()=>CDHExport.rows('creator_library.xlsx','Creator Library',[{key:'channel_title',label:'博主'},{key:'channel_id',label:'Channel ID'},{key:'handle',label:'Handle'},{key:'country',label:'国家/地区'},{key:'subscriber_count',label:'订阅数'},{key:'channel_view_count',label:'频道累计播放量'},{key:'stored_videos',label:'本地视频数'},{key:'latest_upload',label:'最近发布'},{key:'identity',label:'身份标签'},{key:'ugphone_video_count',label:'UgPhone视频数'},{key:'ldcloud_video_count',label:'LDCloud视频数'},{key:'redfinger_video_count',label:'RedFinger视频数'},{key:'vsphone_video_count',label:'VSPhone视频数'},{key:'gmv_total',label:'GMV（USD，最新累计快照）'},{key:'gmv_snapshot_at',label:'GMV快照时间'},{key:'gmv_currency',label:'GMV展示币种'},{key:'new_users_total',label:'拉新（最新累计快照）'},{key:'new_users_snapshot_at',label:'拉新快照时间'},{key:'last_synced_at',label:'最近同步'}],exportRows()).catch(e=>alert(e.message));if(window.CDHSavedViews)CDHSavedViews.attach({pageKey:'creator_library',selectId:'ovSavedView',saveId:'ovSaveView',deleteId:'ovDeleteView',statusId:'ovSavedViewStatus',getConfig:()=>({search:q.value,sort:sort.value,dir:dir.value,page_size:size,conditions:active}),applyConfig:c=>{q.value=c.search||'';if(c.sort&&[...sort.options].some(o=>o.value===c.sort))sort.value=c.sort;sort.nextElementSibling?._fieldPicker?.refresh();if(c.dir)dir.value=c.dir;size=Math.max(1,Math.min(5000,Number(c.page_size||30)));ps.value=String(size);active=Array.isArray(c.conditions)?c.conditions:[];box.innerHTML='';active.forEach(add);if(!active.length)add();page=1;render()}});add();render();fetch('/api/ping').then(r=>r.ok?r.json():null).then(async x=>{interactive=!!x;if(interactive)await refreshLiveData()}).catch(()=>interactive=false);window.addEventListener('focus',()=>{if(interactive)refreshLiveData().catch(()=>{})});window.addEventListener('storage',e=>{if(interactive&&e.key==='cdh-data-revision')refreshLiveData().catch(()=>{})});
})();
/* CDH V3.10.3 UI PATCH START */
(()=>{
'use strict';
const PATCH='3.10.2';
if(window.__CDH_V3103_UI_PATCH__) return;
window.__CDH_V3103_UI_PATCH__=PATCH;

const CSS=`
/* V3.10.3 · unified three-level condition UI across all Creator filter/rule surfaces */
.metric-builder.v3103-grid{
  display:grid!important;
  grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;
  grid-template-rows:auto auto!important;
  column-gap:20px!important;
  row-gap:16px!important;
  align-items:stretch!important;
}
.metric-builder.v3103-grid>div{display:contents!important}
.metric-builder.v3103-grid #metrics-builder{grid-column:1;grid-row:1;margin:0!important}
.metric-builder.v3103-grid #metrics-saved{grid-column:2;grid-row:1;margin:0!important}
.metric-builder.v3103-grid #metrics-rule-builder{grid-column:1;grid-row:2;margin:0!important}
.metric-builder.v3103-grid #metrics-rules{grid-column:2;grid-row:2;margin:0!important}

/* Reuse the native list pagination. V3.10.1's second pager must never remain visible. */
.v3101-list-pager{display:none!important}
#metrics-saved.v3103-scroll-panel,#metrics-rules.v3103-scroll-panel{
  display:flex!important;
  flex-direction:column!important;
  min-height:0!important;
  overflow:hidden!important;
  box-sizing:border-box!important;
}
#metrics-saved.v3103-scroll-panel #metricList,
#metrics-rules.v3103-scroll-panel #ruleList{
  flex:1 1 auto!important;
  min-height:0!important;
  overflow-y:auto!important;
  overflow-x:hidden!important;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
  padding-right:4px;
  margin-bottom:0!important;
}
#metrics-saved.v3103-scroll-panel #metricList::-webkit-scrollbar,
#metrics-rules.v3103-scroll-panel #ruleList::-webkit-scrollbar{width:9px}
#metrics-saved.v3103-scroll-panel #metricList::-webkit-scrollbar-thumb,
#metrics-rules.v3103-scroll-panel #ruleList::-webkit-scrollbar-thumb{background:rgba(100,116,139,.38);border-radius:999px}

/* One condition = one row, shared by Rule Builder and Creator Library result filters. */
#ruleConditions.v3103-condition-list,
#resultFilterConditions.v3103-condition-list,
#ovFilterConditions.v3103-condition-list{
  display:flex!important;
  flex-direction:column!important;
  gap:10px!important;
}
#ruleConditions .condition-row.v3103-condition-row,
#resultFilterConditions .condition-row.v3103-condition-row,
#ovFilterConditions .condition-row.v3103-condition-row{
  width:100%!important;
  max-width:none!important;
  display:block!important;
  margin:0!important;
  padding:0 0 2px 0!important;
  overflow-x:auto;
  overflow-y:hidden;
}
#ruleConditions .v3103-condition-grid,
#resultFilterConditions .v3103-condition-grid,
#ovFilterConditions .v3103-condition-grid{
  width:100%;
  display:grid!important;
  align-items:center;
}
#ruleConditions .v3103-condition-grid{
  min-width:680px;
  grid-template-columns:56px minmax(100px,.78fr) minmax(112px,.9fr) minmax(138px,1.16fr) 96px minmax(104px,.74fr) 38px;
  gap:8px;
}
#ruleConditions .v3103-condition-grid.v3103-no-value{
  min-width:570px;
  grid-template-columns:56px minmax(100px,.78fr) minmax(112px,.9fr) minmax(138px,1.16fr) 106px 38px;
}
#resultFilterConditions .v3103-condition-grid,
#ovFilterConditions .v3103-condition-grid{
  min-width:920px;
  grid-template-columns:72px minmax(140px,.8fr) minmax(160px,.95fr) minmax(210px,1.25fr) 112px minmax(140px,.85fr) 40px;
  gap:10px;
}
#resultFilterConditions .v3103-condition-grid.v3103-no-value,
#ovFilterConditions .v3103-condition-grid.v3103-no-value{
  min-width:760px;
  grid-template-columns:72px minmax(140px,.8fr) minmax(160px,.95fr) minmax(210px,1.25fr) 122px 40px;
}
#ruleConditions .v3103-condition-grid>*,
#resultFilterConditions .v3103-condition-grid>*,
#ovFilterConditions .v3103-condition-grid>*{min-width:0!important;max-width:none!important;margin:0!important}
#ruleConditions .v3103-condition-grid select,
#ruleConditions .v3103-condition-grid input,
#resultFilterConditions .v3103-condition-grid select,
#resultFilterConditions .v3103-condition-grid input,
#ovFilterConditions .v3103-condition-grid select,
#ovFilterConditions .v3103-condition-grid input{
  width:100%!important;
  height:42px!important;
  box-sizing:border-box!important;
}
.v3103-tier3-combo{position:relative;width:100%;min-width:0}
.v3103-tier3-native{display:none!important}
.v3103-tier3-input{padding-right:36px!important;text-overflow:ellipsis}
.v3103-tier3-picker{
  position:absolute!important;right:1px!important;top:1px!important;bottom:1px!important;
  width:34px!important;min-width:34px!important;height:40px!important;
  padding:0!important;margin:0!important;border:0!important;
  border-left:1px solid rgba(148,163,184,.26)!important;
  background:transparent!important;color:#64748b!important;
  display:flex!important;align-items:center!important;justify-content:center!important;cursor:pointer;
}
.v3103-lead{display:flex!important;align-items:center!important;min-height:42px;color:#64748b;white-space:nowrap}
.v3103-delete{
  width:38px!important;min-width:38px!important;height:42px!important;padding:0!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
}
.v3103-hidden-legacy,.v3103-hidden-search{display:none!important}
#metrics-results .builder-panel>.inline.v3103-result-toolbar{margin-top:12px!important;flex-wrap:wrap!important;gap:10px!important;align-items:center!important}

/* Main Creator Library: the deprecated stacked selector is fully retired too. */
#ovFilterConditions{width:100%!important}
#ovFilterConditions .condition-row.v3103-condition-row{overflow-x:auto!important}
#ovFilterConditions .v3103-hidden-legacy,
#ovFilterConditions .v3103-hidden-search{display:none!important}

@media(max-width:1050px){
  .metric-builder.v3103-grid{display:block!important}
  .metric-builder.v3103-grid>div{display:block!important}
  .metric-builder.v3103-grid #metrics-builder,
  .metric-builder.v3103-grid #metrics-saved,
  .metric-builder.v3103-grid #metrics-rule-builder,
  .metric-builder.v3103-grid #metrics-rules{height:auto!important;margin-top:16px!important}
  .metric-builder.v3103-grid #metrics-builder{margin-top:0!important}
  #metrics-saved.v3103-scroll-panel,#metrics-rules.v3103-scroll-panel{max-height:720px}
  #metrics-saved.v3103-scroll-panel #metricList,#metrics-rules.v3103-scroll-panel #ruleList{max-height:560px}
}
`;

function injectCss(){
  if(document.getElementById('cdh-v3103-ui-style'))return;
  const old=document.getElementById('cdh-v3101-ui-style');if(old)old.remove();
  const s=document.createElement('style');s.id='cdh-v3103-ui-style';s.textContent=CSS;document.head.appendChild(s);
}

let layoutBusy=false, pageSizeBusy=false;
function scheduleSyncHeights(){if(layoutBusy)return;layoutBusy=true;requestAnimationFrame(()=>{layoutBusy=false;syncHeights()})}
function syncHeights(){
  const root=document.querySelector('.metric-builder');
  const mb=document.getElementById('metrics-builder'),ms=document.getElementById('metrics-saved'),rb=document.getElementById('metrics-rule-builder'),rs=document.getElementById('metrics-rules');
  if(!root||!mb||!ms||!rb||!rs)return;
  root.classList.add('v3103-grid');ms.classList.add('v3103-scroll-panel');rs.classList.add('v3103-scroll-panel');
  if(window.matchMedia('(max-width:1050px)').matches){ms.style.height='';rs.style.height='';return}
  ms.style.height='';rs.style.height='';
  const h1=Math.ceil(mb.getBoundingClientRect().height),h2=Math.ceil(rb.getBoundingClientRect().height);
  if(h1>0)ms.style.height=`${h1}px`;if(h2>0)rs.style.height=`${h2}px`;
}

function isBefore(a,b){return !!(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING)}
function nativePageSizeControl(panel,list){
  if(!panel||!list)return null;
  const inputs=[...panel.querySelectorAll('input[type="number"]')].filter(i=>isBefore(i,list));
  if(!inputs.length)return null;
  let input=inputs.find(i=>{
    const p=i.parentElement,pp=p?.parentElement;
    const t=((p?.innerText||'')+' '+(pp?.innerText||'')).replace(/\s+/g,' ');
    return t.includes('每页')&&!t.includes('跳转到');
  })||inputs[0];
  const buttons=[...panel.querySelectorAll('button')].filter(b=>isBefore(b,list)&&(b.textContent||'').trim()==='确定');
  let button=buttons.find(b=>b.parentElement===input.parentElement)||buttons.at(-1)||null;
  return {input,button};
}
function forceTenPerPage(panelId,listId){
  const panel=document.getElementById(panelId),list=document.getElementById(listId);if(!panel||!list)return;
  panel.classList.add('v3103-scroll-panel');
  panel.querySelectorAll('.v3101-list-pager').forEach(x=>x.remove());
  const ctl=nativePageSizeControl(panel,list);if(!ctl)return;
  const old=String(ctl.input.value||'').trim();
  if(old==='10')return;
  ctl.input.value='10';ctl.input.setAttribute('value','10');
  ctl.input.dispatchEvent(new Event('input',{bubbles:true}));ctl.input.dispatchEvent(new Event('change',{bubbles:true}));
  if(ctl.button&&!ctl.button.disabled)setTimeout(()=>{try{ctl.button.click()}catch(e){}},0);
}
function configureNativePagination(){
  if(pageSizeBusy)return;pageSizeBusy=true;
  try{forceTenPerPage('metrics-saved','metricList');forceTenPerPage('metrics-rules','ruleList')}
  finally{setTimeout(()=>{pageSizeBusy=false},50)}
  scheduleSyncHeights();
}

function optionTexts(sel){return [...sel.options].map(o=>(o.textContent||'').trim()).filter(Boolean)}
function isJoinSelect(sel){
  if(sel.classList.contains('c-join'))return true;
  const s=new Set(optionTexts(sel).map(x=>x.toUpperCase()));return s.has('AND')&&s.has('OR')&&s.has('NOT');
}
function isOperatorSelect(sel){
  if(sel.classList.contains('c-op'))return true;
  const t=optionTexts(sel).join(' ');
  return /≥|≤|≠|存在\s*\/\s*是|不存在\s*\/\s*否/.test(t)||(/^\s*[><=≠≤≥]/.test(t)&&optionTexts(sel).length<=12);
}
function isDeleteButton(b){const t=(b.textContent||'').trim();return t==='×'||t==='✕'||t==='✖'||b.classList.contains('danger')}
function isSearchControl(el){
  const t=(el.textContent||el.placeholder||'').trim();
  return t==='搜索'||t==='搜索指标'||/search/i.test(el.id||'')||/search/i.test(el.className||'');
}
function installSearchableTier3(native,grid){
  if(!native)return null;
  let wrap=native.closest('.v3103-tier3-combo');if(wrap){grid.appendChild(wrap);return wrap}
  wrap=document.createElement('div');wrap.className='v3103-tier3-combo v3103-l3';
  const listId='v3103-tier3-'+Math.random().toString(36).slice(2,10);
  const input=document.createElement('input');input.type='text';input.className='v3103-tier3-input';input.setAttribute('list',listId);input.setAttribute('autocomplete','off');input.placeholder='选择 / 搜索三级指标';
  const dl=document.createElement('datalist');dl.id=listId;
  const picker=document.createElement('button');picker.type='button';picker.className='v3103-tier3-picker';picker.title='展开 / 搜索三级指标';picker.setAttribute('aria-label','展开 / 搜索三级指标');picker.textContent='⌄';
  native.classList.add('v3103-tier3-native');wrap.appendChild(native);wrap.appendChild(input);wrap.appendChild(dl);wrap.appendChild(picker);grid.appendChild(wrap);
  const options=()=>[...native.options].filter(o=>!o.disabled&&String(o.value||'')!=='');
  const labelOf=()=>native.selectedOptions?.[0]?.textContent?.trim()||'';
  const sync=()=>{const opts=options();dl.innerHTML='';opts.forEach(o=>{const x=document.createElement('option');x.value=(o.textContent||'').trim();dl.appendChild(x)});input.value=labelOf();input.disabled=native.disabled||opts.length===0;picker.disabled=input.disabled};
  const commit=()=>{const typed=input.value.trim(),opts=options();const hit=opts.find(o=>(o.textContent||'').trim()===typed)||opts.find(o=>(o.textContent||'').trim().toLowerCase()===typed.toLowerCase());if(!hit){input.value=labelOf();return}if(native.value!==hit.value){native.value=hit.value;native.dispatchEvent(new Event('input',{bubbles:true}));native.dispatchEvent(new Event('change',{bubbles:true}))}input.value=(hit.textContent||'').trim()};
  input.addEventListener('change',commit);input.addEventListener('blur',()=>setTimeout(commit,80));native.addEventListener('change',sync);
  picker.addEventListener('click',()=>{input.focus();try{if(typeof input.showPicker==='function')input.showPicker()}catch(e){}});
  new MutationObserver(sync).observe(native,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});sync();return wrap;
}
function findLead(row,join){if(join)return join;return [...row.querySelectorAll('span,div,label')].find(x=>x.children.length===0&&(x.textContent||'').trim()==='起始')||null}
function compactConditionRow(row){
  if(!row||!row.classList?.contains('condition-row'))return;
  let grid=row.querySelector(':scope > .v3103-condition-grid');
  if(row.dataset.v3103Compacted==='1'&&grid){syncValueMode(row,grid);return}
  const selects=[...row.querySelectorAll('select')];if(!selects.length)return;
  const join=selects.find(isJoinSelect)||null,op=selects.find(s=>s!==join&&isOperatorSelect(s))||null;
  const candidates=selects.filter(s=>s!==join&&s!==op);if(candidates.length<3)return;
  const levels=candidates.slice(-3),legacy=candidates.slice(0,-3);legacy.forEach(x=>x.classList.add('v3103-hidden-legacy'));
  const buttons=[...row.querySelectorAll('button')],del=buttons.find(isDeleteButton)||buttons.at(-1)||null;
  buttons.filter(b=>b!==del&&isSearchControl(b)).forEach(b=>b.classList.add('v3103-hidden-search'));
  [...row.querySelectorAll('input')].filter(isSearchControl).forEach(x=>x.classList.add('v3103-hidden-search'));
  const value=[...row.querySelectorAll('input')].find(x=>!x.classList.contains('v3103-hidden-search')&&(x.classList.contains('c-value')||['number','text'].includes((x.type||'text').toLowerCase())))||null;
  const lead=findLead(row,join);
  if(!grid){grid=document.createElement('div');grid.className='v3103-condition-grid';row.prepend(grid)}
  const move=(el,cls)=>{if(!el)return;el.classList.add(cls);grid.appendChild(el)};
  move(lead,'v3103-lead');move(levels[0],'v3103-l1');move(levels[1],'v3103-l2');installSearchableTier3(levels[2],grid);move(op,'v3103-op');move(value,'v3103-value');move(del,'v3103-delete');
  row.classList.add('v3103-condition-row');row.dataset.v3103Compacted='1';
  const sync=()=>requestAnimationFrame(()=>syncValueMode(row,grid));
  selects.forEach(s=>s.addEventListener('change',sync));
  new MutationObserver(sync).observe(row,{attributes:true,subtree:true,attributeFilter:['style','class']});
  syncValueMode(row,grid);
}
function syncValueMode(row,grid){
  const value=row.querySelector('.v3103-value');
  const hidden=!value||value.style.display==='none'||getComputedStyle(value).display==='none';
  grid.classList.toggle('v3103-no-value',hidden);
}
function compactConditionBox(id){
  const box=document.getElementById(id);if(!box)return;box.classList.add('v3103-condition-list');[...box.children].forEach(compactConditionRow);
}
function compactAllConditions(){
  compactConditionBox('ruleConditions');compactConditionBox('resultFilterConditions');compactConditionBox('ovFilterConditions');
  ['ruleConditions','resultFilterConditions','ovFilterConditions'].forEach(id=>{
    const box=document.getElementById(id);if(!box)return;
    box.querySelectorAll('button').forEach(b=>{if((b.textContent||'').trim()==='搜索'&&b.closest('.condition-row'))b.classList.add('v3103-hidden-search')});
  });
  const rbox=document.getElementById('resultFilterConditions'),panel=rbox?.closest('.builder-panel');
  if(panel)[...panel.children].forEach(x=>{if(x.classList?.contains('inline')&&x!==rbox)x.classList.add('v3103-result-toolbar')});
}

function observe(){
  const metricList=document.getElementById('metricList'),ruleList=document.getElementById('ruleList');
  if(metricList&&!metricList.__v3103Observed){metricList.__v3103Observed=true;new MutationObserver(()=>{configureNativePagination();scheduleSyncHeights();setTimeout(()=>{metricList.scrollTop=0},0)}).observe(metricList,{childList:true})}
  if(ruleList&&!ruleList.__v3103Observed){ruleList.__v3103Observed=true;new MutationObserver(()=>{configureNativePagination();scheduleSyncHeights();setTimeout(()=>{ruleList.scrollTop=0},0)}).observe(ruleList,{childList:true})}
  ['ruleConditions','resultFilterConditions','ovFilterConditions'].forEach(id=>{
    const box=document.getElementById(id);if(box&&!box.__v3103Observed){box.__v3103Observed=true;new MutationObserver(()=>requestAnimationFrame(compactAllConditions)).observe(box,{childList:true,subtree:true})}
  });
}

function boot(){
  injectCss();
  document.querySelectorAll('.v3101-list-pager').forEach(x=>x.remove());
  const root=document.querySelector('.metric-builder');if(root)root.classList.add('v3103-grid');
  compactAllConditions();observe();configureNativePagination();syncHeights();
  window.addEventListener('resize',scheduleSyncHeights,{passive:true});
  [80,250,700,1500,3000].forEach(ms=>setTimeout(()=>{compactAllConditions();observe();configureNativePagination();syncHeights()},ms));
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
/* CDH V3.10.3 UI PATCH END */
