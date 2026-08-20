from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import json_load
from .metric_config import load_metric_config
from .util import now_utc, parse_iso

WINDOWS=(0,7,30,60,90,180,365)
MEASURES=("current_views","current_likes","current_comments","duration_seconds")
ROLES=("ugphone","competitor","daily","multi_brand","other_cloud_phone","pending")
CORE_BRANDS=("ugphone","ldcloud","redfinger","vsphone")

# Creator-grain values. These are already one value per creator and must never be
# re-aggregated with Average/Median/etc. They are used directly in rules, filters,
# sorting and ratio metrics.
CREATOR_FACT_FIELDS={
    "subscriber_count":"订阅数",
    "channel_view_count":"频道累计播放量",
    "channel_video_count":"YouTube视频总数",
    "stored_videos":"本地已存视频数",
    "ugphone_video_count":"UgPhone视频数量",
    "competitor_video_count":"竞品视频数量",
    "daily_video_count":"日常视频数量",
    "ldcloud_video_count":"LDCloud视频数量",
    "redfinger_video_count":"RedFinger视频数量",
    "vsphone_video_count":"VSPhone视频数量",
    "gmv_total":"GMV（商业数据）",
    "new_users_total":"拉新（商业数据）",
}

# Creator-grain boolean identity labels. They are predicates, not numeric metrics.
CREATOR_LABELS={
    "partnered_ugphone":"合作过博主",
    "unpartnered_ugphone":"未合作博主",
    "ldcloud_creator":"LDCloud合作博主",
    "redfinger_creator":"RedFinger合作博主",
    "vsphone_creator":"VSPhone合作博主",
    "ugphone_and_competitor":"UgPhone与竞品均合作博主",
    "suspected_inactive_partner":"疑似不再合作",
}

# Video-grain fact fields. Only these enter the metric builder. Aggregation converts
# many video rows into one creator-level constructed metric.
VIDEO_FACT_FIELDS={
    "video_count":"视频数量",
    "current_views":"播放量",
    "current_likes":"点赞数",
    "current_comments":"评论数",
    "duration_seconds":"视频时长（秒）",
}
VIDEO_FILTERS={
    "role:ugphone":"UgPhone视频",
    "role:competitor":"竞品视频",
    "role:daily":"日常视频",
    "role:multi_brand":"多品牌云手机视频",
    "role:other_cloud_phone":"其他云手机视频",
    "brand:ldcloud":"LDCloud视频",
    "brand:redfinger":"RedFinger视频",
    "brand:vsphone":"VSPhone视频",
    "brand:ugphone":"UgPhone品牌视频",
}

