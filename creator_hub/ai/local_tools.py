from __future__ import annotations

import statistics
from datetime import datetime, timezone, timedelta
from typing import Any

from ..db import connect, json_load
from ..geography import group_codes
from ..monitoring import suspected_inactive_partner
from ..util import parse_iso

WORKFLOW_LABELS = {
    "unreviewed":"未处理","interested":"感兴趣","to_contact":"待联系","in_library":"已入库","defer":"暂不考虑","excluded":"永久排除"
}


def resolve_local_creator(hub, ref: str) -> dict[str, Any] | None:
    needle = str(ref or "").strip()
    if not needle:
        return None
    raw = needle.lstrip("@").casefold()
    with connect(hub.db_path) as conn:
        row = conn.execute("SELECT * FROM creators WHERE channel_id=?", (needle,)).fetchone()
        if not row:
            rows = conn.execute("SELECT * FROM creators WHERE lower(channel_title)=? OR lower(replace(COALESCE(handle,''),'@',''))=? LIMIT 2", (needle.casefold(), raw)).fetchall()
            row = rows[0] if len(rows) == 1 else None
    return dict(row) if row else None


def _median(values):
    nums = [int(x) for x in values if x is not None]
    return statistics.median(nums) if nums else None


def creator_context(hub, ref: str) -> dict[str, Any]:
    c = resolve_local_creator(hub, ref)
    if not c:
        raise ValueError("Creator not found in local database")
    cid = c["channel_id"]
    now = datetime.now(timezone.utc)
    cutoff90 = (now - timedelta(days=90)).isoformat().replace("+00:00", "Z")
    cutoff365 = (now - timedelta(days=365)).isoformat().replace("+00:00", "Z")
    with connect(hub.db_path) as conn:
        agg = dict(conn.execute("""
            SELECT COUNT(*) stored_videos,
              SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='ugphone' THEN 1 ELSE 0 END) ugphone_videos,
              SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='competitor' THEN 1 ELSE 0 END) competitor_videos,
              SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='daily' THEN 1 ELSE 0 END) daily_videos,
              SUM(CASE WHEN lower(COALESCE(l.brands_json,s.brands_json,'')) LIKE '%ldcloud%' THEN 1 ELSE 0 END) ldcloud_videos,
              SUM(CASE WHEN lower(COALESCE(l.brands_json,s.brands_json,'')) LIKE '%redfinger%' THEN 1 ELSE 0 END) redfinger_videos,
              SUM(CASE WHEN lower(COALESCE(l.brands_json,s.brands_json,'')) LIKE '%vsphone%' THEN 1 ELSE 0 END) vsphone_videos,
              MAX(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='ugphone' THEN v.published_at END) latest_ugphone_upload,
              MAX(v.published_at) latest_upload
            FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id
            WHERE v.channel_id=?
        """, (cid,)).fetchone())
        recent = [dict(r) for r in conn.execute("""
            SELECT v.video_id,v.title,v.published_at,v.current_views,v.current_likes,v.current_comments,
                   COALESCE(l.human_role,s.suggested_role,'pending') role,
                   COALESCE(l.brands_json,s.brands_json,'[]') brands_json
            FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id
            WHERE v.channel_id=? ORDER BY v.published_at DESC LIMIT 500
        """, (cid,)).fetchall()]
        disc = conn.execute("SELECT * FROM creator_discovery_summary WHERE channel_id=?", (cid,)).fetchone()
        wf = conn.execute("SELECT * FROM creator_workflow WHERE channel_id=?", (cid,)).fetchone()
        tags = [r[0] for r in conn.execute("SELECT tag FROM creator_tags WHERE channel_id=? ORDER BY tag", (cid,)).fetchall()]
    views90 = [r["current_views"] for r in recent if (r.get("published_at") or "") >= cutoff90]
    views365 = [r["current_views"] for r in recent if (r.get("published_at") or "") >= cutoff365]
    evidence = {
        "subscriber_count": c.get("subscriber_count"),
        "channel_view_count": c.get("channel_view_count"),
        "stored_videos": int(agg.get("stored_videos") or 0),
        "ugphone_videos": int(agg.get("ugphone_videos") or 0),
        "competitor_videos": int(agg.get("competitor_videos") or 0),
        "median_views_90d": _median(views90),
        "median_views_365d": _median(views365),
        "latest_upload": agg.get("latest_upload"),
        "latest_ugphone_upload": agg.get("latest_ugphone_upload"),
        "last_synced_at": c.get("last_synced_at"),
    }
    return {
        "channel_id": cid,
        "channel_title": c.get("channel_title"),
        "handle": c.get("handle"),
        "country": c.get("country_resolved") or c.get("country_api"),
        "subscriber_count": c.get("subscriber_count"),
        "channel_view_count": c.get("channel_view_count"),
        "monitoring_enabled": bool(c.get("monitoring_enabled")),
        "priority": c.get("priority"),
        "workflow": WORKFLOW_LABELS.get((dict(wf).get("status") if wf else "unreviewed"), (dict(wf).get("status") if wf else "unreviewed")),
        "tags": tags,
        "video_summary": {**agg, "median_views_90d": _median(views90), "median_views_365d": _median(views365)},
        "discovery_summary": dict(disc) if disc else {},
        "recent_videos": [{**r, "brands": json_load(r.pop("brands_json", "[]"), [])} for r in recent[:12]],
        "freshness": hub.data_freshness(cid),
        "evidence": evidence,
    }


