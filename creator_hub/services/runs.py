from __future__ import annotations
import hashlib, json
from typing import Any
from ..db import connect, json_dump, json_load
from ..util import now_utc

class RunService:
    def __init__(self,hub): self.hub=hub; self.db_path=str(hub.db_path)
    @staticmethod
    def canonical(spec:dict[str,Any])->dict[str,Any]:
        # JSON round-trip removes accidental non-serializable subclasses and fixes order at fingerprint time.
        return json.loads(json.dumps(spec,ensure_ascii=False,default=str))
    def save(self,spec_type:str,title:str,spec:dict[str,Any],*,source_ai_run_id:int|None=None,source_result_set_id:int|None=None,parent_spec_id:int|None=None)->dict[str,Any]:
        spec=self.canonical(spec); raw=json.dumps(spec,ensure_ascii=False,sort_keys=True,separators=(',',':')); fp=hashlib.sha256((spec_type+'\n'+raw).encode()).hexdigest();at=now_utc()
        with connect(self.db_path) as conn:
            cur=conn.execute("INSERT INTO run_specs(spec_type,title,spec_version,spec_json,fingerprint,source_ai_run_id,source_result_set_id,parent_spec_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(spec_type,title or spec_type,1,raw,fp,source_ai_run_id,source_result_set_id,parent_spec_id,at));sid=int(cur.lastrowid);conn.commit()
        return {'id':sid,'spec_type':spec_type,'title':title or spec_type,'spec_version':1,'spec':spec,'fingerprint':fp,'created_at':at,'source_ai_run_id':source_ai_run_id,'source_result_set_id':source_result_set_id,'parent_spec_id':parent_spec_id}
    def get(self,spec_id:int)->dict[str,Any]|None:
        with connect(self.db_path) as conn:r=conn.execute('SELECT * FROM run_specs WHERE id=?',(int(spec_id),)).fetchone()
        if not r:return None
        d=dict(r);d['spec']=json_load(d.pop('spec_json'),{});return d
    def list(self,spec_type:str='',page:int=1,page_size:int=30)->dict[str,Any]:
        page=max(1,int(page));page_size=max(1,min(500,int(page_size)));where='';params=[]
        if spec_type:where=' WHERE spec_type=?';params=[spec_type]
        with connect(self.db_path) as conn:
            total=int(conn.execute('SELECT COUNT(*) FROM run_specs'+where,tuple(params)).fetchone()[0]);rows=[dict(r) for r in conn.execute('SELECT * FROM run_specs'+where+' ORDER BY id DESC LIMIT ? OFFSET ?',tuple(params+[page_size,(page-1)*page_size])).fetchall()]
        for d in rows:d['spec']=json_load(d.pop('spec_json'),{})
        return {'rows':rows,'total':total,'page':page,'page_size':page_size,'pages':max(1,(total+page_size-1)//page_size)}
    def clone(self,spec_id:int)->dict[str,Any]:
        src=self.get(spec_id)
        if not src:raise ValueError('run spec not found')
        return self.save(src['spec_type'],src['title']+' · Clone',src['spec'],source_ai_run_id=src.get('source_ai_run_id'),source_result_set_id=src.get('source_result_set_id'),parent_spec_id=src['id'])
    def execute(self,spec_id:int,*,progress=None)->dict[str,Any]:
        src=self.get(spec_id)
        if not src:raise ValueError('run spec not found')
        spec=src['spec'];typ=src['spec_type']
        if typ=='ai_query_search':
            p=dict(spec.get('request') or spec)
            if progress:progress(stage='Clone & Re-run',message='正在按冻结 Run Specification 重新执行',percent=5)
            return self.hub._ai().query_search(str(p.get('query') or ''),language=str(p.get('language') or 'en'),objective=str(p.get('search_requirements') or p.get('objective') or 'creator discovery'),max_queries=int(p.get('max_queries') or 12),max_results=int(p.get('max_results') or 25),lookback_days=p.get('lookback_days'),target_country=p.get('target_country'),target_group=p.get('target_group'),force=True,progress=progress,frozen_plan=dict(spec.get('plan') or {}),frozen_execution=dict(spec.get('execution') or {}),parent_spec_id=src['id'])
        if typ=='ask_hub': return self.hub.ai_ask(str((spec.get('request') or spec).get('question') or ''),force=True)
        raise ValueError(f'run spec type is not executable: {typ}')
