from __future__ import annotations
import json
from typing import Any
from ..db import connect, json_dump, json_load
from ..util import now_utc

LAYER_PRIORITY={'human':40,'ai':30,'derived':20,'fact':10}
VALID_LAYERS=set(LAYER_PRIORITY)

class DataContractService:
    """Canonical provenance contract: Fact -> Derived -> AI -> Human -> Effective.

    The assertion table is additive/auditable. Existing purpose-built tables remain the
    operational source of truth during V3.10, while new/bridged features can publish the
    same value through this uniform contract.
    """
    def __init__(self, db_path): self.db_path=str(db_path)
    def assert_value(self,entity_type:str,entity_id:str,field_id:str,layer:str,value:Any,*,confidence:float|None=None,source_ref:str='',rule_version:str='',observed_at:str|None=None,supersedes_id:int|None=None)->dict[str,Any]:
        layer=str(layer).lower()
        if layer not in VALID_LAYERS: raise ValueError('layer must be fact/derived/ai/human')
        at=now_utc()
        with connect(self.db_path) as conn:
            cur=conn.execute("""INSERT INTO data_assertions(entity_type,entity_id,field_id,layer,value_json,confidence,source_ref,rule_version,observed_at,created_at,supersedes_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(entity_type,entity_id,field_id,layer,json_dump(value),confidence,source_ref,rule_version,observed_at or at,at,supersedes_id))
            conn.commit(); aid=int(cur.lastrowid)
        return {'id':aid,'entity_type':entity_type,'entity_id':entity_id,'field_id':field_id,'layer':layer,'value':value,'created_at':at}
    def effective(self,entity_type:str,entity_id:str,field_id:str)->dict[str,Any]|None:
        with connect(self.db_path) as conn:
            rows=[dict(r) for r in conn.execute("SELECT * FROM data_assertions WHERE entity_type=? AND entity_id=? AND field_id=? ORDER BY created_at DESC,id DESC",(entity_type,entity_id,field_id)).fetchall()]
        if not rows:return None
        rows.sort(key=lambda r:(LAYER_PRIORITY.get(str(r.get('layer')),0),str(r.get('created_at') or ''),int(r.get('id') or 0)),reverse=True)
        r=rows[0]
        return {'value':json_load(r.get('value_json'),None),'effective_layer':r.get('layer'),'source_ref':r.get('source_ref'),'confidence':r.get('confidence'),'rule_version':r.get('rule_version'),'observed_at':r.get('observed_at'),'assertion_id':r.get('id')}
    def history(self,entity_type:str,entity_id:str,field_id:str,limit:int=50)->list[dict[str,Any]]:
        with connect(self.db_path) as conn:
            rows=[dict(r) for r in conn.execute("SELECT * FROM data_assertions WHERE entity_type=? AND entity_id=? AND field_id=? ORDER BY created_at DESC,id DESC LIMIT ?",(entity_type,entity_id,field_id,max(1,min(500,int(limit))))).fetchall()]
        for r in rows:r['value']=json_load(r.pop('value_json'),None)
        return rows
