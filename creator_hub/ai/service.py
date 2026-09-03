from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from ..config import load_query_packs
from ..db import connect, json_dump, json_load
from ..util import now_utc
from . import prompts
from .local_tools import FIELD_CATALOG, creator_context, execute_creator_plan, resolve_local_creator, weekly_context
from .provider import (AIUnavailable, AILocalBudgetExceeded, PROTOCOLS, GENERIC_KEY_ENV, clear_ai_api_key, make_provider, persist_ai_api_key, protocol_default_base_url, read_ai_api_key, resolved_ai_config)


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type":"object","properties":properties,"required":required or list(properties),"additionalProperties":False}


def _nullable(t: str) -> dict[str, Any]:
    return {"anyOf":[{"type":t},{"type":"null"}]}

CREATOR_BRIEF_SCHEMA=_obj({
    "summary":{"type":"string"},"priority":{"type":"string","enum":["high","medium","low","watch"]},"confidence":{"type":"number"},
    "positioning":{"type":"string"},"performance":{"type":"string"},"relationship":{"type":"string"},"opportunity":{"type":"string"},"risks":{"type":"array","items":{"type":"string"}},"next_step":{"type":"string"},
    "evidence_keys":{"type":"array","items":{"type":"string"}}
})
COMPARE_SCHEMA=_obj({"summary":{"type":"string"},"ranking":{"type":"array","items":_obj({"channel_id":{"type":"string"},"channel_title":{"type":"string"},"rank":{"type":"integer"},"reason":{"type":"string"},"risk":{"type":"string"}})},"recommendation":{"type":"string"}})
QUERY_PLAN_SCHEMA=_obj({
    "strategy":{"type":"string"},
    "queries":{"type":"array","items":{"type":"string"}},
    "fit_criteria":_obj({
        "subscriber_min":_nullable("integer"),
        "subscriber_max":_nullable("integer"),
        "search_concepts":{"type":"array","items":{"type":"string"}},
        "preferred_terms":{"type":"array","items":{"type":"string"}},
        "exclude_terms":{"type":"array","items":{"type":"string"}},
        "continuity_terms":{"type":"array","items":{"type":"string"}},
        "require_topic_match":{"type":"boolean"},
        "prefer_long_term":{"type":"boolean"}
    }),
    "notes":{"type":"array","items":{"type":"string"}}
})
ASK_PLAN_SCHEMA=_obj({
    "search":{"type":"string"},"region":{"type":"string"},"country":{"type":"string"},"subscriber_min":_nullable("integer"),"subscriber_max":_nullable("integer"),
    "partnered":_nullable("boolean"),"unpartnered":_nullable("boolean"),"competitor_brand":{"type":"string"},"monitoring":_nullable("boolean"),"priority":{"type":"string"},"workflow":{"type":"string"},"suspected_inactive":_nullable("boolean"),
    "sort":{"type":"string"},"direction":{"type":"string"},"result_limit":_nullable("integer"),"explanation":{"type":"string"}
})
WEEKLY_SCHEMA=_obj({"headline":{"type":"string"},"summary":{"type":"string"},"discoveries":{"type":"array","items":{"type":"string"}},"risks":{"type":"array","items":{"type":"string"}},"actions":{"type":"array","items":{"type":"string"}}})
CONNECTION_TEST_SCHEMA=_obj({"ok":{"type":"boolean"},"message":{"type":"string"}})


