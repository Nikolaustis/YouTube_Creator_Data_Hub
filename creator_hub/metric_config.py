from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_METRIC_CONFIG, LEGACY_METRIC_CONFIG

CANONICAL_METRIC_TYPES={"constructed","ratio"}
CANONICAL_RULE_TYPES={"creator_fact","creator_label","constructed","ratio"}


def _label_false(op: Any, value: Any) -> bool:
    try: n=float(value)
    except Exception: n=None
    return (op=="eq" and n==0) or (op=="lte" and n is not None and n<=0) or (op=="neq" and n==1)


def _normalize_condition(c: dict[str,Any], idx:int, invalid_labels:dict[str,str], valid_ids:set[str]) -> dict[str,Any] | None:
    t=c.get("metric_type") or c.get("type") or ""
    key=c.get("metric_key") or c.get("key") or c.get("metric_id") or ""
    if t=="objective": t="creator_fact"
    if t=="aggregate_label": t="creator_label"
    if t=="constructed" and key in invalid_labels:
        t="creator_label"; key=invalid_labels[key]
    if t not in CANONICAL_RULE_TYPES:
        return None
    if t in {"constructed","ratio"} and key not in valid_ids:
        return None
    join="" if idx==0 else str(c.get("join") or "AND").upper()
    if join not in {"","AND","OR","NOT"}: join="AND"
    if t=="creator_label":
        return {"join":join,"metric_type":t,"metric_key":key,"op":"falsy" if c.get("op")=="falsy" or _label_false(c.get("op"),c.get("value")) else "truthy","value":""}
    return {"join":join,"metric_type":t,"metric_key":key,"op":c.get("op") or "gte","value":c.get("value","")}


