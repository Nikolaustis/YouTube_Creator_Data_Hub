(()=>{
'use strict';

const KEY='cdh-secondary-metrics-v6';
const LEGACY_KEYS=['cdh-secondary-metrics-v5','cdh-secondary-metrics-v4','cdh-secondary-metrics-v3'];
const FACTS=window.CDH_CREATOR_FACTS||{creators:[]};
const BASE=window.CDH_METRIC_BASE||{cubes:{},creator_fact_fields:{},creator_labels:{},video_fact_fields:{},video_filters:{},windows:['all','7','30','60','90','180','365']};
const GEO=window.CDH_GEOGRAPHY||{groups:[],countries:[]};
const geoCountry=new Map((GEO.countries||[]).map(x=>[x.code,x]));
const creators=FACTS.creators||[];

const uid=p=>p+'_'+Math.random().toString(36).slice(2,10);
const iso=()=>new Date().toISOString();
const esc=x=>String(x??'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m]||m));
const fmt=x=>x===null||x===undefined||Number.isNaN(x)?'—':(typeof x==='number'?x.toLocaleString('zh-CN',{maximumFractionDigits:3}):String(x));
const typeNames={creator_fact:'博主客观数据',creator_label:'博主标签',constructed:'构建指标',ratio:'比值指标'};
const aggNames={count:'Count',sum:'Sum',avg:'Average',median:'Median',max:'Max',min:'Min'};
const winNames={all:'全部时间','7':'近7天','30':'近30天','60':'近60天','90':'近90天','180':'近180天','365':'近365天',custom:'指定日期范围'};

const creatorFactFields=BASE.creator_fact_fields||BASE.objective_fields||{};
const creatorLabels=BASE.creator_labels||BASE.aggregate_labels||{};
const videoFactFields=BASE.video_fact_fields||BASE.video_objectives||{};
const videoFilters=BASE.video_filters||BASE.video_labels||{};
let fieldRegistry=[];
function refreshFieldRegistry(){fieldRegistry=window.CDHFieldRegistry?CDHFieldRegistry.build(BASE,state?.metrics||[]):[]}
function regEntries(pred){refreshFieldRegistry();return fieldRegistry.filter(pred)}
function metricFieldEntries(type){
  if(type==='creator_fact')return regEntries(e=>e.kind==='creator_fact'&&e.grain==='creator').map(e=>({...e,id:e.key}));
  if(type==='creator_label')return regEntries(e=>e.kind==='creator_label').map(e=>({...e,id:e.key}));
  if(type==='constructed'||type==='ratio')return regEntries(e=>e.kind===type).map(e=>({...e,id:e.key}));
  return [];
}
function mountFieldPicker(select,entriesFn,namespace,placeholder='选择字段'){if(!window.CDHFieldRegistry||!select)return null;const root=select.nextElementSibling?.classList?.contains('field-picker')?select.nextElementSibling:null;const api=root?root._fieldPicker:CDHFieldRegistry.mount(select,{entries:entriesFn,namespace,placeholder});api?.refresh();return api}


let interactive=false;
async function post(path,payload={}){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),x=await r.json();
  if(!r.ok||x.ok===false)throw new Error(x.error||'请求失败');
  return x;
}
async function refreshLiveMetricData(){
  if(!interactive)return;
  const [facts,base]=await Promise.all([post('/api/creators/facts',{}),post('/api/metrics/base',{})]);
  creators.splice(0,creators.length,...(facts.creators||[]));
  FACTS.creators=creators;
  BASE.cubes=base.cubes||{};
  BASE.brands=base.brands||BASE.brands||[];
  BASE.generated_at=base.generated_at||BASE.generated_at;
  window.CDH_CREATOR_FACTS=FACTS;window.CDH_METRIC_BASE=BASE;refreshFieldRegistry();
  resultPage=1;renderAll();
}

function emptyState(){return {schema_version:1,metrics:[],rules:[],activeRule:'',filters:[]}}
function legacyLabelFalse(op,value){const n=Number(value);return (op==='eq'&&n===0)||(op==='lte'&&n<=0)||(op==='lt'&&n<=1)||(op==='neq'&&n===1)}
function normalizeCondition(c={},index=0,invalidLabelMetrics=new Map()){
  let type=c.metric_type||c.type||'';
  let key=c.metric_key||c.key||c.metric_id||'';
  if(type==='objective')type='creator_fact';
  if(type==='aggregate_label')type='creator_label';
  if(type==='constructed'&&invalidLabelMetrics.has(key)){
    const lab=invalidLabelMetrics.get(key);
    return {join:index===0?'':(c.join||'AND'),metric_type:'creator_label',metric_key:lab,op:legacyLabelFalse(c.op,c.value)?'falsy':'truthy',value:''};
  }
  if(type==='creator_label')return {join:index===0?'':(c.join||'AND'),metric_type:type,metric_key:key,op:(c.op==='falsy'||legacyLabelFalse(c.op,c.value))?'falsy':'truthy',value:''};
  return {join:index===0?'':(c.join||'AND'),metric_type:type,metric_key:key,op:c.op||'gte',value:c.value??''};
}
function legacySpecToConstructed(spec,id,name,internal=true){
  if(!spec)return null;
  const aggregation=spec.aggregation||'count';
  const source=spec.source_field||'current_views';
  return {
    id,name,type:'constructed',source_kind:'video_fact',source_field:source,
    filter_label:spec.filter_label||'',window:spec.window||'all',from_date:spec.from_date||'',to_date:spec.to_date||'',
    aggregation,visible:false,internal,version:1,updated_at:iso(),custom_values:spec.custom_values||undefined,
  };
}
function migrateState(x){
  if(!x||!Array.isArray(x.metrics)||!Array.isArray(x.rules))return emptyState();
  const metrics=[];
  const invalidLabelMetrics=new Map();
  const validIds=new Set();
  const pendingRatios=[];
  for(const old of x.metrics||[]){
    if(!old||!old.id||!['constructed','ratio'].includes(old.type))continue;
    if(old.type==='constructed'){
      if(old.source_kind==='aggregate_label'){
        if(old.source_field)invalidLabelMetrics.set(old.id,old.source_field);
        continue;
      }
      if(old.source_kind==='label'){
        if(['count','sum'].includes(old.aggregation||'count')){
          const m={...old,source_kind:'video_fact',source_field:'video_count',filter_label:old.source_field,aggregation:'count'};
          delete m.custom_values;
          metrics.push(m);validIds.add(m.id);
        }
        continue;
      }
      const m={...old,source_kind:'video_fact'};
      metrics.push(m);validIds.add(m.id);
      continue;
    }
    pendingRatios.push({...old});
  }
  for(const old of pendingRatios){
    let num=old.numerator_ref?{...old.numerator_ref}:null;
    let den=old.denominator_ref?{...old.denominator_ref}:null;
    if(!num&&!den&&old.numerator_spec&&old.denominator_spec){
      const ni=old.id+'__legacy_num',di=old.id+'__legacy_den';
      const nm=legacySpecToConstructed(old.numerator_spec,ni,old.name+' · 分子',true),dm=legacySpecToConstructed(old.denominator_spec,di,old.name+' · 分母',true);
      if(nm&&dm){metrics.push(nm,dm);validIds.add(ni);validIds.add(di);num={kind:'constructed',key:ni};den={kind:'constructed',key:di};}
    }
    if(!num&&old.legacy_numerator)num={kind:'constructed',key:old.legacy_numerator};
    if(!den&&old.legacy_denominator)den={kind:'constructed',key:old.legacy_denominator};
    if(!num&&old.numerator)num={kind:'constructed',key:old.numerator};
    if(!den&&old.denominator)den={kind:'constructed',key:old.denominator};
    if(num&&den){const m={...old,numerator_ref:num,denominator_ref:den};delete m.numerator_spec;delete m.denominator_spec;delete m.legacy_numerator;delete m.legacy_denominator;delete m.numerator;delete m.denominator;metrics.push(m);validIds.add(m.id);}
  }
  const rules=(x.rules||[]).map(r=>{
    const relation=(r.relation||'AND').toUpperCase();
    const conditions=(r.conditions||[]).map((c,i)=>normalizeCondition({...c,join:i===0?'':(c.join||relation)},i,invalidLabelMetrics)).filter(c=>{
      if(!c.metric_key)return false;
      if(['constructed','ratio'].includes(c.metric_type))return validIds.has(c.metric_key);
      return true;
    });
    return {...r,conditions};
  });
  const filters=(Array.isArray(x.filters)?x.filters:[]).map((c,i)=>normalizeCondition(c,i,invalidLabelMetrics)).filter(c=>c.metric_key&&(!['constructed','ratio'].includes(c.metric_type)||validIds.has(c.metric_key)));
  return {...emptyState(),...x,schema_version:1,metrics,rules,filters,activeRule:''};
}
function load(){
  try{
    const current=localStorage.getItem(KEY);if(current)return migrateState(JSON.parse(current));
    for(const k of LEGACY_KEYS){const v=localStorage.getItem(k);if(v){const s=migrateState(JSON.parse(v));localStorage.setItem(KEY,JSON.stringify(s));return s}}
    if(window.CDH_SAVED_METRIC_CONFIG)return migrateState(window.CDH_SAVED_METRIC_CONFIG);
  }catch(e){}
  return emptyState();
}
let state=load(),resultPage=1,resultSize=30,dbConfigReady=false,metricCatalogPage=1,metricCatalogSize=30,ruleCatalogPage=1,ruleCatalogSize=30;const metricCatalogSelected=new Set(),ruleCatalogSelected=new Set();
function persistedState(){return {...state,activeRule:''}}
async function saveStateToDb(){if(!interactive)return;try{await post('/api/settings/set',{key:'secondary_metrics',value:persistedState()});dbConfigReady=true}catch(e){console.warn('SQLite config save failed',e)}}
function persist(){localStorage.setItem(KEY,JSON.stringify(persistedState()));if(interactive)saveStateToDb();resultPage=1;renderAll()}
async function hydrateStateFromDb(){
  if(!interactive)return;
  try{
    const x=await post('/api/settings/get',{key:'secondary_metrics'});
    if(x.value){state=migrateState(x.value);localStorage.setItem(KEY,JSON.stringify(persistedState()));dbConfigReady=true;renderAll();return}
    await post('/api/settings/set',{key:'secondary_metrics',value:persistedState()});dbConfigReady=true;
  }catch(e){console.warn('SQLite config load failed; using browser fallback',e)}
}
function metricById(id){return state.metrics.find(m=>m.id===id)}
function publicMetrics(type){return state.metrics.filter(m=>m.type===type&&!m.internal)}

function cube(c){return (BASE.cubes||{})[c.channel_id]||{}}
function bucket(c,scope,value,window){return ((((cube(c)[scope]||{})[value]||{})[window])||{})}
function parseFilterKey(k){const [scope,val]=String(k||'').split(':');return {scope,val}}
function videoSpecValue(c,spec){
  const w=spec.window||'all',agg=spec.aggregation||'count';
  let b=bucket(c,'all','all',w);
  if(spec.filter_label){const z=parseFilterKey(spec.filter_label);b=bucket(c,z.scope,z.val,w)}
  if(agg==='count'||spec.source_field==='video_count')return agg==='count'?Number(b.count||0):null;
  const stat=((b[spec.source_field]||{})[agg]);return stat===undefined?null:Number(stat);
}
function constructedValue(c,m){
  if(m.custom_values&&Object.prototype.hasOwnProperty.call(m.custom_values,c.channel_id))return m.custom_values[c.channel_id];
  return videoSpecValue(c,m);
}
function ratioRefValue(c,ref,seen){
  if(!ref)return null;
  if(ref.kind==='creator_fact')return Number(c[ref.key]??0);
  if(ref.kind==='constructed')return metricValue(c,metricById(ref.key),seen);
  return null;
}
function metricValue(c,m,seen=new Set()){
  if(!m)return null;if(seen.has(m.id))return null;seen.add(m.id);
  if(m.type==='constructed')return constructedValue(c,m);
  if(m.type==='ratio'){
    if(m.numerator_ref&&m.denominator_ref){const a=ratioRefValue(c,m.numerator_ref,new Set(seen)),b=ratioRefValue(c,m.denominator_ref,new Set(seen));return b!==null&&Number(b)!==0?Number(a||0)/Number(b):null}
    // read-only fallback for imported legacy configs
    if(m.numerator_spec&&m.denominator_spec){const a=videoSpecValue(c,m.numerator_spec),b=videoSpecValue(c,m.denominator_spec);return b?Number(a||0)/Number(b):null}
  }
  return null;
}
function allValues(c){const out={};for(const m of state.metrics)out[m.id]=metricValue(c,m,new Set());return out}

function compare(v,op,t){v=Number(v);t=Number(t);if(Number.isNaN(v)||Number.isNaN(t))return false;return op==='gt'?v>t:op==='gte'?v>=t:op==='lt'?v<t:op==='lte'?v<=t:op==='eq'?v===t:v!==t}
function metricOptions(type){
  if(type==='creator_fact')return Object.entries(creatorFactFields);
  if(type==='creator_label')return Object.entries(creatorLabels);
  return publicMetrics(type).map(m=>[m.id,m.name]);
}
function refValue(c,type,key){if(type==='creator_fact'||type==='creator_label')return Number(c[key]??0);return metricValue(c,metricById(key),new Set())}
function conditionPass(c,cond){
  if(cond.metric_type==='geography'){
    const code=c.country_resolved||c.country_api||'',row=geoCountry.get(code);
    if(!row||row.group!==cond.metric_key)return false;
    return cond.value?code===cond.value:true;
  }
  const v=refValue(c,cond.metric_type,cond.metric_key);
  if(cond.metric_type==='creator_label')return cond.op==='falsy'?!Number(v):!!Number(v);
  return compare(v,cond.op,cond.value);
}
function chainPass(conditions,c){if(!conditions||!conditions.length)return true;let acc=conditionPass(c,conditions[0]);for(let i=1;i<conditions.length;i++){const b=conditionPass(c,conditions[i]),j=(conditions[i].join||'AND').toUpperCase();acc=j==='OR'?(acc||b):j==='NOT'?(acc&&!b):(acc&&b)}return acc}
function rulePass(r,c){return chainPass(r.conditions||[],c)}

const VALID_WINDOWS=new Set(['all','7','30','60','90','180','365','custom']);
const VALID_AGGS=new Set(['count','sum','avg','median','max','min']);
const clone=x=>JSON.parse(JSON.stringify(x));
function defaultConstructedDraft(){return {source_kind:'video_fact',source_field:'current_views',filter_label:'',window:'all',from_date:'',to_date:'',aggregation:'count',last_non_count_aggregation:'median'}}
function defaultRatioDraft(){return {numerator_ref:null,denominator_ref:null}}
let metricDrafts={constructed:defaultConstructedDraft(),ratio:defaultRatioDraft()};
let renderedMetricType='constructed',metricSaving=false;

function timeOptions(selected='all'){
  const invalid=selected&&!VALID_WINDOWS.has(selected)?`<option value="${esc(selected)}" selected>⚠ 配置异常：${esc(selected)}</option>`:'';
  return invalid+['all','7','30','60','90','180','365','custom'].map(w=>`<option value="${w}" ${w===selected?'selected':''}>${winNames[w]}</option>`).join('');
}
function aggOptions(selected='count',source='current_views'){
  const aggs=source==='video_count'?['count']:['count','sum','avg','median','max','min'];
  const invalid=selected&&!aggs.includes(selected)?`<option value="${esc(selected)}" selected>⚠ 配置异常：${esc(selected)}</option>`:'';
  return invalid+aggs.map(a=>`<option value="${a}" ${a===selected?'selected':''}>${aggNames[a]}</option>`).join('');
}
function videoBuilder(spec={}){
  const selectedSource=spec.source_field||'current_views',selectedFilter=spec.filter_label||'',selectedWindow=spec.window||'all',selectedAgg=spec.aggregation||'count';
  const badSource=selectedSource&&!Object.prototype.hasOwnProperty.call(videoFactFields,selectedSource)?`<option value="${esc(selectedSource)}" selected>⚠ 配置异常：${esc(selectedSource)}</option>`:'';
  const src=badSource+Object.entries(videoFactFields).map(([k,v])=>`<option value="${k}" ${k===selectedSource?'selected':''}>${esc(v)}</option>`).join('');
  const badFilter=selectedFilter&&!Object.prototype.hasOwnProperty.call(videoFilters,selectedFilter)?`<option value="${esc(selectedFilter)}" selected>⚠ 配置异常：${esc(selectedFilter)}</option>`:'';
  const filters=badFilter+Object.entries(videoFilters).map(([k,v])=>`<option value="${k}" ${k===selectedFilter?'selected':''}>${esc(v)}</option>`).join('');
  return `<div class="note">数据粒度：视频 → 聚合后输出每位博主一个数值。保存时会严格校验当前表单，不再静默回退到默认值。</div>
    <div class="form-row"><label>视频客观数据</label><select id="constructedSource">${src}</select></div>
    <div class="form-row"><label>视频筛选</label><select id="constructedFilter"><option value="" ${selectedFilter===''?'selected':''}>全部视频</option>${filters}</select></div>
    <div class="form-row"><label>时间范围</label><select id="constructedWindow">${timeOptions(selectedWindow)}</select></div>
    <div id="constructedCustomDates" class="form-row" style="display:${selectedWindow==='custom'?'grid':'none'}"><label>精确日期</label><div class="inline"><input id="constructedFrom" type="date" value="${esc(spec.from_date||'')}"><span>至</span><input id="constructedTo" type="date" value="${esc(spec.to_date||'')}"></div></div>
    <div class="form-row"><label>聚合方式</label><select id="constructedAgg">${aggOptions(selectedAgg,selectedSource)}</select></div>`;
}
function validRatioRef(ref){
  if(!ref||!ref.kind||!ref.key)return false;
  if(ref.kind==='creator_fact')return Object.prototype.hasOwnProperty.call(creatorFactFields,ref.key);
  if(ref.kind==='constructed')return !!metricById(ref.key)&&metricById(ref.key).type==='constructed';
  return false;
}
function ratioRefEntries(){
  refreshFieldRegistry();
  return fieldRegistry.filter(e=>(e.kind==='creator_fact'&&e.ratio)||(e.kind==='constructed')).map(e=>({...e,id:e.kind==='creator_fact'?`creator_fact:${e.key}`:`constructed:${e.key}`}));
}
function ratioRefOptions(selected={}){
  const cur=selected.kind&&selected.key?`${selected.kind}:${selected.key}`:'';const tmp=document.createElement('select');CDHFieldRegistry.optionGroups(tmp,ratioRefEntries(),cur,'请选择指标');return tmp.innerHTML;
}
function ratioBuilder(metric={}){
  return `<div class="note">比值指标不直接聚合视频。请先把视频数据构建成博主级指标，再在这里做 A ÷ B。保存时不会自动选择默认分子或分母。</div>
    <div class="form-row"><label>分子</label><select id="ratioNumerator">${ratioRefOptions(metric.numerator_ref||{})}</select></div>
    <div class="form-row"><label>分母</label><select id="ratioDenominator">${ratioRefOptions(metric.denominator_ref||{})}</select></div>`;
}
function syncCurrentMetricDraft(){
  if(renderedMetricType==='constructed'){
    const source=document.getElementById('constructedSource'),filter=document.getElementById('constructedFilter'),win=document.getElementById('constructedWindow'),agg=document.getElementById('constructedAgg');
    if(!source||!filter||!win||!agg)return;
    const d=metricDrafts.constructed||defaultConstructedDraft();
    d.source_kind='video_fact';d.source_field=source.value;d.filter_label=filter.value;d.window=win.value;d.aggregation=agg.value;
    d.from_date=document.getElementById('constructedFrom')?.value||'';d.to_date=document.getElementById('constructedTo')?.value||'';
    if(agg.value&&agg.value!=='count')d.last_non_count_aggregation=agg.value;
    metricDrafts.constructed=d;
  }else if(renderedMetricType==='ratio'){
    metricDrafts.ratio={numerator_ref:readRatioRefLoose('ratioNumerator'),denominator_ref:readRatioRefLoose('ratioDenominator')};
  }
}
function bindConstructed(){
  const source=document.getElementById('constructedSource'),filter=document.getElementById('constructedFilter'),agg=document.getElementById('constructedAgg'),win=document.getElementById('constructedWindow'),dates=document.getElementById('constructedCustomDates'),from=document.getElementById('constructedFrom'),to=document.getElementById('constructedTo');
  if(source){const vEntries=()=>regEntries(e=>e.kind==='video_fact').map(e=>({...e,id:e.key}));mountFieldPicker(source,vEntries,'metric-builder-video','选择视频客观数据')}
  if(source&&agg)source.onchange=()=>{
    const oldAgg=agg.value,d=metricDrafts.constructed||defaultConstructedDraft();
    if(oldAgg&&oldAgg!=='count')d.last_non_count_aggregation=oldAgg;
    const desired=source.value==='video_count'?'count':(d.last_non_count_aggregation||oldAgg||'count');
    agg.innerHTML=aggOptions(desired,source.value);agg.value=source.value==='video_count'?'count':desired;metricDrafts.constructed=d;syncCurrentMetricDraft();
  };
  if(agg)agg.onchange=()=>syncCurrentMetricDraft();
  if(filter)filter.onchange=()=>syncCurrentMetricDraft();
  if(win&&dates)win.onchange=()=>{dates.style.display=win.value==='custom'?'grid':'none';syncCurrentMetricDraft()};
  if(from)from.onchange=()=>syncCurrentMetricDraft();if(to)to.onchange=()=>syncCurrentMetricDraft();
}
function bindRatio(){
  const a=document.getElementById('ratioNumerator'),b=document.getElementById('ratioDenominator'),entries=()=>ratioRefEntries();
  if(a){mountFieldPicker(a,entries,'ratio-numerator','选择分子');a.onchange=()=>syncCurrentMetricDraft()}if(b){mountFieldPicker(b,entries,'ratio-denominator','选择分母');b.onchange=()=>syncCurrentMetricDraft()}
}
function renderMetricDynamic(metric=null){
  const out=document.getElementById('metricOutputType').value,box=document.getElementById('metricDynamic');
  if(metric){
    if(out==='ratio')metricDrafts.ratio={numerator_ref:clone(metric.numerator_ref||null),denominator_ref:clone(metric.denominator_ref||null)};
    else metricDrafts.constructed={...defaultConstructedDraft(),...clone(metric),last_non_count_aggregation:metric.aggregation&&metric.aggregation!=='count'?metric.aggregation:(metricDrafts.constructed?.last_non_count_aggregation||'median')};
  }
  renderedMetricType=out;
  if(out==='ratio'){box.innerHTML=ratioBuilder(metricDrafts.ratio||defaultRatioDraft());bindRatio();return}
  box.innerHTML=videoBuilder(metricDrafts.constructed||defaultConstructedDraft());bindConstructed();
}
function requireElement(id,label){const el=document.getElementById(id);if(!el)throw new Error(`${label}控件不存在，请刷新页面后重试`);return el}
function readConstructedSpec(){
  const source=requireElement('constructedSource','视频客观数据').value,filter=requireElement('constructedFilter','视频筛选').value,w=requireElement('constructedWindow','时间范围').value,aggregation=requireElement('constructedAgg','聚合方式').value;
  if(!Object.prototype.hasOwnProperty.call(videoFactFields,source))throw new Error(`视频客观数据配置无效：${source||'空值'}`);
  if(filter&&!Object.prototype.hasOwnProperty.call(videoFilters,filter))throw new Error(`视频筛选配置无效：${filter}`);
  if(!VALID_WINDOWS.has(w))throw new Error(`时间范围配置无效：${w||'空值'}`);
  if(!VALID_AGGS.has(aggregation))throw new Error(`聚合方式配置无效：${aggregation||'空值'}`);
  if(source==='video_count'&&aggregation!=='count')throw new Error('“视频数量”只能使用 Count 聚合');
  const allowed=source==='video_count'?['count']:['count','sum','avg','median','max','min'];if(!allowed.includes(aggregation))throw new Error(`当前视频字段不支持 ${aggregation}`);
  const from=w==='custom'?requireElement('constructedFrom','开始日期').value:'',to=w==='custom'?requireElement('constructedTo','结束日期').value:'';
  return {source_kind:'video_fact',source_field:source,filter_label:filter,window:w,from_date:from,to_date:to,aggregation};
}
function readRatioRefLoose(id){const el=document.getElementById(id);if(!el)return null;const raw=el.value||'',i=raw.indexOf(':');return i>0?{kind:raw.slice(0,i),key:raw.slice(i+1)}:null}
function readRatioRef(id,label){const el=requireElement(id,label),raw=el.value||'',i=raw.indexOf(':');if(i<=0)throw new Error(`请选择${label}`);const ref={kind:raw.slice(0,i),key:raw.slice(i+1)};if(!validRatioRef(ref))throw new Error(`${label}配置无效，请重新选择`);return ref}
function validateDates(spec){if(spec.window!=='custom')return true;if(!spec.from_date||!spec.to_date){alert('指定日期范围必须同时填写开始日期和结束日期');return false}if(spec.from_date>spec.to_date){alert('开始日期不能晚于结束日期');return false}return true}
function metricComparable(m){
  if(m.type==='constructed')return {id:m.id,name:m.name,group:m.group||'',description:m.description||'',type:m.type,visible:!!m.visible,source_kind:m.source_kind,source_field:m.source_field,filter_label:m.filter_label,window:m.window,from_date:m.from_date||'',to_date:m.to_date||'',aggregation:m.aggregation};
  return {id:m.id,name:m.name,group:m.group||'',description:m.description||'',type:m.type,visible:!!m.visible,numerator_ref:m.numerator_ref||null,denominator_ref:m.denominator_ref||null};
}
function resetMetricDrafts(){metricDrafts={constructed:defaultConstructedDraft(),ratio:defaultRatioDraft()};renderedMetricType='constructed'}
function clearMetric(){document.getElementById('metricEditId').value='';document.getElementById('metricName').value='';document.getElementById('metricGroup').value='';document.getElementById('metricDescription').value='';document.getElementById('metricOutputType').value='constructed';document.getElementById('metricVisible').value='1';document.getElementById('metricStatus').textContent='';resetMetricDrafts();renderMetricDynamic()}
async function saveMetric(){
  if(metricSaving)return;
  const btn=document.getElementById('saveMetric'),st=document.getElementById('metricStatus');metricSaving=true;if(btn)btn.disabled=true;
  try{
    syncCurrentMetricDraft();
    const id=requireElement('metricEditId','编辑状态').value,name=requireElement('metricName','指标名称').value.trim(),group=requireElement('metricGroup','指标分组').value.trim(),description=requireElement('metricDescription','业务说明').value.trim(),type=requireElement('metricOutputType','输出类型').value,visible=requireElement('metricVisible','显示状态').value==='1';
    if(!name)throw new Error('请输入指标名称');if(!['constructed','ratio'].includes(type))throw new Error('输出类型无效');
    const old=metricById(id),m={id:id||uid('m'),name,group,description,type,visible,created_at:old?.created_at||iso(),version:(old?.version||0)+1,updated_at:iso()};
    if(type==='constructed'){
      Object.assign(m,readConstructedSpec());if(!validateDates(m))return;
      if(m.window==='custom'){
        if(!interactive)throw new Error('精确日期范围需要通过 start-dashboard.cmd 打开交互模式后构建');
        st.textContent='正在从本地 SQLite 聚合视频数据…';const x=await post('/api/metric/evaluate',{spec:m});m.custom_values=x.values||{};
      }
    }else{
      m.numerator_ref=readRatioRef('ratioNumerator','分子');m.denominator_ref=readRatioRef('ratioDenominator','分母');
      if(m.numerator_ref.kind==='constructed'&&m.numerator_ref.key===m.id)throw new Error('比值指标不能引用自身');
      if(m.denominator_ref.kind==='constructed'&&m.denominator_ref.key===m.id)throw new Error('比值指标不能引用自身');
    }
    const expected=metricComparable(m),backup=old?clone(old):null;
    if(old)Object.assign(old,m);else state.metrics.push(m);
    localStorage.setItem(KEY,JSON.stringify(state));
    const disk=JSON.parse(localStorage.getItem(KEY)||'{}'),stored=(disk.metrics||[]).find(x=>x.id===m.id);
    if(!stored||JSON.stringify(metricComparable(stored))!==JSON.stringify(expected)){
      if(old&&backup)Object.assign(old,backup);else state.metrics=state.metrics.filter(x=>x.id!==m.id);
      localStorage.setItem(KEY,JSON.stringify(state));throw new Error('保存后一致性校验失败，已取消本次保存，请重试');
    }
    if(interactive)await saveStateToDb();clearMetric();renderAll();st.textContent=`已按当前设置保存：${m.name}${interactive?' · 已写入 SQLite':' · 浏览器临时保存'}`;
  }catch(e){st.textContent=e.message||String(e);alert(e.message||String(e))}
  finally{metricSaving=false;if(btn)btn.disabled=false}
}
function editMetric(id){
  const m=metricById(id);if(!m||m.internal)return;
  document.getElementById('metricEditId').value=id;document.getElementById('metricName').value=m.name;document.getElementById('metricGroup').value=m.group||'';document.getElementById('metricDescription').value=m.description||'';document.getElementById('metricVisible').value=m.visible?'1':'0';document.getElementById('metricOutputType').value=m.type;renderMetricDynamic(m);
}
function specDesc(s){const src=videoFactFields[s.source_field]||s.source_field,fl=s.filter_label?' · '+(videoFilters[s.filter_label]||s.filter_label):'',w=s.window==='custom'?`${s.from_date||'?'} 至 ${s.to_date||'?'}`:(winNames[s.window]||s.window);return `${src}${fl} · ${w} · ${aggNames[s.aggregation]||s.aggregation}`}
function refDesc(ref){if(!ref)return '—';if(ref.kind==='creator_fact')return creatorFactFields[ref.key]||ref.key;const m=metricById(ref.key);return m?.name||ref.key}
function desc(m){if(m.type==='ratio')return `比值：${refDesc(m.numerator_ref)} ÷ ${refDesc(m.denominator_ref)}`;return `视频聚合：${specDesc(m)}`}
function metricDependencies(id){
 const deps=[];
 for(const m of state.metrics||[]){if(m.id===id)continue;if(m.numerator_ref?.kind==='constructed'&&m.numerator_ref.key===id)deps.push(`比值指标：${m.name}`);if(m.denominator_ref?.kind==='constructed'&&m.denominator_ref.key===id)deps.push(`比值指标：${m.name}`)}
 for(const r of state.rules||[])if((r.conditions||[]).some(c=>['constructed','ratio'].includes(c.metric_type)&&c.metric_key===id))deps.push(`规则：${r.name}`);
 if((state.filters||[]).some(c=>['constructed','ratio'].includes(c.metric_type)&&c.metric_key===id))deps.push('当前应用筛选');
 return deps;
}
function catalogGroups(items){return [...new Set(items.map(x=>(x.group||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'))}
function fillGroupFilter(sel,groups,cur){if(!sel)return;sel.innerHTML='<option value="">全部分组</option><option value="__ungrouped__">未分组</option>'+groups.map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join('');if(cur==='__ungrouped__'||groups.includes(cur))sel.value=cur}
function catalogMatchGroup(item,val){return !val||(val==='__ungrouped__'?!(item.group||'').trim():(item.group||'')===val)}
function catalogCompare(a,b,key){if(key==='name')return String(a.name||'').localeCompare(String(b.name||''),'zh-CN',{numeric:true,sensitivity:'base'});if(key==='group')return String(a.group||'').localeCompare(String(b.group||''),'zh-CN',{numeric:true,sensitivity:'base'})||String(a.name||'').localeCompare(String(b.name||''),'zh-CN');if(key==='type')return String(a.type||'').localeCompare(String(b.type||''))||String(a.name||'').localeCompare(String(b.name||''),'zh-CN');if(key==='conditions')return Number((a.conditions||[]).length)-Number((b.conditions||[]).length);return String(a.updated_at||'').localeCompare(String(b.updated_at||''))}
function updateMetricSelected(){const el=document.getElementById('metricCatalogSelected');if(el)el.textContent=`已选择 ${metricCatalogSelected.size} 项`}
function updateRuleSelected(){const el=document.getElementById('ruleCatalogSelected');if(el)el.textContent=`已选择 ${ruleCatalogSelected.size} 项`}
function moveMetricGroup(group){if(!metricCatalogSelected.size)return alert('请先选择指标');for(const m of state.metrics)if(metricCatalogSelected.has(m.id)&&!m.internal){m.group=group;m.updated_at=iso()}metricCatalogSelected.clear();metricCatalogPage=1;persist()}
function moveRuleGroup(group){if(!ruleCatalogSelected.size)return alert('请先选择规则');for(const r of state.rules)if(ruleCatalogSelected.has(r.id)){r.group=group;r.updated_at=iso()}ruleCatalogSelected.clear();ruleCatalogPage=1;persist()}
function renderMetrics(){
  const box=document.getElementById('metricList'),gf=document.getElementById('metricGroupFilter'),all=state.metrics.filter(m=>!m.internal),groups=catalogGroups(all),cur=gf?.value||'';fillGroupFilter(gf,groups,cur);const dl=document.getElementById('metricGroupOptions');if(dl)dl.innerHTML=groups.map(g=>`<option value="${esc(g)}"></option>`).join('');
  const q=(document.getElementById('metricCatalogSearch')?.value||'').trim().toLowerCase(),key=document.getElementById('metricCatalogSort')?.value||'updated_at',desc=document.getElementById('metricCatalogDir')?.value!=='asc';let items=all.filter(m=>catalogMatchGroup(m,gf?.value||'')&&(!q||`${m.name||''} ${m.group||''} ${m.description||''}`.toLowerCase().includes(q)));items.sort((a,b)=>(desc?-1:1)*catalogCompare(a,b,key));
  const pages=Math.max(1,Math.ceil(items.length/metricCatalogSize));metricCatalogPage=Math.max(1,Math.min(pages,metricCatalogPage));const start=(metricCatalogPage-1)*metricCatalogSize,shown=items.slice(start,start+metricCatalogSize);const summary=document.getElementById('metricCatalogSummary');if(summary)summary.textContent=`共 ${items.length} 项 · 当前 ${items.length?start+1:0}-${Math.min(start+metricCatalogSize,items.length)}`;
  if(!shown.length)box.innerHTML='<div class="empty">没有符合当前条件的已构建指标。</div>';else box.innerHTML=shown.map(m=>{const deps=metricDependencies(m.id),meta=[m.group?`分组：${m.group}`:'未分组',descMetric(m),`v${m.version||1}`,`更新：${m.updated_at||'—'}`].join(' · ');return `<div class="metric-item"><div class="metric-item-head"><div class="metric-item-select"><input type="checkbox" data-select-metric="${m.id}" ${metricCatalogSelected.has(m.id)?'checked':''}><div><div class="metric-item-title">${esc(m.name)} <span class="badge-fact">${typeNames[m.type]}</span></div><div class="metric-meta">${esc(meta)}</div>${m.description?`<div class="small">${esc(m.description)}</div>`:''}${deps.length?`<div class="small">被引用：${esc(deps.join('；'))}</div>`:''}</div></div><div class="inline"><button class="btn" data-toggle="${m.id}">${m.visible?'隐藏':'显示'}</button><button class="btn" data-edit="${m.id}">编辑</button><button class="btn danger" data-del="${m.id}" ${deps.length?'disabled title="存在依赖，不能删除"':''}>删除</button></div></div></div>`}).join('');
  box.querySelectorAll('[data-select-metric]').forEach(cb=>cb.onchange=()=>{if(cb.checked)metricCatalogSelected.add(cb.dataset.selectMetric);else metricCatalogSelected.delete(cb.dataset.selectMetric);updateMetricSelected()});box.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=()=>{const m=metricById(b.dataset.toggle);m.visible=!m.visible;m.updated_at=iso();persist()});box.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>editMetric(b.dataset.edit));box.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{const id=b.dataset.del,deps=metricDependencies(id);if(deps.length)return alert('该指标仍被以下对象引用，不能删除：\n'+deps.join('\n'));if(confirm('删除该指标？')){state.metrics=state.metrics.filter(x=>x.id!==id);metricCatalogSelected.delete(id);persist()}});updateMetricSelected();CDHTableTools.renderPager({page:metricCatalogPage,pages,go:p=>{metricCatalogPage=p;renderMetrics()},firstId:'metricCatalogFirst',prevId:'metricCatalogPrev',nextId:'metricCatalogNext',lastId:'metricCatalogLast',buttonsId:'metricCatalogButtons',inputId:'metricCatalogPageInput',jumpId:'metricCatalogJump',pageInfoId:'metricCatalogPageInfo'});
}
function descMetric(m){if(m.type==='ratio')return `比值：${refDesc(m.numerator_ref)} ÷ ${refDesc(m.denominator_ref)}`;return `视频聚合：${specDesc(m)}`}

function conditionRow(c={},i=0,kind='rule'){
  const d=document.createElement('div');d.className='condition-row';const geoOpt=kind==='filter'?'<option value="geography">地理位置</option>':'';
  d.innerHTML=(i===0?'<span class="small">起始</span>':'<select class="c-join"><option>AND</option><option>OR</option><option>NOT</option></select>')+`<select class="c-type"><option value="creator_fact">博主客观数据</option><option value="creator_label">博主标签</option><option value="constructed">构建指标</option><option value="ratio">比值指标</option>${geoOpt}</select><select class="c-metric"></select><select class="c-op"></select><input class="c-value" type="number" step="any" placeholder="阈值"><button class="btn danger">×</button>`;
  const ts=d.querySelector('.c-type'),ms=d.querySelector('.c-metric'),op=d.querySelector('.c-op'),val=d.querySelector('.c-value');
  ts.value=({objective:'creator_fact',aggregate_label:'creator_label'}[c.metric_type]||c.metric_type||'creator_fact');
  function fillCountry(selected=''){const g=ms.value,arr=g?(GEO.countries||[]).filter(x=>x.group===g):[];op.innerHTML=(g?'<option value="">全部该区域</option>':'<option value="">请先选择区域</option>')+arr.map(x=>`<option value="${x.code}">${esc(x.name_zh)} (${x.code})</option>`).join('');if(selected&&arr.some(x=>x.code===selected))op.value=selected}
  function fill(key='',country=''){
    if(ts.value==='geography'){
      ms.innerHTML='<option value="">选择区域</option>'+(GEO.groups||[]).map(g=>`<option value="${g.id}">${esc(g.name)}</option>`).join('');if(key&&(GEO.groups||[]).some(g=>g.id===key))ms.value=key;fillCountry(country);ms.onchange=()=>fillCountry('');val.style.display='none';return;
    }
    ms.onchange=null;const entries=metricFieldEntries(ts.value);if(entries.length&&window.CDHFieldRegistry)CDHFieldRegistry.optionGroups(ms,entries,key,'请选择字段');else ms.innerHTML='<option value="">暂无该类指标</option>';if(key&&entries.some(x=>x.id===key))ms.value=key;mountFieldPicker(ms,()=>metricFieldEntries(ts.value),`condition-${kind}-${ts.value}`,'选择字段');
    if(ts.value==='creator_label'){
      op.innerHTML='<option value="truthy">存在 / 是</option><option value="falsy">不存在 / 否</option>';op.style.display='';val.style.display='none';
    }else{
      op.innerHTML='<option value="gte">≥</option><option value="gt">&gt;</option><option value="lte">≤</option><option value="lt">&lt;</option><option value="eq">=</option><option value="neq">≠</option>';op.style.display='';val.style.display='';
    }
  }
  fill(c.metric_key||'',c.value||'');ts.onchange=()=>fill();if(c.join&&d.querySelector('.c-join'))d.querySelector('.c-join').value=c.join;if(ts.value!=='geography'&&c.op)op.value=c.op;if(!['geography','creator_label'].includes(ts.value))val.value=c.value??'';d.querySelector('button').onclick=()=>{d.remove();renumberConditions(kind)};return d;
}
function renumberConditions(kind){const box=document.getElementById(kind==='rule'?'ruleConditions':'resultFilterConditions'),data=readConditions(kind,true);box.innerHTML='';data.forEach(c=>box.appendChild(conditionRow(c,box.children.length,kind)));if(!box.children.length)addCondition({},kind)}
function addCondition(c={},kind='rule'){const box=document.getElementById(kind==='rule'?'ruleConditions':'resultFilterConditions');box.appendChild(conditionRow(c,box.children.length,kind))}
function readConditions(kind='rule',includeBlank=false){
  const box=document.getElementById(kind==='rule'?'ruleConditions':'resultFilterConditions');
  return [...box.children].map((d,i)=>{const type=d.querySelector('.c-type').value,key=d.querySelector('.c-metric').value,join=i===0?'':(d.querySelector('.c-join')?.value||'AND');if(type==='geography')return {join,metric_type:type,metric_key:key,op:'geo',value:d.querySelector('.c-op').value};if(type==='creator_label')return {join,metric_type:type,metric_key:key,op:d.querySelector('.c-op').value||'truthy',value:''};return {join,metric_type:type,metric_key:key,op:d.querySelector('.c-op').value,value:d.querySelector('.c-value').value}}).filter(x=>includeBlank?x.metric_key:(x.metric_key&&(x.metric_type==='creator_label'||x.metric_type==='geography'||x.value!=='')));
}
function clearRule(){document.getElementById('ruleEditId').value='';document.getElementById('ruleName').value='';document.getElementById('ruleGroup').value='';document.getElementById('ruleDescription').value='';document.getElementById('ruleConditions').innerHTML='';addCondition({},'rule')}
function saveRule(){const id=document.getElementById('ruleEditId').value,name=document.getElementById('ruleName').value.trim(),group=document.getElementById('ruleGroup').value.trim(),description=document.getElementById('ruleDescription').value.trim(),conditions=readConditions('rule');if(!name)return alert('请输入规则名称');if(!conditions.length)return alert('至少添加一个有效条件');const old=state.rules.find(x=>x.id===id),r={id:id||uid('r'),name,group,description,conditions,created_at:old?.created_at||iso(),version:(old?.version||0)+1,updated_at:iso()};if(old)Object.assign(old,r);else state.rules.push(r);clearRule();persist()}
function editRule(id){const r=state.rules.find(x=>x.id===id);if(!r)return;document.getElementById('ruleEditId').value=id;document.getElementById('ruleName').value=r.name;document.getElementById('ruleGroup').value=r.group||'';document.getElementById('ruleDescription').value=r.description||'';const b=document.getElementById('ruleConditions');b.innerHTML='';(r.conditions||[]).forEach(c=>addCondition(c,'rule'));if(!b.children.length)addCondition({},'rule')}
function renderRules(){
 const box=document.getElementById('ruleList'),sel=document.getElementById('activeRule');sel.innerHTML='<option value="">全部博主（不应用规则）</option>'+state.rules.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join('');sel.value=state.activeRule||'';const gf=document.getElementById('ruleGroupFilter'),groups=catalogGroups(state.rules),cur=gf?.value||'';fillGroupFilter(gf,groups,cur);const dl=document.getElementById('ruleGroupOptions');if(dl)dl.innerHTML=groups.map(g=>`<option value="${esc(g)}"></option>`).join('');const q=(document.getElementById('ruleCatalogSearch')?.value||'').trim().toLowerCase(),key=document.getElementById('ruleCatalogSort')?.value||'updated_at',desc=document.getElementById('ruleCatalogDir')?.value!=='asc';let items=state.rules.filter(r=>catalogMatchGroup(r,gf?.value||'')&&(!q||`${r.name||''} ${r.group||''} ${r.description||''}`.toLowerCase().includes(q)));items.sort((a,b)=>(desc?-1:1)*catalogCompare(a,b,key));const pages=Math.max(1,Math.ceil(items.length/ruleCatalogSize));ruleCatalogPage=Math.max(1,Math.min(pages,ruleCatalogPage));const start=(ruleCatalogPage-1)*ruleCatalogSize,shown=items.slice(start,start+ruleCatalogSize),summary=document.getElementById('ruleCatalogSummary');if(summary)summary.textContent=`共 ${items.length} 项 · 当前 ${items.length?start+1:0}-${Math.min(start+ruleCatalogSize,items.length)}`;
 if(!shown.length)box.innerHTML='<div class="empty">没有符合当前条件的规则。</div>';else box.innerHTML=shown.map(r=>{let hit=0;for(const c of creators)if(rulePass(r,c))hit++;return `<div class="metric-item"><div class="metric-item-head"><div class="metric-item-select"><input type="checkbox" data-select-rule="${r.id}" ${ruleCatalogSelected.has(r.id)?'checked':''}><div><div class="metric-item-title">${esc(r.name)}${r.group?` <span class="badge-label">${esc(r.group)}</span>`:''}</div><div class="metric-meta">博主级规则 · ${r.conditions.length} 条件 · 命中 ${hit} · 更新 ${esc(r.updated_at||'—')}</div>${r.description?`<div class="small">${esc(r.description)}</div>`:''}</div></div><div class="inline"><button class="btn primary" data-apply="${r.id}">应用</button><button class="btn" data-editr="${r.id}">编辑</button><button class="btn danger" data-delr="${r.id}">删除</button></div></div></div>`}).join('');box.querySelectorAll('[data-select-rule]').forEach(cb=>cb.onchange=()=>{if(cb.checked)ruleCatalogSelected.add(cb.dataset.selectRule);else ruleCatalogSelected.delete(cb.dataset.selectRule);updateRuleSelected()});box.querySelectorAll('[data-apply]').forEach(b=>b.onclick=()=>{state.activeRule=b.dataset.apply;resultPage=1;renderAll()});box.querySelectorAll('[data-editr]').forEach(b=>b.onclick=()=>editRule(b.dataset.editr));box.querySelectorAll('[data-delr]').forEach(b=>b.onclick=()=>{state.rules=state.rules.filter(x=>x.id!==b.dataset.delr);ruleCatalogSelected.delete(b.dataset.delr);if(state.activeRule===b.dataset.delr)state.activeRule='';persist()});updateRuleSelected();CDHTableTools.renderPager({page:ruleCatalogPage,pages,go:p=>{ruleCatalogPage=p;renderRules()},firstId:'ruleCatalogFirst',prevId:'ruleCatalogPrev',nextId:'ruleCatalogNext',lastId:'ruleCatalogLast',buttonsId:'ruleCatalogButtons',inputId:'ruleCatalogPageInput',jumpId:'ruleCatalogJump',pageInfoId:'ruleCatalogPageInfo'});
}

function resultSortEntries(){
  refreshFieldRegistry();
  return fieldRegistry.filter(e=>e.grain==='creator'&&e.sortable&&e.kind!=='creator_label'&&(e.kind!=='constructed'&&e.kind!=='ratio'||state.metrics.find(m=>m.id===e.key)?.visible));
}
function fillResultSort(){const sel=document.getElementById('resultSort'),cur=sel.value||'subscriber_count',entries=resultSortEntries();CDHFieldRegistry.optionGroups(sel,entries,cur);if(![...sel.options].some(o=>o.value===cur))sel.value='subscriber_count';mountFieldPicker(sel,resultSortEntries,'secondary-result-sort','选择排序字段')}
function resultSortValue(x,key){const c=x.c;if(key.startsWith('metric:'))return x.vals[key.slice(7)];if(key==='channel_title')return c.channel_title||c.handle||c.channel_id||'';if(key==='country')return c.country_resolved||c.country_api||'';if(key==='last_synced_at')return c.last_synced_at||'';return Number(c[key]??0)}
function renderResultFilters(){const box=document.getElementById('resultFilterConditions');box.innerHTML='';(state.filters||[]).forEach(c=>addCondition(c,'filter'));if(!box.children.length)addCondition({},'filter')}
function identityPills(c){const a=[c.partnered_ugphone?['合作过博主','identity-partnered']:['未合作博主','identity-unpartnered'],c.ldcloud_creator?['LDCloud合作博主','identity-competitor']:null,c.redfinger_creator?['RedFinger合作博主','identity-competitor']:null,c.vsphone_creator?['VSPhone合作博主','identity-competitor']:null,c.suspected_inactive_partner?['疑似不再合作','identity-suspected']:null].filter(Boolean);return a.map(([t,k])=>`<span class="pill ${k}">${esc(t)}</span>`).join('')}
function fixedPlaybackValue(c,filterLabel=''){return videoSpecValue(c,{source_kind:'video_fact',source_field:'current_views',filter_label:filterLabel,window:'all',aggregation:'median'})}
function sortMetric(sortKey){if(!sortKey.startsWith('metric:'))return null;return metricById(sortKey.slice(7))}
function fixedKindForMetric(m){if(!m||m.type!=='constructed'||m.source_kind!=='video_fact'||m.source_field!=='current_views'||(m.window||'all')!=='all'||(m.aggregation||'count')!=='median')return '';const f=m.filter_label||'';if(!f)return 'all';if(f==='role:ugphone'||f==='brand:ugphone')return 'ugphone';if(f==='role:competitor')return 'competitor';return ''}
function sortHeaderClass(sortKey,key){return sortKey===key?' sort-active':''}
function renderResults(){
  fillResultSort();const sortKey=document.getElementById('resultSort').value,sortM=sortMetric(sortKey),fixedSort=fixedKindForMetric(sortM),head=document.getElementById('resultHead');
  const coreKeys=new Set(['channel_title','country','subscriber_count','channel_view_count','stored_videos','last_synced_at']);
  const activeBase=new Set(),filterExtras=[],extraSeen=new Set();
  for(const f of (state.filters||[])){
    if(f.metric_type==='geography'){activeBase.add('country');continue}
    if(f.metric_type==='creator_label'){activeBase.add('identity');continue}
    if(f.metric_type==='creator_fact'){
      if(coreKeys.has(f.metric_key))activeBase.add(f.metric_key);
      else if(creatorFactFields[f.metric_key]&&!extraSeen.has(`fact:${f.metric_key}`)){extraSeen.add(`fact:${f.metric_key}`);filterExtras.push({kind:'fact',key:f.metric_key,name:creatorFactFields[f.metric_key]})}
      continue;
    }
    if(['constructed','ratio'].includes(f.metric_type)){
      const m=metricById(f.metric_key);if(m&&!extraSeen.has(`metric:${m.id}`)){extraSeen.add(`metric:${m.id}`);filterExtras.push({kind:'metric',key:m.id,name:m.name})}
    }
  }
  const extraSortMetric=sortM&&!fixedSort?sortM:null;
  const extraSortFact=!sortM&&!coreKeys.has(sortKey)&&creatorFactFields[sortKey]?{key:sortKey,name:creatorFactFields[sortKey]}:null;
  const hcls=(key,sort=false)=>`${sort?' sort-active':''}${activeBase.has(key)?' filter-sort-active':''}`.trim();
  const filterHeads=filterExtras.map(x=>`<th class="filter-sort-active" title="当前筛选指标" data-field="${esc(x.kind==='metric'?'metric:'+x.key:x.key)}">${esc(x.name)}</th>`).join('');
  const sortIsFilter=extraSortMetric?extraSeen.has(`metric:${extraSortMetric.id}`):extraSortFact?extraSeen.has(`fact:${extraSortFact.key}`):false;
  head.innerHTML='<tr><th class="'+hcls('channel_title',sortKey==='channel_title')+'" data-field="channel_title">博主</th><th class="'+hcls('country',sortKey==='country')+'" data-field="country">国家</th><th class="'+hcls('subscriber_count',sortKey==='subscriber_count')+'" data-field="subscriber_count">订阅数</th><th class="'+hcls('channel_view_count',sortKey==='channel_view_count')+'" data-field="channel_view_count">频道累计播放量</th><th class="'+hcls('stored_videos',sortKey==='stored_videos')+'" data-field="stored_videos">本地视频数</th><th class="'+(activeBase.has('identity')?'filter-sort-active':'')+'" data-field="identity">身份标签</th><th class="fixed-playback '+(fixedSort==='ugphone'?'sort-active':'')+'" title="全部时间 · Median">UgPhone视频播放量<div class="small">Median · 全部时间</div></th><th class="fixed-playback '+(fixedSort==='all'?'sort-active':'')+'" title="全部时间 · Median">总视频播放量<div class="small">Median · 全部时间</div></th><th class="fixed-playback '+(fixedSort==='competitor'?'sort-active':'')+'" title="全部时间 · Median">竞品视频播放量<div class="small">Median · 全部时间</div></th>'+filterHeads+(!sortIsFilter&&extraSortMetric?`<th class="sort-active" title="当前排序指标" data-field="metric:${esc(extraSortMetric.id)}">${esc(extraSortMetric.name)}</th>`:!sortIsFilter&&extraSortFact?`<th class="sort-active" title="当前排序指标" data-field="${esc(extraSortFact.key)}">${esc(extraSortFact.name)}</th>`:'')+'<th class="'+hcls('last_synced_at',sortKey==='last_synced_at')+'" data-field="last_synced_at">最近同步</th></tr>';
  const q=(document.getElementById('metricSearch').value||'').toLowerCase(),rule=state.rules.find(x=>x.id===state.activeRule),rows=[];
  for(const c of creators){if(q&&!`${c.channel_title||''} ${c.handle||''} ${c.country_resolved||c.country_api||''} ${c.channel_id}`.toLowerCase().includes(q))continue;if(!chainPass(state.filters||[],c))continue;const vals=allValues(c);if(rule&&!rulePass(rule,c))continue;rows.push({c,vals})}
  const desc=document.getElementById('resultSortDir').value==='desc';rows.sort((a,b)=>{const av=resultSortValue(a,sortKey),bv=resultSortValue(b,sortKey);let z;if(typeof av==='number'&&typeof bv==='number')z=(Number.isFinite(av)?av:-Infinity)-(Number.isFinite(bv)?bv:-Infinity);else z=String(av??'').localeCompare(String(bv??''),'zh-CN',{numeric:true,sensitivity:'base'});return desc?-z:z});
  const pages=Math.max(1,Math.ceil(rows.length/resultSize));resultPage=Math.max(1,Math.min(pages,resultPage));const start=(resultPage-1)*resultSize,shown=rows.slice(start,start+resultSize),html=[];
  for(const x of shown){const c=x.c,vals=x.vals,channelUrl=`https://www.youtube.com/channel/${encodeURIComponent(c.channel_id)}`,localUrl=`creators/${encodeURIComponent(c.channel_id)}.html`,detail=c.detail_available===false?'':`<div class="small"><a class="link-local" href="${localUrl}">查看详情</a></div>`,ug=fixedPlaybackValue(c,'role:ugphone'),all=fixedPlaybackValue(c,''),comp=fixedPlaybackValue(c,'role:competitor'),filterCells=filterExtras.map(z=>`<td>${fmt(z.kind==='metric'?vals[z.key]:c[z.key])}</td>`).join('');html.push(`<tr><td><a class="link-ext" target="_blank" rel="noopener" href="${channelUrl}"><b>${esc(c.channel_title||c.channel_id)}</b></a><div class="small mono">${esc(c.handle||c.channel_id)}</div>${detail}</td><td>${esc(c.country_resolved||c.country_api||'—')}</td><td>${fmt(c.subscriber_count)}</td><td>${fmt(c.channel_view_count)}</td><td>${fmt(c.stored_videos)}</td><td>${identityPills(c)}</td><td>${fmt(ug)}</td><td>${fmt(all)}</td><td>${fmt(comp)}</td>${filterCells}${!sortIsFilter&&extraSortMetric?`<td>${fmt(vals[extraSortMetric.id])}</td>`:!sortIsFilter&&extraSortFact?`<td>${fmt(c[extraSortFact.key])}</td>`:''}<td class="small">${esc(c.last_synced_at||'—')}</td></tr>`)}
  document.getElementById('resultBody').innerHTML=html.join('')||'<tr><td colspan="99" class="empty">没有命中的博主</td></tr>';const conditionBits=[];if(rule)conditionBits.push(`规则：${rule.name}`);if((state.filters||[]).length)conditionBits.push(`筛选：${state.filters.length} 条`);if(q)conditionBits.push('搜索词已启用');const conditionText=conditionBits.join(' · ');document.getElementById('resultConditionStatus').textContent=conditionText?`当前条件：${conditionText}`:'当前条件：无';document.getElementById('resultSummary').textContent=`共 ${rows.length} 条${rule?` · 当前规则：${rule.name}`:''} · 当前显示 ${rows.length?start+1:0}-${Math.min(start+resultSize,rows.length)}`;CDHTableTools.renderPager({page:resultPage,pages,go:p=>{resultPage=p;renderResults()},firstId:'resultFirst',prevId:'resultPrev',nextId:'resultNext',lastId:'resultLast',buttonsId:'resultPageButtons',inputId:'resultPageInput',jumpId:'resultJump',pageInfoId:'resultPageInfo'});
}

function renderAll(){refreshFieldRegistry();renderMetrics();renderRules();renderResultFilters();renderResults()}

document.getElementById('metricCatalogSearch').oninput=()=>{metricCatalogPage=1;renderMetrics()};document.getElementById('metricGroupFilter').onchange=()=>{metricCatalogPage=1;renderMetrics()};document.getElementById('metricCatalogSort').onchange=()=>{metricCatalogPage=1;renderMetrics()};document.getElementById('metricCatalogDir').onchange=()=>{metricCatalogPage=1;renderMetrics()};document.getElementById('metricCatalogPageSizeOk').onclick=()=>{metricCatalogSize=CDHTableTools.pageSize(document.getElementById('metricCatalogPageSize'),metricCatalogSize);document.getElementById('metricCatalogPageSize').value=String(metricCatalogSize);metricCatalogPage=1;renderMetrics()};document.getElementById('metricMoveGroupBtn').onclick=()=>{const g=document.getElementById('metricMoveGroup').value.trim();if(!g)return alert('请输入目标分组');moveMetricGroup(g)};document.getElementById('metricUngroupBtn').onclick=()=>moveMetricGroup('');
document.getElementById('ruleCatalogSearch').oninput=()=>{ruleCatalogPage=1;renderRules()};document.getElementById('ruleGroupFilter').onchange=()=>{ruleCatalogPage=1;renderRules()};document.getElementById('ruleCatalogSort').onchange=()=>{ruleCatalogPage=1;renderRules()};document.getElementById('ruleCatalogDir').onchange=()=>{ruleCatalogPage=1;renderRules()};document.getElementById('ruleCatalogPageSizeOk').onclick=()=>{ruleCatalogSize=CDHTableTools.pageSize(document.getElementById('ruleCatalogPageSize'),ruleCatalogSize);document.getElementById('ruleCatalogPageSize').value=String(ruleCatalogSize);ruleCatalogPage=1;renderRules()};document.getElementById('ruleMoveGroupBtn').onclick=()=>{const g=document.getElementById('ruleMoveGroup').value.trim();if(!g)return alert('请输入目标分组');moveRuleGroup(g)};document.getElementById('ruleUngroupBtn').onclick=()=>moveRuleGroup('');
document.getElementById('metricOutputType').onchange=()=>{syncCurrentMetricDraft();renderMetricDynamic()};
document.getElementById('saveMetric').onclick=()=>saveMetric();document.getElementById('clearMetric').onclick=clearMetric;
document.getElementById('addRuleCondition').onclick=()=>addCondition({},'rule');document.getElementById('saveRule').onclick=saveRule;document.getElementById('clearRule').onclick=clearRule;
document.getElementById('addResultFilter').onclick=()=>addCondition({},'filter');document.getElementById('applyFilter').onclick=()=>{state.filters=readConditions('filter');persist()};document.getElementById('clearFilter').onclick=()=>{state.filters=[];state.activeRule='';document.getElementById('metricSearch').value='';persist()};
document.getElementById('activeRule').onchange=e=>{state.activeRule=e.target.value;resultPage=1;renderResults()};document.getElementById('metricSearch').oninput=()=>{resultPage=1;renderResults()};document.getElementById('resultSort').onchange=()=>{resultPage=1;renderResults()};document.getElementById('resultSortDir').onchange=()=>{resultPage=1;renderResults()};document.getElementById('resultPageSizeConfirm').onclick=()=>{resultSize=CDHTableTools.pageSize(document.getElementById('resultPageSize'),resultSize);document.getElementById('resultPageSize').value=String(resultSize);resultPage=1;renderResults()};
document.getElementById('resultExport').onclick=()=>{fillResultSort();const sortKey=document.getElementById('resultSort').value,sortM=sortMetric(sortKey),fixedSort=fixedKindForMetric(sortM),coreKeys=new Set(['channel_title','country','subscriber_count','channel_view_count','stored_videos','last_synced_at']),extraSortMetric=sortM&&!fixedSort?sortM:null,extraSortFact=!sortM&&!coreKeys.has(sortKey)&&creatorFactFields[sortKey]?{key:sortKey,name:creatorFactFields[sortKey]}:null,qv=(document.getElementById('metricSearch').value||'').toLowerCase(),rule=state.rules.find(x=>x.id===state.activeRule),arr=[];for(const c of creators){if(qv&&!`${c.channel_title||''} ${c.handle||''} ${c.country_resolved||c.country_api||''} ${c.channel_id}`.toLowerCase().includes(qv))continue;if(!chainPass(state.filters||[],c))continue;const vals=allValues(c);if(rule&&!rulePass(rule,c))continue;arr.push({c,vals})}const desc=document.getElementById('resultSortDir').value==='desc';arr.sort((a,b)=>{const av=resultSortValue(a,sortKey),bv=resultSortValue(b,sortKey);let z;if(typeof av==='number'&&typeof bv==='number')z=(Number.isFinite(av)?av:-Infinity)-(Number.isFinite(bv)?bv:-Infinity);else z=String(av??'').localeCompare(String(bv??''),'zh-CN',{numeric:true,sensitivity:'base'});return desc?-z:z});const data=arr.map(x=>{const c=x.c,o={channel_title:c.channel_title||c.channel_id,channel_id:c.channel_id,country:c.country_resolved||c.country_api||'',subscriber_count:c.subscriber_count,channel_view_count:c.channel_view_count,stored_videos:c.stored_videos,identity:[c.partnered_ugphone?'合作过博主':'未合作博主',c.ldcloud_creator?'LDCloud合作博主':'',c.redfinger_creator?'RedFinger合作博主':'',c.vsphone_creator?'VSPhone合作博主':'',c.suspected_inactive_partner?'疑似不再合作':''].filter(Boolean).join('；'),ugphone_playback_median:fixedPlaybackValue(c,'role:ugphone'),all_playback_median:fixedPlaybackValue(c,''),competitor_playback_median:fixedPlaybackValue(c,'role:competitor'),last_synced_at:c.last_synced_at||''};if(extraSortMetric)o.current_sort_metric=x.vals[extraSortMetric.id];if(extraSortFact)o.current_sort_metric=c[extraSortFact.key];return o});const cols=[{key:'channel_title',label:'博主'},{key:'channel_id',label:'Channel ID'},{key:'country',label:'国家/地区'},{key:'subscriber_count',label:'订阅数'},{key:'channel_view_count',label:'频道累计播放量'},{key:'stored_videos',label:'本地视频数'},{key:'identity',label:'身份标签'},{key:'ugphone_playback_median',label:'UgPhone视频播放量 Median'},{key:'all_playback_median',label:'总视频播放量 Median'},{key:'competitor_playback_median',label:'竞品视频播放量 Median'}];if(extraSortMetric||extraSortFact)cols.push({key:'current_sort_metric',label:extraSortMetric?extraSortMetric.name:extraSortFact.name});cols.push({key:'last_synced_at',label:'最近同步'});CDHExport.rows('secondary_metrics_creator_results.xlsx','Creator Results',cols,data).catch(e=>alert(e.message))};
document.getElementById('exportCfg').onclick=()=>{const blob=new Blob([JSON.stringify(state,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='creator_data_hub_metrics_config_v1.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
document.getElementById('importCfg').onchange=e=>{const f=e.target.files[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{try{state=migrateState(JSON.parse(rd.result));persist()}catch(_){alert('配置文件无效')}};rd.readAsText(f)};
document.getElementById('resetCfg').onclick=()=>{if(confirm('清空全部已构建指标和规则？')){state=emptyState();localStorage.removeItem(KEY);if(interactive)saveStateToDb();renderAll()}};
fetch('/api/ping').then(r=>r.ok?r.json():null).then(async x=>{interactive=!!x;if(interactive){await refreshLiveMetricData();await hydrateStateFromDb()}}).catch(()=>interactive=false);window.addEventListener('focus',()=>{if(interactive)refreshLiveMetricData().catch(()=>{})});window.addEventListener('storage',e=>{if(interactive&&e.key==='cdh-data-revision')refreshLiveMetricData().catch(()=>{})});
refreshFieldRegistry();document.getElementById('resultPageSize').value='30';document.getElementById('metricCatalogPageSize').value='30';document.getElementById('ruleCatalogPageSize').value='30';clearMetric();clearRule();renderAll();
})();

/* CDH V3.10.7 UI PATCH START */
(()=>{
'use strict';
const PATCH='3.10.7';
if(window.__CDH_V3107_UI_PATCH__) return;
window.__CDH_V3107_UI_PATCH__=PATCH;

const CSS=`
/* V3.10.7 · non-shrinking three-row condition viewport + frozen rule shell */
.metric-builder.v3107-grid{
  display:grid!important;
  grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;
  grid-template-rows:max-content max-content!important;
  column-gap:20px!important;
  row-gap:16px!important;
  align-items:start!important;
}
.metric-builder.v3107-grid>div{display:contents!important}
.metric-builder.v3107-grid #metrics-builder{grid-column:1;grid-row:1;margin:0!important}
.metric-builder.v3107-grid #metrics-saved{grid-column:2;grid-row:1;margin:0!important}
.metric-builder.v3107-grid #metrics-rule-builder{grid-column:1;grid-row:2;margin:0!important}
.metric-builder.v3107-grid #metrics-rules{grid-column:2;grid-row:2;margin:0!important}

#metrics-builder,#metrics-rule-builder{
  align-self:start!important;
  height:auto!important;
  min-height:0!important;
}
/* V3.10.7: stable Rule shell derived from the real structured content.
   Conditions are the ONLY growing content, and they grow inside a fixed scroll viewport. */
#metrics-rule-builder{
  --v3107-condition-row-height:46px;
  --v3107-condition-gap:8px;
  --v3107-condition-viewport-height:154px;
  height:auto!important;
  min-height:0!important;
  max-height:none!important;
  padding-bottom:18px!important;
  display:flex!important;
  flex-direction:column!important;
  overflow:hidden!important;
  box-sizing:border-box!important;
}
#metrics-rule-builder>h2{margin-bottom:16px!important;flex:0 0 auto!important}
#metrics-rule-builder .form-row{
  margin-bottom:12px!important;
  flex:0 0 auto!important;
}
#metrics-rule-builder .form-row.top{align-items:flex-start!important}
#metrics-rule-builder #ruleDescription{
  height:76px!important;
  min-height:76px!important;
  max-height:76px!important;
  resize:none!important;
}
#metrics-rule-builder .v3107-condition-section{
  margin-top:4px!important;
  padding-top:12px!important;
  border-top:1px solid rgba(148,163,184,.28)!important;
  flex:0 0 auto!important;
  min-height:0!important;
  overflow:visible!important;
}
#metrics-rule-builder .v3107-condition-head{
  display:flex!important;
  align-items:center!important;
  justify-content:space-between!important;
  gap:12px!important;
  margin-bottom:10px!important;
  flex:0 0 auto!important;
}
#metrics-rule-builder .v3107-condition-title{
  font-weight:700;
  font-size:13px;
  color:#334155;
}
#metrics-rule-builder .v3107-condition-hint{
  font-size:12px;
  color:#64748b;
}

/* This is the single scroll viewport.
   It always reserves a vertical scrollbar gutter and shows ~3 full conditions. */
#metrics-rule-builder #ruleConditions{
  height:var(--v3107-condition-viewport-height)!important;
  min-height:var(--v3107-condition-viewport-height)!important;
  max-height:var(--v3107-condition-viewport-height)!important;
  margin:0!important;
  padding:0 8px 0 0!important;
  display:flex!important;
  flex-direction:column!important;
  gap:var(--v3107-condition-gap)!important;
  overflow-y:scroll!important;
  overflow-x:auto!important;
  overscroll-behavior:contain!important;
  scrollbar-gutter:stable!important;
  box-sizing:border-box!important;
}
#metrics-rule-builder #ruleConditions::-webkit-scrollbar{width:10px;height:8px}
#metrics-rule-builder #ruleConditions::-webkit-scrollbar-track{
  background:rgba(148,163,184,.10);
  border-radius:999px;
}
#metrics-rule-builder #ruleConditions::-webkit-scrollbar-thumb{
  background:rgba(100,116,139,.48);
  border-radius:999px;
}

/* Critical fix: condition rows must NEVER shrink to fit the viewport. */
#metrics-rule-builder #ruleConditions>.condition-row.v3107-condition-row{
  flex:0 0 var(--v3107-condition-row-height)!important;
  min-height:var(--v3107-condition-row-height)!important;
  height:var(--v3107-condition-row-height)!important;
  max-height:var(--v3107-condition-row-height)!important;
  width:100%!important;
  min-width:610px!important;
  overflow:visible!important;
  padding:0!important;
  margin:0!important;
  box-sizing:border-box!important;
}
#metrics-rule-builder #ruleConditions .v3107-condition-grid{
  min-width:610px!important;
  height:42px!important;
  grid-template-columns:52px minmax(96px,.78fr) minmax(106px,.88fr) minmax(132px,1.1fr) 88px minmax(88px,.72fr) 34px!important;
  gap:6px!important;
}
#metrics-rule-builder #ruleConditions .v3107-condition-grid.v3107-no-value{
  min-width:560px!important;
  grid-template-columns:52px minmax(100px,.8fr) minmax(110px,.9fr) minmax(140px,1.12fr) 98px 34px!important;
  gap:6px!important;
}

/* Add / save controls follow the viewport immediately; no filler gap. */
#metrics-rule-builder .v3107-add-condition-row{
  margin-top:10px!important;
  display:flex!important;
  align-items:center!important;
  justify-content:flex-start!important;
  flex:0 0 auto!important;
}
#metrics-rule-builder .v3107-rule-footer{
  margin-top:10px!important;
  padding-top:12px!important;
  border-top:1px solid rgba(148,163,184,.22)!important;
  flex:0 0 auto!important;
}
#metrics-rule-builder .v3107-rule-actions{
  display:flex!important;
  flex-wrap:wrap!important;
  gap:10px!important;
  align-items:center!important;
  margin-bottom:8px!important;
}
#metrics-rule-builder .v3107-rule-note{
  line-height:1.45!important;
  color:#64748b!important;
}

/* The Rule List shell is frozen to the measured Rule Builder shell height.
   Cards remain natural height; only ruleList scrolls. */
#metrics-rules.v3107-scroll-panel{
  display:flex!important;
  flex-direction:column!important;
  overflow:hidden!important;
  box-sizing:border-box!important;
}
#metrics-rules.v3107-scroll-panel #ruleList{
  flex:1 1 0!important;
  min-height:0!important;
  height:auto!important;
  overflow-y:scroll!important;
  overflow-x:hidden!important;
  display:flex!important;
  flex-direction:column!important;
  align-items:stretch!important;
  justify-content:flex-start!important;
  align-content:flex-start!important;
  gap:10px!important;
  scrollbar-gutter:stable!important;
}
#metrics-rules.v3107-scroll-panel #ruleList>*{
  flex:0 0 auto!important;
  flex-grow:0!important;
  flex-shrink:0!important;
  height:auto!important;
  min-height:0!important;
  max-height:none!important;
  align-self:stretch!important;
}

#metrics-saved,#metrics-rules{
  align-self:start!important;
  min-height:0!important;
}
#metrics-saved.v3107-scroll-panel,#metrics-rules.v3107-scroll-panel{
  display:flex!important;
  flex-direction:column!important;
  min-height:0!important;
  overflow:hidden!important;
  box-sizing:border-box!important;
}
#metrics-saved.v3107-scroll-panel #metricList,
#metrics-rules.v3107-scroll-panel #ruleList{
  flex:1 1 auto!important;
  min-height:0!important;
  overflow-y:auto!important;
  overflow-x:hidden!important;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
  padding-right:4px;
  margin-bottom:0!important;
}
#metrics-saved.v3107-scroll-panel #metricList::-webkit-scrollbar,
#metrics-rules.v3107-scroll-panel #ruleList::-webkit-scrollbar{width:9px}
#metrics-saved.v3107-scroll-panel #metricList::-webkit-scrollbar-thumb,
#metrics-rules.v3107-scroll-panel #ruleList::-webkit-scrollbar-thumb{background:rgba(100,116,139,.38);border-radius:999px}

/* One condition = one row, shared by Rule Builder and Creator Library result filters. */
#ruleConditions.v3107-condition-list,
#resultFilterConditions.v3107-condition-list,
#ovFilterConditions.v3107-condition-list{
  display:flex!important;
  flex-direction:column!important;
  gap:10px!important;
}
#ruleConditions .condition-row.v3107-condition-row,
#resultFilterConditions .condition-row.v3107-condition-row,
#ovFilterConditions .condition-row.v3107-condition-row{
  width:100%!important;
  max-width:none!important;
  display:block!important;
  margin:0!important;
  padding:0 0 2px 0!important;
}
#ruleConditions .condition-row.v3107-condition-row{
  overflow:visible!important;
}
#resultFilterConditions .condition-row.v3107-condition-row,
#ovFilterConditions .condition-row.v3107-condition-row{
  overflow-x:auto;
  overflow-y:hidden;
}
#ruleConditions .v3107-condition-grid,
#resultFilterConditions .v3107-condition-grid,
#ovFilterConditions .v3107-condition-grid{
  width:100%;
  display:grid!important;
  align-items:center;
}
#ruleConditions .v3107-condition-grid{
  min-width:680px;
  grid-template-columns:56px minmax(100px,.78fr) minmax(112px,.9fr) minmax(138px,1.16fr) 96px minmax(104px,.74fr) 38px;
  gap:8px;
}
#ruleConditions .v3107-condition-grid.v3107-no-value{
  min-width:570px;
  grid-template-columns:56px minmax(100px,.78fr) minmax(112px,.9fr) minmax(138px,1.16fr) 106px 38px;
}
#resultFilterConditions .v3107-condition-grid,
#ovFilterConditions .v3107-condition-grid{
  min-width:920px;
  grid-template-columns:72px minmax(140px,.8fr) minmax(160px,.95fr) minmax(210px,1.25fr) 112px minmax(140px,.85fr) 40px;
  gap:10px;
}
#resultFilterConditions .v3107-condition-grid.v3107-no-value,
#ovFilterConditions .v3107-condition-grid.v3107-no-value{
  min-width:760px;
  grid-template-columns:72px minmax(140px,.8fr) minmax(160px,.95fr) minmax(210px,1.25fr) 122px 40px;
}
#ruleConditions .v3107-condition-grid>*,
#resultFilterConditions .v3107-condition-grid>*,
#ovFilterConditions .v3107-condition-grid>*{min-width:0!important;max-width:none!important;margin:0!important}
#ruleConditions .v3107-condition-grid select,
#ruleConditions .v3107-condition-grid input,
#resultFilterConditions .v3107-condition-grid select,
#resultFilterConditions .v3107-condition-grid input,
#ovFilterConditions .v3107-condition-grid select,
#ovFilterConditions .v3107-condition-grid input{
  width:100%!important;
  height:42px!important;
  box-sizing:border-box!important;
}
.v3107-tier3-combo{position:relative;width:100%;min-width:0}
.v3107-tier3-native{display:none!important}
.v3107-tier3-input{padding-right:36px!important;text-overflow:ellipsis}
.v3107-tier3-picker{
  position:absolute!important;right:1px!important;top:1px!important;bottom:1px!important;
  width:34px!important;min-width:34px!important;height:40px!important;
  padding:0!important;margin:0!important;border:0!important;
  border-left:1px solid rgba(148,163,184,.26)!important;
  background:transparent!important;color:#64748b!important;
  display:flex!important;align-items:center!important;justify-content:center!important;cursor:pointer;
}
.v3107-lead{display:flex!important;align-items:center!important;min-height:42px;color:#64748b;white-space:nowrap}
.v3107-delete{
  width:38px!important;min-width:38px!important;height:42px!important;padding:0!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
}
.v3107-hidden-legacy,.v3107-hidden-search{display:none!important}
#metrics-results .builder-panel>.inline.v3107-result-toolbar{margin-top:12px!important;flex-wrap:wrap!important;gap:10px!important;align-items:center!important}

/* Main Creator Library: the deprecated stacked selector is fully retired too. */
#ovFilterConditions{width:100%!important}
#ovFilterConditions .condition-row.v3107-condition-row{overflow-x:auto!important}
#ovFilterConditions .v3107-hidden-legacy,
#ovFilterConditions .v3107-hidden-search{display:none!important}


/* Rule card anti-stretch safety. */
.metric-builder.v3107-grid #metrics-rules.v3107-scroll-panel #ruleList>*{
  flex:0 0 auto!important;
  height:auto!important;
}
@media(max-width:1050px){
  .metric-builder.v3107-grid{display:block!important}
  .metric-builder.v3107-grid>div{display:block!important}
  .metric-builder.v3107-grid #metrics-builder,
  .metric-builder.v3107-grid #metrics-saved,
  .metric-builder.v3107-grid #metrics-rule-builder,
  .metric-builder.v3107-grid #metrics-rules{height:auto!important;margin-top:16px!important}
  .metric-builder.v3107-grid #metrics-rule-builder,
  .metric-builder.v3107-grid #metrics-rules{
    height:auto!important;
    min-height:0!important;
    max-height:none!important;
    overflow:visible!important;
  }
  .metric-builder.v3107-grid #metrics-rule-builder #ruleConditions{
    height:154px!important;
    min-height:154px!important;
    max-height:154px!important;
    overflow-y:scroll!important;
    overflow-x:auto!important;
  }
  .metric-builder.v3107-grid #metrics-builder{margin-top:0!important}
  #metrics-saved.v3107-scroll-panel,#metrics-rules.v3107-scroll-panel{max-height:720px}
  #metrics-saved.v3107-scroll-panel #metricList,#metrics-rules.v3107-scroll-panel #ruleList{max-height:560px}
}
`;

function injectCss(){
  if(document.getElementById('cdh-v3107-ui-style'))return;
  const s=document.createElement('style');s.id='cdh-v3107-ui-style';s.textContent=CSS;document.head.appendChild(s);
}

let layoutBusy=false, pageSizeBusy=false;
function scheduleSyncHeights(){if(layoutBusy)return;layoutBusy=true;requestAnimationFrame(()=>{layoutBusy=false;syncHeights()})}
let frozenRuleShellHeight=0;
function measureAndFreezeRuleShell(){
  const rb=document.getElementById('metrics-rule-builder'),rs=document.getElementById('metrics-rules');
  if(!rb||!rs)return 0;
  const mobile=window.matchMedia('(max-width:1050px)').matches;
  if(mobile){
    frozenRuleShellHeight=0;
    rb.style.height='';rb.style.minHeight='';rb.style.maxHeight='';
    rs.style.height='';rs.style.minHeight='';rs.style.maxHeight='';
    return 0;
  }

  // Measure the structured builder with the condition viewport already fixed.
  // Condition count therefore cannot change this measurement.
  rb.style.height='auto';rb.style.minHeight='0';rb.style.maxHeight='none';
  const measured=Math.ceil(rb.scrollHeight || rb.getBoundingClientRect().height);
  frozenRuleShellHeight=Math.max(560,Math.min(720,measured));
  rb.style.height=`${frozenRuleShellHeight}px`;
  rb.style.minHeight=`${frozenRuleShellHeight}px`;
  rb.style.maxHeight=`${frozenRuleShellHeight}px`;
  rs.style.height=`${frozenRuleShellHeight}px`;
  rs.style.minHeight=`${frozenRuleShellHeight}px`;
  rs.style.maxHeight=`${frozenRuleShellHeight}px`;
  return frozenRuleShellHeight;
}
function syncHeights(){
  const root=document.querySelector('.metric-builder');
  const mb=document.getElementById('metrics-builder'),ms=document.getElementById('metrics-saved'),rb=document.getElementById('metrics-rule-builder'),rs=document.getElementById('metrics-rules');
  if(!root||!mb||!ms||!rb||!rs)return;
  root.classList.add('v3107-grid');ms.classList.add('v3107-scroll-panel');rs.classList.add('v3107-scroll-panel');

  const mobile=window.matchMedia('(max-width:1050px)').matches;
  mb.style.height='auto';mb.style.minHeight='0';

  if(mobile){
    ms.style.height='';
    measureAndFreezeRuleShell();
    return;
  }

  // Metric pair keeps its existing behavior.
  ms.style.height='';
  const metricH=Math.ceil(mb.scrollHeight || mb.getBoundingClientRect().height);
  if(metricH>0)ms.style.height=`${metricH}px`;

  // Rule pair freezes once from structured content; condition mutations never resize it.
  if(!frozenRuleShellHeight)measureAndFreezeRuleShell();
  else{
    rb.style.height=`${frozenRuleShellHeight}px`;
    rb.style.minHeight=`${frozenRuleShellHeight}px`;
    rb.style.maxHeight=`${frozenRuleShellHeight}px`;
    rs.style.height=`${frozenRuleShellHeight}px`;
    rs.style.minHeight=`${frozenRuleShellHeight}px`;
    rs.style.maxHeight=`${frozenRuleShellHeight}px`;
  }
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
  panel.classList.add('v3107-scroll-panel');
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
  let wrap=native.closest('.v3107-tier3-combo');if(wrap){grid.appendChild(wrap);return wrap}
  wrap=document.createElement('div');wrap.className='v3107-tier3-combo v3107-l3';
  const listId='v3107-tier3-'+Math.random().toString(36).slice(2,10);
  const input=document.createElement('input');input.type='text';input.className='v3107-tier3-input';input.setAttribute('list',listId);input.setAttribute('autocomplete','off');input.placeholder='选择 / 搜索三级指标';
  const dl=document.createElement('datalist');dl.id=listId;
  const picker=document.createElement('button');picker.type='button';picker.className='v3107-tier3-picker';picker.title='展开 / 搜索三级指标';picker.setAttribute('aria-label','展开 / 搜索三级指标');picker.textContent='⌄';
  native.classList.add('v3107-tier3-native');wrap.appendChild(native);wrap.appendChild(input);wrap.appendChild(dl);wrap.appendChild(picker);grid.appendChild(wrap);
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
  let grid=row.querySelector(':scope > .v3107-condition-grid');
  if(row.dataset.v3107Compacted==='1'&&grid){syncValueMode(row,grid);return}
  const selects=[...row.querySelectorAll('select')];if(!selects.length)return;
  const join=selects.find(isJoinSelect)||null,op=selects.find(s=>s!==join&&isOperatorSelect(s))||null;
  const candidates=selects.filter(s=>s!==join&&s!==op);if(candidates.length<3)return;
  const levels=candidates.slice(-3),legacy=candidates.slice(0,-3);legacy.forEach(x=>x.classList.add('v3107-hidden-legacy'));
  const buttons=[...row.querySelectorAll('button')],del=buttons.find(isDeleteButton)||buttons.at(-1)||null;
  buttons.filter(b=>b!==del&&isSearchControl(b)).forEach(b=>b.classList.add('v3107-hidden-search'));
  [...row.querySelectorAll('input')].filter(isSearchControl).forEach(x=>x.classList.add('v3107-hidden-search'));
  const value=[...row.querySelectorAll('input')].find(x=>!x.classList.contains('v3107-hidden-search')&&(x.classList.contains('c-value')||['number','text'].includes((x.type||'text').toLowerCase())))||null;
  const lead=findLead(row,join);
  if(!grid){grid=document.createElement('div');grid.className='v3107-condition-grid';row.prepend(grid)}
  const move=(el,cls)=>{if(!el)return;el.classList.add(cls);grid.appendChild(el)};
  move(lead,'v3107-lead');move(levels[0],'v3107-l1');move(levels[1],'v3107-l2');installSearchableTier3(levels[2],grid);move(op,'v3107-op');move(value,'v3107-value');move(del,'v3107-delete');
  row.classList.add('v3107-condition-row');row.dataset.v3107Compacted='1';
  const sync=()=>requestAnimationFrame(()=>syncValueMode(row,grid));
  selects.forEach(s=>s.addEventListener('change',sync));
  new MutationObserver(sync).observe(row,{attributes:true,subtree:true,attributeFilter:['style','class']});
  syncValueMode(row,grid);
}
function syncValueMode(row,grid){
  const value=row.querySelector('.v3107-value');
  const hidden=!value||value.style.display==='none'||getComputedStyle(value).display==='none';
  grid.classList.toggle('v3107-no-value',hidden);
}
function compactConditionBox(id){
  const box=document.getElementById(id);if(!box)return;box.classList.add('v3107-condition-list');[...box.children].forEach(compactConditionRow);
}
function compactAllConditions(){
  compactConditionBox('ruleConditions');compactConditionBox('resultFilterConditions');compactConditionBox('ovFilterConditions');
  ['ruleConditions','resultFilterConditions','ovFilterConditions'].forEach(id=>{
    const box=document.getElementById(id);if(!box)return;
    box.querySelectorAll('button').forEach(b=>{if((b.textContent||'').trim()==='搜索'&&b.closest('.condition-row'))b.classList.add('v3107-hidden-search')});
  });
  const rbox=document.getElementById('resultFilterConditions'),panel=rbox?.closest('.builder-panel');
  if(panel)[...panel.children].forEach(x=>{if(x.classList?.contains('inline')&&x!==rbox)x.classList.add('v3107-result-toolbar')});
}


function structureRuleBuilder(){
  const panel=document.getElementById('metrics-rule-builder');
  const cond=document.getElementById('ruleConditions');
  const add=document.getElementById('addRuleCondition');
  const save=document.getElementById('saveRule');
  const clear=document.getElementById('clearRule');
  if(!panel||!cond||!add||!save||!clear||panel.dataset.v3107Structured==='1')return;
  panel.dataset.v3107Structured='1';

  const oldActions=add.closest('.inline');
  const note=oldActions?.nextElementSibling?.classList?.contains('small')?oldActions.nextElementSibling:null;

  const section=document.createElement('div');
  section.className='v3107-condition-section';

  const head=document.createElement('div');
  head.className='v3107-condition-head';
  const title=document.createElement('div');
  title.className='v3107-condition-title';
  title.textContent='条件设置';
  const hint=document.createElement('div');
  hint.className='v3107-condition-hint';
  hint.textContent='每条条件一行；第二条起可使用 AND / OR / NOT';
  head.append(title,hint);

  const addRow=document.createElement('div');
  addRow.className='v3107-add-condition-row';
  addRow.appendChild(add);

  section.append(head,cond,addRow);

  const footer=document.createElement('div');
  footer.className='v3107-rule-footer';
  const actions=document.createElement('div');
  actions.className='v3107-rule-actions';
  actions.append(save,clear);
  footer.appendChild(actions);
  if(note){
    note.classList.add('v3107-rule-note');
    footer.appendChild(note);
  }

  const desc=document.getElementById('ruleDescription');
  const descRow=desc?.closest('.form-row');
  if(descRow)descRow.after(section);
  else panel.appendChild(section);
  panel.appendChild(footer);
  if(oldActions&&oldActions.children.length===0)oldActions.remove();

  requestAnimationFrame(()=>{frozenRuleShellHeight=0;measureAndFreezeRuleShell();});
}

function observe(){
  structureRuleBuilder();
  const metricList=document.getElementById('metricList'),ruleList=document.getElementById('ruleList');
  const mb=document.getElementById('metrics-builder');
  if(window.ResizeObserver){
    if(mb&&!mb.__v3107ResizeObserved){mb.__v3107ResizeObserved=true;new ResizeObserver(scheduleSyncHeights).observe(mb)}
  }
  if(metricList&&!metricList.__v3107Observed){metricList.__v3107Observed=true;new MutationObserver(()=>{configureNativePagination();scheduleSyncHeights();setTimeout(()=>{metricList.scrollTop=0},0)}).observe(metricList,{childList:true})}
  if(ruleList&&!ruleList.__v3107Observed){ruleList.__v3107Observed=true;new MutationObserver(()=>{configureNativePagination();setTimeout(()=>{ruleList.scrollTop=0},0)}).observe(ruleList,{childList:true})}
  ['ruleConditions','resultFilterConditions','ovFilterConditions'].forEach(id=>{
    const box=document.getElementById(id);if(box&&!box.__v3107Observed){box.__v3107Observed=true;new MutationObserver(()=>requestAnimationFrame(()=>{compactAllConditions();if(id==='ruleConditions'){const rows=box.querySelectorAll('.condition-row');if(rows.length>3)box.scrollTop=box.scrollHeight}})).observe(box,{childList:true,subtree:true})}
  });
}

function boot(){
  injectCss();
  const root=document.querySelector('.metric-builder');if(root)root.classList.add('v3107-grid');
  compactAllConditions();observe();configureNativePagination();syncHeights();
  window.addEventListener('resize',scheduleSyncHeights,{passive:true});
  [80,250,700,1500,3000].forEach(ms=>setTimeout(()=>{compactAllConditions();observe();configureNativePagination();syncHeights()},ms));
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
/* CDH V3.10.7 UI PATCH END */
