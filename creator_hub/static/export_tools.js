(()=>{
'use strict';
const escFile=s=>String(s||'export').replace(/[^A-Za-z0-9._-]+/g,'_').replace(/^[_\.]+|[_\.]+$/g,'').slice(0,100)||'export';
async function interactive(){if(window.CDH_INTERACTIVE===true)return true;try{const r=await fetch('/api/ping',{cache:'no-store'});if(r.ok){window.CDH_INTERACTIVE=true;return true}}catch(e){}return false}
async function download(payload,filename){if(!(await interactive())){alert('完整 XLSX 导出需要交互 Dashboard。请使用 start-dashboard.cmd 打开 http://.1:8765/ 后再导出。');return false}const r=await fetch('/api/export/xlsx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok){let msg='导出失败';try{const x=await r.json();msg=x.error||msg}catch(e){}throw new Error(msg)}const blob=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=escFile(filename||'export.xlsx');document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1500);return true}
window.CDHExport={download,rows:(filename,sheet,columns,rows)=>download({source:'rows',filename,sheet,columns,rows},filename),source:(source,filename,sheet,payload={})=>download({source,filename,sheet,...payload},filename),interactive};
})();
