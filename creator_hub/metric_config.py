from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_METRIC_CONFIG

VALID_TYPES={"objective","aggregate_label","constructed","ratio"}  # objective/aggregate kept for legacy import compatibility
VALID_RULE_TYPES={"objective","aggregate_label","constructed","ratio"}


def validate_metric_config(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("metric config must be a JSON object")
    metrics=obj.get("metrics",[]); rules=obj.get("rules",[])
    if not isinstance(metrics,list) or not isinstance(rules,list):
        raise ValueError("metric config requires metrics[] and rules[]")
    ids=set(); type_by_id={}
    for m in metrics:
        if not isinstance(m,dict) or not isinstance(m.get("id"),str) or not m["id"]:
            raise ValueError("each metric requires id")
        if m["id"] in ids:
            raise ValueError(f"duplicate metric id: {m['id']}")
        ids.add(m["id"]); type_by_id[m["id"]]=m.get("type")
        if not isinstance(m.get("name"),str) or not m["name"]:
            raise ValueError("metric requires name")
        if m.get("type") not in VALID_TYPES:
            raise ValueError(f"unsupported metric type: {m.get('type')}")
    for r in rules:
        if not isinstance(r,dict) or not r.get("id"):
            raise ValueError("rule requires id")
        if r.get("relation") and r.get("relation") not in {"AND","OR"}:
            raise ValueError("legacy rule relation must be AND/OR")
        for c in r.get("conditions",[]):
            # v0.6+ conditions can directly reference all four metric categories.
            if c.get("metric_type") and c.get("metric_key"):
                t=c["metric_type"]
                if t not in VALID_RULE_TYPES:
                    raise ValueError(f"unsupported rule metric type: {t}")
                if t in {"constructed","ratio"}:
                    key=c["metric_key"]
                    if key not in ids:
                        raise ValueError(f"rule references missing constructed metric {key}")
                    if type_by_id.get(key)!=t:
                        raise ValueError(f"rule metric type mismatch for {key}")
                if c.get("join") and c.get("join") not in {"AND","OR","NOT"}:
                    raise ValueError("condition join must be AND/OR/NOT")
                continue
            # Legacy v0.5 configuration. Browser migration will convert it; keep imports valid.
            if c.get("metric_id") not in ids:
                raise ValueError(f"rule references missing metric {c.get('metric_id')}")
    filters=obj.get("filters",[])
    if not isinstance(filters,list): filters=[]
    return {"metrics":metrics,"rules":rules,"activeRule":obj.get("activeRule",""),"filters":filters}


def load_metric_config(path: str|Path|None=None)->dict[str,Any]|None:
    p=Path(path) if path else DEFAULT_METRIC_CONFIG
    if not p.exists(): return None
    return validate_metric_config(json.loads(p.read_text(encoding="utf-8")))


def import_metric_config(source: str|Path,dest: str|Path|None=None)->dict[str,Any]:
    obj=validate_metric_config(json.loads(Path(source).read_text(encoding="utf-8"))); dst=Path(dest) if dest else DEFAULT_METRIC_CONFIG
    dst.parent.mkdir(parents=True,exist_ok=True); dst.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"ok":True,"path":str(dst.resolve()),"metrics":len(obj["metrics"]),"rules":len(obj["rules"])}


def export_metric_config(dest: str|Path,source: str|Path|None=None)->dict[str,Any]:
    src=Path(source) if source else DEFAULT_METRIC_CONFIG
    if not src.exists():
        obj={"metrics":[],"rules":[],"activeRule":"","filters":[]}
    else: obj=load_metric_config(src) or {"metrics":[],"rules":[],"activeRule":"","filters":[]}
    dst=Path(dest); dst.parent.mkdir(parents=True,exist_ok=True); dst.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"ok":True,"path":str(dst.resolve()),"metrics":len(obj["metrics"]),"rules":len(obj["rules"])}
