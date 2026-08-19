(()=>{
'use strict';
const links=[...document.querySelectorAll('[data-section-nav]')];
if(!links.length)return;
const items=links.map((link,index)=>({link,index,id:link.dataset.sectionNav,section:document.getElementById(link.dataset.sectionNav)})).filter(x=>x.section);
if(!items.length)return;
let activeId='';
let clickedId='';
let clickHoldUntil=0;
function activate(id){
  activeId=id;
  for(const x of items){
    const on=x.id===id;
    x.link.classList.toggle('section-active',on);
    if(on)x.link.setAttribute('aria-current','location');else x.link.removeAttribute('aria-current');
  }
}
function bestVisible(){
  const threshold=Math.min(150,Math.max(90,window.innerHeight*.16));
  const visible=items.map(x=>({x,rect:x.section.getBoundingClientRect()}))
    .filter(o=>o.rect.bottom>55 && o.rect.top<window.innerHeight-40);
  if(!visible.length)return items[0];
  const passed=visible.filter(o=>o.rect.top<=threshold);
  if(passed.length){
    // Pick the section whose top is closest to the reading line. For side-by-side
    // panels with effectively the same top, keep the user's most recent click.
    passed.sort((a,b)=>Math.abs(a.rect.top-threshold)-Math.abs(b.rect.top-threshold)||a.x.index-b.x.index);
    const nearest=passed[0];
    const ties=passed.filter(o=>Math.abs(o.rect.top-nearest.rect.top)<8);
    if(clickedId && ties.some(o=>o.x.id===clickedId))return ties.find(o=>o.x.id===clickedId).x;
    return nearest.x;
  }
  visible.sort((a,b)=>a.rect.top-b.rect.top||a.x.index-b.x.index);
  return visible[0].x;
}
let queued=false;
function sync(){
  queued=false;
  if(Date.now()<clickHoldUntil)return;
  const item=bestVisible();
  if(item && item.id!==activeId)activate(item.id);
}
function queue(){if(!queued){queued=true;requestAnimationFrame(sync)}}
for(const x of items){
  x.link.addEventListener('click',e=>{
    e.preventDefault();
    clickedId=x.id;
    clickHoldUntil=Date.now()+700;
    history.replaceState(null,'','#'+x.id);
    activate(x.id);
    x.section.scrollIntoView({behavior:'smooth',block:'start'});
  });
}
window.addEventListener('scroll',queue,{passive:true});
window.addEventListener('resize',queue);
const initial=location.hash.slice(1);
const target=items.find(x=>x.id===initial);
if(target){
  clickedId=target.id;
  setTimeout(()=>{target.section.scrollIntoView({block:'start'});activate(target.id)},0);
}else activate(items[0].id);
})();
