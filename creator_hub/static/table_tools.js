(()=>{
'use strict';
function nval(x,d=0){const n=Number(x);return Number.isFinite(n)?n:d}
function pageSize(el,fallback=30){const n=parseInt(el?.value||String(fallback),10);return Number.isFinite(n)&&n>0?Math.min(n,5000):fallback}
function pageList(page,pages){const out=[];for(let p=Math.max(1,page-2);p<=Math.min(pages,page+2);p++)out.push(p);return out}
function renderPager(o){
 const {page,pages,go}=o;
 const first=o.firstId&&document.getElementById(o.firstId),prev=o.prevId&&document.getElementById(o.prevId),next=o.nextId&&document.getElementById(o.nextId),last=o.lastId&&document.getElementById(o.lastId),buttons=o.buttonsId&&document.getElementById(o.buttonsId),input=o.inputId&&document.getElementById(o.inputId),jump=o.jumpId&&document.getElementById(o.jumpId),info=o.pageInfoId&&document.getElementById(o.pageInfoId);
 if(first){first.disabled=page<=1;first.onclick=()=>go(1)} if(prev){prev.disabled=page<=1;prev.onclick=()=>go(page-1)} if(next){next.disabled=page>=pages;next.onclick=()=>go(page+1)} if(last){last.disabled=page>=pages;last.onclick=()=>go(pages)}
 if(buttons){buttons.innerHTML=pageList(page,pages).map(p=>`<button class="btn ${p===page?'primary':''}" data-page="${p}">${p}</button>`).join('');buttons.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>go(Number(b.dataset.page)))}
 if(input&&!input.matches(':focus'))input.value=String(page);
 if(jump)jump.onclick=()=>{const p=Math.max(1,Math.min(pages,parseInt(input?.value||String(page),10)||page));go(p)};
 if(input)input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();jump?.click()}};
 if(info)info.textContent=`第 ${page} / ${pages} 页`;
}
function init(o){
 const tbody=document.getElementById(o.tbodyId);if(!tbody)return null;const rows=[...tbody.querySelectorAll('tr')].filter(r=>!r.classList.contains('empty'));
 const q=o.searchId?document.getElementById(o.searchId):null,ps=o.pageSizeId?document.getElementById(o.pageSizeId):null,psOk=o.pageSizeConfirmId?document.getElementById(o.pageSizeConfirmId):null,sum=o.summaryId?document.getElementById(o.summaryId):null,sort=o.sortId?document.getElementById(o.sortId):null,dir=o.sortDirId?document.getElementById(o.sortDirId):null;
 let page=1,size=pageSize(ps,30); if(ps)ps.value=String(size); if(sort&&o.defaultSort)sort.value=o.defaultSort;if(dir&&o.defaultDir)dir.value=o.defaultDir;
 function matchFilter(r,f){const el=document.getElementById(f.id);if(!el||!el.value)return true;const v=String(r.dataset[f.attr]||'').toLowerCase(),t=String(el.value).toLowerCase();return f.contains?v.includes(t):v===t}
 function sortVal(r,s){const v=r.dataset[s.attr]??'';return s.type==='number'?nval(v):String(v)}
 function compare(a,b){const spec=(o.sortMap||{})[sort?.value]||null;if(!spec)return 0;const av=sortVal(a,spec),bv=sortVal(b,spec);let z=spec.type==='number'?av-bv:String(av).localeCompare(String(bv),'zh-CN',{numeric:true,sensitivity:'base'});return dir?.value==='asc'?z:-z}
 function filtered(){const text=(q?.value||'').toLowerCase();return rows.filter(r=>(!text||String(r.dataset.search||r.textContent||'').toLowerCase().includes(text))&&(o.filters||[]).every(f=>matchFilter(r,f))).sort(compare)}
 function go(p){page=p;render()}
 function render(){const a=filtered(),pages=Math.max(1,Math.ceil(a.length/size));if(page>pages)page=pages;if(page<1)page=1;const start=(page-1)*size,end=start+size,vis=new Set(a.slice(start,end));rows.forEach(r=>{r.style.display=vis.has(r)?'':'none'});a.forEach(r=>tbody.appendChild(r));if(sum)sum.textContent=`共 ${a.length} 条 · 当前显示 ${a.length?start+1:0}-${Math.min(end,a.length)}`;renderPager({page,pages,go,firstId:o.firstId,prevId:o.prevId,nextId:o.nextId,lastId:o.lastId,buttonsId:o.buttonsId,inputId:o.pageInputId,jumpId:o.jumpId,pageInfoId:o.pageInfoId})}
 function reset(){page=1;render()}
 if(q)q.addEventListener('input',reset);if(sort)sort.addEventListener('change',reset);if(dir)dir.addEventListener('change',reset);(o.filters||[]).forEach(f=>document.getElementById(f.id)?.addEventListener('change',reset));
 if(psOk)psOk.onclick=()=>{size=pageSize(ps,size);if(ps)ps.value=String(size);reset()};
 render();return {render,go,setPageSize:n=>{size=Math.max(1,Math.min(5000,n||30));if(ps)ps.value=String(size);reset()}};
}
window.CDHTableTools={init,renderPager,pageSize};
})();
