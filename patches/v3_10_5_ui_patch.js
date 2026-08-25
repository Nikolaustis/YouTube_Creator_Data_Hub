/* CDH V3.10.5 UI PATCH START */
(()=>{
'use strict';
const PATCH='3.10.5';
if(window.__CDH_V3105_UI_PATCH__) return;
window.__CDH_V3105_UI_PATCH__=PATCH;

const CSS=`
/* V3.10.5 · roomier Rule Builder + paired Rule List height */
.metric-builder.v3105-grid{
  display:grid!important;
  grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;
  grid-template-rows:max-content max-content!important;
  column-gap:20px!important;
  row-gap:16px!important;
  align-items:start!important;
}
.metric-builder.v3105-grid>div{display:contents!important}
.metric-builder.v3105-grid #metrics-builder{grid-column:1;grid-row:1;margin:0!important}
.metric-builder.v3105-grid #metrics-saved{grid-column:2;grid-row:1;margin:0!important}
.metric-builder.v3105-grid #metrics-rule-builder{grid-column:1;grid-row:2;margin:0!important}
.metric-builder.v3105-grid #metrics-rules{grid-column:2;grid-row:2;margin:0!important}

#metrics-builder,#metrics-rule-builder{
  align-self:start!important;
  height:auto!important;
  min-height:0!important;
}
/* V3.10.5: Rule Builder is intentionally roomier than a one-line rule needs.
   This is meaningful layout space: metadata -> condition workspace -> footer. */
#metrics-rule-builder{
  min-height:500px!important;
  padding-bottom:20px!important;
  display:flex!important;
  flex-direction:column!important;
}
#metrics-rule-builder>h2{margin-bottom:18px!important}
#metrics-rule-builder .form-row{margin-bottom:14px!important}
#metrics-rule-builder .form-row.top{align-items:flex-start!important}
#metrics-rule-builder #ruleDescription{
  min-height:78px!important;
  resize:vertical;
}
#metrics-rule-builder .v3105-condition-section{
  margin-top:8px!important;
  padding-top:16px!important;
  border-top:1px solid rgba(148,163,184,.28)!important;
}
#metrics-rule-builder .v3105-condition-head{
  display:flex!important;
  align-items:center!important;
  justify-content:space-between!important;
  gap:12px!important;
  margin-bottom:12px!important;
}
#metrics-rule-builder .v3105-condition-title{
  font-weight:700;
  font-size:13px;
  color:#334155;
}
#metrics-rule-builder .v3105-condition-hint{
  font-size:12px;
  color:#64748b;
}
#metrics-rule-builder #ruleConditions{
  margin:0!important;
  padding:0!important;
}
#metrics-rule-builder .v3105-add-condition-row{
  margin-top:12px!important;
  display:flex!important;
  align-items:center!important;
  justify-content:flex-start!important;
}
#metrics-rule-builder .v3105-rule-footer{
  margin-top:auto!important;
  padding-top:18px!important;
  border-top:1px solid rgba(148,163,184,.22)!important;
}
#metrics-rule-builder .v3105-rule-actions{
  display:flex!important;
  flex-wrap:wrap!important;
  gap:10px!important;
  align-items:center!important;
  margin-bottom:10px!important;
}
#metrics-rule-builder .v3105-rule-note{
  line-height:1.55!important;
  color:#64748b!important;
}

#metrics-saved,#metrics-rules{
  align-self:start!important;
  min-height:0!important;
}
#metrics-saved.v3105-scroll-panel,#metrics-rules.v3105-scroll-panel{
  display:flex!important;
  flex-direction:column!important;
  min-height:0!important;
  overflow:hidden!important;
  box-sizing:border-box!important;
}
#metrics-saved.v3105-scroll-panel #metricList,
#metrics-rules.v3105-scroll-panel #ruleList{
  flex:1 1 auto!important;
  min-height:0!important;
  overflow-y:auto!important;
  overflow-x:hidden!important;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
  padding-right:4px;
  margin-bottom:0!important;
}
#metrics-saved.v3105-scroll-panel #metricList::-webkit-scrollbar,
#metrics-rules.v3105-scroll-panel #ruleList::-webkit-scrollbar{width:9px}
#metrics-saved.v3105-scroll-panel #metricList::-webkit-scrollbar-thumb,
#metrics-rules.v3105-scroll-panel #ruleList::-webkit-scrollbar-thumb{background:rgba(100,116,139,.38);border-radius:999px}

/* One condition = one row, shared by Rule Builder and Creator Library result filters. */
#ruleConditions.v3105-condition-list,
#resultFilterConditions.v3105-condition-list,
#ovFilterConditions.v3105-condition-list{
  display:flex!important;
  flex-direction:column!important;
  gap:10px!important;
}
#ruleConditions .condition-row.v3105-condition-row,
#resultFilterConditions .condition-row.v3105-condition-row,
#ovFilterConditions .condition-row.v3105-condition-row{
  width:100%!important;
  max-width:none!important;
  display:block!important;
  margin:0!important;
  padding:0 0 2px 0!important;
  overflow-x:auto;
  overflow-y:hidden;
}
#ruleConditions .v3105-condition-grid,
#resultFilterConditions .v3105-condition-grid,
#ovFilterConditions .v3105-condition-grid{
  width:100%;
  display:grid!important;
  align-items:center;
}
#ruleConditions .v3105-condition-grid{
  min-width:680px;
  grid-template-columns:56px minmax(100px,.78fr) minmax(112px,.9fr) minmax(138px,1.16fr) 96px minmax(104px,.74fr) 38px;
  gap:8px;
}
#ruleConditions .v3105-condition-grid.v3105-no-value{
  min-width:570px;
  grid-template-columns:56px minmax(100px,.78fr) minmax(112px,.9fr) minmax(138px,1.16fr) 106px 38px;
}
#resultFilterConditions .v3105-condition-grid,
#ovFilterConditions .v3105-condition-grid{
  min-width:920px;
  grid-template-columns:72px minmax(140px,.8fr) minmax(160px,.95fr) minmax(210px,1.25fr) 112px minmax(140px,.85fr) 40px;
  gap:10px;
}
#resultFilterConditions .v3105-condition-grid.v3105-no-value,
#ovFilterConditions .v3105-condition-grid.v3105-no-value{
  min-width:760px;
  grid-template-columns:72px minmax(140px,.8fr) minmax(160px,.95fr) minmax(210px,1.25fr) 122px 40px;
}
#ruleConditions .v3105-condition-grid>*,
#resultFilterConditions .v3105-condition-grid>*,
#ovFilterConditions .v3105-condition-grid>*{min-width:0!important;max-width:none!important;margin:0!important}
#ruleConditions .v3105-condition-grid select,
#ruleConditions .v3105-condition-grid input,
#resultFilterConditions .v3105-condition-grid select,
#resultFilterConditions .v3105-condition-grid input,
#ovFilterConditions .v3105-condition-grid select,
#ovFilterConditions .v3105-condition-grid input{
  width:100%!important;
  height:42px!important;
  box-sizing:border-box!important;
}
.v3105-tier3-combo{position:relative;width:100%;min-width:0}
.v3105-tier3-native{display:none!important}
.v3105-tier3-input{padding-right:36px!important;text-overflow:ellipsis}
.v3105-tier3-picker{
  position:absolute!important;right:1px!important;top:1px!important;bottom:1px!important;
  width:34px!important;min-width:34px!important;height:40px!important;
  padding:0!important;margin:0!important;border:0!important;
  border-left:1px solid rgba(148,163,184,.26)!important;
  background:transparent!important;color:#64748b!important;
  display:flex!important;align-items:center!important;justify-content:center!important;cursor:pointer;
}
.v3105-lead{display:flex!important;align-items:center!important;min-height:42px;color:#64748b;white-space:nowrap}
.v3105-delete{
  width:38px!important;min-width:38px!important;height:42px!important;padding:0!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
}
.v3105-hidden-legacy,.v3105-hidden-search{display:none!important}
#metrics-results .builder-panel>.inline.v3105-result-toolbar{margin-top:12px!important;flex-wrap:wrap!important;gap:10px!important;align-items:center!important}

/* Main Creator Library: the deprecated stacked selector is fully retired too. */
#ovFilterConditions{width:100%!important}
#ovFilterConditions .condition-row.v3105-condition-row{overflow-x:auto!important}
#ovFilterConditions .v3105-hidden-legacy,
#ovFilterConditions .v3105-hidden-search{display:none!important}

@media(max-width:1050px){
  .metric-builder.v3105-grid{display:block!important}
  .metric-builder.v3105-grid>div{display:block!important}
  .metric-builder.v3105-grid #metrics-builder,
  .metric-builder.v3105-grid #metrics-saved,
  .metric-builder.v3105-grid #metrics-rule-builder,
  .metric-builder.v3105-grid #metrics-rules{height:auto!important;margin-top:16px!important}
  .metric-builder.v3105-grid #metrics-rule-builder{min-height:0!important}
  .metric-builder.v3105-grid #metrics-builder{margin-top:0!important}
  #metrics-saved.v3105-scroll-panel,#metrics-rules.v3105-scroll-panel{max-height:720px}
  #metrics-saved.v3105-scroll-panel #metricList,#metrics-rules.v3105-scroll-panel #ruleList{max-height:560px}
}
`;

function injectCss(){
  if(document.getElementById('cdh-v3105-ui-style'))return;
  const s=document.createElement('style');s.id='cdh-v3105-ui-style';s.textContent=CSS;document.head.appendChild(s);
}

let layoutBusy=false, pageSizeBusy=false;
function scheduleSyncHeights(){if(layoutBusy)return;layoutBusy=true;requestAnimationFrame(()=>{layoutBusy=false;syncHeights()})}
function syncHeights(){
  const root=document.querySelector('.metric-builder');
  const mb=document.getElementById('metrics-builder'),ms=document.getElementById('metrics-saved'),rb=document.getElementById('metrics-rule-builder'),rs=document.getElementById('metrics-rules');
  if(!root||!mb||!ms||!rb||!rs)return;
  root.classList.add('v3105-grid');ms.classList.add('v3105-scroll-panel');rs.classList.add('v3105-scroll-panel');

  // V3.10.5: Builder owns the row height. The list is never allowed to make
  // the Builder taller. Clear list heights first, keep builders at natural
  // height, measure them, then constrain the two list panels to those heights.
  mb.style.height='auto';rb.style.height='auto';
  mb.style.minHeight='0';
  // V3.10.5 keeps the Rule Builder deliberately tall on desktop.
  rb.style.minHeight=window.matchMedia('(max-width:1050px)').matches?'0':'500px';
  if(window.matchMedia('(max-width:1050px)').matches){
    ms.style.height='';rs.style.height='';
    return;
  }

  ms.style.height='';rs.style.height='';
  const h1=Math.ceil(mb.scrollHeight || mb.getBoundingClientRect().height);
  const h2=Math.ceil(rb.scrollHeight || rb.getBoundingClientRect().height);
  if(h1>0)ms.style.height=`${h1}px`;
  if(h2>0)rs.style.height=`${h2}px`;
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
  panel.classList.add('v3105-scroll-panel');
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
  let wrap=native.closest('.v3105-tier3-combo');if(wrap){grid.appendChild(wrap);return wrap}
  wrap=document.createElement('div');wrap.className='v3105-tier3-combo v3105-l3';
  const listId='v3105-tier3-'+Math.random().toString(36).slice(2,10);
  const input=document.createElement('input');input.type='text';input.className='v3105-tier3-input';input.setAttribute('list',listId);input.setAttribute('autocomplete','off');input.placeholder='选择 / 搜索三级指标';
  const dl=document.createElement('datalist');dl.id=listId;
  const picker=document.createElement('button');picker.type='button';picker.className='v3105-tier3-picker';picker.title='展开 / 搜索三级指标';picker.setAttribute('aria-label','展开 / 搜索三级指标');picker.textContent='⌄';
  native.classList.add('v3105-tier3-native');wrap.appendChild(native);wrap.appendChild(input);wrap.appendChild(dl);wrap.appendChild(picker);grid.appendChild(wrap);
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
  let grid=row.querySelector(':scope > .v3105-condition-grid');
  if(row.dataset.v3105Compacted==='1'&&grid){syncValueMode(row,grid);return}
  const selects=[...row.querySelectorAll('select')];if(!selects.length)return;
  const join=selects.find(isJoinSelect)||null,op=selects.find(s=>s!==join&&isOperatorSelect(s))||null;
  const candidates=selects.filter(s=>s!==join&&s!==op);if(candidates.length<3)return;
  const levels=candidates.slice(-3),legacy=candidates.slice(0,-3);legacy.forEach(x=>x.classList.add('v3105-hidden-legacy'));
  const buttons=[...row.querySelectorAll('button')],del=buttons.find(isDeleteButton)||buttons.at(-1)||null;
  buttons.filter(b=>b!==del&&isSearchControl(b)).forEach(b=>b.classList.add('v3105-hidden-search'));
  [...row.querySelectorAll('input')].filter(isSearchControl).forEach(x=>x.classList.add('v3105-hidden-search'));
  const value=[...row.querySelectorAll('input')].find(x=>!x.classList.contains('v3105-hidden-search')&&(x.classList.contains('c-value')||['number','text'].includes((x.type||'text').toLowerCase())))||null;
  const lead=findLead(row,join);
  if(!grid){grid=document.createElement('div');grid.className='v3105-condition-grid';row.prepend(grid)}
  const move=(el,cls)=>{if(!el)return;el.classList.add(cls);grid.appendChild(el)};
  move(lead,'v3105-lead');move(levels[0],'v3105-l1');move(levels[1],'v3105-l2');installSearchableTier3(levels[2],grid);move(op,'v3105-op');move(value,'v3105-value');move(del,'v3105-delete');
  row.classList.add('v3105-condition-row');row.dataset.v3105Compacted='1';
  const sync=()=>requestAnimationFrame(()=>syncValueMode(row,grid));
  selects.forEach(s=>s.addEventListener('change',sync));
  new MutationObserver(sync).observe(row,{attributes:true,subtree:true,attributeFilter:['style','class']});
  syncValueMode(row,grid);
}
function syncValueMode(row,grid){
  const value=row.querySelector('.v3105-value');
  const hidden=!value||value.style.display==='none'||getComputedStyle(value).display==='none';
  grid.classList.toggle('v3105-no-value',hidden);
}
function compactConditionBox(id){
  const box=document.getElementById(id);if(!box)return;box.classList.add('v3105-condition-list');[...box.children].forEach(compactConditionRow);
}
function compactAllConditions(){
  compactConditionBox('ruleConditions');compactConditionBox('resultFilterConditions');compactConditionBox('ovFilterConditions');
  ['ruleConditions','resultFilterConditions','ovFilterConditions'].forEach(id=>{
    const box=document.getElementById(id);if(!box)return;
    box.querySelectorAll('button').forEach(b=>{if((b.textContent||'').trim()==='搜索'&&b.closest('.condition-row'))b.classList.add('v3105-hidden-search')});
  });
  const rbox=document.getElementById('resultFilterConditions'),panel=rbox?.closest('.builder-panel');
  if(panel)[...panel.children].forEach(x=>{if(x.classList?.contains('inline')&&x!==rbox)x.classList.add('v3105-result-toolbar')});
}


function structureRuleBuilder(){
  const panel=document.getElementById('metrics-rule-builder');
  const cond=document.getElementById('ruleConditions');
  const add=document.getElementById('addRuleCondition');
  const save=document.getElementById('saveRule');
  const clear=document.getElementById('clearRule');
  if(!panel||!cond||!add||!save||!clear||panel.dataset.v3105Structured==='1')return;
  panel.dataset.v3105Structured='1';

  const oldActions=add.closest('.inline');
  const note=oldActions?.nextElementSibling?.classList?.contains('small')?oldActions.nextElementSibling:null;

  const section=document.createElement('div');
  section.className='v3105-condition-section';

  const head=document.createElement('div');
  head.className='v3105-condition-head';
  const title=document.createElement('div');
  title.className='v3105-condition-title';
  title.textContent='条件设置';
  const hint=document.createElement('div');
  hint.className='v3105-condition-hint';
  hint.textContent='每条条件一行；第二条起可使用 AND / OR / NOT';
  head.append(title,hint);

  const addRow=document.createElement('div');
  addRow.className='v3105-add-condition-row';
  addRow.appendChild(add);

  section.append(head,cond,addRow);

  const footer=document.createElement('div');
  footer.className='v3105-rule-footer';
  const actions=document.createElement('div');
  actions.className='v3105-rule-actions';
  actions.append(save,clear);
  footer.appendChild(actions);
  if(note){
    note.classList.add('v3105-rule-note');
    footer.appendChild(note);
  }

  const desc=document.getElementById('ruleDescription');
  const descRow=desc?.closest('.form-row');
  if(descRow)descRow.after(section);
  else panel.appendChild(section);
  panel.appendChild(footer);
  if(oldActions&&oldActions.children.length===0)oldActions.remove();

  scheduleSyncHeights();
}

function observe(){
  structureRuleBuilder();
  const metricList=document.getElementById('metricList'),ruleList=document.getElementById('ruleList');
  const mb=document.getElementById('metrics-builder'),rb=document.getElementById('metrics-rule-builder');
  if(window.ResizeObserver){
    if(mb&&!mb.__v3105ResizeObserved){mb.__v3105ResizeObserved=true;new ResizeObserver(scheduleSyncHeights).observe(mb)}
    if(rb&&!rb.__v3105ResizeObserved){rb.__v3105ResizeObserved=true;new ResizeObserver(scheduleSyncHeights).observe(rb)}
  }
  if(metricList&&!metricList.__v3105Observed){metricList.__v3105Observed=true;new MutationObserver(()=>{configureNativePagination();scheduleSyncHeights();setTimeout(()=>{metricList.scrollTop=0},0)}).observe(metricList,{childList:true})}
  if(ruleList&&!ruleList.__v3105Observed){ruleList.__v3105Observed=true;new MutationObserver(()=>{configureNativePagination();scheduleSyncHeights();setTimeout(()=>{ruleList.scrollTop=0},0)}).observe(ruleList,{childList:true})}
  ['ruleConditions','resultFilterConditions','ovFilterConditions'].forEach(id=>{
    const box=document.getElementById(id);if(box&&!box.__v3105Observed){box.__v3105Observed=true;new MutationObserver(()=>requestAnimationFrame(compactAllConditions)).observe(box,{childList:true,subtree:true})}
  });
}

function boot(){
  injectCss();
  const root=document.querySelector('.metric-builder');if(root)root.classList.add('v3105-grid');
  compactAllConditions();observe();configureNativePagination();syncHeights();
  window.addEventListener('resize',scheduleSyncHeights,{passive:true});
  [80,250,700,1500,3000].forEach(ms=>setTimeout(()=>{compactAllConditions();observe();configureNativePagination();syncHeights()},ms));
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
/* CDH V3.10.5 UI PATCH END */