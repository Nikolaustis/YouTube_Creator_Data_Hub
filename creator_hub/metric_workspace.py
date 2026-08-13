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

OBJECTIVE_FIELDS={
 "subscriber_count":"订阅数","channel_view_count":"频道累计播放量","channel_video_count":"YouTube视频总数","stored_videos":"本地已存视频数",
 "ugphone_video_count":"UgPhone视频数量","competitor_video_count":"竞品视频数量","daily_video_count":"日常视频数量",
 "ldcloud_video_count":"LDCloud视频数量","redfinger_video_count":"RedFinger视频数量","vsphone_video_count":"VSPhone视频数量",
}
AGGREGATE_LABELS={
 "partnered_ugphone":"合作过博主","unpartnered_ugphone":"未合作博主",
 "ldcloud_creator":"LDCloud合作博主","redfinger_creator":"RedFinger合作博主","vsphone_creator":"VSPhone合作博主",
 "ugphone_and_competitor":"UgPhone与竞品均合作博主",
}
VIDEO_OBJECTIVES={"current_views":"播放量","current_likes":"点赞数","current_comments":"评论数","duration_seconds":"视频时长（秒）"}
VIDEO_LABELS={"role:ugphone":"UgPhone视频","role:competitor":"竞品视频","role:daily":"日常视频","brand:ldcloud":"LDCloud视频","brand:redfinger":"RedFinger视频","brand:vsphone":"VSPhone视频","brand:ugphone":"UgPhone品牌视频"}

METRICS_BODY=r'''
<div class="title"><div><h1>二次指标</h1><div class="sub">不预置业务指标。使用者自行从客观数据和聚合标签构建指标。</div></div><div class="inline"><button class="btn" id="exportCfg">导出配置</button><label class="btn">导入配置<input id="importCfg" type="file" accept="application/json" style="display:none"></label><button class="btn danger" id="resetCfg">清空全部指标</button></div></div>
<div class="note"><b>指标构建逻辑：</b>输入类型只有【客观数据】和【聚合标签】；输出类型只有【构建指标】和【比值指标】。构建指标可使用 Count、Sum、Average、Median、Max、Min；比值指标由两个客观数据聚合结果相除。精确日期范围在交互模式下由本地 SQLite 计算，不把全量视频加载进浏览器。</div>
<div class="section metric-builder"><div>
  <div class="builder-panel"><h2>指标构建器</h2><input type="hidden" id="metricEditId"><div class="form-row"><label>指标名称</label><input id="metricName" placeholder="例如：UgPhone视频播放中位数"></div><div class="form-row"><label>输出类型</label><select id="metricOutputType"><option value="constructed">构建指标</option><option value="ratio">比值指标</option></select></div><div class="form-row"><label>输入类型</label><select id="metricInputType"><option value="objective">客观数据</option><option value="aggregate_label">聚合标签</option></select></div><div id="metricDynamic"></div><div class="form-row"><label>结果表显示</label><select id="metricVisible"><option value="1">显示</option><option value="0">隐藏，仅供规则使用</option></select></div><div class="inline"><button class="btn primary" id="saveMetric">构建指标</button><button class="btn" id="clearMetric">清空输入</button></div><div id="metricStatus" class="small"></div></div>
  <div class="builder-panel section"><h2>规则 / 标签构建器</h2><input type="hidden" id="ruleEditId"><div class="form-row"><label>规则名称</label><input id="ruleName" placeholder="例如：高潜未合作博主"></div><div id="ruleConditions"></div><div class="inline"><button class="btn" id="addRuleCondition">添加条件</button><button class="btn primary" id="saveRule">保存规则</button><button class="btn" id="clearRule">清空</button></div><div class="small">第一条条件不需要布尔关系；从第二条开始可逐条选择 AND / OR / NOT（NOT 表示在当前结果中排除满足该条件的博主）。</div></div>
</div><div><div class="builder-panel"><div class="inline spread"><h2>已构建指标</h2><span class="small">初始为空，由使用者自行建立</span></div><div id="metricList" class="metric-list section"></div></div><div class="builder-panel section"><div class="inline spread"><h2>规则列表</h2><span class="small">规则可直接使用四类指标</span></div><div id="ruleList" class="metric-list section"></div></div></div></div>
<div class="section"><div class="title compact-title"><div><h1>应用结果 · 博主库</h1><div class="sub">可添加多条筛选条件，并逐条使用 AND / OR / NOT。</div></div></div>
<div class="builder-panel"><div id="resultFilterConditions"></div><div class="inline"><button class="btn" id="addResultFilter">添加筛选条件</button><button class="btn primary" id="applyFilter">应用筛选</button><button class="btn" id="clearFilter">清除筛选</button><select id="activeRule" class="select"><option value="">全部规则</option></select><input id="metricSearch" class="input" placeholder="搜索博主 / 国家 / Channel ID"></div></div>
<div class="toolbar section"><span class="small">排序</span><select id="resultSort" class="select"></select><select id="resultSortDir" class="select"><option value="desc">降序</option><option value="asc">升序</option></select><span class="small">每页</span><input id="resultPageSize" class="input" type="number" min="1" max="5000" value="30" style="min-width:72px;width:82px"><button class="btn" id="resultPageSizeConfirm">确定</button><span class="small">条</span><span id="resultSummary" class="table-summary"></span></div>
<div class="table-wrap"><table class="metric-table"><thead id="resultHead"></thead><tbody id="resultBody"></tbody></table></div><div class="pager"><button class="btn" id="resultFirst">第一页</button><button class="btn" id="resultPrev">上一页</button><span id="resultPageButtons" class="inline"></span><button class="btn" id="resultNext">下一页</button><button class="btn" id="resultLast">最后一页</button><span class="small">跳转到</span><input id="resultPageInput" class="input" type="number" min="1" value="1"><button class="btn" id="resultJump">跳转</button><span id="resultPageInfo" class="small"></span></div></div>
<script src="assets/creator_facts.js"></script><script src="assets/metric_base.js"></script><script src="assets/metrics_config.js"></script><script src="assets/table_tools.js"></script><script src="assets/metrics_workspace.js"></script>
'''


