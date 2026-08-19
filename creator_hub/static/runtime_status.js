(()=>{
'use strict';
const box=document.getElementById('runtimeStatus');if(!box)return;
function staticMode(){box.className='runtime-status runtime-static';box.innerHTML='<b>运行模式：静态只读</b><span>当前页面是本地生成的 HTML 快照；不会启动 Python 服务。查看数据可用，搜索、写入、完整服务端筛选与 XLSX 导出需使用 <span class="mono">start-dashboard.cmd</span>。</span>'}
fetch('/api/ping',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(x=>{box.className='runtime-status runtime-live';box.innerHTML=`<b>运行模式：交互模式</b><span>Python ${x.python||'—'} · SQLite ${x.db_exists?'已连接':'未连接'} · API Key ${x.api_key_present?'已配置':'未配置'} · <span class="mono">127.0.0.1:8765</span>（仅本机）</span>`;window.CDH_INTERACTIVE=true;window.dispatchEvent(new CustomEvent('cdh-interactive-ready',{detail:x}))}).catch(()=>{window.CDH_INTERACTIVE=false;staticMode()});
})();