METRICS_BODY=r'''
<div class="title"><div><h1>二次指标</h1><div class="sub">博主级事实、博主标签与视频级事实严格分层；视频数据只有经过聚合后才成为博主级构建指标。</div></div><div class="inline"><button class="btn" id="exportCfg">导出配置</button><label class="btn">导入配置<input id="importCfg" type="file" accept="application/json" style="display:none"></label><button class="btn danger" id="resetCfg">清空全部指标</button></div></div>
<div class="note"><b>指标层级：</b>【博主客观数据】和【博主标签】直接用于筛选/规则，不进入聚合器；【指标构建器】只对视频客观数据执行 Count、Sum、Average、Median、Max、Min，输出每位博主一个【构建指标】；【比值指标】只对博主数值型客观数据或已构建指标做 A ÷ B。</div>
<div class="section metric-builder"><div>
  <div class="builder-panel anchor-section" id="metrics-builder"><h2>指标构建器</h2><input type="hidden" id="metricEditId"><div class="form-row"><label>指标名称</label><input id="metricName" placeholder="例如：近90天UgPhone视频播放中位数"></div><div class="form-row"><label>指标分组</label><input id="metricGroup" placeholder="例如：流量指标 / 合作判断"></div><div class="form-row top"><label>业务说明</label><textarea id="metricDescription" rows="2" placeholder="说明该指标的业务含义、使用场景或口径"></textarea></div><div class="form-row"><label>输出类型</label><select id="metricOutputType"><option value="constructed">构建指标</option><option value="ratio">比值指标</option></select></div><div id="metricDynamic"></div><div class="form-row"><label>结果表显示</label><select id="metricVisible"><option value="1">显示</option><option value="0">隐藏，仅供规则/比值使用</option></select></div><div class="inline"><button class="btn primary" id="saveMetric">保存指标</button><button class="btn" id="clearMetric">清空输入</button></div><div id="metricStatus" class="small"></div></div>
  <div class="builder-panel section anchor-section" id="metrics-rule-builder"><h2>规则 / 标签构建器</h2><input type="hidden" id="ruleEditId"><div class="form-row"><label>规则名称</label><input id="ruleName" placeholder="例如：高潜未合作博主"></div><div class="form-row"><label>规则分组</label><input id="ruleGroup" placeholder="例如：合作判断"></div><div class="form-row top"><label>规则说明</label><textarea id="ruleDescription" rows="2" placeholder="说明规则用途"></textarea></div><div id="ruleConditions"></div><div class="inline"><button class="btn" id="addRuleCondition">添加条件</button><button class="btn primary" id="saveRule">保存规则</button><button class="btn" id="clearRule">清空</button></div><div class="small">条件类型包括博主客观数据、博主标签、构建指标和比值指标。博主标签使用“存在 / 不存在”，不填写数字阈值。第二条起可逐条选择 AND / OR / NOT。</div></div>
</div><div><div class="builder-panel anchor-section" id="metrics-saved"><div class="inline spread"><div><h2>已构建指标</h2><span class="small">业务配置优先保存到 SQLite；浏览器仅保留临时回退副本。</span></div><div class="inline"><span class="small">分组</span><select id="metricGroupFilter" class="select"><option value="">全部分组</option></select></div></div><div id="metricList" class="metric-list section"></div></div><div class="builder-panel section anchor-section" id="metrics-rules"><div class="inline spread"><h2>规则列表</h2><span class="small">规则作用对象始终是博主</span></div><div id="ruleList" class="metric-list section"></div></div></div></div>
<div class="section anchor-section" id="metrics-results"><div class="title compact-title"><div><h1>应用结果 · 博主库</h1><div class="sub">全部条件最终都在博主粒度上执行。可添加多条筛选条件，并逐条使用 AND / OR / NOT。</div></div></div>
<div class="builder-panel"><div id="resultFilterConditions"></div><div class="inline"><button class="btn" id="addResultFilter">添加筛选条件</button><button class="btn primary" id="applyFilter">应用筛选</button><button class="btn" id="clearFilter">清除全部条件</button><select id="activeRule" class="select"><option value="">全部博主（不应用规则）</option></select><input id="metricSearch" class="input" placeholder="搜索博主 / 国家 / Channel ID"><span id="resultConditionStatus" class="small"></span></div></div>
<div class="toolbar section"><span class="small">排序</span><select id="resultSort" class="select"></select><select id="resultSortDir" class="select"><option value="desc">降序</option><option value="asc">升序</option></select><span class="small">每页</span><input id="resultPageSize" class="input" type="number" min="1" max="5000" value="30" style="min-width:72px;width:82px"><button class="btn" id="resultPageSizeConfirm">确定</button><span class="small">条</span><button class="btn" id="resultExport">导出当前结果 XLSX</button><span id="resultSummary" class="table-summary"></span></div>
<div class="table-wrap"><table class="metric-table"><thead id="resultHead"></thead><tbody id="resultBody"></tbody></table></div><div class="pager"><button class="btn" id="resultFirst">第一页</button><button class="btn" id="resultPrev">上一页</button><span id="resultPageButtons" class="inline"></span><button class="btn" id="resultNext">下一页</button><button class="btn" id="resultLast">最后一页</button><span class="small">跳转到</span><input id="resultPageInput" class="input" type="number" min="1" value="1"><button class="btn" id="resultJump">跳转</button><span id="resultPageInfo" class="small"></span></div></div>
<script src="assets/creator_facts.js"></script><script src="assets/metric_base.js"></script><script src="assets/geography.js"></script><script src="assets/metrics_config.js"></script><script src="assets/table_tools.js"></script><script src="assets/metrics_workspace.js"></script>
'''


def _new_bucket():
    return {"count":0, **{m:[] for m in MEASURES}}


def _add(bucket:dict[str,Any], row:dict[str,Any]):
    bucket["count"] += 1
    for measure in MEASURES:
        value=row.get(measure)
        if value is None:
            continue
        try:
            bucket[measure].append(float(value))
        except (TypeError, ValueError):
            pass


