from __future__ import annotations

import copy, json, queue, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from .db import connect, json_dump, json_load


def _now()->str:return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

class JobCancelled(RuntimeError): pass

class JobProgress:
    def __init__(self,engine:'JobEngine',jid:str):self.engine=engine;self.jid=jid
    def __call__(self,*,stage=None,message=None,current=None,total=None,percent=None,checkpoint=None,**extra):
        self.raise_if_cancelled();self.engine._progress(self.jid,stage=stage,message=message,current=current,total=total,percent=percent,checkpoint=checkpoint,**extra)
    def cancelled(self)->bool:return self.engine.is_cancel_requested(self.jid)
    def raise_if_cancelled(self):
        if self.cancelled():raise JobCancelled('cancel_requested')
    def checkpoint(self,value:dict[str,Any]):self.engine._progress(self.jid,checkpoint=value)

class JobEngine:
    """Persistent local Job Engine with resource queues, cancellation and checkpoints.

    Resource classes avoid YouTube/AI tasks competing with each other. Payload and checkpoint
    are persisted so explicitly resumable jobs can be re-queued after a server restart.
    """
    DEFAULT_LIMITS={'youtube':1,'ai':1,'local':2,'maintenance':1}
    TERMINAL={'complete','failed','cancelled'}
    def __init__(self,db_path:str|Path|None=None,max_jobs:int=200,limits:dict[str,int]|None=None):
        self.max_jobs=max(30,int(max_jobs));self.db_path=Path(db_path) if db_path else None;self.limits={**self.DEFAULT_LIMITS,**(limits or {})}
        self._lock=threading.RLock();self._jobs={};self._runners={};self._queues={k:queue.Queue() for k in self.limits};self._factory=None;self._stop=False
        self._workers=[]
        for rc,n in self.limits.items():
            for i in range(max(1,int(n))):
                t=threading.Thread(target=self._worker,args=(rc,),name=f'cdh-job-{rc}-{i+1}',daemon=True);t.start();self._workers.append(t)
    def set_runner_factory(self,factory:Callable[[str,dict[str,Any]],Callable[[JobProgress],Any]]):
        self._factory=factory;self._recover_persisted()
    def _recover_persisted(self):
        if not self.db_path:return
        try:
            with connect(self.db_path) as conn:
                rows=conn.execute("SELECT * FROM job_runs WHERE state IN ('queued','running') ORDER BY updated_at").fetchall()
                for r in rows:
                    d=self._from_row(r);jid=str(d['job_id'])
                    if d.get('resumable'):
                        d.update(state='queued',stage='恢复排队',message='Dashboard 重启后根据持久化任务规格重新排队',worker_id=None,updated_at=_now())
                        with self._lock:self._jobs[jid]=d
                        self._persist(d);self._queues.setdefault(d.get('resource_class') or 'local',queue.Queue()).put(jid)
                    else:
                        d.update(state='failed',stage='已中断',message='Dashboard 服务关闭；该任务未声明可恢复，请重新执行。',error='interrupted_by_server_restart',finished_at=_now(),updated_at=_now())
                        self._persist(d)
        except Exception:pass
    def _persist(self,j:dict[str,Any]):
        if not self.db_path:return
        try:
            with connect(self.db_path) as conn:
                conn.execute("""INSERT INTO job_runs(job_id,task,title,state,stage,message,current_value,total_value,percent,started_at,updated_at,finished_at,elapsed_seconds,result_json,error,payload_json,resource_class,cancel_requested,checkpoint_json,resumable,retry_count,parent_job_id,worker_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET task=excluded.task,title=excluded.title,state=excluded.state,stage=excluded.stage,message=excluded.message,current_value=excluded.current_value,total_value=excluded.total_value,percent=excluded.percent,started_at=excluded.started_at,updated_at=excluded.updated_at,finished_at=excluded.finished_at,elapsed_seconds=excluded.elapsed_seconds,result_json=excluded.result_json,error=excluded.error,payload_json=excluded.payload_json,resource_class=excluded.resource_class,cancel_requested=excluded.cancel_requested,checkpoint_json=excluded.checkpoint_json,resumable=excluded.resumable,retry_count=excluded.retry_count,parent_job_id=excluded.parent_job_id,worker_id=excluded.worker_id""",
                (j.get('job_id'),j.get('task'),j.get('title'),j.get('state'),j.get('stage'),j.get('message'),j.get('current'),j.get('total'),j.get('percent'),j.get('started_at'),j.get('updated_at') or _now(),j.get('finished_at'),float(j.get('elapsed_seconds') or 0),json_dump(j.get('result') or {}),j.get('error'),json_dump(j.get('payload') or {}),j.get('resource_class') or 'local',int(bool(j.get('cancel_requested'))),json_dump(j.get('checkpoint') or {}),int(bool(j.get('resumable'))),int(j.get('retry_count') or 0),j.get('parent_job_id'),j.get('worker_id')));conn.commit()
        except Exception:pass
    @staticmethod
    def _from_row(row):
        d=dict(row);return {'job_id':d.get('job_id'),'task':d.get('task'),'title':d.get('title'),'state':d.get('state'),'stage':d.get('stage'),'message':d.get('message'),'current':d.get('current_value'),'total':d.get('total_value'),'percent':d.get('percent'),'started_at':d.get('started_at'),'updated_at':d.get('updated_at'),'finished_at':d.get('finished_at'),'elapsed_seconds':d.get('elapsed_seconds') or 0,'result':json_load(d.get('result_json'),{}),'error':d.get('error'),'payload':json_load(d.get('payload_json'),{}),'resource_class':d.get('resource_class') or 'local','cancel_requested':bool(d.get('cancel_requested')),'checkpoint':json_load(d.get('checkpoint_json'),{}),'resumable':bool(d.get('resumable')),'retry_count':int(d.get('retry_count') or 0),'parent_job_id':d.get('parent_job_id'),'worker_id':d.get('worker_id')}
    def _worker(self,resource_class:str):
        q=self._queues[resource_class]
        while not self._stop:
            try:jid=q.get(timeout=.5)
            except queue.Empty:continue
            try:self._execute(jid,resource_class)
            finally:q.task_done()
    def _execute(self,jid:str,resource_class:str):
        with self._lock:
            j=self._jobs.get(jid) or self.get(jid)
            if not j:return
            if j.get('state')=='cancelled' or j.get('cancel_requested'):
                j.update(state='cancelled',stage='已取消',finished_at=_now(),updated_at=_now());self._jobs[jid]=j;self._persist(j);return
            runner=self._runners.get(jid)
            if runner is None and self._factory:
                payload=dict(j.get('payload') or {});payload['_resume_checkpoint']=dict(j.get('checkpoint') or {})
                try:runner=self._factory(str(j.get('task')),payload)
                except Exception as exc:
                    j.update(state='failed',stage='无法恢复',error=f'{type(exc).__name__}: {exc}',message='无法根据持久化任务规格恢复',finished_at=_now(),updated_at=_now());self._persist(j);return
            if runner is None:return
            j.update(state='running',stage='开始执行',started_at=j.get('started_at') or _now(),updated_at=_now(),worker_id=threading.current_thread().name,_started_monotonic=time.monotonic());self._jobs[jid]=j;self._persist(j)
        progress=JobProgress(self,jid)
        try:
            result=runner(progress);progress.raise_if_cancelled()
            with self._lock:
                j=self._jobs[jid];j.update(state='complete',result=result,stage='完成',percent=100.0,finished_at=_now(),updated_at=_now(),worker_id=None);j['elapsed_seconds']=round(time.monotonic()-float(j.get('_started_monotonic') or time.monotonic()),1);self._persist(j)
        except JobCancelled:
            with self._lock:
                j=self._jobs[jid];j.update(state='cancelled',stage='已取消',message='用户请求取消；已完成的批次数据保留。',finished_at=_now(),updated_at=_now(),worker_id=None);self._persist(j)
        except Exception as exc:
            with self._lock:
                j=self._jobs[jid];err=f'{type(exc).__name__}: {exc}';j.update(state='failed',error=err,stage='失败',message=err,finished_at=_now(),updated_at=_now(),worker_id=None);self._persist(j)
    def _progress(self,jid:str,*,stage=None,message=None,current=None,total=None,percent=None,checkpoint=None,**extra):
        with self._lock:
            j=self._jobs.get(jid)
            if not j:return
            if stage is not None:j['stage']=str(stage)
            if message is not None:j['message']=str(message)
            if current is not None:j['current']=current
            if total is not None:j['total']=total
            if checkpoint is not None:j['checkpoint']=dict(checkpoint)
            elif current is not None:j['checkpoint']={**dict(j.get('checkpoint') or {}),'current':current,'total':total if total is not None else j.get('total')}
            if percent is None and j.get('total') not in (None,0) and current is not None:
                try:percent=100*float(current)/float(j['total'])
                except Exception:percent=None
            if percent is not None:j['percent']=round(max(0,min(100,float(percent))),1)
            for k,v in extra.items():j[k]=v
            j['updated_at']=_now()
            if j.get('_started_monotonic') is not None:j['elapsed_seconds']=round(time.monotonic()-float(j['_started_monotonic']),1)
            self._persist(j)
    def start(self,*,task:str,title:str,runner:Callable[[JobProgress],Any]|None=None,payload:dict[str,Any]|None=None,resource_class:str='local',resumable:bool=False,parent_job_id:str|None=None)->dict[str,Any]:
        rc=resource_class if resource_class in self._queues else 'local';jid=uuid.uuid4().hex;job={'job_id':jid,'task':task,'title':title or task,'state':'queued','stage':'等待执行','message':f'任务已进入 {rc} 队列','current':0,'total':None,'percent':None,'started_at':None,'updated_at':_now(),'finished_at':None,'elapsed_seconds':0,'result':None,'error':None,'payload':dict(payload or {}),'resource_class':rc,'cancel_requested':False,'checkpoint':{},'resumable':bool(resumable),'retry_count':0,'parent_job_id':parent_job_id,'worker_id':None}
        with self._lock:self._jobs[jid]=job;self._runners[jid]=runner;self._persist(job)
        self._queues[rc].put(jid);return self.get(jid) or job
    def is_cancel_requested(self,jid:str)->bool:
        with self._lock:
            j=self._jobs.get(str(jid));
            if j:return bool(j.get('cancel_requested'))
        if self.db_path:
            with connect(self.db_path) as conn:r=conn.execute('SELECT cancel_requested FROM job_runs WHERE job_id=?',(str(jid),)).fetchone()
            return bool(r and r[0])
        return False
    def cancel(self,jid:str)->dict[str,Any]:
        j=self.get(jid)
        if not j:raise ValueError('job not found')
        if j.get('state') in self.TERMINAL:return j
        with self._lock:
            cur=self._jobs.get(jid,j);cur['cancel_requested']=True;cur['message']='已请求取消；将在当前安全检查点停止';cur['updated_at']=_now()
            if cur.get('state')=='queued':cur.update(state='cancelled',stage='已取消',finished_at=_now())
            self._jobs[jid]=cur;self._persist(cur)
        return self.get(jid)
    def retry(self,jid:str)->dict[str,Any]:
        j=self.get(jid)
        if not j:raise ValueError('job not found')
        if not self._factory:raise RuntimeError('runner factory unavailable')
        payload=dict(j.get('payload') or {});runner=self._factory(str(j.get('task')),payload)
        out=self.start(task=str(j.get('task')),title=str(j.get('title')),runner=runner,payload=payload,resource_class=str(j.get('resource_class') or 'local'),resumable=bool(j.get('resumable')),parent_job_id=jid)
        with self._lock:self._jobs[out['job_id']]['retry_count']=int(j.get('retry_count') or 0)+1;self._persist(self._jobs[out['job_id']])
        return self.get(out['job_id'])
    def get(self,jid:str):
        with self._lock:
            j=self._jobs.get(str(jid))
            if j:out=copy.deepcopy(j);out.pop('_started_monotonic',None);return out
        if self.db_path:
            try:
                with connect(self.db_path) as conn:r=conn.execute('SELECT * FROM job_runs WHERE job_id=?',(str(jid),)).fetchone()
                return self._from_row(r) if r else None
            except Exception:pass
        return None
    def list(self,limit:int=30):
        limit=max(1,min(200,int(limit)));merged={}
        if self.db_path:
            try:
                with connect(self.db_path) as conn:rows=conn.execute('SELECT * FROM job_runs ORDER BY updated_at DESC LIMIT ?',(limit,)).fetchall()
                for r in rows:
                    j=self._from_row(r);merged[str(j['job_id'])]=j
            except Exception:pass
        with self._lock:
            for raw in self._jobs.values():j=copy.deepcopy(raw);j.pop('_started_monotonic',None);merged[str(j['job_id'])]=j
        return sorted(merged.values(),key=lambda x:x.get('updated_at') or '',reverse=True)[:limit]

# Backwards-compatible name used by older imports.
JobStore=JobEngine