def normalize_metric_config(obj: Any) -> dict[str,Any]:
    if not isinstance(obj,dict):
        raise ValueError("metric config must be a JSON object")
    raw_metrics=obj.get("metrics",[]); raw_rules=obj.get("rules",[])
    if not isinstance(raw_metrics,list) or not isinstance(raw_rules,list):
        raise ValueError("metric config requires metrics[] and rules[]")

    metrics:list[dict[str,Any]]=[]
    valid_ids:set[str]=set()
    invalid_labels:dict[str,str]={}
    ratios:list[dict[str,Any]]=[]
    seen:set[str]=set()

    for raw in raw_metrics:
        if not isinstance(raw,dict) or not isinstance(raw.get("id"),str) or not raw.get("id"):
            raise ValueError("each metric requires id")
        if raw["id"] in seen:
            raise ValueError(f"duplicate metric id: {raw['id']}")
        seen.add(raw["id"])
        if not isinstance(raw.get("name"),str) or not raw.get("name"):
            raise ValueError("metric requires name")
        typ=raw.get("type")
        if typ not in {"constructed","ratio","objective","aggregate_label"}:
            raise ValueError(f"unsupported metric type: {typ}")
        if typ in {"objective","aggregate_label"}:
            # Legacy pseudo-metrics were only wrappers around creator facts/labels.
            if typ=="aggregate_label" and raw.get("field"):
                invalid_labels[raw["id"]]=str(raw["field"])
            continue
        if typ=="ratio":
            ratios.append(dict(raw)); continue
        source_kind=raw.get("source_kind") or "video_fact"
        if source_kind=="aggregate_label":
            if raw.get("source_field"): invalid_labels[raw["id"]]=str(raw["source_field"])
            continue
        m=dict(raw)
        if source_kind=="objective": source_kind="video_fact"
        if source_kind=="label":
            if str(raw.get("aggregation") or "count") not in {"count","sum"}:
                continue
            m["source_field"]="video_count";m["filter_label"]=raw.get("source_field") or "";m["aggregation"]="count";source_kind="video_fact"
        m["source_kind"]="video_fact"
        metrics.append(m);valid_ids.add(m["id"])

    # Ratios now reference creator-level numeric values. Legacy direct video specs are
    # migrated into hidden constructed metrics, then referenced by the ratio.
    for raw in ratios:
        num=raw.get("numerator_ref"); den=raw.get("denominator_ref")
        if not (isinstance(num,dict) and isinstance(den,dict)) and raw.get("numerator_spec") and raw.get("denominator_spec"):
            refs=[]
            for suffix,label,spec in (("num","分子",raw["numerator_spec"]),("den","分母",raw["denominator_spec"])):
                iid=f"{raw['id']}__legacy_{suffix}"
                side={"id":iid,"name":f"{raw['name']} · {label}","type":"constructed","source_kind":"video_fact","source_field":spec.get("source_field") or "current_views","filter_label":spec.get("filter_label") or "","window":spec.get("window") or "all","from_date":spec.get("from_date") or "","to_date":spec.get("to_date") or "","aggregation":spec.get("aggregation") or "count","visible":False,"internal":True,"version":1}
                metrics.append(side);valid_ids.add(iid);refs.append({"kind":"constructed","key":iid})
            num,den=refs
        if not isinstance(num,dict):
            old=raw.get("legacy_numerator") or raw.get("numerator")
            if old:num={"kind":"constructed","key":old}
        if not isinstance(den,dict):
            old=raw.get("legacy_denominator") or raw.get("denominator")
            if old:den={"kind":"constructed","key":old}
        if not (isinstance(num,dict) and isinstance(den,dict)):
            continue
        for ref in (num,den):
            if ref.get("kind") not in {"creator_fact","constructed"}:
                raise ValueError("ratio refs must use creator_fact or constructed")
            if ref.get("kind")=="constructed" and ref.get("key") not in valid_ids:
                raise ValueError(f"ratio references missing constructed metric {ref.get('key')}")
        m={k:v for k,v in raw.items() if k not in {"numerator_spec","denominator_spec","legacy_numerator","legacy_denominator","numerator","denominator"}}
        m["numerator_ref"]=num;m["denominator_ref"]=den
        metrics.append(m);valid_ids.add(m["id"])

    rules=[]
    for raw in raw_rules:
        if not isinstance(raw,dict) or not raw.get("id"):
            raise ValueError("rule requires id")
        relation=str(raw.get("relation") or "AND").upper()
        conds=[]
        for i,c in enumerate(raw.get("conditions",[])):
            if not isinstance(c,dict): continue
            cc=dict(c)
            if i and not cc.get("join"): cc["join"]=relation
            n=_normalize_condition(cc,i,invalid_labels,valid_ids)
            if n and n.get("metric_key"): conds.append(n)
        rules.append({**raw,"conditions":conds})

    filters=[]
    raw_filters=obj.get("filters",[])
    if isinstance(raw_filters,list):
        for i,c in enumerate(raw_filters):
            if isinstance(c,dict):
                n=_normalize_condition(c,i,invalid_labels,valid_ids)
                if n and n.get("metric_key"): filters.append(n)

    return {"schema_version":1,"metrics":metrics,"rules":rules,"activeRule":obj.get("activeRule",""),"filters":filters}


def validate_metric_config(obj: Any) -> dict[str,Any]:
    return normalize_metric_config(obj)


def load_metric_config(path: str|Path|None=None)->dict[str,Any]|None:
    if path:
        p=Path(path)
    else:
        p=DEFAULT_METRIC_CONFIG if DEFAULT_METRIC_CONFIG.exists() else LEGACY_METRIC_CONFIG
    if not p.exists(): return None
    return validate_metric_config(json.loads(p.read_text(encoding="utf-8")))


def import_metric_config(source: str|Path,dest: str|Path|None=None)->dict[str,Any]:
    obj=validate_metric_config(json.loads(Path(source).read_text(encoding="utf-8")))
    dst=Path(dest) if dest else DEFAULT_METRIC_CONFIG
    dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    public=sum(1 for m in obj["metrics"] if not m.get("internal"))
    return {"ok":True,"path":str(dst.resolve()),"metrics":public,"rules":len(obj["rules"])}


def export_metric_config(dest: str|Path,source: str|Path|None=None)->dict[str,Any]:
    obj=load_metric_config(source) if source else load_metric_config()
    obj=obj or {"schema_version":1,"metrics":[],"rules":[],"activeRule":"","filters":[]}
    dst=Path(dest);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    public=sum(1 for m in obj["metrics"] if not m.get("internal"))
    return {"ok":True,"path":str(dst.resolve()),"metrics":public,"rules":len(obj["rules"])}