def _finish(bucket:dict[str,Any]):
    out={"count":bucket["count"]}
    for measure in MEASURES:
        vals=bucket[measure]
        if vals:
            out[measure]={
                "sum":sum(vals),
                "avg":sum(vals)/len(vals),
                "median":statistics.median(vals),
                "min":min(vals),
                "max":max(vals),
            }
    return out


def _creator_cube(conn, channel_id:str, now):
    rows=conn.execute(
        """SELECT v.published_at,v.current_views,v.current_likes,v.current_comments,v.duration_seconds,
                  s.suggested_role,s.brands_json suggested_brands,l.human_role,l.brands_json human_brands
           FROM videos v
           LEFT JOIN label_suggestions s ON s.video_id=v.video_id
           LEFT JOIN video_labels l ON l.video_id=v.video_id
           WHERE v.channel_id=?""",
        (channel_id,),
    ).fetchall()
    buckets=defaultdict(_new_bucket)
    brands=set()
    for rr in rows:
        r=dict(rr)
        system_role=r.get("suggested_role") or "pending"
        human_role=r.get("human_role")
        final_role=human_role or system_role
        suggested_brands=json_load(r.get("suggested_brands"),[])
        human_brands=json_load(r.get("human_brands"),[])
        final_brands=human_brands if human_role else suggested_brands
        brands.update(str(x) for x in final_brands if x)
        published=parse_iso(r.get("published_at"))
        age=(now-published).total_seconds()/86400 if published else None
        windows=["all"]
        if age is not None and age>=0:
            windows += [str(w) for w in WINDOWS if w and age<=w]
        scopes=[("all","all"),("role",final_role)] + [("brand",str(b)) for b in final_brands if b]
        for scope,value in scopes:
            for window in windows:
                _add(buckets[(scope,value,window)],r)
    cube={}
    for (scope,value,window),bucket in buckets.items():
        cube.setdefault(scope,{}).setdefault(value,{})[window]=_finish(bucket)
    return cube,brands


def _count(cube, scope, value):
    return int((((cube.get(scope) or {}).get(value) or {}).get("all") or {}).get("count") or 0)


def build_creator_facts(creators:list[dict[str,Any]])->dict[str,Any]:
    """Build the creator-grain facts payload used by interactive Dashboard pages.

    This path is intentionally lightweight: counts already aggregated by _creator_rows()
    are reused, so refreshing Creator facts does not rebuild HTML or scan every video cube.
    """
    facts=[]
    for c in creators:
        ug=int(c.get("identified_ugphone") or c.get("ugphone_video_count") or 0)
        comp=int(c.get("identified_competitor") or c.get("competitor_video_count") or 0)
        daily=int(c.get("identified_daily") or c.get("daily_video_count") or 0)
        brand_counts={
            "ldcloud":int(c.get("ldcloud_videos") or c.get("ldcloud_video_count") or 0),
            "redfinger":int(c.get("redfinger_videos") or c.get("redfinger_video_count") or 0),
            "vsphone":int(c.get("vsphone_videos") or c.get("vsphone_video_count") or 0),
        }
        f={
            "channel_id":c["channel_id"],
            "channel_title":c.get("channel_title"),
            "handle":c.get("handle"),
            "channel_url":c.get("channel_url"),
            "country_api":c.get("country_api"),
            "country_resolved":c.get("country_resolved"),
            "country_source":c.get("country_source"),
            "subscriber_count":c.get("subscriber_count"),
            "channel_view_count":c.get("channel_view_count"),
            "channel_video_count":c.get("channel_video_count"),
            "stored_videos":c.get("stored_videos"),
            "latest_upload":c.get("latest_upload"),
            "last_synced_at":c.get("last_synced_at"),
            "channel_data_at":c.get("channel_data_at"),
            "video_metrics_at":c.get("video_metrics_at"),
            "classification_data_at":c.get("classification_data_at"),
            "contact_scraped_at":c.get("contact_scraped_at"),
            "last_sync_attempt_at":c.get("last_sync_attempt_at"),
            "last_sync_status":c.get("last_sync_status"),
            "last_sync_error":c.get("last_sync_error"),
            "sync_error_type":c.get("sync_error_type"),
            "consecutive_sync_failures":c.get("consecutive_sync_failures"),
            "next_sync_at":c.get("next_sync_at"),
            "next_retry_at":c.get("next_retry_at"),
            "sync_suspended":c.get("sync_suspended"),
            "priority":c.get("priority"),
            "monitoring_enabled":c.get("monitoring_enabled"),
            "ugphone_video_count":ug,
            "competitor_video_count":comp,
            "daily_video_count":daily,
            "ldcloud_video_count":brand_counts["ldcloud"],
            "redfinger_video_count":brand_counts["redfinger"],
            "vsphone_video_count":brand_counts["vsphone"],
            "gmv_total":float(c.get("gmv_total") or 0),
            "new_users_total":float(c.get("new_users_total") or 0),
            "business_metric_count":int(c.get("business_metric_count") or 0),
            "business_metric_updated_at":c.get("business_metric_updated_at"),
            "gmv_currency":c.get("gmv_currency") or "",
            "partnered_ugphone":1 if ug>0 else 0,
            "unpartnered_ugphone":1 if ug==0 else 0,
            "competitor_creator":1 if comp>0 or sum(brand_counts.values())>0 else 0,
            "ldcloud_creator":1 if brand_counts["ldcloud"]>0 else 0,
            "redfinger_creator":1 if brand_counts["redfinger"]>0 else 0,
            "vsphone_creator":1 if brand_counts["vsphone"]>0 else 0,
            "ugphone_and_competitor":1 if ug>0 and (comp>0 or sum(brand_counts.values())>0) else 0,
            "suspected_inactive_partner":1 if c.get("suspected_inactive_partner") else 0,
        }
        facts.append(f)
    return {"generated_at":now_utc(),"creators":facts}


