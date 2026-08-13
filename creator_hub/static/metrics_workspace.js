(()=>{
'use strict';
const KEY='cdh-secondary-metrics-v5';
const LEGACY_KEYS=['cdh-secondary-metrics-v4','cdh-secondary-metrics-v3'];
const FACTS=window.CDH_CREATOR_FACTS||{creators:[]};
const BASE=window.CDH_METRIC_BASE||{cubes:{},objective_fields:{},aggregate_labels:{},video_objectives:{},video_labels:{},windows:['all','7','30','60','90','180','365']};
const creators=FACTS.creators||[];
const uid=p=>p+'_'+Math.random().toString(36).slice(2,10);
const iso=()=>new Date().toISOString();
const esc=x=>String(x??'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m]||m));
const fmt=x=>x===null||x===undefined||Number.isNaN(x)?'—':(typeof x==='number'?x.toLocaleString('zh-CN',{maximumFractionDigits:3}):String(x));
const typeNames={objective:'客观数据',aggregate_label:'聚合标签',constructed:'构建指标',ratio:'比值指标'};
const aggNames={count:'Count',sum:'Sum',avg:'Average',median:'Median',max:'Max',min:'Min'};
const winNames={all:'全部时间','7':'近7天','30':'近30天','60':'近60天','90':'近90天','180':'近180天','365':'近365天',custom:'指定日期范围'};
let interactive=false;
async function post(path,payload={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),x=await r.json();if(!r.ok||x.ok===false)throw new Error(x.error||'请求失败');return x}
function emptyState(){return {metrics:[],rules:[],activeRule:'',filters:[]}}
function metricByIdFrom(list,id){return (list||[]).find(m=>m.id===id)}
function migrateState(x){
 if(!x||!Array.isArray(x.metrics)||!Array.isArray(x.rules))return emptyState();
 const oldMetrics=x.metrics||[],index=new Map(oldMetrics.filter(Boolean).map(m=>[m.id,m]));
 const kept=oldMetrics.filter(m=>m&&['constructed','ratio'].includes(m.type)).map(m=>({...m}));
 for(const m of kept){if(m.type==='ratio'&&!m.numerator_spec&&m.numerator){m.legacy_numerator=m.numerator;m.legacy_denominator=m.denominator}}
 const rules=(x.rules||[]).map(r=>{
   const relation=(r.relation||'AND').toUpperCase();
   const cs=(r.conditions||[]).map((c,i)=>{
     if(c.metric_type&&c.metric_key)return {...c,join:i===0?'':(c.join||relation)};
     const m=index.get(c.metric_id);if(!m)return null;
     if(m.type==='objective'||m.type==='aggregate_label')return {join:i===0?'':relation,metric_type:m.type,metric_key:m.field,op:c.op,value:c.value};
     return {join:i===0?'':relation,metric_type:m.type,metric_key:m.id,op:c.op,value:c.value};
   }).filter(Boolean);
   return {...r,conditions:cs};
 });
 let filters=Array.isArray(x.filters)?x.filters:[];
 if(!filters.length&&x.filter&&x.filter.metric)filters=[{join:'',metric_type:x.filter.category,metric_key:x.filter.metric,op:x.filter.op,value:x.filter.value}];
 return {...emptyState(),...x,metrics:kept,rules,filters};
}
function load(){try{const now=localStorage.getItem(KEY);if(now)return migrateState(JSON.parse(now));for(const k of LEGACY_KEYS){const v=localStorage.getItem(k);if(v){const s=migrateState(JSON.parse(v));localStorage.setItem(KEY,JSON.stringify(s));return s}}if(window.CDH_SAVED_METRIC_CONFIG)return migrateState(window.CDH_SAVED_METRIC_CONFIG)}catch(e){}return emptyState()}
let state=load(),resultPage=1,resultSize=30;
function persist(){localStorage.setItem(KEY,JSON.stringify(state));resultPage=1;renderAll()}
function cube(c){return (BASE.cubes||{})[c.channel_id]||{}}
function bucket(c,scope,value,window){return ((((cube(c)[scope]||{})[value]||{})[window])||{})}
function builtinValue(c,cat,id){if(cat==='objective'||cat==='aggregate_label')return Number(c[id]??0);return null}
function parseLabelKey(k){const [scope,val]=String(k||'').split(':');return {scope,val}}
function objectiveSpecValue(c,spec){
 const w=spec.window||'all',agg=spec.aggregation||'count';
 let b=bucket(c,'all','all',w);
 if(spec.filter_label){const z=parseLabelKey(spec.filter_label);b=bucket(c,z.scope,z.val,w)}
 if(agg==='count')return Number(b.count||0);
 const stat=((b[spec.source_field]||{})[agg]);return stat===undefined?null:Number(stat);
}
function constructedValue(c,m){
 if(m.window==='custom'&&m.custom_values)return m.custom_values[c.channel_id]??null;
 if(m.source_kind==='aggregate_label')return Number(c[m.source_field]??0);
 // v0.6 以前把视频标签当作输入来源；继续只读兼容。
 if(m.source_kind==='label'){
   const win=m.window||'all',agg=m.aggregation||'count',{scope,val}=parseLabelKey(m.source_field),match=Number(bucket(c,scope,val,win).count||0),total=Number(bucket(c,'all','all',win).count||0);
   if(agg==='count'||agg==='sum')return match;if(agg==='avg')return total?match/total:0;if(agg==='median')return total?(match*2>=total?1:0):0;if(agg==='max')return match>0?1:0;return total>0&&match===total?1:0;
 }
 return objectiveSpecValue(c,m);
}
function metricById(id){return state.metrics.find(m=>m.id===id)}
function metricValue(c,m,seen=new Set()){
 if(!m)return null;if(seen.has(m.id))return null;seen.add(m.id);
 if(m.custom_values&&Object.prototype.hasOwnProperty.call(m.custom_values,c.channel_id))return m.custom_values[c.channel_id];
 if(m.type==='constructed')return constructedValue(c,m);
 if(m.type==='ratio'){
   if(m.numerator_spec&&m.denominator_spec){const a=objectiveSpecValue(c,m.numerator_spec),b=objectiveSpecValue(c,m.denominator_spec);return b?Number(a||0)/b:null}
   const a=metricValue(c,metricById(m.legacy_numerator||m.numerator),new Set(seen)),b=metricValue(c,metricById(m.legacy_denominator||m.denominator),new Set(seen));return b?Number(a||0)/b:null;
 }
 return null;
}
function allValues(c){const o={};for(const m of state.metrics)o[m.id]=metricValue(c,m,new Set());return o}
function compare(v,op,t){v=Number(v);t=Number(t);if(Number.isNaN(v)||Number.isNaN(t))return false;return op==='gt'?v>t:op==='gte'?v>=t:op==='lt'?v<t:op==='lte'?v<=t:op==='eq'?v===t:v!==t}
function metricOptions(type){if(type==='objective')return Object.entries(BASE.objective_fields||{});if(type==='aggregate_label')return Object.entries(BASE.aggregate_labels||{});return state.metrics.filter(m=>m.type===type).map(m=>[m.id,m.name])}
function refValue(c,type,key){if(type==='objective'||type==='aggregate_label')return builtinValue(c,type,key);return metricValue(c,metricById(key),new Set())}
function conditionPass(c,cond){const v=refValue(c,cond.metric_type,cond.metric_key);if(cond.metric_type==='aggregate_label')return !!Number(v);return compare(v,cond.op,cond.value)}
function chainPass(conditions,c){if(!conditions||!conditions.length)return true;let acc=conditionPass(c,conditions[0]);for(let i=1;i<conditions.length;i++){const b=conditionPass(c,conditions[i]),j=(conditions[i].join||'AND').toUpperCase();acc=j==='OR'?(acc||b):j==='NOT'?(acc&&!b):(acc&&b)}return acc}
function rulePass(r,c){return chainPass(r.conditions||[],c)}
function videoObjectiveOptions(){return Object.entries(BASE.video_objectives||{})}
function aggregateLabelOptions(){return Object.entries(BASE.aggregate_labels||{})}
function videoLabelOptions(){return Object.entries(BASE.video_labels||{})}
function timeOptions(selected='all'){return ['all','7','30','60','90','180','365','custom'].map(w=>`<option value="${w}" ${w===selected?'selected':''}>${winNames[w]}</option>`).join('')}
function aggOptions(selected='count'){return ['count','sum','avg','median','max','min'].map(a=>`<option value="${a}" ${a===selected?'selected':''}>${aggNames[a]}</option>`).join('')}
function objectiveSide(prefix,spec={}){const src=videoObjectiveOptions().map(([k,v])=>`<option value="${k}" ${k===(spec.source_field||'current_views')?'selected':''}>${esc(v)}</option>`).join(''),vl=videoLabelOptions().map(([k,v])=>`<option value="${k}" ${k===(spec.filter_label||'')?'selected':''}>${esc(v)}</option>`).join('');return `<div class="form-row"><label>${prefix==='num'?'分子':'分母'}客观数据</label><select id="${prefix}Source">${src}</select></div><div class="form-row"><label>视频筛选</label><select id="${prefix}Filter"><option value="">不筛选视频标签</option>${vl}</select></div><div class="form-row"><label>时间范围</label><select id="${prefix}Window">${timeOptions(spec.window||'all')}</select></div><div id="${prefix}CustomDates" class="form-row" style="display:${spec.window==='custom'?'grid':'none'}"><label>精确日期</label><div class="inline"><input id="${prefix}From" type="date" value="${esc(spec.from_date||'')}"><span>至</span><input id="${prefix}To" type="date" value="${esc(spec.to_date||'')}"></div></div><div class="form-row"><label>聚合方式</label><select id="${prefix}Agg">${aggOptions(spec.aggregation||'count')}</select></div>`}
function bindWindow(prefix){const s=document.getElementById(prefix+'Window'),d=document.getElementById(prefix+'CustomDates');if(s&&d)s.onchange=()=>d.style.display=s.value==='custom'?'grid':'none'}
function renderMetricDynamic(metric=null){
 const out=document.getElementById('metricOutputType').value,input=document.getElementById('metricInputType'),box=document.getElementById('metricDynamic');
 if(out==='ratio'){
   input.value='objective';input.disabled=true;box.innerHTML='<div class="note">比值指标仅使用客观数据作为输入。</div>'+objectiveSide('num',metric?.numerator_spec||{})+objectiveSide('den',metric?.denominator_spec||{});bindWindow('num');bindWindow('den');return;
 }
 input.disabled=false;const t=input.value;
 if(t==='aggregate_label'){
   const opts=aggregateLabelOptions().map(([k,v])=>`<option value="${k}" ${k===metric?.source_field?'selected':''}>${esc(v)}</option>`).join('');box.innerHTML=`<div class="form-row"><label>聚合标签</label><select id="constructedSource">${opts}</select></div><div class="form-row"><label>聚合方式</label><select id="constructedAgg">${aggOptions(metric?.aggregation||'count')}</select></div>`;return;
 }
 box.innerHTML=objectiveSide('constructed',metric||{});bindWindow('constructed');
}
function readSide(prefix){const w=document.getElementById(prefix+'Window')?.value||'all';return {source_field:document.getElementById(prefix+'Source')?.value||'current_views',filter_label:document.getElementById(prefix+'Filter')?.value||'',window:w,from_date:w==='custom'?(document.getElementById(prefix+'From')?.value||''):'',to_date:w==='custom'?(document.getElementById(prefix+'To')?.value||''):'',aggregation:document.getElementById(prefix+'Agg')?.value||'count'}}
function validateDates(spec){if(spec.window!=='custom')return true;if(!spec.from_date||!spec.to_date){alert('指定日期范围必须同时填写开始日期和结束日期');return false}if(spec.from_date>spec.to_date){alert('开始日期不能晚于结束日期');return false}return true}
function clearMetric(){document.getElementById('metricEditId').value='';document.getElementById('metricName').value='';document.getElementById('metricOutputType').value='constructed';document.getElementById('metricInputType').value='objective';document.getElementById('metricInputType').disabled=false;document.getElementById('metricVisible').value='1';document.getElementById('metricStatus').textContent='';renderMetricDynamic()}
async function saveMetric(){
 const id=document.getElementById('metricEditId').value,name=document.getElementById('metricName').value.trim(),out=document.getElementById('metricOutputType').value,input=document.getElementById('metricInputType').value;if(!name)return alert('请输入指标名称');
 const old=metricById(id);let m={id:id||uid('m'),name,type:out,visible:document.getElementById('metricVisible').value==='1',version:(old?.version||0)+1,updated_at:iso()};
 if(out==='ratio'){
   m.numerator_spec=readSide('num');m.denominator_spec=readSide('den');if(!validateDates(m.numerator_spec)||!validateDates(m.denominator_spec))return;
 }else if(input==='aggregate_label'){
   m.source_kind='aggregate_label';m.source_field=document.getElementById('constructedSource').value;m.aggregation=document.getElementById('constructedAgg').value;
 }else{
   const s=readSide('constructed');if(!validateDates(s))return;Object.assign(m,s,{source_kind:'objective'});
 }
 const needsCustom=out==='ratio'?(m.numerator_spec.window==='custom'||m.denominator_spec.window==='custom'):(m.source_kind==='objective'&&m.window==='custom');
 if(needsCustom){if(!interactive)return alert('精确日期范围需要通过 start-dashboard.cmd 打开交互模式后构建');const st=document.getElementById('metricStatus');try{st.textContent='正在从本地 SQLite 计算精确日期范围…';const x=await post('/api/metric/evaluate',{spec:m});m.custom_values=x.values||{};st.textContent='精确日期范围计算完成'}catch(e){st.textContent=e.message;return}}
 if(old)Object.assign(old,m);else state.metrics.push(m);clearMetric();persist();
}
function editMetric(id){const m=metricById(id);if(!m)return;document.getElementById('metricEditId').value=id;document.getElementById('metricName').value=m.name;document.getElementById('metricVisible').value=m.visible?'1':'0';document.getElementById('metricOutputType').value=m.type==='ratio'?'ratio':'constructed';document.getElementById('metricInputType').value=m.source_kind==='aggregate_label'?'aggregate_label':'objective';renderMetricDynamic(m)}
function specDesc(s){const src=(BASE.video_objectives||{})[s.source_field]||s.source_field,fl=s.filter_label?' · '+((BASE.video_labels||{})[s.filter_label]||s.filter_label):'',w=s.window==='custom'?`${s.from_date||'?'} 至 ${s.to_date||'?'}`:(winNames[s.window]||s.window);return `${src}${fl} · ${w} · ${aggNames[s.aggregation]||s.aggregation}`}
function desc(m){if(m.type==='ratio'){if(m.numerator_spec)return `比值：(${specDesc(m.numerator_spec)}) ÷ (${specDesc(m.denominator_spec)})`;return '旧版比值指标'}if(m.source_kind==='aggregate_label')return `${(BASE.aggregate_labels||{})[m.source_field]||m.source_field} · ${aggNames[m.aggregation]||m.aggregation}`;if(m.source_kind==='label')return '旧版视频标签构建指标';return specDesc(m)}
function renderMetrics(){const box=document.getElementById('metricList');if(!state.metrics.length){box.innerHTML='<div class="empty">尚无已构建指标。请从左侧自行构建。</div>';return}box.innerHTML=state.metrics.map(m=>`<div class="metric-item"><div class="metric-item-head"><div><div class="metric-item-title">${esc(m.name)} <span class="badge-fact">${typeNames[m.type]||'构建指标'}</span></div><div class="metric-meta">${esc(desc(m))} · v${m.version||1}</div></div><div class="inline"><button class="btn" data-toggle="${m.id}">${m.visible?'隐藏':'显示'}</button><button class="btn" data-edit="${m.id}">编辑</button><button class="btn danger" data-del="${m.id}">删除</button></div></div></div>`).join('');box.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=()=>{const m=metricById(b.dataset.toggle);m.visible=!m.visible;persist()});box.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>editMetric(b.dataset.edit));box.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{if(confirm('删除该指标？')){const id=b.dataset.del;state.metrics=state.metrics.filter(x=>x.id!==id);state.rules.forEach(r=>r.conditions=(r.conditions||[]).filter(c=>c.metric_key!==id));state.filters=(state.filters||[]).filter(c=>c.metric_key!==id);persist()}})}
function conditionMetricOptions(type){return metricOptions(type)}
function conditionRow(c={},index=0,kind='rule'){
 const d=document.createElement('div');d.className='condition-row';const ctype=c.metric_type||'objective',ckey=c.metric_key||'';
 const join=index===0?'<span class="small c-start">起始</span>':`<select class="c-join"><option value="AND">AND</option><option value="OR">OR</option><option value="NOT">NOT</option></select>`;
 d.innerHTML=join+'<select class="c-type"><option value="objective">客观数据</option><option value="aggregate_label">聚合标签</option><option value="constructed">构建指标</option><option value="ratio">比值指标</option></select><select class="c-metric"></select><select class="c-op"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option><option value="eq">=</option><option value="neq">≠</option></select><input class="c-value" type="number" step="any" placeholder="阈值"><button class="btn danger">×</button>';
 const ts=d.querySelector('.c-type');ts.value=ctype;function fill(wanted=''){const opts=conditionMetricOptions(ts.value),sel=d.querySelector('.c-metric');sel.innerHTML=opts.length?opts.map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join(''):'<option value="">暂无该类指标</option>';if(wanted&&opts.some(x=>x[0]===wanted))sel.value=wanted;const bool=ts.value==='aggregate_label';d.querySelector('.c-op').style.display=bool?'none':'';d.querySelector('.c-value').style.display=bool?'none':''}fill(ckey);ts.onchange=()=>fill('');if(c.join&&d.querySelector('.c-join'))d.querySelector('.c-join').value=c.join;if(c.op)d.querySelector('.c-op').value=c.op;d.querySelector('.c-value').value=c.value??'';d.querySelector('button').onclick=()=>{d.remove();renumberConditions(kind)};return d;
}
function renumberConditions(kind){const box=document.getElementById(kind==='rule'?'ruleConditions':'resultFilterConditions'),data=[...box.children].map((d,i)=>({join:d.querySelector('.c-join')?.value||'',metric_type:d.querySelector('.c-type')?.value||'objective',metric_key:d.querySelector('.c-metric')?.value||'',op:d.querySelector('.c-op')?.value||'eq',value:d.querySelector('.c-value')?.value||''}));box.innerHTML='';data.forEach((c,i)=>box.appendChild(conditionRow(c,i,kind)))}
function addCondition(c={},kind='rule'){const box=document.getElementById(kind==='rule'?'ruleConditions':'resultFilterConditions');box.appendChild(conditionRow(c,box.children.length,kind))}
function readConditions(kind='rule'){const box=document.getElementById(kind==='rule'?'ruleConditions':'resultFilterConditions');return [...box.children].map((d,i)=>{const type=d.querySelector('.c-type').value,key=d.querySelector('.c-metric').value,bool=type==='aggregate_label';return {join:i===0?'':(d.querySelector('.c-join')?.value||'AND'),metric_type:type,metric_key:key,op:bool?'truthy':d.querySelector('.c-op').value,value:bool?'':d.querySelector('.c-value').value}}).filter(x=>x.metric_key&&(x.metric_type==='aggregate_label'||x.value!==''))}
function clearRule(){document.getElementById('ruleEditId').value='';document.getElementById('ruleName').value='';document.getElementById('ruleConditions').innerHTML='';addCondition({},'rule')}
function saveRule(){const id=document.getElementById('ruleEditId').value,name=document.getElementById('ruleName').value.trim(),conds=readConditions('rule');if(!name)return alert('请输入规则名称');if(!conds.length)return alert('至少添加一个有效条件');const old=state.rules.find(x=>x.id===id),r={id:id||uid('r'),name,conditions:conds,version:(old?.version||0)+1,updated_at:iso()};if(old)Object.assign(old,r);else state.rules.push(r);clearRule();persist()}
function editRule(id){const r=state.rules.find(x=>x.id===id);if(!r)return;document.getElementById('ruleEditId').value=id;document.getElementById('ruleName').value=r.name;const b=document.getElementById('ruleConditions');b.innerHTML='';(r.conditions||[]).forEach(c=>addCondition(c,'rule'));if(!b.children.length)addCondition({},'rule')}
function renderRules(){const box=document.getElementById('ruleList'),sel=document.getElementById('activeRule');sel.innerHTML='<option value="">全部博主</option>'+state.rules.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join('');sel.value=state.activeRule||'';if(!state.rules.length){box.innerHTML='<div class="empty">尚无规则。</div>';return}box.innerHTML=state.rules.map(r=>{let hit=0;for(const c of creators)if(rulePass(r,c))hit++;return `<div class="metric-item"><div class="metric-item-head"><div><div class="metric-item-title">${esc(r.name)}</div><div class="metric-meta">逐条件布尔逻辑 · ${r.conditions.length} 条件 · 命中 ${hit}</div></div><div class="inline"><button class="btn primary" data-apply="${r.id}">应用</button><button class="btn" data-editr="${r.id}">编辑</button><button class="btn danger" data-delr="${r.id}">删除</button></div></div></div>`}).join('');box.querySelectorAll('[data-apply]').forEach(b=>b.onclick=()=>{state.activeRule=b.dataset.apply;persist()});box.querySelectorAll('[data-editr]').forEach(b=>b.onclick=()=>editRule(b.dataset.editr));box.querySelectorAll('[data-delr]').forEach(b=>b.onclick=()=>{state.rules=state.rules.filter(x=>x.id!==b.dataset.delr);if(state.activeRule===b.dataset.delr)state.activeRule='';persist()})}
function fillResultSort(){const sel=document.getElementById('resultSort'),cur=sel.value||'subscriber_count',visible=state.metrics.filter(m=>m.visible),opts=[['channel_title','博主名称'],['country','国家'],['subscriber_count','订阅数'],['channel_view_count','频道累计播放量'],['stored_videos','本地视频数'],['last_synced_at','最近同步'],...visible.map(m=>['metric:'+m.id,m.name])];sel.innerHTML=opts.map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('');if(opts.some(x=>x[0]===cur))sel.value=cur;else sel.value='subscriber_count'}
function resultSortValue(x,key){const c=x.c;if(key.startsWith('metric:'))return x.vals[key.slice(7)];if(key==='channel_title')return c.channel_title||c.handle||c.channel_id||'';if(key==='country')return c.country_resolved||c.country_api||'';if(key==='last_synced_at')return c.last_synced_at||'';return Number(c[key]??0)}
function renderResultFilters(){const box=document.getElementById('resultFilterConditions');box.innerHTML='';(state.filters||[]).forEach(c=>addCondition(c,'filter'));if(!box.children.length)addCondition({},'filter')}
function renderResults(){const visible=state.metrics.filter(m=>m.visible),head=document.getElementById('resultHead');head.innerHTML='<tr><th>博主</th><th>国家</th><th>订阅数</th><th>频道累计播放量</th><th>本地视频数</th><th>身份标签</th>'+visible.map(m=>`<th class="dynamic">${esc(m.name)}</th>`).join('')+'<th>最近同步</th></tr>';fillResultSort();const q=(document.getElementById('metricSearch').value||'').toLowerCase(),rule=state.rules.find(x=>x.id===state.activeRule),rows=[];for(const c of creators){if(q&&!`${c.channel_title||''} ${c.handle||''} ${c.country_resolved||c.country_api||''} ${c.channel_id}`.toLowerCase().includes(q))continue;if(!chainPass(state.filters||[],c))continue;const vals=allValues(c);if(rule&&!rulePass(rule,c))continue;rows.push({c,vals})}const sortKey=document.getElementById('resultSort').value,desc=document.getElementById('resultSortDir').value==='desc';rows.sort((a,b)=>{const av=resultSortValue(a,sortKey),bv=resultSortValue(b,sortKey);let z;if(typeof av==='number'&&typeof bv==='number')z=(Number.isFinite(av)?av:-Infinity)-(Number.isFinite(bv)?bv:-Infinity);else z=String(av??'').localeCompare(String(bv??''),'zh-CN',{numeric:true,sensitivity:'base'});return desc?-z:z});const pages=Math.max(1,Math.ceil(rows.length/resultSize));resultPage=Math.max(1,Math.min(pages,resultPage));const start=(resultPage-1)*resultSize,shown=rows.slice(start,start+resultSize),html=[];for(const x of shown){const c=x.c,vals=x.vals,tags=[c.partnered_ugphone?'合作过博主':'未合作博主',c.ldcloud_creator?'LDCloud合作博主':'',c.redfinger_creator?'RedFinger合作博主':'',c.vsphone_creator?'VSPhone合作博主':''].filter(Boolean).map(t=>`<span class="pill">${esc(t)}</span>`).join(''),channelUrl=`https://www.youtube.com/channel/${encodeURIComponent(c.channel_id)}`,localUrl=`creators/${encodeURIComponent(c.channel_id)}.html`;html.push(`<tr><td><a class="link-ext" target="_blank" rel="noopener" href="${channelUrl}"><b>${esc(c.channel_title||c.channel_id)}</b></a><div class="small mono">${esc(c.handle||c.channel_id)}</div><div class="small"><a class="link-local" href="${localUrl}">查看详情</a></div></td><td>${esc(c.country_resolved||c.country_api||'—')}</td><td>${fmt(c.subscriber_count)}</td><td>${fmt(c.channel_view_count)}</td><td>${fmt(c.stored_videos)}</td><td>${tags}</td>${visible.map(m=>`<td>${fmt(vals[m.id])}</td>`).join('')}<td class="small">${esc(c.last_synced_at||'—')}</td></tr>`)}document.getElementById('resultBody').innerHTML=html.join('')||'<tr><td colspan="99" class="empty">没有命中的博主</td></tr>';document.getElementById('resultSummary').textContent=`共 ${rows.length} 条 · 当前显示 ${rows.length?start+1:0}-${Math.min(start+resultSize,rows.length)}`;CDHTableTools.renderPager({page:resultPage,pages,go:p=>{resultPage=p;renderResults()},firstId:'resultFirst',prevId:'resultPrev',nextId:'resultNext',lastId:'resultLast',buttonsId:'resultPageButtons',inputId:'resultPageInput',jumpId:'resultJump',pageInfoId:'resultPageInfo'})}
function renderAll(){renderMetrics();renderRules();renderResultFilters();renderResults()}
document.getElementById('metricOutputType').onchange=()=>renderMetricDynamic();document.getElementById('metricInputType').onchange=()=>renderMetricDynamic();document.getElementById('saveMetric').onclick=()=>saveMetric();document.getElementById('clearMetric').onclick=clearMetric;document.getElementById('addRuleCondition').onclick=()=>addCondition({},'rule');document.getElementById('saveRule').onclick=saveRule;document.getElementById('clearRule').onclick=clearRule;document.getElementById('addResultFilter').onclick=()=>addCondition({},'filter');document.getElementById('applyFilter').onclick=()=>{state.filters=readConditions('filter');persist()};document.getElementById('clearFilter').onclick=()=>{state.filters=[];persist()};document.getElementById('activeRule').onchange=e=>{state.activeRule=e.target.value;persist()};document.getElementById('metricSearch').oninput=()=>{resultPage=1;renderResults()};document.getElementById('resultSort').onchange=()=>{resultPage=1;renderResults()};document.getElementById('resultSortDir').onchange=()=>{resultPage=1;renderResults()};document.getElementById('resultPageSizeConfirm').onclick=()=>{resultSize=CDHTableTools.pageSize(document.getElementById('resultPageSize'),resultSize);document.getElementById('resultPageSize').value=String(resultSize);resultPage=1;renderResults()};document.getElementById('exportCfg').onclick=()=>{const blob=new Blob([JSON.stringify(state,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='creator_data_hub_metrics_config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};document.getElementById('importCfg').onchange=e=>{const f=e.target.files[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{try{state=migrateState(JSON.parse(rd.result));persist()}catch(_){alert('配置文件无效')}};rd.readAsText(f)};document.getElementById('resetCfg').onclick=()=>{if(confirm('清空全部已构建指标和规则？')){state=emptyState();localStorage.removeItem(KEY);renderAll()}};
fetch('/api/ping').then(r=>r.ok?r.json():null).then(x=>interactive=!!x).catch(()=>interactive=false);
document.getElementById('resultPageSize').value='30';clearMetric();clearRule();renderAll();
})();
