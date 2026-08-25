(()=>{
'use strict';
const LS_RECENT='cdh-field-cascade-recent-v2', LS_FAV='cdh-field-cascade-favorites-v2';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]||c));
const load=(k,d)=>{try{return JSON.parse(localStorage.getItem(k)||JSON.stringify(d))}catch(_){return d}};
const save=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v))}catch(_){}};
const L1=[['objective','客观数据',10],['labels','博主标签',20],['constructed','构建指标',30],['ratio','比值指标',40]];
const L1N=Object.fromEntries(L1.map(x=>[x[0],x[1]])), L1O=Object.fromEntries(L1.map(x=>[x[0],x[2]]));
const L2N={
 basic_info:'基础信息',geography:'地理位置',channel_scale:'频道规模',content_brand:'内容与品牌',content_performance:'内容表现',business:'商业数据',discovery_ai:'Discovery / AI',data_health:'数据健康',video_fact:'视频客观数据',
 partnership:'合作身份',competitor_partnership:'竞品合作',workflow:'工作流',monitoring:'监控标签',manual:'人工标签'
};
const creatorL2=k=>{
 if(['channel_title','channel_id','handle'].includes(k))return 'basic_info';
 if(['country','country_resolved','country_api','language','creator_language'].includes(k))return 'geography';
 if(['subscriber_count','channel_view_count','channel_video_count','stored_videos'].includes(k))return 'channel_scale';
 if(['gmv_total','new_users_total','orders_total','revenue_total','commission_total','cost_total'].includes(k))return 'business';
 if(['discovery_score','discovery_pre_score','query_coverage','objective_fit_score','topic_affinity_score','use_case_continuity_score','brand_safety_score'].includes(k))return 'discovery_ai';
 if(['last_synced_at','latest_upload','monitoring_enabled','priority','last_sync_status','availability_status','sync_health','failure_count'].includes(k))return 'data_health';
 if(/video_count$/.test(k)||['ugphone_video_count','competitor_video_count','daily_video_count'].includes(k))return 'content_brand';
 return 'basic_info';
};
const labelL2=k=>{
 if(['partnered_ugphone','unpartnered_ugphone','suspected_inactive_partner'].includes(k))return 'partnership';
 if(['ldcloud_creator','redfinger_creator','vsphone_creator','ugphone_and_competitor'].includes(k))return 'competitor_partnership';
 if(String(k).startsWith('workflow_')||k==='workflow_status')return 'workflow';
 if(String(k).startsWith('monitor_')||['monitoring_enabled','priority'].includes(k))return 'monitoring';
 return 'manual';
};
function normalize(e){
 if(!e)return e;
 if(e.level1&&e.level2)return e;
 let l1='objective',l2='basic_info';
 if(e.kind==='creator_label'){l1='labels';l2=labelL2(e.key)}
 else if(e.kind==='ratio'||e.level1==='ratio'){l1='ratio';l2=e.group_label||e.group||'未分组'}
 else if(e.kind==='constructed'||String(e.id||'').startsWith('metric:')){l1=e.kind==='ratio'?'ratio':'constructed';l2=e.group_label||e.group||'未分组'}
 else if(e.kind==='video_fact'){l1='objective';l2='video_fact'}
 else {l1='objective';l2=creatorL2(e.key||e.id)}
 return {...e,level1:l1,level2:l2,level2_label:e.level2_label||L2N[l2]||l2};
}
function build(base={},metrics=[]){
 const out=[];const push=x=>{x=normalize(x);if(x&&x.id&&!out.some(y=>y.id===x.id))out.push(x)};
 push({id:'channel_title',key:'channel_title',kind:'creator_fact',label:'博主名称',level1:'objective',level2:'basic_info',grain:'creator',type:'text',filterable:false,sortable:true});
 push({id:'country',key:'country',kind:'geography',label:'国家',level1:'objective',level2:'geography',grain:'creator',type:'text',filterable:true,sortable:true});
 for(const [k,label] of Object.entries(base.creator_fact_fields||base.objective_fields||{}))push({id:k,key:k,kind:'creator_fact',label,level1:'objective',level2:creatorL2(k),grain:'creator',type:'number',filterable:true,sortable:true,ratio:true});
 push({id:'latest_upload',key:'latest_upload',kind:'creator_fact',label:'最近发布',level1:'objective',level2:'data_health',grain:'creator',type:'date',filterable:false,sortable:true});
 push({id:'last_synced_at',key:'last_synced_at',kind:'creator_fact',label:'最近同步',level1:'objective',level2:'data_health',grain:'creator',type:'date',filterable:false,sortable:true});
 for(const [k,label] of Object.entries(base.creator_labels||base.aggregate_labels||{}))push({id:`label:${k}`,key:k,kind:'creator_label',label,level1:'labels',level2:labelL2(k),grain:'creator',type:'boolean',filterable:true,sortable:false});
 for(const [k,label] of Object.entries(base.video_fact_fields||base.video_objectives||{}))push({id:`video:${k}`,key:k,kind:'video_fact',label,level1:'objective',level2:'video_fact',grain:'video',type:'number',filterable:false,sortable:false});
 for(const m of metrics||[]){if(!m||m.internal||!m.id)continue;const typ=m.type==='ratio'?'ratio':'constructed';const group=String(m.group||'').trim()||'未分组';push({id:`metric:${m.id}`,key:m.id,kind:typ,label:m.name||m.id,level1:typ,level2:group,level2_label:group,grain:'creator',type:'number',filterable:true,sortable:!!m.visible,ratio:typ==='constructed'})}
 return out;
}
const l1Label=e=>L1N[e.level1]||e.level1||'客观数据';
const l2Label=e=>e.level2_label||L2N[e.level2]||e.level2||'未分组';
function sortEntries(items){return items.map(normalize).sort((a,b)=>(L1O[a.level1]??99)-(L1O[b.level1]??99)||l2Label(a).localeCompare(l2Label(b),'zh-CN')||String(a.label).localeCompare(String(b.label),'zh-CN'))}
function optionGroups(select,entries,current,placeholder){
 select.innerHTML='';if(placeholder){const o=document.createElement('option');o.value='';o.textContent=placeholder;select.appendChild(o)}
 const groups=new Map();for(const e of sortEntries(entries)){const g=`${l1Label(e)} › ${l2Label(e)}`;if(!groups.has(g))groups.set(g,[]);groups.get(g).push(e)}
 for(const [g,arr] of groups){const og=document.createElement('optgroup');og.label=g;for(const e of arr){const o=document.createElement('option');o.value=e.id;o.textContent=e.label;og.appendChild(o)}select.appendChild(og)}
 if(current&&[...select.options].some(o=>o.value===current))select.value=current;else if(!placeholder&&select.options.length)select.selectedIndex=0;
}
function mount(select,{namespace='default',entries=()=>[],placeholder='选择字段',onSelect=null}={}){
 if(!select)return null;let root=select.nextElementSibling?.classList?.contains('field-picker')?select.nextElementSibling:null;
 if(!root){root=document.createElement('div');root.className='field-picker field-cascade';root.innerHTML=`<select class="select field-level1" title="一级：字段大类"></select><select class="select field-level2" title="二级：业务维度 / 指标分组"></select><select class="select field-level3" title="三级：具体指标"></select><button type="button" class="btn field-search-btn" title="跨全部字段搜索">搜索</button><div class="field-picker-popover"><input class="field-picker-search" placeholder="搜索全部字段 / 指标"><div class="field-picker-list"></div></div>`;select.insertAdjacentElement('afterend',root);select.classList.add('field-picker-native')}
 const s1=root.querySelector('.field-level1'),s2=root.querySelector('.field-level2'),s3=root.querySelector('.field-level3'),btn=root.querySelector('.field-search-btn'),pop=root.querySelector('.field-picker-popover'),search=root.querySelector('.field-picker-search'),list=root.querySelector('.field-picker-list');
 const favKey=`${LS_FAV}:${namespace}`,recentKey=`${LS_RECENT}:${namespace}`;const getFav=()=>new Set(load(favKey,[])),getRecent=()=>load(recentKey,[]);
 const all=()=>sortEntries((entries()||[]).map(normalize));
 function setOptions(sel,arr,val,ph){sel.innerHTML='';if(ph){const o=document.createElement('option');o.value='';o.textContent=ph;sel.appendChild(o)}for(const [v,t] of arr){const o=document.createElement('option');o.value=v;o.textContent=t;sel.appendChild(o)}if(val&&arr.some(x=>x[0]===val))sel.value=val;else if(!ph&&arr.length)sel.value=arr[0][0]}
 function current(){return all().find(e=>e.id===select.value)}
 function populate(preferId=select.value){const es=all();let cur=es.find(e=>e.id===preferId)||es[0];const l1s=L1.filter(x=>es.some(e=>e.level1===x[0])).map(x=>[x[0],x[1]]);setOptions(s1,l1s,cur?.level1,'一级分类');const l2vals=[...new Map(es.filter(e=>e.level1===s1.value).map(e=>[e.level2,l2Label(e)])).entries()];setOptions(s2,l2vals,cur?.level1===s1.value?cur?.level2:'','二级分组');const xs=es.filter(e=>e.level1===s1.value&&e.level2===s2.value);setOptions(s3,xs.map(e=>[e.id,e.label]),cur?.id,'三级指标');if(s3.value)select.value=s3.value}
 function choose(id){select.value=id;const rec=[id,...getRecent().filter(x=>x!==id)].slice(0,12);save(recentKey,rec);populate(id);select.dispatchEvent(new Event('change',{bubbles:true}));if(onSelect)onSelect(id)}
 s1.onchange=()=>{const es=all(),l2vals=[...new Map(es.filter(e=>e.level1===s1.value).map(e=>[e.level2,l2Label(e)])).entries()];setOptions(s2,l2vals,'','二级分组');s2.dispatchEvent(new Event('change'))};
 s2.onchange=()=>{const es=all().filter(e=>e.level1===s1.value&&e.level2===s2.value);setOptions(s3,es.map(e=>[e.id,e.label]),'','三级指标');if(s3.value)choose(s3.value)};
 s3.onchange=()=>{if(s3.value)choose(s3.value)};
 function renderSearch(){const q=(search.value||'').trim().toLowerCase(),fav=getFav(),recent=getRecent(),es=all();let arr=es.filter(e=>!q||`${e.label} ${l1Label(e)} ${l2Label(e)} ${e.key||''}`.toLowerCase().includes(q));if(!q){const ids=[...getFav(),...recent],seen=new Set();arr=[...ids.map(id=>es.find(e=>e.id===id)).filter(Boolean),...arr].filter(e=>{if(seen.has(e.id))return false;seen.add(e.id);return true})}list.innerHTML=arr.slice(0,100).map(e=>`<div class="field-picker-option" data-field-id="${esc(e.id)}"><button type="button" class="field-picker-star" data-star-id="${esc(e.id)}">${fav.has(e.id)?'★':'☆'}</button><span><b>${esc(e.label)}</b><small>${esc(l1Label(e))} › ${esc(l2Label(e))}</small></span></div>`).join('')||'<div class="field-picker-empty">没有匹配字段</div>';list.querySelectorAll('[data-field-id]').forEach(x=>x.onclick=ev=>{if(ev.target.closest('[data-star-id]'))return;choose(x.dataset.fieldId);pop.classList.remove('open')});list.querySelectorAll('[data-star-id]').forEach(b=>b.onclick=ev=>{ev.stopPropagation();const f=getFav(),id=b.dataset.starId;f.has(id)?f.delete(id):f.add(id);save(favKey,[...f]);renderSearch()})}
 btn.onclick=e=>{e.preventDefault();pop.classList.toggle('open');if(pop.classList.contains('open')){search.value='';renderSearch();setTimeout(()=>search.focus(),0)}};search.oninput=renderSearch;document.addEventListener('click',e=>{if(!root.contains(e.target))pop.classList.remove('open')});
 const api={refresh(){populate(select.value)},choose,render:renderSearch};root._fieldPicker=api;populate(select.value);return api;
}
window.CDHFieldRegistry={build,normalize,sortEntries,optionGroups,mount,l1Label,l2Label,taxonomy:{level1:L1,level2Labels:L2N}};
})();