FIELD_CATALOG = {
    "search": "title/handle substring",
    "region": "product geography group name/id",
    "country": "ISO alpha-2 code",
    "subscriber_min": "integer",
    "subscriber_max": "integer",
    "partnered": "boolean: historical UgPhone videos exist",
    "unpartnered": "boolean: no historical UgPhone videos",
    "competitor_brand": "ldcloud|redfinger|vsphone|any",
    "monitoring": "boolean",
    "priority": "high|normal|low|archive",
    "workflow": "unreviewed|interested|to_contact|in_library|defer|excluded",
    "suspected_inactive": "boolean",
    "sort": "subscribers|channel_views|ugphone_videos|competitor_videos|discovery_score|latest_upload|title",
    "direction": "asc|desc",
    "result_limit": "optional integer; only when user explicitly requests Top N / an exact maximum",
}


def _creator_rows_for_query(hub) -> list[dict[str, Any]]:
    with connect(hub.db_path) as conn:
        rows = conn.execute("""
        WITH va AS (
          SELECT v.channel_id,COUNT(*) stored_videos,MAX(v.published_at) latest_upload,
            MAX(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='ugphone' THEN v.published_at END) latest_ugphone_upload,
            SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='ugphone' THEN 1 ELSE 0 END) ugphone_videos,
            SUM(CASE WHEN COALESCE(l.human_role,s.suggested_role,'pending')='competitor' THEN 1 ELSE 0 END) competitor_videos,
            SUM(CASE WHEN lower(COALESCE(l.brands_json,s.brands_json,'')) LIKE '%ldcloud%' THEN 1 ELSE 0 END) ldcloud_videos,
            SUM(CASE WHEN lower(COALESCE(l.brands_json,s.brands_json,'')) LIKE '%redfinger%' THEN 1 ELSE 0 END) redfinger_videos,
            SUM(CASE WHEN lower(COALESCE(l.brands_json,s.brands_json,'')) LIKE '%vsphone%' THEN 1 ELSE 0 END) vsphone_videos
          FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id GROUP BY v.channel_id
        )
        SELECT c.channel_id,c.channel_title,c.handle,c.country_resolved,c.country_api,c.subscriber_count,c.channel_view_count,c.monitoring_enabled,c.priority,c.last_synced_at,
          COALESCE(va.stored_videos,0) stored_videos,COALESCE(va.ugphone_videos,0) ugphone_videos,COALESCE(va.competitor_videos,0) competitor_videos,
          COALESCE(va.ldcloud_videos,0) ldcloud_videos,COALESCE(va.redfinger_videos,0) redfinger_videos,COALESCE(va.vsphone_videos,0) vsphone_videos,
          va.latest_upload,va.latest_ugphone_upload,COALESCE(w.status,'unreviewed') workflow,ds.best_discovery_score
        FROM creators c LEFT JOIN va ON va.channel_id=c.channel_id LEFT JOIN creator_workflow w ON w.channel_id=c.channel_id LEFT JOIN creator_discovery_summary ds ON ds.channel_id=c.channel_id
        """).fetchall()
    return [dict(r) for r in rows]


