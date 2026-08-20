(()=>{
'use strict';
const api=async(path,body)=>{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const j=await r.json().catch(()=>({}));if(!r.ok||j.ok===false)throw new Error(j.error||`HTTP ${r.status}`);return j};
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const LS_MODE='cdh_job_center_mode_v2',LS_DISMISSED='cdh_job_center_dismissed_v2';
let pollTimer=null,lastJobs=[],mode=localStorage.getItem(LS_MODE)||'expanded';
let dismissed=new Set(JSON.parse(localStorage.getItem(LS_DISMISSED)||'[]'));
function saveDismissed(){localStorage.setItem(LS_DISMISSED,JSON.stringify([...dismissed].slice(-200)))}
function setMode(next){mode=next;localStorage.setItem(LS_MODE,mode);applyMode()}
function shell(){let d=document.getElementById('cdhJobDock');if(d)return d;
 d=document.createElement('div');d.id='cdhJobDock';d.className='job-dock';
 d.innerHTML=`<div class="job-center-head"><div class="job-center-title"><b>任务中心</b><span id="cdhJobBadge" class="job-badge">0</span></div><div class="job-center-actions"><button type="button" class="job-icon-btn" id="cdhJobMin" title="最小化">—</button><button type="button" class="job-icon-btn" id="cdhJobClose" title="关闭任务中心（不会停止后台任务）">×</button></div></div><div id="cdhJobList" class="job-list"></div>`;
 document.body.appendChild(d);
 let launcher=document.getElementById('cdhJobLauncher');if(!launcher){launcher=document.createElement('button');launcher.type='button';launcher.id='cdhJobLauncher';launcher.className='job-launcher';launcher.title='打开任务中心';launcher.innerHTML=`<span>任务</span><b id="cdhJobLauncherBadge">0</b>`;document.body.appendChild(launcher);launcher.onclick=()=>setMode('expanded')}
 d.querySelector('#cdhJobMin').onclick=()=>setMode('minimized');d.querySelector('#cdhJobClose').onclick=()=>setMode('closed');applyMode();return d}
function applyMode(){const d=document.getElementById('cdhJobDock'),l=document.getElementById('cdhJobLauncher');if(!d||!l)return;const active=lastJobs.filter(j=>['queued','running'].includes(j.state)).length;d.classList.toggle('job-hidden',mode!=='expanded');l.classList.toggle('visible',mode==='minimized'||(mode==='closed'&&active>0));l.classList.toggle('quiet',mode==='closed')}
function listEl(){return shell().querySelector('#cdhJobList')}
function badge(n){const el=shell().querySelector('#cdhJobBadge'),lb=document.getElementById('cdhJobLauncherBadge');el.textContent=String(n||0);el.classList.toggle('active',Number(n||0)>0);if(lb)lb.textContent=String(n||0)}
function dismiss(jobId){dismissed.add(String(jobId));saveDismissed();document.getElementById(`job-${jobId}`)?.remove();renderJobs(lastJobs)}
function card(job){const list=listEl();let c=document.getElementById(`job-${job.job_id}`);if(!c){c=document.createElement('div');c.id=`job-${job.job_id}`;list.prepend(c)}
 const pct=job.percent==null?'':`${Math.round(Number(job.percent)||0)}%`;const cur=job.total!=null?`${job.current||0} / ${job.total}`:'';const elapsed=job.elapsed_seconds!=null?`耗时 ${Math.round(Number(job.elapsed_seconds)||0)} 秒`:'';const when=job.finished_at||job.updated_at||'';
 c.className=`job-card job-${job.state||'running'}`;
 c.innerHTML=`<div class="job-top"><b>${esc(job.title||job.task||'后台任务')}</b><div class="job-card-actions"><span>${esc(pct)}</span><button type="button" class="job-card-dismiss" title="从任务中心隐藏；不会取消任务">×</button></div></div><div class="job-stage">${esc(job.stage||'')}</div><div class="job-message">${esc(job.message||job.error||'')}</div>${job.percent!=null?`<div class="job-track"><div class="job-bar" style="width:${Math.max(0,Math.min(100,Number(job.percent)||0))}%"></div></div>`:''}<div class="job-meta">${esc([cur,elapsed,when].filter(Boolean).join(' · '))}</div>`;
 c.querySelector('.job-card-dismiss').onclick=()=>dismiss(job.job_id);return c;
}
function renderJobs(jobs){lastJobs=jobs||[];const keep=new Set();let active=0;lastJobs.slice(0,20).forEach(j=>{if(['queued','running'].includes(j.state))active++;if(dismissed.has(String(j.job_id)))return;keep.add(`job-${j.job_id}`);card(j)});listEl().querySelectorAll('.job-card').forEach(x=>{if(!keep.has(x.id))x.remove()});badge(active);applyMode();return active}
async function refresh(){try{const x=await api('/api/jobs/list',{limit:20});const active=renderJobs(x.jobs||[]);clearTimeout(pollTimer);pollTimer=setTimeout(refresh,active?1000:6000)}catch(_){clearTimeout(pollTimer);pollTimer=setTimeout(refresh,10000)}}
async function watch(jobId){dismissed.delete(String(jobId));saveDismissed();while(true){const j=(await api('/api/jobs/status',{job_id:jobId})).job;card(j);await refresh();if(j.state==='complete')return j.result;if(j.state==='failed')throw new Error(j.error||'任务失败');await new Promise(r=>setTimeout(r,700))}}
async function run(task,payload){const start=await api('/api/jobs/start',{task,payload:payload||{}});dismissed.delete(String(start.job.job_id));saveDismissed();card(start.job);setMode('expanded');refresh();return watch(start.job.job_id)}
window.CDHJobs={run,watch,api,refresh,open:()=>setMode('expanded'),minimize:()=>setMode('minimized'),close:()=>setMode('closed'),dismiss};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{shell();refresh()});else{shell();refresh()}
})();