def build_metric_base(conn, creators:list[dict[str,Any]])->dict[str,Any]:
    """Build the current video-grain aggregate cubes without writing Dashboard files."""
    now=parse_iso(now_utc())
    cubes={}
    brands=set()
    for c in creators:
        cube,found=_creator_cube(conn,c["channel_id"],now)
        cubes[c["channel_id"]]=cube
        brands.update(found)
    return {
        "schema_version":1,
        "generated_at":now_utc(),
        "windows":["all","7","30","60","90","180","365"],
        "roles":list(ROLES),
        "brands":sorted(brands|set(CORE_BRANDS)),
        "cubes":cubes,
        "creator_fact_fields":CREATOR_FACT_FIELDS,
        "creator_labels":CREATOR_LABELS,
        "video_fact_fields":VIDEO_FACT_FIELDS,
        "video_filters":VIDEO_FILTERS,
        # Read-only aliases for legacy configurations. New UI never exposes these names.
        "objective_fields":CREATOR_FACT_FIELDS,
        "aggregate_labels":CREATOR_LABELS,
        "video_objectives":VIDEO_FACT_FIELDS,
        "video_labels":VIDEO_FILTERS,
    }


def write_metric_assets(conn, out:Path, creators:list[dict[str,Any]], last_sync:dict[str,Any], static_js:Path)->dict[str,int]:
    assets=out/"assets"
    assets.mkdir(parents=True,exist_ok=True)
    facts_payload=build_creator_facts(creators)
    base=build_metric_base(conn,creators)
    (assets/"creator_facts.js").write_text(
        "window.CDH_CREATOR_FACTS="+json.dumps(facts_payload,ensure_ascii=False,separators=(",",":"))+";\n",
        encoding="utf-8",
    )
    (assets/"metric_base.js").write_text(
        "window.CDH_METRIC_BASE="+json.dumps(base,ensure_ascii=False,separators=(",",":"))+";\n",
        encoding="utf-8",
    )
    row=conn.execute("SELECT value_json FROM app_settings WHERE key='secondary_metrics'").fetchone()
    saved=json_load(row["value_json"],None) if row else load_metric_config()
    (assets/"metrics_config.js").write_text(
        "window.CDH_SAVED_METRIC_CONFIG="+(json.dumps(saved,ensure_ascii=False,separators=(",",":")) if saved else "null")+";\n",
        encoding="utf-8",
    )
    (assets/"metrics_workspace.js").write_text(static_js.read_text(encoding="utf-8"),encoding="utf-8")
    overview_js=static_js.parent/"overview_filters.js"
    if overview_js.exists():
        (assets/"overview_filters.js").write_text(overview_js.read_text(encoding="utf-8"),encoding="utf-8")
    return {"creators":len(facts_payload["creators"]),"cubes":len(base["cubes"]),"video_rows_exported":0,"saved_config":int(bool(saved))}
