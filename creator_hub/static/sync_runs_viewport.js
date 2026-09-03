(()=>{
'use strict';

const VISIBLE_ROWS = 5;

function installStyle(){
  if(document.getElementById('cdh-sync-runs-viewport-style')) return;
  const style=document.createElement('style');
  style.id='cdh-sync-runs-viewport-style';
  style.textContent=`
#syncRunsScroll{
  overflow-y:scroll!important;
  overflow-x:auto!important;
  scrollbar-gutter:stable!important;
  overscroll-behavior:contain!important;
  position:relative!important;
  border-radius:10px!important;
}
#syncRunsScroll #syncRunsTable{
  margin:0!important;
  width:100%!important;
}
#syncRunsScroll #syncRunsTable thead th{
  position:sticky!important;
  top:0!important;
  z-index:6!important;
  background:#fafbfc!important;
}
#syncRunsScroll::-webkit-scrollbar{width:10px;height:9px}
#syncRunsScroll::-webkit-scrollbar-track{
  background:rgba(148,163,184,.10);
  border-radius:999px;
}
#syncRunsScroll::-webkit-scrollbar-thumb{
  background:rgba(100,116,139,.48);
  border-radius:999px;
}
#sync-runs .sync-fixed-page-size{
  white-space:nowrap;
  color:var(--muted);
  font-size:12px;
}
`;
  document.head.appendChild(style);
}

function init(){
  const section=document.getElementById('sync-runs');
  const shell=document.getElementById('syncRunsScroll');
  const table=document.getElementById('syncRunsTable');
  const tbody=document.getElementById('syncRows');
  if(!section||!shell||!table||!tbody) return;

  installStyle();

  let frame=0;
  let resetScroll=false;

  function visibleRows(){
    return [...tbody.querySelectorAll('tr')].filter(row=>{
      if(row.classList.contains('empty')) return false;
      return getComputedStyle(row).display!=='none';
    });
  }

  function fitShell(){
    frame=0;
    if(resetScroll){
      shell.scrollTop=0;
      resetScroll=false;
    }

    const rows=visibleRows();
    const headH=Math.ceil(table.tHead?.getBoundingClientRect().height||0);
    const sample=rows.slice(0,VISIBLE_ROWS);

    let rowsH=0;
    sample.forEach(row=>{
      rowsH+=Math.ceil(row.getBoundingClientRect().height||0);
    });

    const target=Math.max(80, headH+rowsH+2);
    shell.style.height=`${target}px`;
    shell.style.minHeight=`${target}px`;
    shell.style.maxHeight=`${target}px`;
    shell.style.overflowY=rows.length>VISIBLE_ROWS?'scroll':'auto';
  }

  function schedule(reset=false){
    if(reset) resetScroll=true;
    if(frame) cancelAnimationFrame(frame);
    frame=requestAnimationFrame(()=>requestAnimationFrame(fitShell));
  }

  const mo=new MutationObserver(()=>schedule(true));
  mo.observe(tbody,{
    childList:true,
    subtree:false,
    attributes:true,
    attributeFilter:['style']
  });

  if(window.ResizeObserver){
    const ro=new ResizeObserver(()=>schedule(false));
    ro.observe(table);
  }else{
    window.addEventListener('resize',()=>schedule(false));
  }

  section.addEventListener('click',e=>{
    if(e.target.closest('.pager')){
      setTimeout(()=>schedule(true),0);
    }
  });
  document.getElementById('syncSearch')?.addEventListener('input',()=>setTimeout(()=>schedule(true),0));
  document.getElementById('syncSort')?.addEventListener('change',()=>setTimeout(()=>schedule(true),0));
  document.getElementById('syncSortDir')?.addEventListener('change',()=>setTimeout(()=>schedule(true),0));

  schedule(true);
}

if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
else init();
})();