def _new_bucket(): return {"count":0,**{m:[] for m in MEASURES}}
def _add(b,row):
 b["count"]+=1
 for m in MEASURES:
  v=row.get(m)
  if v is not None:
   try:b[m].append(float(v))
   except:pass

def _finish(b):
 out={"count":b["count"]}
 for m in MEASURES:
  vals=b[m]
  if vals: out[m]={"sum":sum(vals),"avg":sum(vals)/len(vals),"median":statistics.median(vals),"min":min(vals),"max":max(vals)}
 return out

def _creator_cube(conn,cid,now):
 rows=conn.execute("""SELECT v.published_at,v.current_views,v.current_likes,v.current_comments,v.duration_seconds,s.suggested_role,s.brands_json suggested_brands,l.human_role,l.brands_json human_brands FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id WHERE v.channel_id=?""",(cid,)).fetchall()
 buckets=defaultdict(_new_bucket); brands=set()
 for rr in rows:
  r=dict(rr); sys=r.get("suggested_role") or "pending"; human=r.get("human_role"); role=human or sys; sb=json_load(r.get("suggested_brands"),[]); hb=json_load(r.get("human_brands"),[]); bs=hb if human else sb; brands.update(str(x) for x in bs if x)
  pub=parse_iso(r.get("published_at")); age=(now-pub).total_seconds()/86400 if pub else None; wins=["all"]
  if age is not None and age>=0: wins += [str(w) for w in WINDOWS if w and age<=w]
  scopes=[("all","all"),("role",role)]+[("brand",str(b)) for b in bs if b]
  for sc,val in scopes:
   for win in wins:_add(buckets[(sc,val,win)],r)
 cube={}
 for (sc,val,win),b in buckets.items():cube.setdefault(sc,{}).setdefault(val,{})[win]=_finish(b)
 return cube,brands

