(()=>{
'use strict';
const input=document.getElementById('businessImportFile'),btn=document.getElementById('businessImportBtn'),status=document.getElementById('businessImportStatus');if(!input||!btn)return;
function b64(buf){let bin='',u=new Uint8Array(buf),step=0x8000;for(let i=0;i<u.length;i+=step)bin+=String.fromCharCode(...u.subarray(i,i+step));return btoa(bin)}
btn.onclick=async()=>{const f=input.files?.[0];if(!f)return alert('请选择 XLSX / CSV');if(f.size>40*1024*1024)return alert('文件超过 40MB');try{status.textContent='正在读取文件并提交导入任务…';const content_base64=b64(await f.arrayBuffer());const payload={filename:f.name,content_base64,source_type:'dashboard_import'};const x=window.CDHJobs?await CDHJobs.run('business_import',payload):null;if(!x)throw new Error('需要交互 Dashboard');status.textContent=`导入完成：匹配 ${x.creators_matched||0} 个博主，写入 ${x.metric_values_upserted||0} 个指标值，未匹配 ${x.unmatched_rows||0} 行。刷新博主库即可看到 GMV/拉新。`;try{localStorage.setItem('cdh-data-revision',String(Date.now()))}catch(_){}}catch(e){status.textContent='导入失败：'+e.message}}
})();