class AICopilot:
    def __init__(self, hub):
        self.hub=hub

    def config(self) -> dict[str, Any]:
        saved=self.hub.get_setting("ai_config",{}) or {}
        return resolved_ai_config(self.hub.settings,saved)

    def provider(self, api_key_override: str | None = None, config_override: dict[str, Any] | None = None):
        cfg=self.config() if config_override is None else resolved_ai_config(self.hub.settings,config_override)
        return make_provider(cfg, api_key_override=api_key_override)

    def status(self) -> dict[str, Any]:
        cfg=self.config(); p=self.provider(); env=str(cfg.get("api_key_env") or GENERIC_KEY_ENV)
        key,key_source=read_ai_api_key(cfg)
        today=datetime.now(timezone.utc).date().isoformat()
        with connect(self.hub.db_path) as conn:
            used=conn.execute("SELECT COUNT(*) FROM ai_runs WHERE substr(started_at,1,10)=? AND status='complete'",(today,)).fetchone()[0]
        protocol=str(cfg.get("protocol") or cfg.get("provider") or "openai_responses")
        return {
            "enabled":bool(cfg.get("enabled")),
            "available":bool(getattr(p,"available",False)),
            "provider":protocol,
            "protocol":protocol,
            "protocol_label":str((PROTOCOLS.get(protocol) or {}).get("label") or protocol),
            "model":str(cfg.get("model") or ""),
            "base_url":str(cfg.get("base_url") or ""),
            "api_key_env":env,
            "api_key_present":bool(key),
            "api_key_source":key_source,
            "daily_request_soft_limit":int(cfg.get("daily_request_soft_limit") or 100),
            "requests_today":int(used),
            "store_remote":bool(cfg.get("store_remote",False)),
            "send_contact_data":False,
            "reason":getattr(p,"reason","") if not getattr(p,"available",False) else "",
            "protocols":[{"id":k,**v} for k,v in PROTOCOLS.items() if k != "disabled"],
        }

    def configure(self, patch: dict[str, Any], *, api_key: str | None = None, clear_api_key: bool=False) -> dict[str, Any]:
        old=self.hub.get_setting("ai_config",{}) or {}
        allowed={"enabled","protocol","provider","model","base_url","api_key_env","daily_request_soft_limit","max_creators_per_task","store_remote","timeout_seconds"}
        incoming={k:v for k,v in dict(patch or {}).items() if k in allowed}
        if "provider" in incoming and "protocol" not in incoming:
            legacy=str(incoming.pop("provider") or "").lower()
            incoming["protocol"]={"openai":"openai_responses","mock":"mock","disabled":"disabled"}.get(legacy,legacy)
        cfg={**old,**incoming}
        protocol=str(cfg.get("protocol") or "openai_responses").lower()
        if protocol not in PROTOCOLS: raise ValueError("unsupported AI protocol")
        cfg["protocol"]=protocol; cfg["provider"]=protocol
        cfg["api_key_env"]=str(cfg.get("api_key_env") or GENERIC_KEY_ENV)
        if protocol != "mock":
            if not str(cfg.get("base_url") or "").strip(): cfg["base_url"]=protocol_default_base_url(protocol)
            if str(cfg.get("base_url") or "").strip() and not str(cfg.get("base_url")).lower().startswith(("http://","https://")):
                raise ValueError("API Base URL must start with http:// or https://")
        else:
            cfg["base_url"]=""
            if not str(cfg.get("model") or "").strip(): cfg["model"]="mock-v1"
        if "daily_request_soft_limit" in cfg: cfg["daily_request_soft_limit"]=max(1,min(100000,int(cfg["daily_request_soft_limit"])))
        if "max_creators_per_task" in cfg: cfg["max_creators_per_task"]=max(2,min(100,int(cfg["max_creators_per_task"])))
        if "timeout_seconds" in cfg: cfg["timeout_seconds"]=max(5,min(600,int(cfg["timeout_seconds"])))
        self.hub.set_setting("ai_config",cfg)
        if clear_api_key:
            clear_ai_api_key(cfg["api_key_env"])
        elif api_key is not None and str(api_key).strip():
            persist_ai_api_key(str(api_key),cfg["api_key_env"])
        return self.status()

    def available_models(self, patch: dict[str, Any] | None = None, api_key: str | None = None) -> dict[str, Any]:
        merged={**(self.hub.get_setting("ai_config",{}) or {}),**dict(patch or {})}
        cfg=resolved_ai_config(self.hub.settings,merged)
        # Model listing does not require the feature to be enabled.
        cfg["enabled"]=True
        if not str(cfg.get("base_url") or "").strip(): cfg["base_url"]=protocol_default_base_url(str(cfg.get("protocol") or ""))
        p=make_provider(cfg,api_key_override=api_key)
        if not getattr(p,"available",False) and str(cfg.get("protocol")) != "mock":
            # available also checks model, while model listing intentionally happens before model selection.
            key,_=read_ai_api_key(cfg,api_key)
            if not key: raise AIUnavailable("请先输入 API Key，再读取模型列表。")
        models=p.list_models()
        return {"protocol":cfg.get("protocol"),"base_url":cfg.get("base_url"),"models":models,"count":len(models)}

    def test_connection(self, *, force: bool=True) -> dict[str, Any]:
        return self._run("connection_test",prompt="Return JSON confirming that the API connection is working.",schema=CONNECTION_TEST_SCHEMA,source={"test":"connection","config":{k:v for k,v in self.config().items() if k not in {"api_key"}}},prompt_version="connection-test-v1",force=force)

    def _fingerprint(self, payload: Any) -> str:
        return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def _mock_result(self, task: str, source: Any) -> dict[str, Any]:
        if task=="creator_brief":
            return {"summary":"Mock Creator Brief（离线自检）","priority":"medium","confidence":0.8,"positioning":"基于本地视频事实的内容定位。","performance":"使用本地播放指标。","relationship":"使用当前 Workspace 的品牌 / 关系 / Taxonomy 事实。","opportunity":"用于验证AI增强层，不代表真实模型判断。","risks":["Mock provider仅用于测试"],"next_step":"保持人工复核","evidence_keys":["subscriber_count","stored_videos","ugphone_videos"]}
        if task=="creator_compare":
            ranking=[]
            for i,c in enumerate(source,1): ranking.append({"channel_id":c["channel_id"],"channel_title":c.get("channel_title") or c["channel_id"],"rank":i,"reason":"Mock ranking","risk":"Mock provider"})
            return {"summary":"Mock compare","ranking":ranking,"recommendation":"Mock provider仅用于测试。"}
        if task=="query_planner":
            return {"strategy":"Mock query plan","queries":[source.get("query",""),source.get("query","")+" guide"],"fit_criteria":{"subscriber_min":None,"subscriber_max":None,"search_concepts":["guide"],"preferred_terms":[],"exclude_terms":[],"continuity_terms":[],"require_topic_match":False,"prefer_long_term":False},"notes":["Mock provider"]}
        if task=="ask_hub": return {"search":"","region":"","country":"","subscriber_min":None,"subscriber_max":None,"partnered":None,"unpartnered":None,"competitor_brand":"","monitoring":None,"priority":"","workflow":"","suspected_inactive":None,"sort":"subscribers","direction":"desc","result_limit":None,"explanation":"Mock provider returns a broad local query."}
        if task=="weekly_brief": return {"headline":"Mock weekly brief","summary":"离线自检结果","discoveries":[],"risks":[],"actions":["Mock provider仅用于测试"]}
        if task=="connection_test": return {"ok":True,"message":"Mock provider connection is available."}
        return {}

    def _run(self, task: str, *, prompt: str, schema: dict[str,Any], source: Any, prompt_version: str, force: bool=False, progress=None) -> dict[str,Any]:
        cfg=self.config(); model=str(cfg.get("model") or "").strip();
        if not model: raise AIUnavailable("尚未配置模型 ID。请在 AI 状态与配置中输入或读取模型后选择。")
        provider=self.provider(); fp=self._fingerprint(source)
        cache_key=self._fingerprint({"task":task,"provider":str(cfg.get("protocol") or cfg.get("provider")),"model":model,"prompt_version":prompt_version,"source":fp})
        if not force:
            with connect(self.hub.db_path) as conn:
                row=conn.execute("SELECT result_json FROM ai_cache WHERE cache_key=?",(cache_key,)).fetchone()
            if row:
                cached_data=json_load(row["result_json"],{})
                at=now_utc()
                with connect(self.hub.db_path) as conn:
                    cur=conn.execute("INSERT INTO ai_runs(task,provider,model,prompt_version,source_fingerprint,started_at,finished_at,status,source_json,result_json,cache_hit) VALUES(?,?,?,?,?,?,?,?,?,?,1)",(task,str(cfg.get("protocol") or cfg.get("provider")),model,prompt_version,fp,at,at,"cached",json_dump(source),json_dump(cached_data)))
                    run_id=cur.lastrowid; conn.commit()
                return {"cached":True,"run_id":run_id,"result":cached_data,"provider":str(cfg.get("protocol") or cfg.get("provider")),"model":model,"prompt_version":prompt_version}
        st=self.status()
        if not st["enabled"]: raise AIUnavailable("AI功能未启用。核心数据中心不受影响。")
        if st["requests_today"]>=st["daily_request_soft_limit"]: raise AILocalBudgetExceeded("Reached local AI daily request soft limit")
        started=now_utc()
        with connect(self.hub.db_path) as conn:
            cur=conn.execute("INSERT INTO ai_runs(task,provider,model,prompt_version,source_fingerprint,started_at,status,source_json,result_json,cache_hit) VALUES(?,?,?,?,?,?,?,?,?,0)",(task,str(cfg.get("protocol") or cfg.get("provider")),model,prompt_version,fp,started,"running",json_dump(source),"{}")); run_id=cur.lastrowid; conn.commit()
        try:
            mock=self._mock_result(task,source) if str(cfg.get("protocol") or cfg.get("provider"))=="mock" else None
            attempts=3 if str(cfg.get("protocol") or cfg.get("provider"))!="mock" else 1
            resp=None
            for attempt in range(1,attempts+1):
                try:
                    resp=provider.generate_json(task=task,prompt=prompt,schema=schema,model=model,mock_data=mock)
                    break
                except AIUnavailable as exc:
                    msg=str(exc).casefold()
                    transient=any(x in msg for x in ("timed out","timeout","read operation timed out","temporarily unavailable","connection reset","connection aborted","http 429","http 500","http 502","http 503","http 504"))
                    if not transient or attempt>=attempts: raise
                    wait=(2,5)[min(attempt-1,1)]
                    if progress: progress(stage="AI 请求重试",message=f"AI 请求暂时失败，正在自动重试 {attempt}/{attempts-1}：{str(exc)[:180]}",percent=4+attempt*2)
                    time.sleep(wait)
            if resp is None: raise AIUnavailable("AI request failed after retries")
            finished=now_utc()
            with connect(self.hub.db_path) as conn:
                conn.execute("UPDATE ai_runs SET finished_at=?,status='complete',response_id=?,input_tokens=?,output_tokens=?,result_json=? WHERE id=?",(finished,resp.response_id,resp.input_tokens,resp.output_tokens,json_dump(resp.data),run_id))
                conn.execute("INSERT INTO ai_cache(cache_key,task,provider,model,prompt_version,source_fingerprint,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET result_json=excluded.result_json,updated_at=excluded.updated_at",(cache_key,task,str(cfg.get("protocol") or cfg.get("provider")),model,prompt_version,fp,json_dump(resp.data),finished,finished));conn.commit()
            return {"cached":False,"run_id":run_id,"result":resp.data,"provider":str(cfg.get("protocol") or cfg.get("provider")),"model":model,"prompt_version":prompt_version}
        except Exception as exc:
            with connect(self.hub.db_path) as conn:
                conn.execute("UPDATE ai_runs SET finished_at=?,status='failed',error_message=? WHERE id=?",(now_utc(),f"{type(exc).__name__}: {exc}"[:2000],run_id));conn.commit()
            raise

    @staticmethod
    def _normalize_result_item(row: dict[str, Any], item_type: str="creator") -> dict[str, Any]:
        x=dict(row or {})
        x["channel_id"]=str(x.get("channel_id") or "")
        x["channel_title"]=x.get("channel_title") or x.get("title") or x.get("channel_id") or ""
        x["country"]=x.get("country") or x.get("country_resolved") or x.get("country_api") or ""
        sub=x.get("subscribers") if x.get("subscribers") is not None else x.get("subscriber_count")
        x["subscribers"]=int(sub) if sub not in (None,"") else None
        for key in ("ugphone_videos","competitor_videos"):
            v=x.get(key)
            x[key]=int(v) if v not in (None,"") else None
        score=x.get("discovery_score",x.get("pre_score",x.get("best_discovery_score")))
        x["discovery_score"]=float(score) if score not in (None,"") else None
        fit=x.get("objective_fit_score")
        x["objective_fit_score"]=float(fit) if fit not in (None,"") else None
        for key in ("content_fit_score","continuity_fit_score","topic_affinity_score","use_case_continuity_score","brand_safety_score","audience_size_fit_score","query_coverage_score"):
            v=x.get(key); x[key]=float(v) if v not in (None,"") else None
        x["objective_fit_status"]=str(x.get("objective_fit_status") or "")
        x["brand_safety_status"]=str(x.get("brand_safety_status") or "")
        x["brand_safety_flags"]=list(x.get("brand_safety_flags") or [])
        x["candidate_pool"]=str(x.get("candidate_pool") or "推荐候选")
        x["creator_language"]=str(x.get("creator_language") or "")
        x["creator_language_status"]=str(x.get("creator_language_status") or "")
        lr=x.get("creator_language_ratio"); x["creator_language_ratio"]=float(lr) if lr not in (None,"") else None
        x["representative_fit_video_title"]=str(x.get("representative_fit_video_title") or "")
        x["representative_fit_video_id"]=str(x.get("representative_fit_video_id") or "")
        x["representative_fit_video_published_at"]=str(x.get("representative_fit_video_published_at") or "")
        x["representative_topic_video_title"]=str(x.get("representative_topic_video_title") or "")
        x["representative_topic_video_id"]=str(x.get("representative_topic_video_id") or "")
        x["representative_use_case_video_title"]=str(x.get("representative_use_case_video_title") or x.get("representative_fit_video_title") or "")
        x["representative_use_case_video_id"]=str(x.get("representative_use_case_video_id") or x.get("representative_fit_video_id") or "")
        x["profile_verification_status"]=str(x.get("profile_verification_status") or "")
        x["continuity_gate_passed"]=bool(x.get("continuity_gate_passed")) if x.get("continuity_gate_passed") is not None else None
        x["objective_fit_reason"]=str(x.get("objective_fit_reason") or "")
        x["objective_terms_matched"]=list(x.get("objective_terms_matched") or [])
        for key in ("sampled_recent_videos","objective_recent_videos","objective_active_months","topic_recent_videos","topic_active_months"):
            v=x.get(key); x[key]=int(v) if v not in (None,"") else None
        ratio=x.get("objective_recent_ratio")
        x["objective_recent_ratio"]=float(ratio) if ratio not in (None,"") else None
        x["workflow_status"]=x.get("workflow_status") or x.get("workflow") or "unreviewed"
        mon=x.get("monitoring_enabled")
        x["monitoring_enabled"]=bool(mon) if mon is not None else None
        x["priority"]=x.get("priority") or ""
        x["local_data_status"]=x.get("local_data_status") or ("已采集" if x.get("ugphone_videos") is not None else "未采集")
        x["best_video_title"]=x.get("best_video_title") or x.get("title") or ""
        x["best_video_id"]=str(x.get("best_video_id") or x.get("video_id") or "")
        views=x.get("best_video_views") if x.get("best_video_views") is not None else x.get("views")
        x["best_video_views"]=int(views) if views not in (None,"") else None
        x["query_coverage"]=int(x.get("query_coverage") or 0)
        x["matched_queries"]=list(x.get("matched_queries") or [])
        return x

    @staticmethod
    def _text(value: Any) -> str:
        return " ".join(str(value or "").casefold().split())

    @staticmethod
    def _language_code(value: str) -> str:
        v=str(value or "").strip().casefold()
        return {"zh-tw":"zh","zh-cn":"zh","es-419":"es","pt-br":"pt","en":"en","th":"th","vi":"vi","id":"id","ko":"ko","ja":"ja"}.get(v,v.split("-")[0])

    @classmethod
    def _detect_title_language(cls, value: str) -> str:
        text=str(value or "").strip().casefold()
        if not text: return "unknown"
        if re.search(r"[\u0e00-\u0e7f]",text): return "th"
        if re.search(r"[\uac00-\ud7af]",text): return "ko"
        if re.search(r"[\u3040-\u30ff]",text): return "ja"
        if re.search(r"[\u4e00-\u9fff]",text): return "zh"
        if re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",text): return "vi"
        toks=set(re.findall(r"[a-zà-ÿ]+",text))
        if not toks: return "unknown"
        lex={
          "es":{"el","la","los","las","una","uno","como","para","con","mejor","nuevo","guia","guía","actualizacion","actualización","que"},
          "pt":{"uma","como","para","com","melhor","novo","guia","atualizacao","atualização","voce","você","nao","não","jogo"},
          "id":{"cara","untuk","dengan","terbaik","baru","akun","panduan","game","main"},
          "en":{"the","how","best","guide","new","update","with","for","and","you","this","get","way","why","when","all","farm","farming","account","accounts"},
        }
        scores={k:len(toks&v) for k,v in lex.items()}
        best=max(scores,key=scores.get)
        return best if scores[best]>=2 else "unknown"

    @classmethod
    def _language_profile(cls, titles: list[str], desired: str) -> dict[str,Any]:
        target=cls._language_code(desired); counts={}
        for title in titles:
            code=cls._detect_title_language(title)
            if code=="unknown": continue
            counts[code]=counts.get(code,0)+1
        detected=sum(counts.values()); target_hits=counts.get(target,0)
        ratio=(target_hits/detected) if detected else None
        dominant=max(counts,key=counts.get) if counts else ""
        return {"target":target,"counts":counts,"detected":detected,"target_hits":target_hits,"ratio":ratio,"dominant":dominant}

    @staticmethod
    def _fit_strategy(fc: dict[str,Any]) -> str:
        parts=[]
        lo,hi=fc.get("subscriber_min"),fc.get("subscriber_max")
        if lo is not None or hi is not None:
            parts.append("订阅硬约束 "+("" if lo is None else f">={int(lo):,}")+("" if hi is None else f" <= {int(hi):,}"))
        if fc.get("creator_language"):
            parts.append(f"Creator主要内容语言={fc.get('creator_language')}（有效样本占比>={float(fc.get('creator_language_min_ratio') or 0.6):.0%}）")
        if fc.get("require_topic_match",True): parts.append("必须匹配基础主题")
        if fc.get("prefer_long_term"):
            parts.append(f"长期硬门槛>={int(fc.get('long_term_min_videos') or 5)}条且>={int(fc.get('long_term_min_months') or 3)}个月")
        if fc.get("exclude_official_channels",True): parts.append("排除官方 / 产品账号")
        if fc.get("exclude_script_cheat_channels",True): parts.append("排除主要脚本/外挂频道")
        return "；".join(parts) or "高召回搜索后按结构化 Fit Criteria 排序。"

    @staticmethod
    def _topic_tokens(query: str) -> list[str]:
        return [x for x in re.findall(r"[\w\-]+", str(query or "").casefold(), flags=re.UNICODE) if len(x)>=2]

    def _objective_heuristics(self, objective: str, plan: dict[str,Any]) -> dict[str,Any]:
        """Turn natural-language sourcing requirements into visible deterministic gates."""
        out=dict(plan or {}); fc=dict(out.get("fit_criteria") or {})
        for k in ("search_concepts","preferred_terms","exclude_terms","continuity_terms"):
            vals=[]; seen=set()
            for x in list(fc.get(k) or []):
                v=" ".join(str(x or "").split()).strip()[:80]; key=self._text(v)
                if v and key not in seen: vals.append(v);seen.add(key)
            fc[k]=vals
        text=self._text(objective)
        notes=list(out.get("notes") or [])
        if fc.get("subscriber_max") is None and any(x in text for x in ("中小体量","中小型","中小博主","small-to-medium","small to medium","small/medium")):
            fc["subscriber_max"]=100000
            notes.append("“中小体量”未给出数值时，当前默认按 ≤100,000 订阅作为硬约束；可在搜索要求中写明其他范围。")
        mapped=[]
        mapping=[
            ("afk",["AFK"]),
            ("挂机",["AFK","overnight","farm while sleeping","idle farming"]),
            ("auto farm",["auto farm"]),("自动刷",["auto farm","auto grind"]),("24/7",["24/7"]),("过夜",["overnight","farm while sleeping"]),
            ("多开",["multi-instance","multi account","multiple accounts","alt account","alts","multiple alts","multi client","multiple clients","run two accounts","farm with alts","alt farming"]),
            ("多账号",["multi account","multiple accounts","alt account","alts","multiple alts","farm with alts","alt farming"]),
            ("multi-instance",["multi-instance","multi client","multiple clients"]),("multi account",["multi account","multiple accounts","alt account","alts"]),
        ]
        for needle,vals in mapping:
            if needle in text: mapped.extend(vals)
        if mapped:
            for field in ("search_concepts","preferred_terms"):
                existing={self._text(x) for x in fc[field]}
                for x in mapped:
                    if self._text(x) not in existing: fc[field].append(x);existing.add(self._text(x))
        wants_long=bool(fc.get("prefer_long_term")) or any(x in text for x in ("长期","持续","经常","反复","long-term","long term","ongoing","repeated"))
        fc["prefer_long_term"]=wants_long
        if wants_long:
            fc["continuity_terms"]=list(dict.fromkeys(fc["continuity_terms"]+(mapped or fc["preferred_terms"])))
            fc["long_term_min_videos"]=max(1,int(fc.get("long_term_min_videos") or 5))
            fc["long_term_min_months"]=max(1,int(fc.get("long_term_min_months") or 3))
            notes.append(f"长期制作按硬约束执行：最近最多50条上传中，相关视频至少 {fc['long_term_min_videos']} 条且覆盖至少 {fc['long_term_min_months']} 个月；未完成 Profile 的候选不会进入正式 Result Set。")
        else:
            fc["long_term_min_videos"]=None;fc["long_term_min_months"]=None
        include_official=any(x in text for x in ("包含官方","包括官方","include official","official accounts are allowed"))
        include_unsafe=any(x in text for x in ("包含脚本","包括脚本","包含外挂","包括外挂","include scripts","include cheats","include exploits"))
        fc["exclude_official_channels"]=not include_official
        fc["exclude_script_cheat_channels"]=not include_unsafe
        fc.setdefault("subscriber_min",None);fc.setdefault("subscriber_max",None)
        fc.setdefault("require_topic_match",True)
        out["notes"]=notes;out["fit_criteria"]=fc
        out["ai_strategy_raw"]=str(out.get("strategy") or "")
        out["strategy"]=self._fit_strategy(fc)
        return out

    @staticmethod
    def _canonical_query(base: str, value: str) -> str:
        base=" ".join(str(base or "").split()).strip(); v=" ".join(str(value or "").split()).strip()
        if not v: return ""
        # Repair only textual duplication; do not invent a second expansion layer.
        bf=base.casefold();vf=v.casefold()
        if bf and vf.startswith(bf+" "+bf):
            v=base+v[len(base)*2+1:]
            v=" ".join(v.split())
        return v[:200]

    def _official_cloud_brand_channel(self, channel_title: str) -> tuple[bool,str]:
        title=self._text(channel_title)
        if not title: return False,""
        cfg=self.hub.brand_cfg or {}; exact=set()
        for b in cfg.get("brands") or []:
            names=[b.get("display_name")]+list(b.get("aliases") or [])
            for raw in names:
                n=self._text(raw)
                if not n: continue
                exact.update({n,n+" official",n+" cloud phone",n+" cloudphone",n+" official channel",n+" product"})
        if title in exact: return True,"品牌官方 / 产品频道"
        return False,""

    def _official_game_channel(self, base_query: str, channel_title: str, description: str="") -> tuple[bool,str]:
        q=self._text(base_query); title=self._text(channel_title); desc=self._text(description)
        if not q or not title: return False,""
        if title==q or title in {q+" official",q+" game",q+" developers",q+" developer",q+" studio"}:
            return True,"游戏官方/开发者频道"
        if all(tok in title for tok in self._topic_tokens(base_query)) and any(x in title for x in ("official","developer","developers","studio","dev team","game team")):
            return True,"游戏官方/开发者频道"
        if q in desc and any(x in desc for x in ("official channel","official youtube channel","developer of","developers of")):
            return True,"游戏官方/开发者频道"
        return False,""

    def _script_cheat_profile(self, channel_title: str, titles: list[str]) -> tuple[bool,float,list[str]]:
        terms=("script","scripts","hack","hacks","cheat","cheats","exploit","exploits","executor","executors","keyless","dupe","duplication","rollback","injector","aimbot","esp","silent aim")
        ct=self._text(channel_title); normalized=[self._text(x) for x in titles if str(x or "").strip()]
        flags=sorted({t for t in terms if t in ct or any(t in x for x in normalized)})
        hits=sum(1 for x in normalized if any(t in x for t in terms)); ratio=(hits/len(normalized)) if normalized else 0.0
        title_flag=any(t in ct for t in terms)
        primary=title_flag or hits>=8 or (hits>=3 and ratio>=0.25)
        return primary,ratio,flags

    def _enrich_local_facts(self, rows: list[dict[str,Any]]) -> None:
        ids=[str(r.get("channel_id") or "") for r in rows if r.get("channel_id")]
        if not ids: return
        with connect(self.hub.db_path) as conn:
            for batch in [ids[i:i+400] for i in range(0,len(ids),400)]:
                qs=','.join('?' for _ in batch)
                local={r['channel_id']:dict(r) for r in conn.execute(f"SELECT channel_id,handle,monitoring_enabled,priority FROM creators WHERE channel_id IN ({qs})",tuple(batch)).fetchall()}
                agg={r['channel_id']:dict(r) for r in conn.execute(f"""SELECT v.channel_id,
                    SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='ugphone' THEN 1 ELSE 0 END) ugphone_videos,
                    SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='competitor' THEN 1 ELSE 0 END) competitor_videos
                    FROM videos v LEFT JOIN video_labels l ON l.video_id=v.video_id LEFT JOIN label_suggestions s ON s.video_id=v.video_id
                    WHERE v.channel_id IN ({qs}) GROUP BY v.channel_id""",tuple(batch)).fetchall()}
                for r in rows:
                    cid=str(r.get('channel_id') or '')
                    if cid not in batch: continue
                    cr=local.get(cid)
                    if not cr:
                        r['local_data_status']='未采集';r['ugphone_videos']=None;r['competitor_videos']=None;r['monitoring_enabled']=None;r['priority']=''
                        continue
                    a=agg.get(cid) or {}
                    r['local_data_status']='已采集';r['handle']=r.get('handle') or cr.get('handle') or ''
                    r['ugphone_videos']=int(a.get('ugphone_videos') or 0);r['competitor_videos']=int(a.get('competitor_videos') or 0)
                    r['monitoring_enabled']=bool(cr.get('monitoring_enabled'));r['priority']=cr.get('priority') or ''

    def _recent_upload_profiles(self, rows: list[dict[str,Any]], limit: int=100, progress=None) -> tuple[dict[str,list[dict[str,Any]]],dict[str,Any]]:
        """Lightweight recent-upload sampling without writing candidate videos into the local library."""
        ids=[str(r.get('channel_id') or '') for r in rows if r.get('channel_id')][:max(0,int(limit))]
        profiles={cid:[] for cid in ids}; meta={"profiled_creators":0,"profile_api_calls":0,"profile_errors":[],"profile_status":{},"channel_details":{}}
        if not ids: return profiles,meta
        try:
            playlist={}
            for i in range(0,len(ids),50):
                data=self.hub.api.call('channels',part='snippet,contentDetails',id=','.join(ids[i:i+50]),maxResults=50);meta['profile_api_calls']+=1
                for item in data.get('items') or []:
                    cid=str(item.get('id') or '');sn=item.get('snippet') or {};upl=(((item.get('contentDetails') or {}).get('relatedPlaylists') or {}).get('uploads') or '')
                    if cid:
                        meta['channel_details'][cid]={"title":str(sn.get('title') or ''),"description":str(sn.get('description') or ''),"custom_url":str(sn.get('customUrl') or '')}
                    if cid and upl: playlist[cid]=upl
            for idx,cid in enumerate(ids,1):
                upl=playlist.get(cid)
                if not upl:
                    meta['profile_status'][cid]='channel_or_uploads_unavailable'
                    if progress: progress(stage='候选博主抽样', message=f'最近上传不可用：{idx}/{len(ids)}', current=idx, total=len(ids))
                    continue
                try:
                    data=self.hub.api.call('playlistItems',part='snippet,contentDetails',playlistId=upl,maxResults=50);meta['profile_api_calls']+=1
                    vals=[]
                    for item in data.get('items') or []:
                        sn=item.get('snippet') or {}; vals.append({"title":str(sn.get('title') or ''),"published_at":str(sn.get('publishedAt') or ''),"video_id":str(((item.get('contentDetails') or {}).get('videoId') or ''))})
                    profiles[cid]=vals;meta['profiled_creators']+=1;meta['profile_status'][cid]='profiled'
                except Exception as exc:
                    meta['profile_status'][cid]='profile_error';meta['profile_errors'].append({"channel_id":cid,"error":f"{type(exc).__name__}: {exc}"[:300]})
                if progress:
                    progress(stage='候选博主抽样', message=f'正在读取候选 Creator 最近上传：{idx}/{len(ids)}', current=idx, total=len(ids))
        except Exception as exc:
            meta['profile_errors'].append({"error":f"{type(exc).__name__}: {exc}"[:500]})
            for cid in ids:
                meta['profile_status'].setdefault(cid,'profile_error')
        return profiles,meta

    def _cheap_agent_prefilter(self, query: str, fc: dict[str,Any], raw: list[dict[str,Any]]) -> tuple[list[dict[str,Any]],list[dict[str,Any]],dict[str,int]]:
        """Apply low-cost deterministic gates before recent-upload profiling.

        This stage uses only Discovery facts already in memory. It removes obvious audience,
        official-channel, user-exclusion and script-channel misses so the profile budget is
        spent on plausible Creator candidates instead of arbitrary result order.
        """
        topic_tokens=self._topic_tokens(query); excluded=[self._text(x) for x in fc.get('exclude_terms') or [] if self._text(x)]
        sub_min=fc.get('subscriber_min');sub_max=fc.get('subscriber_max');kept=[];filtered=[];counts={}
        for r in raw:
            title=str(r.get('channel_title') or r.get('title') or '');best=self._text(r.get('best_video_title') or r.get('title') or '')
            blob=self._text(title+' '+best); sub=r.get('subscribers'); reasons=[];cats=[]
            if (sub_min is not None or sub_max is not None) and sub is None:
                reasons.append('订阅数未知，无法验证体量硬约束');cats.append('audience_unverified')
            if sub_min is not None and sub is not None and int(sub)<int(sub_min): reasons.append(f'订阅数低于 {int(sub_min):,}');cats.append('audience_size')
            if sub_max is not None and sub is not None and int(sub)>int(sub_max): reasons.append(f'订阅数高于 {int(sub_max):,}');cats.append('audience_size')
            if excluded and any(term in blob for term in excluded): reasons.append('命中用户排除词');cats.append('user_exclusion')
            cloud_official,cloud_reason=self._official_cloud_brand_channel(title)
            game_official,game_reason=self._official_game_channel(query,title,'')
            script_primary,_,script_flags=self._script_cheat_profile(title,[best])
            if fc.get('exclude_official_channels',True) and cloud_official: reasons.append(cloud_reason);cats.append('official_cloud_phone')
            if fc.get('exclude_official_channels',True) and game_official: reasons.append(game_reason);cats.append('official_game')
            if fc.get('exclude_script_cheat_channels',True) and script_primary: reasons.append('频道名称显示其以脚本/外挂/漏洞内容为主');cats.append('script_cheat')
            # Only discard a topic miss cheaply when not even one base-topic token occurs.
            # Full topic validation happens after channel/recent-upload profiling.
            if fc.get('require_topic_match',True) and topic_tokens and not any(tok in blob for tok in topic_tokens):
                reasons.append('Discovery 标题/频道名缺少基础主题线索');cats.append('cheap_topic_mismatch')
            if reasons:
                for c in set(cats): counts[c]=counts.get(c,0)+1
                filtered.append({'channel_id':str(r.get('channel_id') or ''),'channel_title':title,'reasons':reasons,'categories':sorted(set(cats)),'brand_safety_flags':(['script_cheat_terms:'+','.join(script_flags[:8])] if script_flags else [])})
            else: kept.append(r)
        return kept,filtered,counts

    def _agent_fit(self, query: str, objective: str, plan: dict[str,Any], discovery: dict[str,Any], progress=None) -> tuple[list[dict[str,Any]],dict[str,Any]]:
        fc=dict(plan.get('fit_criteria') or {}); raw=[dict(r) for r in list(discovery.get('results') or [])]
        topic_tokens=self._topic_tokens(query); preferred=[self._text(x) for x in fc.get('preferred_terms') or [] if self._text(x)]
        continuity=[self._text(x) for x in fc.get('continuity_terms') or [] if self._text(x)]
        excluded=[self._text(x) for x in fc.get('exclude_terms') or [] if self._text(x)]
        sub_min=fc.get('subscriber_min');sub_max=fc.get('subscriber_max')
        wants_long=bool(fc.get('prefer_long_term'));min_long_videos=int(fc.get('long_term_min_videos') or 5);min_long_months=int(fc.get('long_term_min_months') or 3)
        if progress: progress(stage='候选预过滤',message=f'正在对 {len(raw)} 个去重候选执行低成本硬约束过滤',current=0,total=max(1,len(raw)))
        candidates,cheap_filtered,category_counts=self._cheap_agent_prefilter(query,fc,raw)
        # A long-term request needs verified recent-upload evidence. After cheap filtering we
        # profile every plausible candidate up to a generous low-cost cap instead of profiling
        # an arbitrary first 100 and treating the remainder as failed.
        profile_limit=min(len(candidates),250 if wants_long else 120)
        profiles,pmeta=self._recent_upload_profiles(candidates,limit=profile_limit,progress=progress)
        profile_status=dict(pmeta.get('profile_status') or {}); channel_details=dict(pmeta.get('channel_details') or {})
        retained=[];filtered=list(cheap_filtered);pending=[]
        for r in candidates:
            cid=str(r.get('channel_id') or ''); recent=profiles.get(cid) or []; verified=profile_status.get(cid)=='profiled'
            details=channel_details.get(cid) or {}; channel_title=str(details.get('title') or r.get('channel_title') or '')
            best=self._text(r.get('title') or r.get('best_video_title') or '')
            recent_text=[self._text(x.get('title')) for x in recent];texts=[best]+recent_text
            channel_blob=self._text(channel_title+' '+str(details.get('description') or ''))
            def topic_ok(t): return bool(topic_tokens) and all(tok in t for tok in topic_tokens)
            topic_hits=[t for t in texts if topic_ok(t)]
            channel_topic_context=(not topic_tokens) or bool(topic_hits) or (bool(channel_blob) and all(tok in channel_blob for tok in topic_tokens))
            topic_recent=[x for x,tx in zip(recent,recent_text) if topic_ok(tx)] if topic_tokens else list(recent)
            topic_months=sorted({str(x.get('published_at') or '')[:7] for x in topic_recent if str(x.get('published_at') or '')[:7]})
            topic_representative=max(topic_recent,key=lambda x:str(x.get('published_at') or '')) if topic_recent else None
            if not topic_representative and topic_ok(best) and r.get('best_video_id'):
                topic_representative={'title':r.get('best_video_title') or r.get('title') or '', 'video_id':r.get('best_video_id') or r.get('video_id') or '', 'published_at':''}
            evidence_terms=preferred or continuity; continuity_terms=continuity or preferred
            matched=sorted({term for term in evidence_terms if any(term in t for t in texts)})
            # Once the Creator has channel-level topic context, continuity terms do not need
            # to repeat the full game name in every upload title. This is the key v3.8 fix.
            objective_recent=[]
            if channel_topic_context:
                for x,tx in zip(recent,recent_text):
                    if continuity_terms and any(term in tx for term in continuity_terms): objective_recent.append(x)
            months=sorted({str(x.get('published_at') or '')[:7] for x in objective_recent if str(x.get('published_at') or '')[:7]})
            ratio=(len(objective_recent)/len(recent)) if recent else 0.0
            desired_lang=str(fc.get('creator_language') or '')
            lang_profile=self._language_profile([x.get('title') or '' for x in recent],desired_lang) if desired_lang and verified else {"target":desired_lang,"counts":{},"detected":0,"target_hits":0,"ratio":None,"dominant":""}
            representative=None
            if objective_recent:
                def rep_key(x):
                    tx=self._text(x.get('title') or '')
                    return (sum(1 for term in continuity_terms if term in tx),str(x.get('published_at') or ''))
                representative=max(objective_recent,key=rep_key)
            sub=r.get('subscribers'); reasons=[];hard=[];hard_categories=[];safety_flags=[]
            if (sub_min is not None or sub_max is not None) and sub is None: hard.append('订阅数未知，无法验证体量硬约束');hard_categories.append('audience_unverified')
            if sub_min is not None and sub is not None and int(sub)<int(sub_min): hard.append(f'订阅数低于 {int(sub_min):,}');hard_categories.append('audience_size')
            if sub_max is not None and sub is not None and int(sub)>int(sub_max): hard.append(f'订阅数高于 {int(sub_max):,}');hard_categories.append('audience_size')
            all_blob=self._text(channel_title+' '+str(details.get('description') or '')+' '+' '.join(texts))
            if excluded and any(term in all_blob for term in excluded): hard.append('命中用户排除词');hard_categories.append('user_exclusion')
            if fc.get('require_topic_match',True) and topic_tokens and not channel_topic_context: hard.append('频道/最近样本缺少基础主题上下文');hard_categories.append('topic_mismatch')
            if preferred and not matched: hard.append('未发现搜索要求中的场景/内容证据');hard_categories.append('objective_evidence')
            if desired_lang and verified and int(lang_profile.get('detected') or 0)>=3 and float(lang_profile.get('ratio') or 0)<float(fc.get('creator_language_min_ratio') or 0.60):
                hard.append(f"Creator主要内容语言不匹配：{lang_profile.get('dominant') or 'unknown'}，目标 {lang_profile.get('target')} 占比 {float(lang_profile.get('ratio') or 0):.0%}");hard_categories.append('creator_language')
            cloud_official,cloud_reason=self._official_cloud_brand_channel(channel_title)
            game_official,game_reason=self._official_game_channel(query,channel_title,str(details.get('description') or ''))
            desc_text=self._text(details.get('description') or '')
            official_game_video=bool(topic_ok(best) and any(x in best for x in ('official trailer','official teaser','official launch','official reveal','official gameplay trailer')) and ('official' in self._text(channel_title) or 'official channel' in desc_text or 'official youtube channel' in desc_text))
            script_primary,script_ratio,script_flags=self._script_cheat_profile(channel_title,[x.get('title') or '' for x in recent]+[r.get('best_video_title') or r.get('title') or ''])
            if cloud_official: safety_flags.append('official_cloud_phone')
            if game_official: safety_flags.append('official_game')
            if official_game_video: safety_flags.append('official_game_video')
            if script_flags: safety_flags.append('script_cheat_terms:'+','.join(script_flags[:8]))
            if fc.get('exclude_official_channels',True) and cloud_official: hard.append(cloud_reason);hard_categories.append('official_cloud_phone')
            if fc.get('exclude_official_channels',True) and game_official: hard.append(game_reason);hard_categories.append('official_game')
            if fc.get('exclude_official_channels',True) and official_game_video: hard.append('命中游戏官方视频/官方预告片');hard_categories.append('official_game_video')
            if fc.get('exclude_script_cheat_channels',True) and script_primary: hard.append(f'频道以脚本/外挂/漏洞内容为主（样本命中率 {script_ratio:.0%}）');hard_categories.append('script_cheat')
            continuity_pass=None
            if wants_long and not verified:
                pending.append({'channel_id':cid,'channel_title':channel_title,'reason':profile_status.get(cid) or ('profile_budget_pending' if cid not in profile_status else 'not_profiled')})
                # Pending verification is not counted as a failed hard filter and cannot enter
                # the formal Result Set until continuity evidence is available.
                continue
            if wants_long:
                continuity_pass=len(objective_recent)>=min_long_videos and len(months)>=min_long_months
                if len(objective_recent)<min_long_videos: hard.append(f'长期制作不足：最近样本相关视频 {len(objective_recent)} < {min_long_videos}');hard_categories.append('continuity')
                if len(months)<min_long_months: hard.append(f'长期制作不足：相关内容覆盖 {len(months)} 个月 < {min_long_months}');hard_categories.append('continuity')
            topic_ratio=(len(topic_recent)/len(recent)) if recent else 0.0
            topic_score=round(max(0,min(100,(45.0 if channel_topic_context else 0.0)+(35.0*min(1.0,topic_ratio/0.30) if verified else 0.0)+(20.0*min(1.0,len(topic_months)/4.0) if verified else 0.0))),1)
            term_component=25.0 if not preferred else 25.0*min(1.0,len(matched)/max(1,len(preferred)))
            use_case_score=round(max(0,min(100,(45.0*min(1.0,len(objective_recent)/10.0)+30.0*min(1.0,len(months)/6.0)+term_component) if verified else term_component)),1)
            content_score=topic_score
            continuity_score=use_case_score
            brand_safety=100.0
            if cloud_official or game_official or official_game_video or script_primary: brand_safety=0.0
            elif script_flags: brand_safety=max(35.0,80.0-200.0*script_ratio)
            if sub_min is None and sub_max is None: audience_score=80.0
            elif sub is None: audience_score=0.0
            else: audience_score=100.0 if not any(c=='audience_size' for c in hard_categories) else 0.0
            expected_cov=max(1,min(5,len(fc.get('search_concepts') or []) or 1));coverage_score=round(min(100.0,100.0*int(r.get('query_coverage') or 0)/expected_cov),1)
            total_score=round(max(0,min(100,0.30*topic_score+0.30*use_case_score+0.20*brand_safety+0.10*audience_score+0.10*coverage_score)),1)
            if not verified and not wants_long: status='待验证'
            elif total_score>=85: status='A · 强匹配'
            elif total_score>=75: status='B · 较强'
            elif total_score>=65: status='C · 候选'
            else: status='D · 弱匹配'
            safety_status='排除' if brand_safety<=0 else ('需关注' if brand_safety<80 else '正常')
            candidate_pool=('风险候选 · 需人工复核' if safety_status=='需关注' else ('推荐候选' if status.startswith(('A','B')) else ('候补候选' if status.startswith('C') else '弱候选'))) 
            language_status=('未验证' if not verified or int(lang_profile.get('detected') or 0)<3 else ('匹配' if float(lang_profile.get('ratio') or 0)>=float(fc.get('creator_language_min_ratio') or 0.60) else '不匹配')) if desired_lang else '未要求'
            reasons.extend([f'主题适配 {topic_score:.0f}',f'场景连续性 {use_case_score:.0f}',f'品牌安全 {brand_safety:.0f}',f'体量 {audience_score:.0f}',f'Query覆盖 {coverage_score:.0f}',f'主题视频 {len(topic_recent)} / {len(recent)} · {len(topic_months)}个月',f'场景视频 {len(objective_recent)} / {len(recent)} · {len(months)}个月'])
            if desired_lang: reasons.append(f"内容语言 {lang_profile.get('target')} {language_status}{(' '+format(float(lang_profile.get('ratio') or 0),'.0%')) if lang_profile.get('ratio') is not None else ''}")
            r.update({'objective_fit_score':total_score,'objective_fit_status':status,'objective_fit_reason':'；'.join(reasons),'objective_terms_matched':matched,'content_fit_score':content_score,'continuity_fit_score':continuity_score,'topic_affinity_score':topic_score,'use_case_continuity_score':use_case_score,'brand_safety_score':round(brand_safety,1),'audience_size_fit_score':round(audience_score,1),'query_coverage_score':coverage_score,'brand_safety_status':safety_status,'brand_safety_flags':safety_flags,'candidate_pool':candidate_pool,'creator_language':str(lang_profile.get('dominant') or ''),'creator_language_target':str(lang_profile.get('target') or ''),'creator_language_ratio':lang_profile.get('ratio'),'creator_language_status':language_status,'profile_verification_status':('已验证' if verified else '待验证'),'continuity_gate_passed':continuity_pass,'channel_topic_context_verified':bool(channel_topic_context),'sampled_recent_videos':len(recent) if verified else None,'objective_recent_videos':len(objective_recent) if verified else None,'objective_recent_ratio':ratio if verified else None,'objective_active_months':len(months) if verified else None,'topic_recent_videos':len(topic_recent) if verified else None,'topic_active_months':len(topic_months) if verified else None,'representative_topic_video_title':(str(topic_representative.get('title') or '') if topic_representative else ''),'representative_topic_video_id':(str(topic_representative.get('video_id') or '') if topic_representative else ''),'representative_use_case_video_title':(str(representative.get('title') or '') if representative else ''),'representative_use_case_video_id':(str(representative.get('video_id') or '') if representative else ''),'objective_first_match':(min((x.get('published_at') or '') for x in objective_recent) if objective_recent else ''),'objective_last_match':(max((x.get('published_at') or '') for x in objective_recent) if objective_recent else ''),'representative_fit_video_title':(str(representative.get('title') or '') if representative else ''),'representative_fit_video_id':(str(representative.get('video_id') or '') if representative else ''),'representative_fit_video_published_at':(str(representative.get('published_at') or '') if representative else ''),'objective_filter_reasons':hard})
            if hard:
                for cat in set(hard_categories): category_counts[cat]=category_counts.get(cat,0)+1
                filtered.append({'channel_id':cid,'channel_title':channel_title,'reasons':hard,'categories':sorted(set(hard_categories)),'brand_safety_flags':safety_flags})
            else: retained.append(r)
        retained.sort(key=lambda r:(1 if str(r.get('candidate_pool') or '').startswith('推荐') else 0,float(r.get('objective_fit_score') or 0),float(r.get('continuity_fit_score') or 0),float(r.get('pre_score') or r.get('discovery_score') or 0)),reverse=True)
        self._enrich_local_facts(retained)
        public_meta={k:v for k,v in pmeta.items() if k not in {'channel_details','profile_status'}}
        return retained,{**public_meta,'raw_unique_creators':len(raw),'pre_filter_candidates':len(candidates),'profile_budget':profile_limit,'retained_creators':len(retained),'recommended_candidates':sum(1 for r in retained if str(r.get('candidate_pool') or '').startswith('推荐')),'backup_candidates':sum(1 for r in retained if str(r.get('candidate_pool') or '').startswith('候补')),'weak_candidates':sum(1 for r in retained if str(r.get('candidate_pool') or '').startswith('弱')),'risk_candidates':sum(1 for r in retained if str(r.get('candidate_pool') or '').startswith('风险')),'filtered_out':len(filtered),'filtered_categories':category_counts,'filtered_examples':filtered[:40],'pending_verification':len(pending),'pending_verification_examples':pending[:30],'unverified_candidates':len(pending),'unverified_examples':pending[:20],'fit_criteria':fc}

    def _save_result_set(self, *, result_type: str, input_text: str, rows: list[dict[str,Any]], ai_run_id: int | None=None, discovery_run_id: str | None=None, request: dict[str,Any] | None=None, plan: dict[str,Any] | None=None, metadata: dict[str,Any] | None=None, title: str="") -> int:
        at=now_utc(); norm=[self._normalize_result_item(r) for r in rows]
        with connect(self.hub.db_path) as conn:
            cur=conn.execute("INSERT INTO ai_result_sets(ai_run_id,result_type,title,input_text,source_type,request_json,plan_json,metadata_json,discovery_run_id,total_items,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(ai_run_id,result_type,title or input_text[:120],input_text,"youtube_discovery" if discovery_run_id else "local_db",json_dump(request or {}),json_dump(plan or {}),json_dump(metadata or {}),discovery_run_id,len(norm),at))
            rsid=cur.lastrowid
            payload=[(rsid,i,"creator",r.get("channel_id") or str(i),r.get("channel_id") or None,json_dump(r),at) for i,r in enumerate(norm,1)]
            if payload: conn.executemany("INSERT INTO ai_result_items(result_set_id,item_index,item_type,item_key,channel_id,snapshot_json,created_at) VALUES(?,?,?,?,?,?,?)",payload)
            conn.commit()
        return int(rsid)

    @staticmethod
    def _result_condition(row: dict[str,Any], c: dict[str,Any]) -> bool:
        field=str(c.get("field") or ""); op=str(c.get("op") or "contains"); target=c.get("value")
        if not field or target in (None,""): return True
        aliases={"title":"channel_title","country":"country","subs":"subscribers","score":"discovery_score"}
        field=aliases.get(field,field); value=row.get(field)
        numeric=field in {"subscribers","ugphone_videos","competitor_videos","discovery_score","best_video_views","query_coverage","objective_fit_score","content_fit_score","continuity_fit_score","topic_affinity_score","use_case_continuity_score","brand_safety_score","audience_size_fit_score","query_coverage_score","sampled_recent_videos","objective_recent_videos","objective_recent_ratio","objective_active_months","creator_language_ratio"}
        if numeric:
            if value in (None,""): return False
            try: a=float(value); b=float(target)
            except Exception: return False
            return {">=":a>=b,">":a>b,"<=":a<=b,"<":a<b,"=":a==b,"!=":a!=b}.get(op,a>=b)
        a=str(value or "").casefold(); b=str(target or "").casefold()
        return {"contains":b in a,"=":a==b,"!=":a!=b,"not_contains":b not in a}.get(op,b in a)

    def result_set_list(self, result_set_id:int, *, page:int=1, page_size:int=30, search:str="", conditions:list[dict[str,Any]]|None=None, sort:str="rank", direction:str="asc") -> dict[str,Any]:
        with connect(self.hub.db_path) as conn:
            rs=conn.execute("SELECT * FROM ai_result_sets WHERE id=?",(int(result_set_id),)).fetchone()
            if not rs: raise ValueError("AI result set not found")
            raw=conn.execute("SELECT item_index,snapshot_json FROM ai_result_items WHERE result_set_id=? ORDER BY item_index",(int(result_set_id),)).fetchall()
        rows=[]
        q=str(search or "").casefold().strip()
        for z in raw:
            r=self._normalize_result_item(json_load(z["snapshot_json"],{})); r["result_rank"]=int(z["item_index"])
            if q and q not in (str(r.get("channel_title") or "")+" "+str(r.get("channel_id") or "")+" "+str(r.get("country") or "")+" "+str(r.get("handle") or "")).casefold(): continue
            if not all(self._result_condition(r,c) for c in (conditions or [])): continue
            rows.append(r)
        field={"rank":"result_rank","title":"channel_title","country":"country","subscribers":"subscribers","ugphone_videos":"ugphone_videos","competitor_videos":"competitor_videos","discovery_score":"discovery_score","best_video_views":"best_video_views","query_coverage":"query_coverage","objective_fit_score":"objective_fit_score","content_fit_score":"content_fit_score","continuity_fit_score":"continuity_fit_score","topic_affinity_score":"topic_affinity_score","use_case_continuity_score":"use_case_continuity_score","brand_safety_score":"brand_safety_score","audience_size_fit_score":"audience_size_fit_score","query_coverage_score":"query_coverage_score","objective_recent_videos":"objective_recent_videos","objective_active_months":"objective_active_months","creator_language_ratio":"creator_language_ratio","candidate_pool":"candidate_pool"}.get(str(sort),"result_rank")
        reverse=str(direction).lower()=="desc"
        def key(r):
            v=r.get(field)
            return str(v or "").casefold() if field in {"channel_title","country","candidate_pool"} else float(v or 0)
        rows.sort(key=key,reverse=reverse)
        total=len(rows); page_size=max(1,min(5000,int(page_size or 30))); pages=max(1,(total+page_size-1)//page_size); page=max(1,min(int(page or 1),pages)); start=(page-1)*page_size
        meta=dict(rs); meta["request"]=json_load(meta.pop("request_json"),{}); meta["plan"]=json_load(meta.pop("plan_json"),{}); meta["metadata"]=json_load(meta.pop("metadata_json"),{})
        return {"result_set":meta,"rows":rows[start:start+page_size],"total":total,"page":page,"page_size":page_size,"pages":pages}

    def result_set_history(self, *, page:int=1,page_size:int=30,result_type:str="",search:str="") -> dict[str,Any]:
        where=[];params=[]
        if result_type: where.append("result_type=?");params.append(str(result_type))
        if search: where.append("lower(COALESCE(input_text,'')||' '||COALESCE(title,'')) LIKE ?");params.append('%'+str(search).casefold()+'%')
        w=' WHERE '+' AND '.join(where) if where else ''
        with connect(self.hub.db_path) as conn:
            total=conn.execute("SELECT COUNT(*) FROM ai_result_sets"+w,tuple(params)).fetchone()[0]
            page_size=max(1,min(500,int(page_size or 30)));pages=max(1,(total+page_size-1)//page_size);page=max(1,min(int(page or 1),pages));off=(page-1)*page_size
            rows=[dict(r) for r in conn.execute("SELECT * FROM ai_result_sets"+w+" ORDER BY id DESC LIMIT ? OFFSET ?",tuple(params+[page_size,off])).fetchall()]
        for r in rows: r["metadata"]=json_load(r.pop("metadata_json"),{});r.pop("request_json",None);r.pop("plan_json",None)
        return {"rows":rows,"total":int(total),"page":page,"page_size":page_size,"pages":pages}

    def result_set_channel_ids(self, result_set_id:int, *, search:str="",conditions:list[dict[str,Any]]|None=None) -> list[str]:
        ids=[];page=1
        while True:
            data=self.result_set_list(result_set_id,page=page,page_size=5000,search=search,conditions=conditions,sort="rank",direction="asc")
            ids.extend(str(r.get("channel_id") or "") for r in data["rows"] if r.get("channel_id"))
            if page>=int(data.get("pages") or 1): break
            page+=1
        return list(dict.fromkeys(ids))

    def creator_brief(self, ref: str, *, force: bool=False) -> dict[str,Any]:
        ctx=creator_context(self.hub,ref); result=self._run("creator_brief",prompt=prompts.creator_brief(ctx),schema=CREATOR_BRIEF_SCHEMA,source=ctx,prompt_version=prompts.PROMPT_VERSIONS["creator_brief"],force=force)
        finding_id=None
        if result.get("run_id"):
            with connect(self.hub.db_path) as conn:
                cur=conn.execute("INSERT INTO ai_findings(run_id,finding_type,channel_id,title,summary,confidence,result_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(result["run_id"],"creator_brief",ctx["channel_id"],ctx.get("channel_title") or ctx["channel_id"],str(result["result"].get("summary") or ""),float(result["result"].get("confidence") or 0),json_dump(result["result"]),now_utc()));finding_id=cur.lastrowid
                for k,v in ctx.get("evidence",{}).items(): conn.execute("INSERT INTO ai_evidence(finding_id,evidence_key,evidence_value_json,source_type,source_ref,captured_at) VALUES(?,?,?,?,?,?)",(finding_id,k,json_dump(v),"local_db",ctx["channel_id"],now_utc()))
                conn.commit()
        return {**result,"finding_id":finding_id,"context":ctx}

    def compare_creators(self, refs: list[str], *, force: bool=False) -> dict[str,Any]:
        max_n=min(5,int(self.config().get("max_creators_per_task") or 50)); refs=[x for x in refs if str(x).strip()][:max_n]
        if len(refs)<2: raise ValueError("at least two creators are required")
        ctx=[creator_context(self.hub,x) for x in refs]
        result=self._run("creator_compare",prompt=prompts.creator_compare(ctx),schema=COMPARE_SCHEMA,source=ctx,prompt_version=prompts.PROMPT_VERSIONS["creator_compare"],force=force)
        if result.get("run_id"):
            with connect(self.hub.db_path) as conn:
                conn.execute("INSERT INTO ai_findings(run_id,finding_type,channel_id,title,summary,confidence,result_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(result["run_id"],"creator_compare",None,"Creator 对比",str(result["result"].get("summary") or ""),None,json_dump(result["result"]),now_utc()));conn.commit()
        return {**result,"contexts":ctx}

    def query_planner(self, query: str, *, language: str="en", objective: str="creator discovery", max_queries: int=12, force: bool=False, progress=None) -> dict[str,Any]:
        q=str(query or "").strip()
        if not q: raise ValueError("query is required")
        max_queries=max(1,min(40,int(max_queries or 12)))
        qp=load_query_packs(); source={"query":q,"language":language,"objective":objective,"max_queries":max_queries,"query_packs":qp}
        result=self._run("query_planner",prompt=prompts.query_planner(q,language,objective,qp,max_queries=max_queries),schema=QUERY_PLAN_SCHEMA,source=source,prompt_version=prompts.PROMPT_VERSIONS["query_planner"],force=force,progress=progress)
        plan=self._objective_heuristics(objective,result.get("result") or {})
        final=[];seen=set()
        for raw in [q]+list(plan.get("queries") or []):
            v=self._canonical_query(q,str(raw or ""));k=self._text(v)
            if not v or k in seen: continue
            seen.add(k);final.append(v)
            if len(final)>=max_queries: break
        plan["queries"]=final
        plan["query_budget"]={"max_queries":max_queries,"planned_queries":len(final),"policy":"Planner final queries + exact base topic; only de-duplicate/canonicalize, no secondary expansion layer"}
        result["result"]=plan
        return result

    def query_search(self, query: str, *, language: str="en", objective: str="creator discovery", max_queries: int=12, max_results: int=25, lookback_days: int | None=None, target_country: str | None=None, target_group: str | None=None, force: bool=False, progress=None, frozen_plan: dict[str,Any] | None=None, frozen_execution: dict[str,Any] | None=None, parent_spec_id: int | None=None) -> dict[str,Any]:
        q=str(query or "").strip()
        if not q: raise ValueError("query is required")
        max_queries=max(1,min(40,int(max_queries or 12))); max_results=max(1,min(100,int(max_results or 25)))
        frozen=bool(frozen_plan)
        if frozen:
            # Clone & Re-run is deliberately deterministic at the planning layer: reuse the
            # exact stored plan/queries instead of asking the LLM to plan again. Fresh YouTube
            # facts can still change, which is recorded as a new Result Set/Run Spec.
            plan=json.loads(json.dumps(frozen_plan or {},ensure_ascii=False,default=str))
            exec_meta=dict(frozen_execution or {})
            planned={"run_id":None,"result":plan,"provider":exec_meta.get("provider"),"model":exec_meta.get("model"),"prompt_version":exec_meta.get("prompt_version"),"frozen_plan":True}
            if progress: progress(stage="冻结计划", message="正在按 Run Specification 的冻结 Query / Fit Criteria 重新执行", percent=8)
        else:
            if progress: progress(stage="AI 规划", message="正在把自然语言要求拆成搜索 Query 与目标适配条件", percent=3)
            planned=self.query_planner(q,language=language,objective=objective,max_queries=max_queries,force=force,progress=progress); plan=planned.get("result") or {}
        fc=plan.get("fit_criteria") or {}
        fc["creator_language"]=self._language_code(language)
        fc["creator_language_min_ratio"]=float(fc.get("creator_language_min_ratio") or 0.60)
        plan["fit_criteria"]=fc; plan["strategy"]=self._fit_strategy(fc)
        if progress: progress(stage=("冻结计划" if frozen else "AI 规划"), message="计划已锁定，准备执行 YouTube 搜索", percent=12)
        if frozen and list((frozen_execution or {}).get("queries") or []):
            planned_queries=[str(x) for x in list((frozen_execution or {}).get("queries") or []) if str(x).strip()][:max_queries]
        else:
            planned_queries=list(plan.get("queries") or [])[:max_queries]
        # discover_expanded always executes the exact base query once; pass only the Planner's remaining final queries.
        queries=[x for x in planned_queries if self._text(x)!=self._text(q)][:max(0,max_queries-1)]
        def _search_progress(**kw):
            if not progress: return
            cur=int(kw.get("current") or 0); total=max(1,int(kw.get("total") or 1))
            pct=15 + int(42*min(1,cur/total))
            progress(stage="YouTube 搜索", message=str(kw.get("message") or "正在执行搜索"), percent=pct, current=cur, total=total)
        discovery=self.hub.discover_expanded(q,queries=queries,max_results=max_results,language=language,search_source="api",target_country=target_country,target_group=target_group,lookback_days=lookback_days,max_queries=max_queries,query_language=language,progress=_search_progress)
        if progress: progress(stage="目标适配检查", message=f"搜索完成，开始检查 {int(discovery.get('unique_creators') or 0)} 个去重候选 Creator", percent=60)
        ai_run_id=planned.get("run_id")
        if ai_run_id and discovery.get("run_id"):
            with connect(self.hub.db_path) as conn:
                conn.execute("UPDATE discovery_runs SET ai_run_id=? WHERE run_id=?",(int(ai_run_id),str(discovery.get("run_id"))));conn.commit()
        def _fit_progress(**kw):
            if not progress: return
            cur=int(kw.get("current") or 0); total=max(1,int(kw.get("total") or 1))
            pct=62 + int(27*min(1,cur/total))
            progress(stage=str(kw.get("stage") or "目标适配检查"), message=str(kw.get("message") or "正在检查候选 Creator"), percent=pct, current=cur, total=total)
        fitted,fit_meta=self._agent_fit(q,objective,plan,discovery,progress=_fit_progress)
        if progress: progress(stage="保存 Result Set", message=f"保留 {len(fitted)} 个候选，正在保存结果快照", percent=93)
        query_funnel=[]
        executed_queries=list(discovery.get("queries_executed") or [])
        hit_by_query={}
        try:
            with connect(self.hub.db_path) as conn:
                hit_by_query={str(r["query"]):{"video_hits":int(r["videos"] or 0),"creator_hits":int(r["creators"] or 0)} for r in conn.execute("SELECT query,COUNT(DISTINCT video_id) videos,COUNT(DISTINCT channel_id) creators FROM discovery_hits WHERE run_id=? GROUP BY query",(str(discovery.get("run_id") or ""),)).fetchall()}
        except Exception:
            hit_by_query={}
        raw_rows=list(discovery.get("results") or [])
        for qx in executed_queries:
            raw_creator=sum(1 for r in raw_rows if qx in list(r.get("matched_queries") or []))
            keep_creator=sum(1 for r in fitted if qx in list(r.get("matched_queries") or []))
            risk_creator=sum(1 for r in fitted if qx in list(r.get("matched_queries") or []) and str(r.get("candidate_pool") or "").startswith("风险"))
            query_funnel.append({"query":qx,**hit_by_query.get(qx,{}),"raw_creators":raw_creator,"retained_creators":keep_creator,"risk_creators":risk_creator})
        metadata={"queries_executed":executed_queries,"hits":discovery.get("hits") or 0,"unique_creators":discovery.get("unique_creators") or 0,"query_funnel":query_funnel,**fit_meta,"ai_provider":planned.get("provider"),"ai_model":planned.get("model"),"prompt_version":planned.get("prompt_version")}
        rsid=self._save_result_set(result_type="youtube_agent",input_text=q,rows=fitted,ai_run_id=(int(ai_run_id) if ai_run_id else None),discovery_run_id=str(discovery.get("run_id") or "") or None,request={"query":q,"language":language,"search_requirements":objective,"max_queries":max_queries,"max_results":max_results,"lookback_days":lookback_days,"target_country":target_country,"target_group":target_group},plan=plan,metadata=metadata,title="AI 搜索 Agent · "+q)
        run_spec=self.hub.runs.save("ai_query_search","AI 搜索 Agent · "+q,{"request":{"query":q,"language":language,"search_requirements":objective,"max_queries":max_queries,"max_results":max_results,"lookback_days":lookback_days,"target_country":target_country,"target_group":target_group},"plan":plan,"execution":{"queries":executed_queries,"profile_budget":fit_meta.get("profile_budget"),"prompt_version":metadata.get("prompt_version"),"provider":metadata.get("ai_provider"),"model":metadata.get("ai_model")}},source_ai_run_id=(int(ai_run_id) if ai_run_id else None),source_result_set_id=rsid,parent_spec_id=parent_spec_id)
        with connect(self.hub.db_path) as conn:
            conn.execute("UPDATE ai_result_sets SET run_spec_id=? WHERE id=?",(run_spec["id"],rsid));conn.commit()
        for r in fitted:
            cid=str(r.get("channel_id") or "")
            if not cid: continue
            try:
                self.hub.contracts.assert_value("creator",cid,"ai.objective_fit","ai",{"score":r.get("objective_fit_score"),"pool":r.get("candidate_pool"),"topic":r.get("topic_affinity_score"),"use_case":r.get("use_case_continuity_score")},source_ref=f"result_set:{rsid}",rule_version=str(metadata.get("prompt_version") or ""),observed_at=now_utc())
            except Exception: pass
        if progress: progress(stage="完成", message=f"AI 搜索完成：保留 {len(fitted)} 个 Creator", percent=100, current=len(fitted), total=len(fitted) or 1)
        return {"planner":planned,"discovery":discovery,"objective_fit":fit_meta,"youtube_api_used":True,"queries_executed":discovery.get("queries_executed") or [],"run_id":discovery.get("run_id"),"result_set_id":rsid,"run_spec_id":run_spec["id"]}

    def ask_hub(self, question: str, *, force: bool=False) -> dict[str,Any]:
        q=str(question or "").strip()
        if not q: raise ValueError("question is required")
        result=self._run("ask_hub",prompt=prompts.ask_hub(q,FIELD_CATALOG),schema=ASK_PLAN_SCHEMA,source={"question":q,"fields":FIELD_CATALOG},prompt_version=prompts.PROMPT_VERSIONS["ask_hub"],force=force)
        plan=dict(result["result"]); explanation=plan.pop("explanation","")
        rows=execute_creator_plan(self.hub,plan)
        rsid=self._save_result_set(result_type="ask_hub",input_text=q,rows=rows,ai_run_id=(int(result["run_id"]) if result.get("run_id") else None),request={"question":q},plan=plan,metadata={"explanation":explanation},title="Ask Hub · "+q[:100])
        run_spec=self.hub.runs.save("ask_hub","Ask Hub · "+q[:100],{"request":{"question":q},"plan":plan},source_ai_run_id=(int(result["run_id"]) if result.get("run_id") else None),source_result_set_id=rsid)
        with connect(self.hub.db_path) as conn: conn.execute("UPDATE ai_result_sets SET run_spec_id=? WHERE id=?",(run_spec["id"],rsid));conn.commit()
        return {**result,"plan":plan,"explanation":explanation,"rows":rows[:30],"count":len(rows),"result_set_id":rsid,"run_spec_id":run_spec["id"]}

    def weekly_brief(self, *, force: bool=False) -> dict[str,Any]:
        ctx=weekly_context(self.hub)
        result=self._run("weekly_brief",prompt=prompts.weekly_brief(ctx),schema=WEEKLY_SCHEMA,source=ctx,prompt_version=prompts.PROMPT_VERSIONS["weekly_brief"],force=force)
        if isinstance(result.get("result"),dict):
            result["result"]["headline"]=str(ctx.get("deterministic_headline") or result["result"].get("headline") or "七日 Creator Intelligence Brief")
        result["brief_metrics"]=ctx.get("brief_metrics") or {}
        result["intelligence"]={"workflow_changes":ctx.get("workflow_changes") or [],"gmv_changes":ctx.get("gmv_changes") or [],"new_users_changes":ctx.get("new_users_changes") or [],"top_discoveries":ctx.get("top_discoveries") or [],"partnership_intelligence":ctx.get("partnership_intelligence") or {},"recent_ai_pool_counts":ctx.get("recent_ai_pool_counts") or {},"recent_ai_unique_creators":ctx.get("recent_ai_unique_creators") or 0,"stuck_sync_runs":ctx.get("stuck_sync_runs") or 0}
        if result.get("run_id"):
            with connect(self.hub.db_path) as conn:
                conn.execute("INSERT INTO ai_findings(run_id,finding_type,channel_id,title,summary,confidence,result_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(result["run_id"],"weekly_brief",None,"七日 Creator Intelligence Brief",str(result["result"].get("summary") or result["result"].get("headline") or ""),None,json_dump(result["result"]),now_utc()));conn.commit()
        return result

    def history(self, *, page:int=1,page_size:int=30) -> dict[str,Any]:
        page=max(1,int(page)); page_size=max(1,min(500,int(page_size))); off=(page-1)*page_size
        with connect(self.hub.db_path) as conn:
            total=conn.execute("SELECT COUNT(*) FROM ai_runs").fetchone()[0]
            rows=[dict(r) for r in conn.execute("SELECT * FROM ai_runs ORDER BY id DESC LIMIT ? OFFSET ?",(page_size,off)).fetchall()]
        pages=max(1,(total+page_size-1)//page_size)
        return {"rows":rows,"total":total,"page":page,"page_size":page_size,"pages":pages}

    def feedback(self, finding_id:int, rating:str, note:str="") -> dict[str,Any]:
        if rating not in {"up","down","neutral"}: raise ValueError("rating must be up/down/neutral")
        with connect(self.hub.db_path) as conn:
            conn.execute("INSERT INTO ai_feedback(finding_id,rating,note,created_at) VALUES(?,?,?,?)",(int(finding_id),rating,str(note or "")[:1000],now_utc()));conn.commit()
        return {"ok":True}