def _count(cube,scope,val): return int((((cube.get(scope) or {}).get(val) or {}).get("all") or {}).get("count") or 0)

def write_metric_assets(conn,out:Path,creators:list[dict[str,Any]],last_sync:dict[str,Any],static_js:Path)->dict[str,int]:
 assets=out/"assets";assets.mkdir(parents=True,exist_ok=True); now=parse_iso(now_utc()); cubes={}; brands=set(); facts=[]
 for c in creators:
  cube,found=_creator_cube(conn,c["channel_id"],now);cubes[c["channel_id"]]=cube;brands.update(found)
  ug=_count(cube,"role","ugphone"); comp=_count(cube,"role","competitor"); daily=_count(cube,"role","daily")
  bc={b:_count(cube,"brand",b) for b in CORE_BRANDS}
  f={"channel_id":c["channel_id"],"channel_title":c.get("channel_title"),"handle":c.get("handle"),"country_api":c.get("country_api"),"country_resolved":c.get("country_resolved"),"country_source":c.get("country_source"),"subscriber_count":c.get("subscriber_count"),"channel_view_count":c.get("channel_view_count"),"channel_video_count":c.get("channel_video_count"),"stored_videos":c.get("stored_videos"),"latest_upload":c.get("latest_upload"),"last_synced_at":c.get("last_synced_at"),"priority":c.get("priority"),"monitoring_enabled":c.get("monitoring_enabled"),"ugphone_video_count":ug,"competitor_video_count":comp,"daily_video_count":daily,"ldcloud_video_count":bc["ldcloud"],"redfinger_video_count":bc["redfinger"],"vsphone_video_count":bc["vsphone"],"partnered_ugphone":1 if ug>0 else 0,"unpartnered_ugphone":1 if ug==0 else 0,"competitor_creator":1 if comp>0 or bc["ldcloud"]+bc["redfinger"]+bc["vsphone"]>0 else 0,"ldcloud_creator":1 if bc["ldcloud"]>0 else 0,"redfinger_creator":1 if bc["redfinger"]>0 else 0,"vsphone_creator":1 if bc["vsphone"]>0 else 0,"ugphone_and_competitor":1 if ug>0 and (comp>0 or bc["ldcloud"]+bc["redfinger"]+bc["vsphone"]>0) else 0}
  facts.append(f)
 (assets/"creator_facts.js").write_text("window.CDH_CREATOR_FACTS="+json.dumps({"generated_at":now_utc(),"creators":facts},ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
 base={"generated_at":now_utc(),"windows":["all","7","30","60","90","180","365"],"roles":list(ROLES),"brands":sorted(brands|set(CORE_BRANDS)),"cubes":cubes,"objective_fields":OBJECTIVE_FIELDS,"aggregate_labels":AGGREGATE_LABELS,"video_objectives":VIDEO_OBJECTIVES,"video_labels":VIDEO_LABELS}
 (assets/"metric_base.js").write_text("window.CDH_METRIC_BASE="+json.dumps(base,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
 saved=load_metric_config();(assets/"metrics_config.js").write_text("window.CDH_SAVED_METRIC_CONFIG="+(json.dumps(saved,ensure_ascii=False,separators=(",",":")) if saved else "null")+";\n",encoding="utf-8")
 (assets/"metrics_workspace.js").write_text(static_js.read_text(encoding="utf-8"),encoding="utf-8")
 ov=static_js.parent/"overview_filters.js"
 if ov.exists():(assets/"overview_filters.js").write_text(ov.read_text(encoding="utf-8"),encoding="utf-8")
 return {"creators":len(facts),"video_rows_exported":0,"saved_config":int(bool(saved))}