def execute_creator_plan(hub, plan: dict[str, Any]) -> list[dict[str, Any]]:
    p = dict(plan or {})
    allowed = set(FIELD_CATALOG)
    p = {k:v for k,v in p.items() if k in allowed}
    rows = _creator_rows_for_query(hub)
    search = str(p.get("search") or "").casefold().strip()
    codes = set()
    if p.get("region"):
        try: codes = set(group_codes(str(p["region"])))
        except Exception: codes = set()
    country = str(p.get("country") or "").upper().strip()
    brand = str(p.get("competitor_brand") or "").lower().strip()
    out=[]
    for r in rows:
        if search and search not in (str(r.get("channel_title") or "") + " " + str(r.get("handle") or "")).casefold(): continue
        cc = str(r.get("country_resolved") or r.get("country_api") or "").upper()
        if codes and cc not in codes: continue
        if country and cc != country: continue
        subs=int(r.get("subscriber_count") or 0)
        if p.get("subscriber_min") is not None and subs < int(p["subscriber_min"]): continue
        if p.get("subscriber_max") is not None and subs > int(p["subscriber_max"]): continue
        if p.get("partnered") is True and int(r.get("ugphone_videos") or 0)<=0: continue
        if p.get("unpartnered") is True and int(r.get("ugphone_videos") or 0)>0: continue
        if p.get("monitoring") is not None and bool(r.get("monitoring_enabled")) != bool(p["monitoring"]): continue
        if p.get("priority") and r.get("priority") != p["priority"]: continue
        if p.get("workflow") and r.get("workflow") != p["workflow"]: continue
        if brand == "any" and int(r.get("competitor_videos") or 0)<=0: continue
        if brand in {"ldcloud","redfinger","vsphone"} and int(r.get(brand+"_videos") or 0)<=0: continue
        if p.get("suspected_inactive") is True:
            if not suspected_inactive_partner(hub.settings, monitoring_enabled=int(r.get("monitoring_enabled") or 0), priority=str(r.get("priority") or "normal"), last_synced_at=r.get("last_synced_at"), ugphone_video_count=int(r.get("ugphone_videos") or 0), latest_ugphone_upload=r.get("latest_ugphone_upload")): continue
        out.append(r)
    sk = str(p.get("sort") or "subscribers")
    keymap={"subscribers":"subscriber_count","channel_views":"channel_view_count","ugphone_videos":"ugphone_videos","competitor_videos":"competitor_videos","discovery_score":"best_discovery_score","latest_upload":"latest_upload","title":"channel_title"}
    field=keymap.get(sk,"subscriber_count")
    reverse=str(p.get("direction") or "desc").lower()!="asc"
    def key(r):
        v=r.get(field)
        if field=="channel_title": return str(v or "").casefold()
        if field=="latest_upload": return str(v or "")
        return float(v or 0)
    out.sort(key=key,reverse=reverse)
    raw_limit=p.get("result_limit", p.get("limit"))
    if raw_limit not in (None, ""):
        limit=max(1,min(5000,int(raw_limit)))
        return out[:limit]
    return out


def weekly_context(hub) -> dict[str, Any]:
    now=datetime.now(timezone.utc); cutoff=(now-timedelta(days=7)).isoformat().replace("+00:00","Z")
    with connect(hub.db_path) as conn:
        new_creators=conn.execute("SELECT COUNT(DISTINCT channel_id) FROM discovery_creator_results WHERE found_at>=?",(cutoff,)).fetchone()[0]
        top=[dict(r) for r in conn.execute("SELECT d.channel_id,d.channel_title,MAX(d.best_discovery_score) score,MAX(d.opportunity_tier) tier FROM discovery_creator_results d WHERE d.found_at>=? GROUP BY d.channel_id,d.channel_title ORDER BY score DESC LIMIT 10",(cutoff,)).fetchall()]
        workflows=[dict(r) for r in conn.execute("SELECT status,COUNT(*) count FROM creator_workflow GROUP BY status").fetchall()]
        sync=[dict(r) for r in conn.execute("SELECT status,COUNT(*) count FROM sync_runs WHERE started_at>=? GROUP BY status",(cutoff,)).fetchall()]
    health=hub.monitoring_health(page=1,page_size=1).get("counts",{})
    return {"period_days":7,"generated_at":now.isoformat(),"new_discovered_creators":new_creators,"top_discoveries":top,"workflow_counts":workflows,"sync_counts":sync,"monitoring_health":health}
