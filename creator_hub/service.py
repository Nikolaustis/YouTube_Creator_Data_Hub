from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
import uuid
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

from .classifier import suggest_label
from .contacts import scrape_public_channel_contact
from .country import best_country
from .geography import group_codes
from .scoring import pre_score
from .web_search import youtube_web_search
from .config import DEFAULT_BRANDS, DEFAULT_DB, DEFAULT_SETTINGS, load_brands, load_settings
from .db import connect, init_db, json_dump, json_load
from .util import (
    channel_id_from_ref,
    chunks,
    custom_path_from_ref,
    handle_from_ref,
    now_utc,
    parse_duration_seconds,
    parse_iso,
    username_from_ref,
    video_id_from_ref,
)
from .youtube_api import QuotaBudgetExceeded, YouTubeAPI, YouTubeAPIError


KEYWORD_SOURCE_LABELS = {"exact": "精确记录", "inferred": "历史推断", "unknown": "无法还原"}


class CreatorHub:
    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB,
        settings_path: str | Path = DEFAULT_SETTINGS,
        brands_path: str | Path = DEFAULT_BRANDS,
        unit_budget: int | None = None,
    ):
        self.db_path = str(db_path)
        self.settings = load_settings(settings_path)
        init_db(self.db_path)
        from .workspace import WorkspaceService
        self.workspace = WorkspaceService(self.db_path)
        self.workspace.bootstrap()
        self.legacy_brand_cfg = load_brands(brands_path)
        self.brand_cfg = self.workspace.classifier_config(self.legacy_brand_cfg)
        self._api: YouTubeAPI | None = None
        self.unit_budget = unit_budget
        # Cross-cutting architecture services live outside the legacy facade.
        from .services import RunService, IntelligenceService, DataContractService
        self.runs = RunService(self)
        self.intelligence = IntelligenceService(self)
        self.contracts = DataContractService(self.db_path)

    @property
    def api(self) -> YouTubeAPI:
        if self._api is None:
            self._api = YouTubeAPI(self.db_path, self.settings, unit_budget=self.unit_budget)
        return self._api


    # ---------- persistent user configuration ----------
    _SETTING_KEYS = {"secondary_metrics", "query_profile", "dashboard_preferences", "ai_config"}

    def get_setting(self, key: str, default: Any = None) -> Any:
        if key not in self._SETTING_KEYS:
            raise ValueError("unsupported setting key")
        if key == "secondary_metrics":
            return self.workspace.get_setting(key, default)
        with connect(self.db_path) as conn:
            row=conn.execute("SELECT value_json FROM app_settings WHERE key=?",(key,)).fetchone()
        return json_load(row["value_json"], default) if row else default

    def set_setting(self, key: str, value: Any) -> dict[str, Any]:
        if key not in self._SETTING_KEYS:
            raise ValueError("unsupported setting key")
        if key=="secondary_metrics":
            from .metric_config import validate_metric_config
            value=validate_metric_config(value)
            return self.workspace.set_setting(key, value)
        if key in {"query_profile","dashboard_preferences","ai_config"} and not isinstance(value,dict):
            raise ValueError("setting value must be an object")
        at=now_utc()
        with connect(self.db_path) as conn:
            conn.execute("""INSERT INTO app_settings(key,value_json,updated_at) VALUES(?,?,?)
                          ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",(key,json_dump(value),at));conn.commit()
        return {"key":key,"value":value,"updated_at":at}

    def list_settings(self) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            rows=conn.execute("SELECT key,value_json,updated_at FROM app_settings ORDER BY key").fetchall()
        return {r["key"]:{"value":json_load(r["value_json"],None),"updated_at":r["updated_at"]} for r in rows}

    # ---------- business metrics / saved workspace views ----------
    def import_business_metrics(self, source: str | Path, *, source_type: str="manual_import", capture_at: str | None=None, progress=None) -> dict[str,Any]:
        from .importers import import_business_metrics
        return import_business_metrics(self,source,source_type=source_type,capture_at=capture_at,progress=progress)

    def creator_business_metrics(self, channel_id: str) -> dict[str,Any]:
        """Return point-in-time business snapshots.

        The headline value for each metric is the latest captured snapshot, never the sum
        of historical cumulative snapshots. UgPhone backend GMV is defined as USD.
        """
        with connect(self.db_path) as conn:
            creator=conn.execute("SELECT channel_id,channel_title,handle,channel_url FROM creators WHERE channel_id=?",(channel_id,)).fetchone()
            if not creator: raise ValueError("creator not found")
            rows=[dict(r) for r in conn.execute("""SELECT id,metric_key,metric_value,currency,metric_value_usd,fx_rate_to_usd,fx_rate_date,fx_provider,fx_status,snapshot_kind,period_start,period_end,campaign,region,source_type,source_ref,import_batch,captured_at,note
                                                  FROM creator_business_metrics WHERE channel_id=?
                                                  ORDER BY captured_at DESC,id DESC""",(channel_id,)).fetchall()]
        latest_at={}
        for r in rows:
            latest_at.setdefault(r["metric_key"],r.get("captured_at") or "")
        totals={}
        for key,at in latest_at.items():
            bucket=[r for r in rows if r["metric_key"]==key and (r.get("captured_at") or "")==at]
            monetary=key in {"gmv","revenue","commission","cost"}
            if key == "gmv":
                value=sum(float(r.get("metric_value") or 0) for r in bucket)
                totals[key]={"value":value,"currency":"USD","captured_at":at,"records":len(bucket),"source_currencies":["USD"]}
            elif monetary:
                # No automatic currency conversion is performed.  Non-GMV money
                # remains source data unless it is explicitly native USD.
                usd=[r for r in bucket if str(r.get("currency") or "").upper()=="USD"]
                value=sum(float(r.get("metric_value") or 0) for r in usd) if usd and len(usd)==len(bucket) else None
                totals[key]={"value":value,"currency":"USD" if value is not None else "","captured_at":at,"records":len(bucket),"source_currencies":sorted({str(r.get("currency") or "") for r in bucket if r.get("currency")})}
            else:
                totals[key]={"value":sum(float(r.get("metric_value") or 0) for r in bucket),"currency":"","captured_at":at,"records":len(bucket),"source_currencies":[]}
        return {"creator":dict(creator),"totals":totals,"rows":rows,"snapshot_semantics":"latest_point_in_time_total"}

    def _workspace_page_key(self, page_key: str) -> str:
        wid = self.workspace.active_id() or "general"
        return f"{wid}:{str(page_key or '').strip()}"

    def saved_views(self, page_key: str) -> list[dict[str,Any]]:
        internal = self._workspace_page_key(page_key)
        with connect(self.db_path) as conn:
            rows=conn.execute("SELECT id,page_key,name,config_json,created_at,updated_at FROM saved_views WHERE page_key=? ORDER BY updated_at DESC,name",(internal,)).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["page_key"]=str(page_key or "")
            d["config"]=json_load(d["config_json"],{})
            out.append(d)
        return out

    def save_view(self, page_key: str, name: str, config: dict[str,Any]) -> dict[str,Any]:
        page_key=str(page_key or "").strip(); name=" ".join(str(name or "").split()).strip()
        if not page_key or not name: raise ValueError("page_key and name are required")
        if not isinstance(config,dict): raise ValueError("view config must be an object")
        internal=self._workspace_page_key(page_key); at=now_utc()
        with connect(self.db_path) as conn:
            conn.execute("""INSERT INTO saved_views(page_key,name,config_json,created_at,updated_at) VALUES(?,?,?,?,?)
                          ON CONFLICT(page_key,name) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at""",(internal,name,json_dump(config),at,at))
            row=conn.execute("SELECT id,page_key,name,config_json,created_at,updated_at FROM saved_views WHERE page_key=? AND name=?",(internal,name)).fetchone(); conn.commit()
        d=dict(row); d["page_key"]=page_key; d["config"]=json_load(d["config_json"],{})
        return d

    def delete_view(self, view_id: int) -> dict[str,Any]:
        prefix=(self.workspace.active_id() or "general")+":%"
        with connect(self.db_path) as conn:
            cur=conn.execute("DELETE FROM saved_views WHERE id=? AND page_key LIKE ?",(int(view_id),prefix)); conn.commit()
        return {"deleted":int(cur.rowcount or 0),"id":int(view_id)}

    # ---------- normalization / persistence ----------
    # ---------- optional AI copilot (lazy; core does not depend on an AI SDK) ----------
    def _ai(self):
        from .ai.service import AICopilot
        return AICopilot(self)

    def ai_status(self): return self._ai().status()
    def configure_ai(self, patch, api_key=None, clear_api_key=False): return self._ai().configure(patch, api_key=api_key, clear_api_key=clear_api_key)
    def ai_models(self, patch=None, api_key=None): return self._ai().available_models(patch or {}, api_key=api_key)
    def ai_test(self): return self._ai().test_connection(force=True)
    def ai_creator_brief(self, ref, force=False): return self._ai().creator_brief(ref, force=force)
    def ai_compare_creators(self, refs, force=False): return self._ai().compare_creators(refs, force=force)
    def ai_query_planner(self, query, language="en", objective="creator discovery", max_queries=12, force=False): return self._ai().query_planner(query, language=language, objective=objective, max_queries=max_queries, force=force)
    def ai_query_search(self, query, language="en", objective="creator discovery", max_queries=12, max_results=25, lookback_days=None, target_country=None, target_group=None, force=False, progress=None): return self._ai().query_search(query, language=language, objective=objective, max_queries=max_queries, max_results=max_results, lookback_days=lookback_days, target_country=target_country, target_group=target_group, force=force, progress=progress)
    def ai_ask(self, question, force=False): return self._ai().ask_hub(question, force=force)
    def ai_weekly_brief(self, force=False): return self._ai().weekly_brief(force=force)
    def ai_history(self, page=1, page_size=30): return self._ai().history(page=page, page_size=page_size)
    def ai_result_set(self, result_set_id, page=1, page_size=30, search="", conditions=None, sort="rank", direction="asc"): return self._ai().result_set_list(result_set_id,page=page,page_size=page_size,search=search,conditions=conditions or [],sort=sort,direction=direction)
    def ai_result_history(self, page=1, page_size=30, result_type="", search=""): return self._ai().result_set_history(page=page,page_size=page_size,result_type=result_type,search=search)
    def ai_result_channel_ids(self, result_set_id, search="", conditions=None): return self._ai().result_set_channel_ids(result_set_id,search=search,conditions=conditions or [])
    def ai_feedback(self, finding_id, rating, note=""): return self._ai().feedback(finding_id, rating, note)
    def run_spec(self, spec_id): return self.runs.get(int(spec_id))
    def run_specs(self, spec_type="", page=1, page_size=30): return self.runs.list(spec_type,page,page_size)
    def clone_run_spec(self, spec_id): return self.runs.clone(int(spec_id))
    def execute_run_spec(self, spec_id, progress=None): return self.runs.execute(int(spec_id),progress=progress)
    def effective_value(self, entity_type, entity_id, field_id): return self.contracts.effective(entity_type,entity_id,field_id)

    def creator_suggestions(self, query: str, *, limit: int=10) -> list[dict[str,Any]]:
        q=" ".join(str(query or "").split()).strip()
        if len(q)<1: return []
        like='%'+q.casefold()+'%'; limit=max(1,min(30,int(limit or 10)))
        with connect(self.db_path) as conn:
            rows=conn.execute("""SELECT channel_id,channel_title,handle,country_resolved,country_api,subscriber_count,thumbnail_url
                                 FROM creators
                                 WHERE lower(COALESCE(channel_title,'')) LIKE ? OR lower(COALESCE(handle,'')) LIKE ? OR lower(channel_id) LIKE ?
                                 ORDER BY CASE WHEN lower(COALESCE(channel_title,''))=lower(?) THEN 0 WHEN lower(COALESCE(handle,''))=lower(?) THEN 1 ELSE 2 END, subscriber_count DESC, channel_title
                                 LIMIT ?""",(like,like,like,q,q,limit)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _int(value: Any) -> int | None:
        try:
            return int(value) if value is not None and str(value) != "" else None
        except Exception:
            return None

    @staticmethod
    def _best_thumb(snippet: dict[str, Any]) -> str:
        thumbs = snippet.get("thumbnails") or {}
        for key in ("maxres", "standard", "high", "medium", "default"):
            if key in thumbs and thumbs[key].get("url"):
                return thumbs[key]["url"]
        return ""

    def _channel_from_item(self, item: dict[str, Any]) -> dict[str, Any]:
        sn = item.get("snippet") or {}
        st = item.get("statistics") or {}
        cd = item.get("contentDetails") or {}
        return {
            "channel_id": item.get("id") or "",
            "channel_title": sn.get("title") or "",
            "handle": sn.get("customUrl") or "",
            "channel_url": f"https://www.youtube.com/channel/{item.get('id','')}",
            "description": sn.get("description") or "",
            "country_api": sn.get("country") or "",
            "published_at": sn.get("publishedAt") or "",
            "subscriber_count": self._int(st.get("subscriberCount")),
            "channel_view_count": self._int(st.get("viewCount")),
            "channel_video_count": self._int(st.get("videoCount")),
            "hidden_subscriber_count": 1 if st.get("hiddenSubscriberCount") else 0,
            "uploads_playlist_id": ((cd.get("relatedPlaylists") or {}).get("uploads") or ""),
            "thumbnail_url": self._best_thumb(sn),
        }

    def _video_from_item(self, item: dict[str, Any], captured_at: str | None = None) -> dict[str, Any]:
        captured_at = captured_at or now_utc()
        sn = item.get("snippet") or {}
        st = item.get("statistics") or {}
        cd = item.get("contentDetails") or {}
        status = item.get("status") or {}
        vid = item.get("id") or ""
        return {
            "video_id": vid,
            "channel_id": sn.get("channelId") or "",
            "title": sn.get("title") or "",
            "description": sn.get("description") or "",
            "tags": sn.get("tags") or [],
            "published_at": sn.get("publishedAt") or "",
            "duration_iso8601": cd.get("duration") or "",
            "duration_seconds": parse_duration_seconds(cd.get("duration")),
            "live_broadcast_content": sn.get("liveBroadcastContent") or "none",
            "category_id": sn.get("categoryId") or "",
            "default_language": sn.get("defaultLanguage") or sn.get("defaultAudioLanguage") or "",
            "privacy_status": status.get("privacyStatus") or "",
            "thumbnail_url": self._best_thumb(sn),
            "current_views": self._int(st.get("viewCount")),
            "current_likes": self._int(st.get("likeCount")),
            "current_comments": self._int(st.get("commentCount")),
            "last_metric_at": captured_at,
            "discovered_at": captured_at,
        }

    def upsert_creator(self, row: dict[str, Any], *, monitoring: bool | None = None, priority: str | None = None, source: str | None = None, snapshot: bool = True) -> None:
        captured_at = now_utc()
        with connect(self.db_path) as conn:
            old = conn.execute("SELECT monitoring_enabled, priority, created_at, discovered_at, source, last_synced_at FROM creators WHERE channel_id=?", (row["channel_id"],)).fetchone()
            mon = int(monitoring) if monitoring is not None else (int(old["monitoring_enabled"]) if old else 0)
            pr = priority or (old["priority"] if old else "normal")
            created = old["created_at"] if old else captured_at
            discovered = old["discovered_at"] if old and old["discovered_at"] else captured_at
            src = source or (old["source"] if old else "youtube")
            last_synced = old["last_synced_at"] if old else None
            conn.execute(
                """INSERT INTO creators(channel_id, channel_title, handle, channel_url, description, country_api, published_at,
                subscriber_count, channel_view_count, channel_video_count, hidden_subscriber_count, uploads_playlist_id,
                thumbnail_url, monitoring_enabled, priority, source, discovered_at, created_at, last_synced_at, channel_data_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(channel_id) DO UPDATE SET
                  channel_title=excluded.channel_title, handle=excluded.handle, channel_url=excluded.channel_url,
                  description=excluded.description, country_api=excluded.country_api, published_at=excluded.published_at,
                  subscriber_count=excluded.subscriber_count, channel_view_count=excluded.channel_view_count,
                  channel_video_count=excluded.channel_video_count, hidden_subscriber_count=excluded.hidden_subscriber_count,
                  uploads_playlist_id=excluded.uploads_playlist_id, thumbnail_url=excluded.thumbnail_url,
                  monitoring_enabled=excluded.monitoring_enabled, priority=excluded.priority, source=excluded.source,
                  channel_data_at=excluded.channel_data_at""",
                (
                    row["channel_id"], row.get("channel_title"), row.get("handle"), row.get("channel_url"), row.get("description"),
                    row.get("country_api"), row.get("published_at"), row.get("subscriber_count"), row.get("channel_view_count"),
                    row.get("channel_video_count"), row.get("hidden_subscriber_count"), row.get("uploads_playlist_id"),
                    row.get("thumbnail_url"), mon, pr, src, discovered, created, last_synced, captured_at,
                ),
            )
            if row.get("country_api"):
                conn.execute("UPDATE creators SET country_resolved=COALESCE(NULLIF(country_resolved,''),?), country_source=COALESCE(NULLIF(country_source,''),'youtube_api'), country_evidence_json=CASE WHEN country_evidence_json IS NULL OR country_evidence_json='' OR country_evidence_json='[]' THEN ? ELSE country_evidence_json END WHERE channel_id=?",
                             (row.get("country_api"), json_dump([{"country":row.get("country_api"),"source":"youtube_api"}]), row["channel_id"]))
            if snapshot:
                conn.execute(
                    "INSERT OR IGNORE INTO creator_snapshots(channel_id,captured_at,subscriber_count,channel_view_count,channel_video_count,hidden_subscriber_count) VALUES(?,?,?,?,?,?)",
                    (row["channel_id"], captured_at, row.get("subscriber_count"), row.get("channel_view_count"), row.get("channel_video_count"), row.get("hidden_subscriber_count")),
                )
            conn.commit()

    def upsert_video(self, row: dict[str, Any], *, snapshot: bool = True, suggestion: dict[str, Any] | None = None) -> None:
        captured_at = row.get("last_metric_at") or now_utc()
        with connect(self.db_path) as conn:
            old = conn.execute("SELECT discovered_at FROM videos WHERE video_id=?", (row["video_id"],)).fetchone()
            discovered = old["discovered_at"] if old else row.get("discovered_at") or captured_at
            conn.execute(
                """INSERT INTO videos(video_id,channel_id,title,description,tags_json,published_at,duration_iso8601,duration_seconds,
                live_broadcast_content,category_id,default_language,privacy_status,thumbnail_url,current_views,current_likes,current_comments,last_metric_at,discovered_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(video_id) DO UPDATE SET channel_id=excluded.channel_id,title=excluded.title,description=excluded.description,
                tags_json=excluded.tags_json,published_at=excluded.published_at,duration_iso8601=excluded.duration_iso8601,
                duration_seconds=excluded.duration_seconds,live_broadcast_content=excluded.live_broadcast_content,
                category_id=excluded.category_id,default_language=excluded.default_language,privacy_status=excluded.privacy_status,
                thumbnail_url=excluded.thumbnail_url,current_views=excluded.current_views,current_likes=excluded.current_likes,
                current_comments=excluded.current_comments,last_metric_at=excluded.last_metric_at""",
                (row["video_id"], row["channel_id"], row.get("title"), row.get("description"), json_dump(row.get("tags") or []),
                 row.get("published_at"), row.get("duration_iso8601"), row.get("duration_seconds"), row.get("live_broadcast_content"),
                 row.get("category_id"), row.get("default_language"), row.get("privacy_status"), row.get("thumbnail_url"),
                 row.get("current_views"), row.get("current_likes"), row.get("current_comments"), captured_at, discovered),
            )
            if snapshot:
                conn.execute(
                    "INSERT OR IGNORE INTO video_snapshots(video_id,captured_at,views,likes,comments) VALUES(?,?,?,?,?)",
                    (row["video_id"], captured_at, row.get("current_views"), row.get("current_likes"), row.get("current_comments")),
                )
            if suggestion is None:
                suggestion = suggest_label({**row, "tags": row.get("tags") or []}, self.brand_cfg)
            conn.execute(
                """INSERT INTO label_suggestions(video_id,suggested_role,brands_json,confidence,evidence_json,generated_at,rule_version)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET suggested_role=excluded.suggested_role,
                brands_json=excluded.brands_json,confidence=excluded.confidence,evidence_json=excluded.evidence_json,
                generated_at=excluded.generated_at,rule_version=excluded.rule_version""",
                (row["video_id"], suggestion["suggested_role"], json_dump(suggestion.get("brands") or []), suggestion["confidence"],
                 json_dump(suggestion.get("evidence") or []), suggestion["generated_at"], suggestion["rule_version"]),
            )
            conn.execute("UPDATE creators SET video_metrics_at=?, classification_data_at=? WHERE channel_id=?",
                         (captured_at, suggestion.get("generated_at") or captured_at, row["channel_id"]))
            conn.commit()

    # ---------- resolving ----------
    def resolve_channel_id(self, ref: str) -> str:
        if cid := channel_id_from_ref(ref):
            return cid
        if handle := handle_from_ref(ref):
            data = self.api.call("channels", part="id", forHandle=handle.lstrip("@"), maxResults=1)
            items = data.get("items") or []
            if items:
                return items[0]["id"]
            raise YouTubeAPIError(f"无法解析 handle: {handle}")
        if username := username_from_ref(ref):
            data = self.api.call("channels", part="id", forUsername=username, maxResults=1)
            items = data.get("items") or []
            if items:
                return items[0]["id"]
        if vid := video_id_from_ref(ref):
            data = self.api.call("videos", part="snippet", id=vid)
            items = data.get("items") or []
            if items:
                return items[0]["snippet"]["channelId"]
        # Last resort for legacy /c/ or custom channel URLs: parse public HTML for stable channel ID.
        if ref.startswith("http") and "youtube.com" in ref:
            try:
                req = urllib.request.Request(ref, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    text = resp.read().decode("utf-8", errors="ignore")
                for pattern in (r'"channelId":"(UC[A-Za-z0-9_-]{22})"', r'"externalId":"(UC[A-Za-z0-9_-]{22})"'):
                    m = re.search(pattern, text)
                    if m:
                        return m.group(1)
            except Exception:
                pass
        raise YouTubeAPIError("无法安全解析频道。请提供 Channel ID、/channel/ URL、@handle、/user/ URL 或任一公开视频 URL。")

    def fetch_channel(self, channel_id: str) -> dict[str, Any]:
        data = self.api.call("channels", part="snippet,statistics,contentDetails", id=channel_id, maxResults=1)
        items = data.get("items") or []
        if not items:
            raise YouTubeAPIError(f"未找到频道：{channel_id}")
        return self._channel_from_item(items[0])

    def ensure_creator(self, ref: str, *, monitoring: bool = True, priority: str = "normal", source: str = "manual") -> dict[str, Any]:
        cid = self.resolve_channel_id(ref)
        row = self.fetch_channel(cid)
        self.upsert_creator(row, monitoring=monitoring, priority=priority, source=source)
        if source.startswith("discovery"):
            with connect(self.db_path) as conn:
                d=conn.execute("SELECT * FROM discovery_hits WHERE channel_id=? ORDER BY id DESC LIMIT 1",(cid,)).fetchone()
                if d:
                    conn.execute("""UPDATE creators SET discovery_pre_score=?,discovery_opportunity_tier=?,discovery_score_updated_at=?,
                                 public_email=COALESCE(NULLIF(public_email,''),?),social_links_json=CASE WHEN social_links_json='[]' THEN COALESCE(?,social_links_json) ELSE social_links_json END,
                                 website_url=COALESCE(NULLIF(website_url,''),?),contactability_score=COALESCE(contactability_score,?),contact_status=COALESCE(contact_status,?),
                                 country_resolved=COALESCE(NULLIF(country_resolved,''),?),country_source=COALESCE(NULLIF(country_source,''),?) WHERE channel_id=?""",
                                 (d["pre_score"],d["opportunity_tier"],now_utc(),d["public_email"],d["social_links_json"],d["website_url"],d["contactability_score"],d["contact_status"],d["country_resolved"],d["country_source"],cid))
                    conn.commit()
        if source.startswith("discovery") or source=="batch_add":
            try:
                self.set_creator_workflow(cid,"added",actor="system-add")
            except Exception:
                pass
        return row

    # ---------- discovery ----------
    def _hydrate_discovery_metrics(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich discovery hits without adding creators/videos to the main library."""
        by_video = {c.get("video_id"): c for c in candidates if c.get("video_id")}
        video_ids = list(by_video)
        for batch in chunks(video_ids, 50):
            data = self.api.call("videos", part="snippet,statistics,contentDetails,status", id=",".join(batch), maxResults=50)
            for item in data.get("items") or []:
                sn = item.get("snippet") or {}; st = item.get("statistics") or {}
                c = by_video.get(item.get("id"))
                if not c: continue
                c.update({
                    "title": sn.get("title") or c.get("title") or "",
                    "published_at": sn.get("publishedAt") or c.get("published_at") or "",
                    "channel_id": sn.get("channelId") or c.get("channel_id") or "",
                    "channel_title": sn.get("channelTitle") or c.get("channel_title") or "",
                    "views": self._int(st.get("viewCount")) or 0,
                    "likes": self._int(st.get("likeCount")) or 0,
                    "comments": self._int(st.get("commentCount")) or 0,
                    "video_language": sn.get("defaultLanguage") or sn.get("defaultAudioLanguage") or "",
                    "video_description": sn.get("description") or "",
                    "video_tags": sn.get("tags") or [],
                })
        channel_ids = list(dict.fromkeys(c.get("channel_id") for c in candidates if c.get("channel_id")))
        channel_map: dict[str, dict[str, Any]] = {}
        for batch in chunks(channel_ids, 50):
            data = self.api.call("channels", part="snippet,statistics,contentDetails", id=",".join(batch), maxResults=50)
            for item in data.get("items") or []:
                channel_map[item.get("id") or ""] = self._channel_from_item(item)
        for c in candidates:
            ch = channel_map.get(c.get("channel_id") or "", {})
            c["channel_title"] = ch.get("channel_title") or c.get("channel_title") or ""
            c["channel_url"] = ch.get("channel_url") or c.get("channel_url") or (f"https://www.youtube.com/channel/{c.get('channel_id')}" if c.get("channel_id") else "")
            c["subscribers"] = ch.get("subscriber_count") or 0
            c["channel_description"] = ch.get("description") or ""
            c["country_api"] = ch.get("country_api") or ""
            c["thumbnail_url"] = ch.get("thumbnail_url") or ""
            score = pre_score(views=c.get("views") or 0, likes=c.get("likes") or 0, comments=c.get("comments") or 0,
                              subscribers=c.get("subscribers") or 0, published_at=c.get("published_at"))
            c.update(score)
        return candidates

    def discover(self, query: str, *, max_results: int = 100, region: str | None = None, language: str | None = None,
                 add: bool = False, search_source: str = "web", target_country: str | None = None,
                 target_group: str | None = None, lookback_days: int | None = None,
                 from_date: str | None = None, to_date: str | None = None,
                 run_id: str | None = None, found_at_override: str | None = None) -> dict[str, Any]:
        """Search related videos first, then resolve the creators that published them.

        Web search is preferred (related-video to creator discovery) and does not spend search.list quota. API search remains a fallback.
        Discovery results are persisted in discovery_hits but do not enter the creator library unless add=True.
        """
        max_results = max(1, min(int(max_results), 500))
        found_at = found_at_override or now_utc(); candidates: list[dict[str, Any]] = []
        source = search_source.lower().replace("-", "_")
        if source in {"web", "youtube_web_search"}:
            try:
                raw = youtube_web_search(query, max_results=max_results, timeout=int(self.settings["api"].get("timeout_seconds", 30)), region=region, language=language)
                for x in raw:
                    candidates.append({
                        "query": query, "source": "youtube_web_search", "rank": x["raw_search_rank"],
                        "video_id": x["video_id"], "channel_id": x.get("channel_id") or "",
                        "channel_title": x.get("channel_title") or "", "channel_url": x.get("channel_url") or "",
                        "title": x.get("title") or "", "published_at": "", "found_at": found_at,
                        "raw_json": json_dump(x),
                    })
            except Exception:
                source = "api"
        if source in {"api", "youtube_api_search"}:
            token = None; rank = 0
            while len(candidates) < max_results:
                size = min(50, max_results-len(candidates))
                kwargs = {"part":"snippet","type":"video","q":query,"maxResults":size,"pageToken":token,
                          "regionCode":region,"relevanceLanguage":language}
                from datetime import datetime, timezone, timedelta
                if from_date:
                    start=parse_iso(from_date)
                    if start is None:
                        start=datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
                    kwargs["publishedAfter"]=start.isoformat().replace("+00:00","Z")
                elif lookback_days:
                    kwargs["publishedAfter"]=(datetime.now(timezone.utc)-timedelta(days=int(lookback_days))).isoformat().replace("+00:00","Z")
                if to_date:
                    end=parse_iso(to_date)
                    if end is None:
                        end=datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
                    if len(str(to_date))<=10:
                        end=end+timedelta(days=1)
                    kwargs["publishedBefore"]=end.isoformat().replace("+00:00","Z")
                data=self.api.call("search", **kwargs)
                items=data.get("items") or []
                if not items: break
                for item in items:
                    rank += 1; sn=item.get("snippet") or {}; vid=((item.get("id") or {}).get("videoId") or "")
                    candidates.append({"query":query,"source":"youtube_api_search","rank":rank,"video_id":vid,
                        "channel_id":sn.get("channelId") or "","channel_title":sn.get("channelTitle") or "",
                        "channel_url":"","title":sn.get("title") or "","published_at":sn.get("publishedAt") or "",
                        "found_at":found_at,"raw_json":json_dump(item)})
                token=data.get("nextPageToken")
                if not token: break
        candidates=self._hydrate_discovery_metrics(candidates[:max_results])
        # Apply the same date window to web-search results after API hydration.
        from datetime import datetime, timezone, timedelta
        start=None; end=None
        if from_date:
            start=parse_iso(from_date)
            if start is None:start=datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
        elif lookback_days:
            start=datetime.now(timezone.utc)-timedelta(days=int(lookback_days))
        if to_date:
            end=parse_iso(to_date)
            if end is None:end=datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
            if len(str(to_date))<=10:end=end+timedelta(days=1)
        if start or end:
            filtered=[]
            for c in candidates:
                pub=parse_iso(c.get("published_at"))
                if pub is None: continue
                if start and pub < start: continue
                if end and pub >= end: continue
                filtered.append(c)
            candidates=filtered
        # Country evidence hierarchy: About-page > API > metadata keyword > language hint.
        for c in candidates:
            resolved=best_country(api_country=c.get("country_api"), metadata_text=" ".join([c.get("channel_title") or "",c.get("channel_description") or "",c.get("title") or ""]),
                                  language=c.get("video_language") or "", target_country=target_country)
            c["country_resolved"]=resolved["country"]; c["country_source"]=resolved["source"]
        allowed=group_codes(target_group) if target_group else set()
        if target_country:
            exact=target_country.upper(); candidates=[c for c in candidates if (c.get("country_resolved") or c.get("country_api") or "").upper()==exact]
        elif allowed:
            candidates=[c for c in candidates if (c.get("country_resolved") or c.get("country_api") or "").upper() in allowed]
        with connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO discovery_hits(run_id,query,source,rank,video_id,channel_id,channel_title,channel_url,title,published_at,
                   views,likes,comments,subscribers,country_resolved,country_source,pre_score,opportunity_tier,engagement_rate,comment_rate,
                   view_sub_ratio,relative_velocity,found_at,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(run_id,c["query"],c["source"],c.get("rank"),c.get("video_id"),c.get("channel_id"),c.get("channel_title"),c.get("channel_url"),c.get("title"),c.get("published_at"),
                  c.get("views"),c.get("likes"),c.get("comments"),c.get("subscribers"),c.get("country_resolved"),c.get("country_source"),c.get("pre_score"),c.get("opportunity_tier"),
                  c.get("engagement_rate"),c.get("comment_rate"),c.get("view_sub_ratio"),c.get("relative_velocity"),c["found_at"],c.get("raw_json")) for c in candidates]
            ); conn.commit()
        added=0
        if add:
            seen=set()
            for c in candidates:
                cid=c.get("channel_id")
                if not cid or cid in seen: continue
                seen.add(cid)
                try:
                    row=self.fetch_channel(cid); self.upsert_creator(row, monitoring=True, source="discovery"); added += 1
                    # Persist the discovery-hit video as the first local video fact.
                    self.hydrate_videos([c.get("video_id")])
                except Exception:
                    pass
        # Return per-creator best hit for the interactive Dashboard.
        best: dict[str, dict[str, Any]] = {}
        for c in candidates:
            cid=c.get("channel_id") or c.get("channel_title") or c.get("video_id")
            old=best.get(cid)
            if old is None or (c.get("pre_score") or 0) > (old.get("pre_score") or 0): best[cid]=c
        result=sorted(best.values(), key=lambda x: (x.get("pre_score") or 0, -(x.get("rank") or 999999)), reverse=True)
        return {"query":query,"hits":len(candidates),"unique_creators":len(best),"added_to_monitoring":added,"found_at":found_at,"results":result}

    def _refresh_discovery_summary(self, channel_ids: Iterable[str] | None = None) -> None:
        ids=list(dict.fromkeys(str(x) for x in (channel_ids or []) if x))
        where="";params=[]
        if ids:
            where=f"WHERE r.channel_id IN ({','.join('?' for _ in ids)})";params=ids
        with connect(self.db_path) as conn:
            rows=conn.execute(f"""SELECT r.channel_id,r.run_id,r.found_at,r.hit_video_count,r.best_discovery_score,dr.base_query
                                FROM discovery_creator_results r LEFT JOIN discovery_runs dr ON dr.run_id=r.run_id
                                {where} ORDER BY r.channel_id,r.found_at,r.id""",tuple(params)).fetchall()
            agg={}
            for r in rows:
                cid=r['channel_id'];a=agg.setdefault(cid,{'first':r['found_at'] or '','last':r['found_at'] or '','runs':set(),'hits':0,'best':None,'query':''})
                at=r['found_at'] or ''
                if at and (not a['first'] or at<a['first']):a['first']=at
                if at and (not a['last'] or at>=a['last']):a['last']=at;a['query']=r['base_query'] or ''
                if r['run_id']:a['runs'].add(r['run_id'])
                a['hits']+=int(r['hit_video_count'] or 0)
                sc=r['best_discovery_score']
                if sc is not None and (a['best'] is None or float(sc)>float(a['best'])):a['best']=float(sc)
            at=now_utc()
            for cid,a in agg.items():
                conn.execute("""INSERT INTO creator_discovery_summary(channel_id,first_seen_at,last_seen_at,discovery_run_count,hit_video_count_total,best_discovery_score,last_base_query,updated_at)
                              VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET first_seen_at=excluded.first_seen_at,last_seen_at=excluded.last_seen_at,discovery_run_count=excluded.discovery_run_count,hit_video_count_total=excluded.hit_video_count_total,best_discovery_score=excluded.best_discovery_score,last_base_query=excluded.last_base_query,updated_at=excluded.updated_at""",
                             (cid,a['first'],a['last'],len(a['runs']),a['hits'],a['best'],a['query'],at))
            conn.commit()

    def discover_expanded(self, base_query: str, queries: list[str] | None = None, *, max_results: int = 50,
                          region: str | None = None, language: str | None = None, search_source: str = "web",
                          target_country: str | None = None, target_group: str | None = None,
                          lookback_days: int | None = None, from_date: str | None = None,
                          to_date: str | None = None, max_queries: int = 80,
                          query_language: str | None = None, progress=None) -> dict[str, Any]:
        """Run one discovery batch and persist both creator-level and video-level evidence.

        v1.3+ gives every search a run_id.  Each exact video hit remains in discovery_hits,
        while the de-duplicated per-creator outcome is saved in discovery_creator_results.
        """
        base=(base_query or "").strip()
        if not base:
            raise ValueError("搜索关键词不能为空")
        raw=[base]+list(queries or [])
        normalized=[]; seen=set()
        for q in raw:
            q=" ".join(str(q or "").split()).strip(); k=q.casefold()
            if not q or k in seen: continue
            seen.add(k); normalized.append(q)
            if len(normalized)>=max(1,int(max_queries)): break
        run_id=uuid.uuid4().hex
        found_at=now_utc()
        with connect(self.db_path) as conn:
            conn.execute("""INSERT INTO discovery_runs(run_id,base_query,search_source,search_language,query_language,queries_requested_json,target_group,target_country,region,lookback_days,from_date,to_date,max_results,started_at,status)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (run_id,base,search_source,language or '',query_language or language or '',json_dump(normalized),target_group or '',target_country or '',region or '',lookback_days,from_date or '',to_date or '',int(max_results),found_at,'running'))
            conn.commit()
        merged: dict[str,dict[str,Any]]={}; total_hits=0; executed=[]; errors=[]
        if progress: progress(stage="YouTube 搜索",message=f"准备执行 {len(normalized)} 个 Query",current=0,total=len(normalized))
        for qi,q in enumerate(normalized,1):
            try:
                r=self.discover(q,max_results=max_results,region=region,language=language,add=False,
                    search_source=search_source,target_country=target_country,target_group=target_group,
                    lookback_days=lookback_days,from_date=from_date,to_date=to_date,
                    run_id=run_id,found_at_override=found_at)
            except Exception as e:
                errors.append({"query":q,"error":f"{type(e).__name__}: {e}"})
                if "quota" in str(e).lower() or "budget" in str(e).lower(): break
                continue
            executed.append(q); total_hits+=int(r.get("hits") or 0)
            if progress: progress(stage="YouTube 搜索",message=f"已执行 {qi}/{len(normalized)} 个 Query · 命中视频 {total_hits} 条 · 去重博主 {len(merged)} 个",current=qi,total=len(normalized),hits=total_hits)
            for c0 in r.get("results") or []:
                c=dict(c0); cid=c.get("channel_id") or c.get("channel_title") or c.get("video_id")
                if not cid: continue
                old=merged.get(cid); matched=list((old or {}).get("matched_queries") or [])
                if q not in matched: matched.append(q)
                if old is None or float(c.get("pre_score") or 0)>float(old.get("pre_score") or 0):
                    c["matched_queries"]=matched; c["query_coverage"]=len(matched); merged[cid]=c
                else:
                    old["matched_queries"]=matched; old["query_coverage"]=len(matched)
        # Derive exact hit counts from the persisted video-hit layer for this run.
        with connect(self.db_path) as conn:
            hit_counts={r['channel_id']:int(r['n'] or 0) for r in conn.execute("SELECT channel_id,COUNT(DISTINCT video_id) n FROM discovery_hits WHERE run_id=? GROUP BY channel_id",(run_id,)).fetchall()}
            payload=[]
            for cid,c in merged.items():
                payload.append((run_id,cid,c.get('channel_title'),c.get('channel_url'),c.get('subscribers'),c.get('country_resolved'),c.get('country_source'),c.get('video_id'),c.get('title'),c.get('views'),c.get('pre_score'),c.get('opportunity_tier'),int(c.get('query_coverage') or 0),json_dump(c.get('matched_queries') or []),int(hit_counts.get(cid,0)),found_at))
            if payload:
                conn.executemany("""INSERT OR REPLACE INTO discovery_creator_results(run_id,channel_id,channel_title,channel_url,subscribers,country_resolved,country_source,best_video_id,best_video_title,best_video_views,best_discovery_score,opportunity_tier,query_coverage,matched_queries_json,hit_video_count,found_at)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",payload)
            status='partial' if errors else 'complete'
            conn.execute("""UPDATE discovery_runs SET queries_executed_json=?,finished_at=?,status=?,hits=?,unique_creators=?,errors_json=? WHERE run_id=?""",
                         (json_dump(executed),now_utc(),status,int(total_hits),len(merged),json_dump(errors),run_id))
            conn.commit()
        self._refresh_discovery_summary(merged.keys())
        workflows=self.creator_workflow_map(merged.keys())
        with connect(self.db_path) as conn:
            summaries={r['channel_id']:dict(r) for r in conn.execute(f"SELECT * FROM creator_discovery_summary WHERE channel_id IN ({','.join('?' for _ in merged)})",tuple(merged.keys())).fetchall()} if merged else {}
        for cid,c in merged.items():
            wf=workflows.get(cid) or {};sm=summaries.get(cid) or {}
            c['workflow_status']=wf.get('status') or 'unreviewed';c['workflow_label']=self._workflow_label(c['workflow_status'])
            c['discovery_run_count']=int(sm.get('discovery_run_count') or 1);c['first_seen_at']=sm.get('first_seen_at') or found_at;c['last_seen_at']=sm.get('last_seen_at') or found_at
            c['discovery_freshness']='first' if c['discovery_run_count']<=1 else 'repeat';c['hidden_by_default']=c['workflow_status']=='excluded'
        result=sorted(merged.values(),key=lambda x:(float(x.get('pre_score') or 0),int(x.get('query_coverage') or 0)),reverse=True)
        if progress: progress(stage="保存发现结果",message=f"搜索完成 · {len(executed)} 个 Query · {total_hits} 条视频 · {len(merged)} 个博主",current=len(normalized),total=len(normalized),percent=100)
        return {"run_id":run_id,"query":base,"queries_requested":normalized,"queries_executed":executed,"query_count":len(executed),
                "hits":total_hits,"unique_creators":len(merged),"added_to_monitoring":0,"found_at":found_at,
                "errors":errors,"results":result}

    def capture_window(self, ref: str, *, days: int | None = None, from_date: str | None = None, to_date: str | None = None, full_history: bool = False,
                       priority: str = "normal") -> dict[str, Any]:
        """Add a creator to the library and persist videos from the selected time window."""
        from datetime import datetime, timezone, timedelta
        row=self.ensure_creator(ref, monitoring=True, priority=priority, source="discovery_capture")
        cid=row["channel_id"]
        if full_history:
            ids,_=self._playlist_video_ids(cid, full=True)
        else:
            if from_date:
                cutoff=parse_iso(from_date)
                if cutoff is None: cutoff=datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
            else:
                cutoff=datetime.now(timezone.utc)-timedelta(days=int(days or 30))
            upper=None
            if to_date:
                upper=parse_iso(to_date)
                if upper is None: upper=datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
                if len(str(to_date))<=10: upper=upper+timedelta(days=1)
            ids=self._playlist_video_ids_between(cid, cutoff, upper)
        processed=self.hydrate_videos(ids)
        at=now_utc();cur=parse_iso(at);hours=self._sync_due_hours(priority or "normal","incremental");nxt=(cur+timedelta(hours=hours)).isoformat().replace("+00:00","Z") if cur else None
        with connect(self.db_path) as conn:
            conn.execute("UPDATE creators SET last_synced_at=?,last_sync_attempt_at=?,last_sync_status='complete',last_sync_error=NULL,sync_error_type=NULL,consecutive_sync_failures=0,next_retry_at=NULL,next_sync_at=?,sync_suspended=0,availability_status='available',availability_reason=NULL,availability_source='youtube_api',availability_checked_at=?,availability_failures=0 WHERE channel_id=?",(at,at,nxt,at,cid)); conn.commit()
        return {"channel_id":cid,"videos_processed":processed,"days":days,"from_date":from_date,"to_date":to_date,"full_history":full_history}

    def _playlist_video_ids_between(self, channel_id: str, cutoff, upper=None) -> list[str]:
        with connect(self.db_path) as conn:
            cr=conn.execute("SELECT uploads_playlist_id FROM creators WHERE channel_id=?",(channel_id,)).fetchone()
        if not cr or not cr[0]:
            row=self.fetch_channel(channel_id); self.upsert_creator(row); playlist=row["uploads_playlist_id"]
        else: playlist=cr[0]
        cfg=self.settings["collection"]; out=[]; token=None
        for _ in range(int(cfg["max_playlist_pages_full"])):
            data=self.api.call("playlistItems",part="contentDetails,snippet",playlistId=playlist,maxResults=50,pageToken=token)
            items=data.get("items") or []
            if not items: break
            stop=False
            for item in items:
                sn=item.get("snippet") or {}; published=parse_iso(sn.get("publishedAt"))
                if published and published < cutoff:
                    stop=True; continue
                if published and upper and published >= upper:
                    continue
                vid=((item.get("contentDetails") or {}).get("videoId") or ((sn.get("resourceId") or {}).get("videoId")) or "")
                if vid: out.append(vid)
            if stop or len(out)>=int(cfg["max_videos_per_creator"]): break
            token=data.get("nextPageToken")
            if not token: break
        return list(dict.fromkeys(out[:int(cfg["max_videos_per_creator"])]))

    def scrape_contact(self, ref: str) -> dict[str, Any]:
        cid=self.resolve_channel_id(ref)
        with connect(self.db_path) as conn:
            cr=conn.execute("SELECT channel_url,country_api FROM creators WHERE channel_id=?",(cid,)).fetchone()
            dh=conn.execute("SELECT channel_url,country_resolved FROM discovery_hits WHERE channel_id=? ORDER BY id DESC LIMIT 1",(cid,)).fetchone()
        channel_url=(cr["channel_url"] if cr and cr["channel_url"] else (dh["channel_url"] if dh and dh["channel_url"] else f"https://www.youtube.com/channel/{cid}"))
        result=scrape_public_channel_contact(channel_url, timeout=int(self.settings["api"].get("timeout_seconds",30)))
        api_country=cr["country_api"] if cr else None
        resolved=best_country(api_country=api_country,about_country=result.get("about_page_country"))
        with connect(self.db_path) as conn:
            if cr:
                conn.execute("""UPDATE creators SET public_email=?,social_links_json=?,website_url=?,contactability_score=?,contact_status=?,contact_scraped_at=?,
                             country_resolved=?,country_source=?,country_evidence_json=? WHERE channel_id=?""",
                             (result.get("public_email"),json_dump(result.get("social_links") or []),result.get("website_url"),result.get("contactability_score"),result.get("contact_status"),
                              result.get("scraped_at"),resolved["country"],resolved["source"],json_dump(resolved["evidence"]),cid))
            conn.execute("""UPDATE discovery_hits SET public_email=?,social_links_json=?,website_url=?,contactability_score=?,contact_status=?,
                         country_resolved=CASE WHEN ?<>'' THEN ? ELSE country_resolved END,
                         country_source=CASE WHEN ?<>'' THEN ? ELSE country_source END WHERE channel_id=?""",
                         (result.get("public_email"),json_dump(result.get("social_links") or []),result.get("website_url"),result.get("contactability_score"),result.get("contact_status"),
                          resolved["country"],resolved["country"],resolved["country"],resolved["source"],cid))
            conn.commit()
        return {"channel_id":cid,**result,"country_resolved":resolved["country"],"country_source":resolved["source"]}


    # ---------- sync ----------
    def _playlist_video_ids(self, channel_id: str, *, full: bool, max_pages: int | None = None) -> tuple[list[str], bool]:
        with connect(self.db_path) as conn:
            cr = conn.execute("SELECT uploads_playlist_id FROM creators WHERE channel_id=?", (channel_id,)).fetchone()
            known = {r[0] for r in conn.execute("SELECT video_id FROM videos WHERE channel_id=?", (channel_id,)).fetchall()}
        if not cr or not cr[0]:
            row = self.fetch_channel(channel_id)
            self.upsert_creator(row)
            playlist = row["uploads_playlist_id"]
        else:
            playlist = cr[0]
        cfg = self.settings["collection"]
        page_cap = max_pages or (int(cfg["max_playlist_pages_full"]) if full else int(cfg["incremental_max_pages"]))
        if not full and not known:
            # Incremental mode on a brand-new creator is intentionally shallow; use full-history explicitly for complete backfill.
            page_cap = min(page_cap, 1)
        max_videos = int(cfg["max_videos_per_creator"])
        out: list[str] = []
        token = None
        reached_known = False
        for _ in range(page_cap):
            data = self.api.call("playlistItems", part="contentDetails,snippet", playlistId=playlist, maxResults=50, pageToken=token)
            items = data.get("items") or []
            if not items:
                break
            page_ids: list[str] = []
            for item in items:
                vid = ((item.get("contentDetails") or {}).get("videoId") or ((item.get("snippet") or {}).get("resourceId") or {}).get("videoId") or "")
                if vid:
                    page_ids.append(vid)
            if not full and known:
                for vid in page_ids:
                    if vid in known:
                        reached_known = True
                        break
                    out.append(vid)
                if reached_known:
                    break
            else:
                out.extend(page_ids)
            if len(out) >= max_videos:
                out = out[:max_videos]
                break
            token = data.get("nextPageToken")
            if not token:
                break
        return list(dict.fromkeys(out)), reached_known

    def hydrate_videos(self, video_ids: Iterable[str]) -> int:
        ids = list(dict.fromkeys(v for v in video_ids if v))
        count = 0
        for batch in chunks(ids, int(self.settings["collection"]["video_batch_size"])):
            data = self.api.call("videos", part="snippet,statistics,contentDetails,status", id=",".join(batch), maxResults=50)
            for item in data.get("items") or []:
                self.upsert_video(self._video_from_item(item))
                count += 1
        return count

    def sync_creator(self, ref: str, *, mode: str = "incremental", metric_days: int | None = None, all_videos: bool = False, priority: str | None = None, sync_run_id: int | None = None) -> dict[str, Any]:
        mode = mode.replace("_", "-")
        cid = self.resolve_channel_id(ref)
        started=now_utc();attempt_id=None
        with connect(self.db_path) as conn:
            old = conn.execute("SELECT monitoring_enabled,priority FROM creators WHERE channel_id=?", (cid,)).fetchone()
            if old:
                attempt_id=conn.execute("INSERT INTO creator_sync_attempts(sync_run_id,channel_id,mode,started_at,status) VALUES(?,?,?,?,?)",(sync_run_id,cid,mode,started,"running")).lastrowid
                conn.execute("UPDATE creators SET last_sync_attempt_at=?,last_sync_status='running' WHERE channel_id=?",(started,cid));conn.commit()
        pr=priority or (old["priority"] if old else "normal")
        try:
            row = self.fetch_channel(cid)
            self.upsert_creator(row, monitoring=bool(old["monitoring_enabled"]) if old else True, priority=pr, source="sync")
            if attempt_id is None:
                with connect(self.db_path) as conn:
                    attempt_id=conn.execute("INSERT INTO creator_sync_attempts(sync_run_id,channel_id,mode,started_at,status) VALUES(?,?,?,?,?)",(sync_run_id,cid,mode,started,"running")).lastrowid
                    conn.execute("UPDATE creators SET last_sync_attempt_at=?,last_sync_status='running' WHERE channel_id=?",(started,cid));conn.commit()
            processed = 0
            if mode in {"full-history", "full"}:
                ids, _ = self._playlist_video_ids(cid, full=True)
                processed += self.hydrate_videos(ids)
            elif mode in {"incremental", "new"}:
                ids, _ = self._playlist_video_ids(cid, full=False)
                processed += self.hydrate_videos(ids)
                processed += self.refresh_metrics(cid, days=metric_days, all_videos=False)
            elif mode in {"metrics-only", "metrics"}:
                processed += self.refresh_metrics(cid, days=metric_days, all_videos=all_videos)
            elif mode in {"channel-only", "channel"}:
                pass
            else:
                raise ValueError(f"未知同步模式：{mode}")
            self._record_sync_success(cid,mode=mode,attempt_id=attempt_id,videos=processed,priority=pr)
            return {"channel_id": cid, "mode": mode, "videos_processed": processed, "sync_status":"complete"}
        except Exception as e:
            state=self._record_sync_failure(cid,mode=mode,attempt_id=attempt_id,exc=e) if attempt_id is not None else {}
            try: setattr(e,"creator_sync_state",state)
            except Exception: pass
            raise

    def refresh_metrics(self, channel_id: str, *, days: int | None = None, all_videos: bool = False) -> int:
        days = days if days is not None else int(self.settings["collection"]["metrics_recent_days"])
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT video_id,published_at FROM videos WHERE channel_id=? ORDER BY published_at DESC", (channel_id,)).fetchall()
        ids: list[str] = []
        now = parse_iso(now_utc())
        for r in rows:
            if all_videos:
                ids.append(r["video_id"])
                continue
            published = parse_iso(r["published_at"])
            if not published or not now or (now - published).days <= days:
                ids.append(r["video_id"])
        return self.hydrate_videos(ids)

    def _sync_due_hours(self, priority: str, mode: str) -> float:
        policy=(self.settings.get("refresh_policy") or {}).get(priority or "normal", {})
        new_h=float(policy.get("new_video_hours") or 24)
        metric_h=float(policy.get("metric_hours") or new_h)
        if mode in {"metrics-only","metrics"}:
            return metric_h
        if mode in {"channel-only","channel","full-history"}:
            return new_h
        return min(new_h,metric_h)

    def sync_all(self, *, mode: str = "incremental", priority: str | None = None, metric_days: int | None = None, all_videos: bool = False, limit: int | None = None, force: bool = False) -> dict[str, Any]:
        started = now_utc(); now_dt=parse_iso(started)
        with connect(self.db_path) as conn:
            run_id = conn.execute("INSERT INTO sync_runs(mode,target,started_at,status) VALUES(?,?,?,?)", (mode, (priority or "all_monitored")+("_force" if force else "_due"), started, "running")).lastrowid
            sql = "SELECT channel_id,priority,last_synced_at,last_sync_status,next_retry_at,sync_suspended,consecutive_sync_failures FROM creators WHERE monitoring_enabled=1"
            params: list[Any] = []
            if priority:
                sql += " AND priority=?"; params.append(priority)
            candidates=[dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
            conn.commit()
        due=[]; skipped_not_due=0; skipped_suspended=0; retry_wait=0
        for row in candidates:
            if row.get("sync_suspended") and not force:
                skipped_suspended += 1; continue
            retry=parse_iso(row.get("next_retry_at"))
            if row.get("last_sync_status")=="failed" and retry and now_dt:
                if retry<=now_dt: due.append(row); continue
                if not force: retry_wait += 1; continue
            if force or not row.get("last_synced_at"):
                due.append(row); continue
            last=parse_iso(row.get("last_synced_at"));hours=self._sync_due_hours(row.get("priority") or "normal",mode)
            if not last or not now_dt or (now_dt-last).total_seconds() >= hours*3600: due.append(row)
            else: skipped_not_due += 1
        due.sort(key=lambda r:(0 if r.get("last_sync_status")=="failed" else 1,{"high":0,"normal":1,"low":2,"archive":3}.get(r.get("priority"),9),r.get("last_synced_at") or ""))
        if limit is not None: due=due[:max(0,int(limit))]
        channels=[r["channel_id"] for r in due];creators_done=0;videos_done=0;errors=[]
        try:
            for cid in channels:
                try:
                    res=self.sync_creator(cid,mode=mode,metric_days=metric_days,all_videos=all_videos,sync_run_id=run_id)
                    creators_done+=1;videos_done+=int(res["videos_processed"])
                except (YouTubeAPIError,QuotaBudgetExceeded) as e:
                    state=getattr(e,"creator_sync_state",{}) or {};errors.append(f"{cid}: {state.get('error_type') or type(e).__name__}: {e}")
                    if isinstance(e,QuotaBudgetExceeded) or getattr(e,"reason",None) in {"quotaExceeded","dailyLimitExceeded"}: break
                except Exception as e:
                    state=getattr(e,"creator_sync_state",{}) or {};errors.append(f"{cid}: {state.get('error_type') or type(e).__name__}: {e}")
            status="complete" if not errors else ("partial" if creators_done else "failed")
        except Exception as e:
            status="failed";errors.append(str(e))
        units=self.api.usage.units if self._api else 0
        note=f"due={len(channels)}; skipped_not_due={skipped_not_due}; retry_wait={retry_wait}; suspended={skipped_suspended}; force={force}"
        message=(note+("\n"+"\n".join(errors) if errors else ""))[:10000]
        with connect(self.db_path) as conn:
            conn.execute("UPDATE sync_runs SET finished_at=?,status=?,creators_processed=?,videos_processed=?,quota_units=?,message=? WHERE id=?",(now_utc(),status,creators_done,videos_done,units,message,run_id));conn.commit()
        return {"run_id":run_id,"status":status,"creators_processed":creators_done,"videos_processed":videos_done,"quota_units":units,"errors":errors,"eligible_due":len(channels),"skipped_not_due":skipped_not_due,"retry_wait":retry_wait,"skipped_suspended":skipped_suspended,"force":force}

    def sync_selected(self, channel_ids: list[str], *, mode: str = "incremental", metric_days: int | None = None, all_videos: bool = False, progress=None) -> dict[str, Any]:
        """Immediately sync explicitly selected monitored Creators.

        This bypasses cadence/retry waiting because the operator explicitly requested a refresh.
        A successful run clears prior retry/suspension state through _record_sync_success.
        """
        ids=list(dict.fromkeys(str(x).strip() for x in channel_ids if str(x).strip()))
        if not ids:return {"status":"complete","requested":0,"creators_processed":0,"videos_processed":0,"errors":[]}
        mode=str(mode or "incremental").replace("_","-")
        allowed={"incremental","new","metrics-only","metrics","channel-only","channel","full-history","full"}
        if mode not in allowed:raise ValueError("unsupported sync mode")
        started=now_utc()
        with connect(self.db_path) as conn:
            marks=','.join('?' for _ in ids)
            known={r[0] for r in conn.execute(f"SELECT channel_id FROM creators WHERE monitoring_enabled=1 AND channel_id IN ({marks})",tuple(ids)).fetchall()}
            selected=[x for x in ids if x in known]
            run_id=conn.execute("INSERT INTO sync_runs(mode,target,started_at,status) VALUES(?,?,?,?)",(mode,f"selected:{len(selected)}",started,"running")).lastrowid
            conn.commit()
        errors=[];done=0;videos=0
        if progress: progress(stage="同步 Creator",message=f"准备同步 {len(selected)} 个 Creator",current=0,total=len(selected))
        for idx,cid in enumerate(selected,1):
            try:
                r=self.sync_creator(cid,mode=mode,metric_days=metric_days,all_videos=all_videos,sync_run_id=run_id)
                done+=1;videos+=int(r.get("videos_processed") or 0)
            except Exception as e:
                state=getattr(e,"creator_sync_state",{}) or {};errors.append(f"{cid}: {state.get('error_type') or type(e).__name__}: {e}")
                if isinstance(e,QuotaBudgetExceeded) or (isinstance(e,YouTubeAPIError) and getattr(e,"reason",None) in {"quotaExceeded","dailyLimitExceeded"}):break
            if progress: progress(stage="同步 Creator",message=f"已处理 {idx}/{len(selected)} · 成功 {done} · 视频 {videos} · 错误 {len(errors)}",current=idx,total=len(selected),videos_processed=videos,errors_count=len(errors))
        missing=[x for x in ids if x not in known]
        errors.extend(f"{x}: not monitored or not in creator library" for x in missing)
        status="complete" if not errors else ("partial" if done else "failed")
        units=self.api.usage.units if self._api else 0
        with connect(self.db_path) as conn:
            conn.execute("UPDATE sync_runs SET finished_at=?,status=?,creators_processed=?,videos_processed=?,quota_units=?,message=? WHERE id=?",(now_utc(),status,done,videos,units,("\n".join(errors))[:10000],run_id));conn.commit()
        return {"run_id":run_id,"status":status,"requested":len(ids),"eligible":len(selected),"creators_processed":done,"videos_processed":videos,"quota_units":units,"errors":errors,"mode":mode}

    # ---------- offline classification ----------
    def reclassify_videos(self, *, only_missing: bool = False, limit: int | None = None, batch_size: int = 2000, progress=None) -> dict[str, Any]:
        """Re-run the deterministic UgPhone/competitor/daily classifier from stored metadata.

        No YouTube API request is made. Human corrections in video_labels are not
        changed; only label_suggestions is refreshed.
        """
        with connect(self.db_path) as conn:
            total_target=int(conn.execute("SELECT COUNT(*) FROM videos" if not only_missing else "SELECT COUNT(*) FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id WHERE s.video_id IS NULL").fetchone()[0])
        if limit is not None: total_target=min(total_target,max(0,int(limit)))
        if progress: progress(stage="离线系统分类",message=f"准备重新识别 {total_target} 条视频",current=0,total=total_target)
        processed = 0
        changed = 0
        offset = 0
        while True:
            with connect(self.db_path) as conn:
                sql = """SELECT v.video_id,v.channel_id,v.title,v.description,v.tags_json,
                                s.suggested_role AS old_suggested_role,s.brands_json AS old_brands_json,
                                s.confidence AS old_confidence,s.evidence_json AS old_evidence_json,s.rule_version AS old_rule_version
                         FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id"""
                params: list[Any] = []
                if only_missing:
                    sql += " WHERE s.video_id IS NULL"
                sql += " ORDER BY v.video_id LIMIT ? OFFSET ?"
                take = batch_size
                if limit is not None:
                    remain = max(0, int(limit) - processed)
                    if remain <= 0:
                        break
                    take = min(take, remain)
                params.extend([take, offset])
                rows = conn.execute(sql, tuple(params)).fetchall()
            if not rows:
                break
            payload = []
            for r in rows:
                suggestion = suggest_label({
                    "video_id": r["video_id"],
                    "title": r["title"] or "",
                    "description": r["description"] or "",
                    "tags": json_load(r["tags_json"], []),
                }, self.brand_cfg)
                new_brands = json_dump(suggestion.get("brands") or [])
                new_evidence = json_dump(suggestion.get("evidence") or [])
                if (r["old_suggested_role"] != suggestion["suggested_role"] or
                    (r["old_brands_json"] or "[]") != new_brands or
                    r["old_confidence"] != suggestion["confidence"] or
                    (r["old_evidence_json"] or "[]") != new_evidence or
                    r["old_rule_version"] != suggestion["rule_version"]):
                    changed += 1
                payload.append((
                    r["video_id"], suggestion["suggested_role"], new_brands,
                    suggestion["confidence"], new_evidence,
                    suggestion["generated_at"], suggestion["rule_version"],
                ))
            with connect(self.db_path) as conn:
                conn.executemany(
                    """INSERT INTO label_suggestions(video_id,suggested_role,brands_json,confidence,evidence_json,generated_at,rule_version)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET suggested_role=excluded.suggested_role,
                    brands_json=excluded.brands_json,confidence=excluded.confidence,evidence_json=excluded.evidence_json,
                    generated_at=excluded.generated_at,rule_version=excluded.rule_version""",
                    payload,
                )
                cids=list(dict.fromkeys(r["channel_id"] for r in rows if r["channel_id"]))
                if cids:
                    marks=','.join('?' for _ in cids);conn.execute(f"UPDATE creators SET classification_data_at=? WHERE channel_id IN ({marks})",tuple([now_utc()]+cids))
                conn.commit()
            processed += len(rows)
            if only_missing:
                # Missing rows disappear from the filtered result after insertion, so keep offset at zero.
                offset = 0
            else:
                offset += len(rows)
            if len(rows) < take:
                break
        return {"videos_reclassified": processed, "changed": changed, "only_missing": only_missing, "api_calls": 0, "rule_version": self.brand_cfg.get("rule_version")}

    # ---------- video classification / review ----------
    def classification_stats(self) -> dict[str, int]:
        """Return classification KPI counts without joining the full video table.

        The classification list is latency-sensitive. These totals are intentionally
        separated from page queries so opening, filtering and paging 500k+ videos does
        not repeat a global multi-table aggregation every time.
        """
        with connect(self.db_path) as conn:
            all_total = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            classified_total = conn.execute("SELECT COUNT(*) FROM label_suggestions").fetchone()[0]
            reviewed_total = conn.execute("SELECT COUNT(*) FROM video_labels").fetchone()[0]
            pending_total = conn.execute(
                """SELECT COUNT(*)
                   FROM label_suggestions s
                   LEFT JOIN video_labels l ON l.video_id=s.video_id
                   WHERE l.video_id IS NULL
                     AND (s.suggested_role='pending' OR s.confidence='review')"""
            ).fetchone()[0]
        return {
            "all_total": int(all_total or 0),
            "classified_total": int(classified_total or 0),
            "pending_total": int(pending_total or 0),
            "reviewed_total": int(reviewed_total or 0),
        }

    def classification_list(self, *, page: int = 1, page_size: int = 30, search: str = "", role: str = "", brand: str = "", conditions: list[dict[str,Any]] | None = None, sort: str = "published", direction: str = "desc", include_stats: bool = False) -> dict[str, Any]:
        """List all locally stored videos with system classification and optional human override.

        Page data and filtered totals are resolved first. Global classification KPIs are
        optional and normally requested separately, avoiding repeated 500k-row aggregate
        joins during paging/sorting/filtering.
        """
        page=max(1,int(page or 1)); page_size=max(1,min(5000,int(page_size or 30)))
        where=["1=1"]
        params:list[Any]=[]
        if search:
            q=f"%{search.lower()}%"; where.append("(lower(COALESCE(v.title,'')) LIKE ? OR lower(COALESCE(c.channel_title,'')) LIKE ? OR lower(v.video_id) LIKE ?)"); params.extend([q,q,q])
        if role:
            where.append("COALESCE(l.human_role,s.suggested_role,'pending')=?"); params.append(role)
        if brand:
            where.append("instr(lower(COALESCE(l.brands_json,s.brands_json,'')),?)>0"); params.append(str(brand).lower())

        def cexpr(cond:dict[str,Any]):
            field=str(cond.get("field") or ""); value=str(cond.get("value") or "")
            if field in {"role","effective_role"}: return "COALESCE(l.human_role,s.suggested_role,'pending')=?",[value]
            if field=="system_role": return "COALESCE(s.suggested_role,'pending')=?",[value]
            if field=="classification_source":
                if value=="human": return "l.video_id IS NOT NULL",[]
                if value=="system": return "l.video_id IS NULL AND s.video_id IS NOT NULL",[]
                if value=="none": return "l.video_id IS NULL AND s.video_id IS NULL",[]
                return "1=1",[]
            if field=="human_system_mismatch":
                if value in {"1","true","yes","mismatch"}: return "l.video_id IS NOT NULL AND COALESCE(l.human_role,'')<>COALESCE(s.suggested_role,'pending')",[]
                if value in {"0","false","no","match"}: return "l.video_id IS NOT NULL AND COALESCE(l.human_role,'')=COALESCE(s.suggested_role,'pending')",[]
                return "1=1",[]
            if field=="brand": return "instr(lower(COALESCE(l.brands_json,s.brands_json,'')),?)>0",[value.lower()]
            if field=="review_status":
                if value=="pending_review": return "(l.video_id IS NULL AND (COALESCE(s.suggested_role,'pending')='pending' OR s.confidence='review'))",[]
                if value=="manual_reviewed": return "l.video_id IS NOT NULL",[]
                if value=="not_manual_reviewed": return "l.video_id IS NULL",[]
                if value=="system_only": return "(l.video_id IS NULL AND s.video_id IS NOT NULL AND COALESCE(s.suggested_role,'pending')<>'pending' AND COALESCE(s.confidence,'')<>'review')",[]
                return "1=1",[]
            if field=="confidence": return "COALESCE(s.confidence,'low')=?",[value]
            op=str(cond.get("op") or "gte").lower()
            sql_op={"gte":">=","gt":">","lte":"<=","lt":"<","eq":"=","neq":"<>"}.get(op,">=")
            if field=="views": return f"COALESCE(v.current_views,0) {sql_op} ?",[float(value)]
            if field=="likes": return f"COALESCE(v.current_likes,0) {sql_op} ?",[float(value)]
            if field=="comments": return f"COALESCE(v.current_comments,0) {sql_op} ?",[float(value)]
            if field=="duration": return f"COALESCE(v.duration_seconds,0) {sql_op} ?",[float(value)]
            if field=="published": return f"substr(COALESCE(v.published_at,''),1,10) {sql_op} ?",[value[:10]]
            return "1=1",[]

        conds=[c for c in (conditions or []) if c.get("field") and (c.get("value") not in (None,""))]
        if conds:
            e,p=cexpr(conds[0]); group=f"({e})"; params.extend(p)
            for c in conds[1:]:
                e,p=cexpr(c); join=str(c.get("join") or "AND").upper()
                if join=="OR": group=f"({group} OR ({e}))"
                elif join=="NOT": group=f"({group} AND NOT ({e}))"
                else: group=f"({group} AND ({e}))"
                params.extend(p)
            where.append(group)

        order_map={
            "published":"v.published_at", "views":"v.current_views", "likes":"v.current_likes", "comments":"v.current_comments", "duration":"v.duration_seconds", "creator":"c.channel_title",
            "title":"v.title", "role":"COALESCE(l.human_role,s.suggested_role,'pending')", "system_role":"COALESCE(s.suggested_role,'pending')",
            "review_status":"CASE WHEN l.video_id IS NOT NULL THEN 2 WHEN COALESCE(s.suggested_role,'pending')='pending' OR s.confidence='review' THEN 1 ELSE 0 END"
        }
        order=order_map.get(sort,"v.published_at"); d="ASC" if str(direction).lower()=="asc" else "DESC"
        where_sql=" AND ".join(where)
        base_from="""FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id JOIN creators c ON c.channel_id=v.channel_id LEFT JOIN video_labels l ON l.video_id=v.video_id"""

        # Build the lightest possible COUNT query. The unfiltered initial page is a
        # direct COUNT(videos), while video-only numeric/date filters also avoid label joins.
        cond_fields={str(c.get("field") or "") for c in conds}
        need_l=bool(role or brand or cond_fields & {"role","effective_role","brand","review_status","classification_source","human_system_mismatch"})
        need_s=bool(role or brand or cond_fields & {"role","effective_role","system_role","brand","review_status","confidence","classification_source","human_system_mismatch"}) or need_l
        need_c=bool(search)
        count_from="FROM videos v"
        if need_s: count_from+=" LEFT JOIN label_suggestions s ON s.video_id=v.video_id"
        if need_c: count_from+=" JOIN creators c ON c.channel_id=v.channel_id"
        if need_l: count_from+=" LEFT JOIN video_labels l ON l.video_id=v.video_id"

        with connect(self.db_path) as conn:
            total=conn.execute(f"SELECT COUNT(*) {count_from} WHERE {where_sql}",tuple(params)).fetchone()[0]
            pages=max(1,(int(total)+page_size-1)//page_size); page=min(page,pages); offset=(page-1)*page_size
            rows=conn.execute(f"""SELECT v.video_id,v.title,v.channel_id,v.published_at,v.current_views,v.current_likes,v.current_comments,v.duration_seconds,
                s.suggested_role,s.brands_json AS system_brands_json,s.confidence,s.evidence_json,s.rule_version,
                l.human_role,l.brands_json AS human_brands_json,l.labeled_by,l.labeled_at,c.channel_title
                {base_from} WHERE {where_sql} ORDER BY {order} {d}, v.video_id ASC LIMIT ? OFFSET ?""",tuple(params+[page_size,offset])).fetchall()
        out=[]
        for r in rows:
            x=dict(r)
            system_brands=json_load(x.pop("system_brands_json"),[])
            human_brands=json_load(x.pop("human_brands_json"),[]) if x.get("human_role") else []
            x["system_brands"]=system_brands
            x["human_brands"]=human_brands
            x["brands"]=human_brands if x.get("human_role") else system_brands
            x["evidence"]=json_load(x.pop("evidence_json"),[])
            x["effective_role"]=x.get("human_role") or x.get("suggested_role") or "pending"
            x["final_role"]=x["effective_role"]  # compatibility alias; business logic uses effective_role.
            x["classification_source"]="human" if x.get("human_role") else ("system" if x.get("suggested_role") else "none")
            x["human_system_mismatch"]=bool(x.get("human_role") and x.get("human_role")!=(x.get("suggested_role") or "pending"))
            x["manual_reviewed"]=bool(x.get("human_role"))
            x["requires_review"]=(not x["manual_reviewed"] and ((x.get("suggested_role") or "pending")=="pending" or x.get("confidence")=="review"))
            x["review_status"]="manual_reviewed" if x["manual_reviewed"] else ("pending_review" if x["requires_review"] else "system_only")
            out.append(x)
        result={"rows":out,"total":int(total),"page":page,"page_size":page_size,"pages":pages}
        if include_stats:
            result.update(self.classification_stats())
        return result

    def review_queue(self, *, page: int = 1, page_size: int = 30, search: str = "", role: str = "", brand: str = "", conditions: list[dict[str,Any]] | None = None, sort: str = "published", direction: str = "desc") -> dict[str, Any]:
        """Compatibility wrapper returning only unresolved review items."""
        conds=list(conditions or [])
        conds.insert(0,{"field":"review_status","value":"pending_review"})
        return self.classification_list(page=page,page_size=page_size,search=search,role=role,brand=brand,conditions=conds,sort=sort,direction=direction)

    def review_video(self, video_id: str, *, confirm_system: bool = False, role: str | None = None, brands: list[str] | None = None, actor: str = "dashboard-review") -> dict[str, Any]:
        with connect(self.db_path) as conn:
            s=conn.execute("SELECT suggested_role,brands_json FROM label_suggestions WHERE video_id=?",(video_id,)).fetchone()
        if not s:
            raise ValueError(f"视频 {video_id} 没有系统分类")
        if confirm_system:
            use_role=s["suggested_role"]; use_brands=json_load(s["brands_json"],[]); note="人工复核确认系统分类"
        else:
            use_role=role or s["suggested_role"]; use_brands=brands if brands is not None else json_load(s["brands_json"],[]); note="人工复核修正系统分类"
        out=self.label_video(video_id,use_role,brands=use_brands,actor=actor,note=note)
        try:
            self.contracts.assert_value("video",video_id,"classification.role","human",use_role,source_ref=actor,observed_at=now_utc())
            self.contracts.assert_value("video",video_id,"classification.brands","human",use_brands,source_ref=actor,observed_at=now_utc())
        except Exception:
            pass
        return out

    def reclassify_review_queue(self, *, batch_size: int = 500, progress=None) -> dict[str, Any]:
        """Re-run the current deterministic classifier for every unresolved review item.

        This is fully offline and does not consume YouTube API quota. Items that still
        have weak evidence remain in the review queue; items resolved by the current
        rules leave the queue automatically.
        """
        with connect(self.db_path) as conn:
            ids=[r[0] for r in conn.execute("""SELECT s.video_id FROM label_suggestions s LEFT JOIN video_labels l ON l.video_id=s.video_id WHERE l.video_id IS NULL AND (s.suggested_role='pending' OR s.confidence='review') ORDER BY s.video_id""").fetchall()]
        before=len(ids);processed=0
        if progress: progress(stage="重新识别待复核",message=f"准备处理 {before} 条待复核视频",current=0,total=before)
        for i in range(0,len(ids),max(1,batch_size)):
            chunk=ids[i:i+max(1,batch_size)]; marks=','.join('?' for _ in chunk)
            with connect(self.db_path) as conn:
                rows=conn.execute(f"SELECT video_id,title,description,tags_json FROM videos WHERE video_id IN ({marks})",tuple(chunk)).fetchall()
            payload=[]
            for r in rows:
                suggestion=suggest_label({"video_id":r["video_id"],"title":r["title"] or "","description":r["description"] or "","tags":json_load(r["tags_json"],[])},self.brand_cfg)
                payload.append((r["video_id"],suggestion["suggested_role"],json_dump(suggestion.get("brands") or []),suggestion["confidence"],json_dump(suggestion.get("evidence") or []),suggestion["generated_at"],suggestion["rule_version"]))
            if payload:
                with connect(self.db_path) as conn:
                    conn.executemany("""INSERT INTO label_suggestions(video_id,suggested_role,brands_json,confidence,evidence_json,generated_at,rule_version) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(video_id) DO UPDATE SET suggested_role=excluded.suggested_role,brands_json=excluded.brands_json,confidence=excluded.confidence,evidence_json=excluded.evidence_json,generated_at=excluded.generated_at,rule_version=excluded.rule_version""",payload);conn.commit()
            processed+=len(rows)
            if progress: progress(stage="重新识别待复核",message=f"已处理 {processed}/{before}",current=processed,total=before)
        with connect(self.db_path) as conn:
            after=conn.execute("""SELECT COUNT(*) FROM label_suggestions s LEFT JOIN video_labels l ON l.video_id=s.video_id WHERE l.video_id IS NULL AND (s.suggested_role='pending' OR s.confidence='review')""").fetchone()[0]
        return {"videos_reclassified":processed,"before":before,"after":int(after),"api_calls":0,"rule_version":self.brand_cfg.get("rule_version")}

    def discovery_creator_history(self, *, page:int=1, page_size:int=30, search:str="", conditions:list[dict[str,Any]]|None=None, sort:str="score", direction:str="desc") -> dict[str,Any]:
        """Saved creator-level discovery outcomes: one row per search run x creator."""
        page=max(1,int(page or 1)); page_size=max(1,min(5000,int(page_size or 30)))
        where=[]; params:list[Any]=[]
        if search:
            q=f"%{search.lower()}%"; where.append("(lower(COALESCE(r.channel_title,'')) LIKE ? OR lower(COALESCE(dr.base_query,'')) LIKE ? OR lower(COALESCE(r.best_video_title,'')) LIKE ? OR lower(COALESCE(r.country_resolved,'')) LIKE ? OR lower(COALESCE(r.channel_id,'')) LIKE ?)"); params.extend([q,q,q,q,q])
        def expr(cond:dict[str,Any]):
            field=str(cond.get('field') or ''); value=str(cond.get('value') or '')
            if field=='status': return ("c.channel_id IS NOT NULL" if value=='library' else "c.channel_id IS NULL"),[]
            if field=='tier': return "COALESCE(r.opportunity_tier,'')=?",[value]
            if field=='workflow': return "COALESCE(wf.status,'unreviewed')=?",[value]
            if field=='freshness':
                return ("COALESCE(ds.discovery_run_count,1)<=1" if value=='first' else "COALESCE(ds.discovery_run_count,1)>1"),[]
            if field=='geo':
                country=str(cond.get('country') or '').upper(); resolved="COALESCE(NULLIF(c.country_resolved,''),NULLIF(r.country_resolved,''),NULLIF(c.country_api,''),'')"
                if country:return f"{resolved}=?",[country]
                codes=sorted(group_codes(value))
                if not codes:return "0=1",[]
                return f"{resolved} IN ({','.join('?' for _ in codes)})",codes
            return "1=1",[]
        conds=[c for c in (conditions or []) if c.get('field') and c.get('value')]
        if conds:
            e,p=expr(conds[0]); group=f"({e})"; params.extend(p)
            for cnd in conds[1:]:
                e,p=expr(cnd); join=str(cnd.get('join') or 'AND').upper()
                group=f"({group} OR ({e}))" if join=='OR' else f"({group} AND NOT ({e}))" if join=='NOT' else f"({group} AND ({e}))"; params.extend(p)
            where.append(group)
        w=' AND '.join(where) if where else '1=1'
        sortmap={'score':'r.best_discovery_score','found':'r.found_at','subs':'COALESCE(c.subscriber_count,r.subscribers)','views':'r.best_video_views','coverage':'r.query_coverage','hits':'r.hit_video_count','title':'r.channel_title','repeat':'COALESCE(ds.discovery_run_count,1)'}
        order=sortmap.get(sort,'r.best_discovery_score'); d='ASC' if str(direction).lower()=='asc' else 'DESC'
        with connect(self.db_path) as conn:
            base="FROM discovery_creator_results r JOIN discovery_runs dr ON dr.run_id=r.run_id LEFT JOIN creators c ON c.channel_id=r.channel_id LEFT JOIN creator_workflow wf ON wf.channel_id=r.channel_id LEFT JOIN creator_discovery_summary ds ON ds.channel_id=r.channel_id"
            total=conn.execute(f"SELECT COUNT(*) {base} WHERE {w}",tuple(params)).fetchone()[0]
            pages=max(1,(int(total)+page_size-1)//page_size); page=min(page,pages); offset=(page-1)*page_size
            rows=conn.execute(f"""SELECT r.*,dr.base_query,dr.base_query_source,dr.search_source,dr.query_language,dr.status AS run_status,c.channel_id AS library_channel_id,c.country_api,c.country_resolved AS library_country,c.subscriber_count AS library_subscribers,COALESCE(wf.status,'unreviewed') workflow_status,wf.note workflow_note,ds.first_seen_at,ds.last_seen_at,COALESCE(ds.discovery_run_count,1) discovery_run_count,COALESCE(ds.hit_video_count_total,r.hit_video_count) hit_video_count_total,ds.last_base_query {base} WHERE {w} ORDER BY {order} {d},r.found_at DESC,r.id DESC LIMIT ? OFFSET ?""",tuple(params+[page_size,offset])).fetchall()
        out=[]
        for rr in rows:
            x=dict(rr); x['matched_queries']=json_load(x.pop('matched_queries_json'),[]); x['keyword_source_label']=KEYWORD_SOURCE_LABELS.get(x.get('base_query_source') or 'exact', x.get('base_query_source') or '精确记录');x['workflow_label']=self._workflow_label(x.get('workflow_status'));x['discovery_freshness']='first' if int(x.get('discovery_run_count') or 1)<=1 else 'repeat';out.append(x)
        return {'rows':out,'total':int(total),'page':page,'page_size':page_size,'pages':pages}

    def discovery_creator_ids(self, *, search: str = "", conditions: list[dict[str,Any]] | None = None) -> dict[str,Any]:
        """Return unique creator ids across every page of the current saved-discovery filter."""
        ids=[];seen=set();page=1
        while True:
            x=self.discovery_creator_history(page=page,page_size=5000,search=search,conditions=conditions or [],sort="score",direction="desc")
            for r in x.get("rows") or []:
                cid=str(r.get("channel_id") or "").strip()
                if cid and cid not in seen:seen.add(cid);ids.append(cid)
            if page>=int(x.get("pages") or 1):break
            page+=1
        return {"channel_ids":ids,"count":len(ids)}

    def discovery_history(self, *, page:int=1, page_size:int=30, search:str="", conditions:list[dict[str,Any]]|None=None, sort:str="score", direction:str="desc") -> dict[str,Any]:
        page=max(1,int(page or 1));page_size=max(1,min(5000,int(page_size or 30)))
        where=[];params:list[Any]=[]
        if search:
            q=f"%{search.lower()}%";where.append("(lower(COALESCE(d.query,'')) LIKE ? OR lower(COALESCE(d.channel_title,'')) LIKE ? OR lower(COALESCE(d.title,'')) LIKE ? OR lower(COALESCE(d.country_resolved,'')) LIKE ? OR lower(COALESCE(d.channel_id,'')) LIKE ?)");params.extend([q,q,q,q,q])
        def expr(cond:dict[str,Any]):
            field=str(cond.get('field') or '');value=str(cond.get('value') or '')
            if field=='status':return ("c.channel_id IS NOT NULL" if value=='library' else "c.channel_id IS NULL"),[]
            if field=='tier':return "COALESCE(d.opportunity_tier,'')=?",[value]
            if field=='workflow':return "COALESCE(wf.status,'unreviewed')=?",[value]
            if field=='freshness':return ("COALESCE(ds.discovery_run_count,1)<=1" if value=='first' else "COALESCE(ds.discovery_run_count,1)>1"),[]
            if field=='country':return "COALESCE(NULLIF(c.country_resolved,''),NULLIF(d.country_resolved,''),NULLIF(c.country_api,''),'')=?",[value.upper()]
            if field=='geo':
                country=str(cond.get('country') or '').upper();resolved="COALESCE(NULLIF(c.country_resolved,''),NULLIF(d.country_resolved,''),NULLIF(c.country_api,''),'')"
                if country:return f"{resolved}=?",[country]
                codes=sorted(group_codes(value))
                if not codes:return "0=1",[]
                return f"{resolved} IN ({','.join('?' for _ in codes)})",codes
            return "1=1",[]
        conds=[c for c in (conditions or []) if c.get('field') and c.get('value')]
        if conds:
            e,p=expr(conds[0]);group=f"({e})";params.extend(p)
            for c in conds[1:]:
                e,p=expr(c);join=str(c.get('join') or 'AND').upper();group=f"({group} OR ({e}))" if join=='OR' else f"({group} AND NOT ({e}))" if join=='NOT' else f"({group} AND ({e}))";params.extend(p)
            where.append(group)
        w=' AND '.join(where) if where else '1=1'
        sortmap={'score':'d.pre_score','found':'d.found_at','subs':'COALESCE(c.subscriber_count,d.subscribers)','views':'d.views','title':'d.channel_title','repeat':'COALESCE(ds.discovery_run_count,1)'}
        order=sortmap.get(sort,'d.pre_score');d='ASC' if str(direction).lower()=='asc' else 'DESC'
        with connect(self.db_path) as conn:
            base="FROM discovery_hits d LEFT JOIN creators c ON c.channel_id=d.channel_id LEFT JOIN creator_workflow wf ON wf.channel_id=d.channel_id LEFT JOIN creator_discovery_summary ds ON ds.channel_id=d.channel_id"
            total=conn.execute(f"SELECT COUNT(*) {base} WHERE {w}",tuple(params)).fetchone()[0]
            pages=max(1,(int(total)+page_size-1)//page_size);page=min(page,pages);offset=(page-1)*page_size
            rows=conn.execute(f"""SELECT d.*,c.channel_id AS library_channel_id,c.country_api,c.country_resolved AS library_country,c.subscriber_count AS library_subscribers,COALESCE(wf.status,'unreviewed') workflow_status,COALESCE(ds.discovery_run_count,1) discovery_run_count,ds.first_seen_at,ds.last_seen_at {base} WHERE {w} ORDER BY {order} {d},d.found_at DESC,d.id DESC LIMIT ? OFFSET ?""",tuple(params+[page_size,offset])).fetchall()
        out=[]
        for r in rows:
            x=dict(r);x['workflow_label']=self._workflow_label(x.get('workflow_status'));x['discovery_freshness']='first' if int(x.get('discovery_run_count') or 1)<=1 else 'repeat';out.append(x)
        return {'rows':out,'total':int(total),'page':page,'page_size':page_size,'pages':pages}

    def evaluate_metric_spec(self, spec:dict[str,Any]) -> dict[str,Any]:
        """Evaluate an exact-date VIDEO aggregation from SQLite.
        The output is one numeric value per creator. Ratio support is retained only for legacy config migration.
        """
        allowed_fields={'video_count','current_views','current_likes','current_comments','duration_seconds'}
        allowed_aggs={'count','sum','avg','median','min','max'}
        def side(s:dict[str,Any])->dict[str,float|None]:
            field=str(s.get('source_field') or 'current_views');agg=str(s.get('aggregation') or 'count')
            if field not in allowed_fields:raise ValueError('unsupported video fact field')
            if field=='video_count' and agg!='count':raise ValueError('video_count only supports count aggregation')
            if agg not in allowed_aggs:raise ValueError('unsupported aggregation')
            where=['1=1'];params=[]
            if s.get('from_date'):
                where.append('v.published_at>=?');params.append(str(s['from_date'])+'T00:00:00Z' if len(str(s['from_date']))<=10 else str(s['from_date']))
            if s.get('to_date'):
                from datetime import datetime,timedelta
                td=str(s['to_date'])
                if len(td)<=10:
                    end=(datetime.fromisoformat(td)+timedelta(days=1)).date().isoformat()+'T00:00:00Z'
                else:end=td
                where.append('v.published_at<?');params.append(end)
            fl=str(s.get('filter_label') or '')
            if fl:
                scope,val=(fl.split(':',1)+[''])[:2]
                if scope=='role':where.append("COALESCE(l.human_role,s.suggested_role,'pending')=?");params.append(val)
                elif scope=='brand':where.append("instr(lower(COALESCE(l.brands_json,s.brands_json,'')),?)>0");params.append(val.lower())
            w=' AND '.join(where)
            joins='FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id'
            with connect(self.db_path) as conn:
                if agg!='median':
                    fn={'count':'COUNT','sum':'SUM','avg':'AVG','min':'MIN','max':'MAX'}[agg]
                    expr='COUNT(v.video_id)' if agg=='count' else f'{fn}(v.{field})'
                    rows=conn.execute(f'SELECT v.channel_id,{expr} value {joins} WHERE {w} GROUP BY v.channel_id',tuple(params)).fetchall()
                    return {r['channel_id']:(float(r['value']) if r['value'] is not None else None) for r in rows}
                rows=conn.execute(f'SELECT v.channel_id,v.{field} value {joins} WHERE {w} AND v.{field} IS NOT NULL ORDER BY v.channel_id,v.{field}',tuple(params)).fetchall()
            import statistics
            by:dict[str,list[float]]={}
            for r in rows:by.setdefault(r['channel_id'],[]).append(float(r['value']))
            return {cid:statistics.median(vals) if vals else None for cid,vals in by.items()}
        if str(spec.get('type') or '')=='ratio':
            a=side(dict(spec.get('numerator_spec') or {}));b=side(dict(spec.get('denominator_spec') or {}));keys=set(a)|set(b);vals={}
            for k in keys:
                den=b.get(k);vals[k]=(float(a.get(k) or 0)/float(den)) if den not in (None,0) else None
            return {'values':vals}
        return {'values':side(spec)}

    # ---------- labels / tags ----------
    def label_video(self, video_id: str, role: str, *, brands: list[str] | None = None, actor: str = "operator", note: str = "") -> dict[str, Any]:
        allowed = {"ugphone", "competitor", "daily", "multi_brand", "other_cloud_phone", "pending"}
        if role not in allowed:
            raise ValueError(f"role 必须是 {', '.join(sorted(allowed))}")
        at = now_utc()
        brands = brands or []
        with connect(self.db_path) as conn:
            exists = conn.execute("SELECT video_id FROM videos WHERE video_id=?", (video_id,)).fetchone()
            if not exists:
                raise ValueError(f"数据库中不存在视频 {video_id}")
            old = conn.execute("SELECT * FROM video_labels WHERE video_id=?", (video_id,)).fetchone()
            old_json = json_dump(dict(old)) if old else None
            new_obj = {"video_id": video_id, "human_role": role, "brands": brands, "labeled_by": actor, "note": note, "labeled_at": at}
            conn.execute(
                "INSERT INTO video_labels(video_id,human_role,brands_json,labeled_by,note,labeled_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(video_id) DO UPDATE SET human_role=excluded.human_role,brands_json=excluded.brands_json,labeled_by=excluded.labeled_by,note=excluded.note,labeled_at=excluded.labeled_at",
                (video_id, role, json_dump(brands), actor, note, at),
            )
            conn.execute("INSERT INTO video_label_audit(video_id,old_value_json,new_value_json,actor,changed_at) VALUES(?,?,?,?,?)",
                         (video_id, old_json, json_dump(new_obj), actor, at))
            conn.execute("UPDATE creators SET classification_data_at=? WHERE channel_id=(SELECT channel_id FROM videos WHERE video_id=?)",(at,video_id))
            conn.commit()
        return new_obj

    def clear_label(self, video_id: str, actor: str = "operator") -> None:
        at = now_utc()
        with connect(self.db_path) as conn:
            old = conn.execute("SELECT * FROM video_labels WHERE video_id=?", (video_id,)).fetchone()
            if old:
                conn.execute("INSERT INTO video_label_audit(video_id,old_value_json,new_value_json,actor,changed_at) VALUES(?,?,?,?,?)",
                             (video_id, json_dump(dict(old)), None, actor, at))
                conn.execute("DELETE FROM video_labels WHERE video_id=?", (video_id,))
                conn.commit()

    def tag_creator(self, ref: str, tag: str, actor: str = "operator") -> str:
        cid = self.resolve_channel_id(ref)
        with connect(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO creator_tags(channel_id,tag,created_by,created_at) VALUES(?,?,?,?)", (cid, tag, actor, now_utc()))
            conn.commit()
        return cid

    def set_monitoring(self, ref: str, enabled: bool, priority: str | None = None) -> str:
        cid = self.resolve_channel_id(ref)
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT channel_id FROM creators WHERE channel_id=?", (cid,)).fetchone()
        if not row:
            self.ensure_creator(cid, monitoring=enabled, priority=priority or "normal")
        else:
            with connect(self.db_path) as conn:
                if priority:
                    conn.execute("UPDATE creators SET monitoring_enabled=?,priority=? WHERE channel_id=?", (int(enabled), priority, cid))
                else:
                    conn.execute("UPDATE creators SET monitoring_enabled=? WHERE channel_id=?", (int(enabled), cid))
                conn.commit()
        return cid

    # ---------- workflow / batch / maintenance ----------
    WORKFLOW_STATUSES = {"unreviewed","interested","to_contact","added","defer","excluded"}

    @staticmethod
    def _workflow_label(status: str | None) -> str:
        return {"unreviewed":"未处理","interested":"感兴趣","to_contact":"待联系","added":"已入库","defer":"暂不考虑","excluded":"永久排除"}.get(status or "unreviewed",status or "未处理")

    def set_creator_workflow(self, channel_id: str, status: str, *, note: str = "", actor: str = "dashboard") -> dict[str, Any]:
        cid=str(channel_id or "").strip()
        if not cid: raise ValueError("channel_id required")
        if status not in self.WORKFLOW_STATUSES: raise ValueError("unsupported workflow status")
        at=now_utc()
        with connect(self.db_path) as conn:
            old=conn.execute("SELECT status,note FROM creator_workflow WHERE channel_id=?",(cid,)).fetchone()
            conn.execute("INSERT INTO creator_workflow(channel_id,status,note,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET status=excluded.status,note=excluded.note,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(cid,status,note,actor,at))
            conn.execute("INSERT INTO creator_workflow_audit(channel_id,old_status,new_status,note,actor,changed_at) VALUES(?,?,?,?,?,?)",(cid,old["status"] if old else None,status,note,actor,at))
            conn.commit()
        return {"channel_id":cid,"status":status,"status_label":self._workflow_label(status),"note":note,"updated_at":at}

    def creator_workflow_map(self, channel_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids=list(dict.fromkeys(str(x) for x in channel_ids if x))
        if not ids:return {}
        out={}
        with connect(self.db_path) as conn:
            for batch in chunks(ids,500):
                marks=','.join('?' for _ in batch)
                rows=conn.execute(f"SELECT * FROM creator_workflow WHERE channel_id IN ({marks})",tuple(batch)).fetchall()
                for r in rows:
                    x=dict(r);x["status_label"]=self._workflow_label(x.get("status"));out[x["channel_id"]]=x
        return out

    def batch_creators(self, channel_ids: list[str], action: str, *, value: str = "", actor: str = "dashboard", progress=None) -> dict[str, Any]:
        ids=list(dict.fromkeys(str(x).strip() for x in channel_ids if str(x).strip()))
        if not ids:return {"processed":0,"errors":[]}
        errors=[];done=0
        if progress: progress(stage="批量 Creator 操作",message=f"准备处理 {len(ids)} 个 Creator",current=0,total=len(ids))
        for idx,cid in enumerate(ids,1):
            try:
                if action=="workflow": self.set_creator_workflow(cid,value or "unreviewed",actor=actor)
                elif action=="add": self.ensure_creator(cid,monitoring=True,source="batch_add")
                elif action=="monitor_on":
                    # Existing library rows are a pure SQLite update; discovery-only rows are materialized once.
                    with connect(self.db_path) as conn:
                        exists=conn.execute("SELECT 1 FROM creators WHERE channel_id=?",(cid,)).fetchone()
                        if exists:
                            conn.execute("UPDATE creators SET monitoring_enabled=1 WHERE channel_id=?",(cid,));conn.commit()
                    if not exists:self.ensure_creator(cid,monitoring=True,source="batch_monitor")
                elif action=="monitor_off":
                    with connect(self.db_path) as conn:
                        conn.execute("UPDATE creators SET monitoring_enabled=0 WHERE channel_id=?",(cid,));conn.commit()
                elif action=="priority":
                    if value not in {"high","normal","low","archive"}:raise ValueError("invalid priority")
                    # Avoid an API refresh for existing rows; only discovery-only selections need materialization.
                    with connect(self.db_path) as conn:
                        exists=conn.execute("SELECT 1 FROM creators WHERE channel_id=?",(cid,)).fetchone()
                        if exists:
                            conn.execute("UPDATE creators SET priority=? WHERE channel_id=?",(value,cid));conn.commit()
                    if not exists:self.ensure_creator(cid,monitoring=True,priority=value,source="batch_priority")
                elif action=="tag":
                    if not value.strip():raise ValueError("tag required")
                    with connect(self.db_path) as conn:
                        conn.execute("INSERT OR IGNORE INTO creator_tags(channel_id,tag,created_by,created_at) VALUES(?,?,?,?)",(cid,value.strip(),actor,now_utc()));conn.commit()
                elif action=="contact":
                    self.scrape_contact(cid)
                elif action=="resume_sync":
                    with connect(self.db_path) as conn:
                        conn.execute("UPDATE creators SET sync_suspended=0,consecutive_sync_failures=0,next_retry_at=NULL,last_sync_error=NULL,sync_error_type=NULL WHERE channel_id=?",(cid,));conn.commit()
                else: raise ValueError("unsupported creator batch action")
                done+=1
            except Exception as e: errors.append(f"{cid}: {type(e).__name__}: {e}")
            if progress: progress(stage="批量 Creator 操作",message=f"已处理 {idx}/{len(ids)} · 成功 {done} · 错误 {len(errors)}",current=idx,total=len(ids),errors_count=len(errors))
        return {"processed":done,"requested":len(ids),"errors":errors}

    def batch_capture_creators(self, channel_ids: list[str], *, window: str = "30", from_date: str = "", to_date: str = "", priority: str = "normal", actor: str = "dashboard-batch", progress=None) -> dict[str, Any]:
        """Capture the same selected time window for multiple Creators.

        The batch is intentionally executed Creator-by-Creator so API failures remain isolated;
        Dashboard files are never rebuilt inside this loop.
        """
        ids=list(dict.fromkeys(str(x).strip() for x in channel_ids if str(x).strip()))
        if not ids:return {"processed":0,"requested":0,"videos_processed":0,"errors":[],"results":[]}
        mode=str(window or "30")
        if mode not in {"7","30","60","90","180","365","date","date_range","full"}:
            raise ValueError("unsupported capture window")
        if mode in {"date","date_range"}:
            if not from_date or not to_date: raise ValueError("date range requires from_date and to_date")
            if str(from_date)>str(to_date): raise ValueError("from_date cannot be later than to_date")
        if priority not in {"high","normal","low","archive"}: raise ValueError("invalid priority")
        errors=[];done=0;videos=0;results=[]
        if progress: progress(stage="抓取并入库",message=f"准备抓取 {len(ids)} 个 Creator",current=0,total=len(ids))
        for idx,cid in enumerate(ids,1):
            try:
                if mode=="full": res=self.capture_window(cid,full_history=True,priority=priority)
                elif mode in {"date","date_range"}: res=self.capture_window(cid,from_date=from_date,to_date=to_date,priority=priority)
                else: res=self.capture_window(cid,days=int(mode),priority=priority)
                done+=1;videos+=int(res.get("videos_processed") or 0);results.append(res)
            except Exception as e:
                errors.append(f"{cid}: {type(e).__name__}: {e}")
            if progress: progress(stage="抓取并入库",message=f"已处理 {idx}/{len(ids)} · 成功 {done} · 视频 {videos} · 错误 {len(errors)}",current=idx,total=len(ids),videos_processed=videos,errors_count=len(errors))
        return {"processed":done,"requested":len(ids),"videos_processed":videos,"errors":errors,"results":results,"window":mode,"from_date":from_date or None,"to_date":to_date or None}

    def classification_matching_ids(self, *, search: str = "", conditions: list[dict[str,Any]] | None = None, exclude_ids: list[str] | None = None) -> list[str]:
        """Resolve all video ids matching the current classification filter without browser-side enumeration."""
        where=["1=1"]; params:list[Any]=[]
        if search:
            q=f"%{search.lower()}%";where.append("(lower(COALESCE(v.title,'')) LIKE ? OR lower(COALESCE(c.channel_title,'')) LIKE ? OR lower(v.video_id) LIKE ?)");params.extend([q,q,q])
        def cexpr(cond:dict[str,Any]):
            field=str(cond.get("field") or "");value=str(cond.get("value") or "")
            if field in {"role","effective_role"}:return "COALESCE(l.human_role,s.suggested_role,'pending')=?",[value]
            if field=="system_role":return "COALESCE(s.suggested_role,'pending')=?",[value]
            if field=="classification_source":
                if value=="human":return "l.video_id IS NOT NULL",[]
                if value=="system":return "l.video_id IS NULL AND s.video_id IS NOT NULL",[]
                if value=="none":return "l.video_id IS NULL AND s.video_id IS NULL",[]
                return "1=1",[]
            if field=="human_system_mismatch":
                if value in {"1","true","yes","mismatch"}:return "l.video_id IS NOT NULL AND COALESCE(l.human_role,'')<>COALESCE(s.suggested_role,'pending')",[]
                if value in {"0","false","no","match"}:return "l.video_id IS NOT NULL AND COALESCE(l.human_role,'')=COALESCE(s.suggested_role,'pending')",[]
                return "1=1",[]
            if field=="brand":return "instr(lower(COALESCE(l.brands_json,s.brands_json,'')),?)>0",[value.lower()]
            if field=="review_status":
                if value=="pending_review":return "(l.video_id IS NULL AND (COALESCE(s.suggested_role,'pending')='pending' OR s.confidence='review'))",[]
                if value=="manual_reviewed":return "l.video_id IS NOT NULL",[]
                if value=="not_manual_reviewed":return "l.video_id IS NULL",[]
                if value=="system_only":return "(l.video_id IS NULL AND s.video_id IS NOT NULL AND COALESCE(s.suggested_role,'pending')<>'pending' AND COALESCE(s.confidence,'')<>'review')",[]
                return "1=1",[]
            if field=="confidence":return "COALESCE(s.confidence,'low')=?",[value]
            op=str(cond.get("op") or "gte").lower();sql_op={"gte":">=","gt":">","lte":"<=","lt":"<","eq":"=","neq":"<>"}.get(op,">=")
            if field=="views":return f"COALESCE(v.current_views,0) {sql_op} ?",[float(value)]
            if field=="likes":return f"COALESCE(v.current_likes,0) {sql_op} ?",[float(value)]
            if field=="comments":return f"COALESCE(v.current_comments,0) {sql_op} ?",[float(value)]
            if field=="duration":return f"COALESCE(v.duration_seconds,0) {sql_op} ?",[float(value)]
            if field=="published":return f"substr(COALESCE(v.published_at,''),1,10) {sql_op} ?",[value[:10]]
            return "1=1",[]
        conds=[c for c in (conditions or []) if c.get("field") and c.get("value") not in (None,"")]
        if conds:
            e,p=cexpr(conds[0]);group=f"({e})";params.extend(p)
            for c in conds[1:]:
                e,p=cexpr(c);join=str(c.get("join") or "AND").upper();group=f"({group} OR ({e}))" if join=="OR" else f"({group} AND NOT ({e}))" if join=="NOT" else f"({group} AND ({e}))";params.extend(p)
            where.append(group)
        base="FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id JOIN creators c ON c.channel_id=v.channel_id LEFT JOIN video_labels l ON l.video_id=v.video_id"
        with connect(self.db_path) as conn:
            rows=conn.execute(f"SELECT v.video_id {base} WHERE {' AND '.join(where)} ORDER BY v.video_id",tuple(params)).fetchall()
        excluded={str(x) for x in (exclude_ids or []) if x}
        return [str(r[0]) for r in rows if str(r[0]) not in excluded]

    def batch_review_matching(self, selection: dict[str,Any], action: str, *, role: str = "", brands: list[str] | None = None, actor: str = "dashboard-batch") -> dict[str,Any]:
        ids=self.classification_matching_ids(search=str(selection.get("search") or ""),conditions=list(selection.get("conditions") or []),exclude_ids=list(selection.get("exclude_ids") or []))
        return self.batch_review(ids,action,role=role,brands=brands,actor=actor)

    def batch_review(self, video_ids: list[str], action: str, *, role: str = "", brands: list[str] | None = None, actor: str = "dashboard-batch") -> dict[str, Any]:
        ids=list(dict.fromkeys(str(x).strip() for x in video_ids if str(x).strip()));done=0;errors=[]
        if action not in {"confirm_system","set_role","clear"}:raise ValueError("unsupported review batch action")
        if action=="set_role" and role not in {"ugphone","competitor","daily","multi_brand","other_cloud_phone","pending"}:raise ValueError("invalid role")
        at=now_utc();use_brands=list(brands or [])
        with connect(self.db_path) as conn:
            for batch in chunks(ids,400):
                marks=','.join('?' for _ in batch)
                rows=conn.execute(f"""SELECT v.video_id,v.channel_id,s.suggested_role,s.brands_json AS system_brands_json,
                    l.video_id AS old_video_id,l.human_role AS old_human_role,l.brands_json AS old_brands_json,l.labeled_by AS old_labeled_by,l.note AS old_note,l.labeled_at AS old_labeled_at
                    FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id
                    WHERE v.video_id IN ({marks})""",tuple(batch)).fetchall()
                by={str(r["video_id"]):r for r in rows}
                touched=set()
                for vid in batch:
                    r=by.get(vid)
                    if not r:
                        errors.append(f"{vid}: ValueError: 数据库中不存在视频");continue
                    try:
                        if action=="clear":
                            if r["old_video_id"]:
                                old_obj={"video_id":vid,"human_role":r["old_human_role"],"brands_json":r["old_brands_json"],"labeled_by":r["old_labeled_by"],"note":r["old_note"],"labeled_at":r["old_labeled_at"]}
                                conn.execute("INSERT INTO video_label_audit(video_id,old_value_json,new_value_json,actor,changed_at) VALUES(?,?,?,?,?)",(vid,json_dump(old_obj),None,actor,at))
                                conn.execute("DELETE FROM video_labels WHERE video_id=?",(vid,))
                            done+=1;touched.add(str(r["channel_id"]));continue
                        if not r["suggested_role"]:raise ValueError(f"视频 {vid} 没有系统分类")
                        if action=="confirm_system":
                            use_role=str(r["suggested_role"]);bs=json_load(r["system_brands_json"],[]);note="人工复核确认系统分类"
                        else:
                            use_role=role or str(r["suggested_role"]);bs=use_brands;note="人工复核修正系统分类"
                        old_obj=None
                        if r["old_video_id"]:old_obj={"video_id":vid,"human_role":r["old_human_role"],"brands_json":r["old_brands_json"],"labeled_by":r["old_labeled_by"],"note":r["old_note"],"labeled_at":r["old_labeled_at"]}
                        new_obj={"video_id":vid,"human_role":use_role,"brands":bs,"labeled_by":actor,"note":note,"labeled_at":at}
                        conn.execute("INSERT INTO video_labels(video_id,human_role,brands_json,labeled_by,note,labeled_at) VALUES(?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET human_role=excluded.human_role,brands_json=excluded.brands_json,labeled_by=excluded.labeled_by,note=excluded.note,labeled_at=excluded.labeled_at",(vid,use_role,json_dump(bs),actor,note,at))
                        conn.execute("INSERT INTO video_label_audit(video_id,old_value_json,new_value_json,actor,changed_at) VALUES(?,?,?,?,?)",(vid,json_dump(old_obj) if old_obj else None,json_dump(new_obj),actor,at))
                        done+=1;touched.add(str(r["channel_id"]))
                    except Exception as e:errors.append(f"{vid}: {type(e).__name__}: {e}")
                if touched:
                    cm=','.join('?' for _ in touched);conn.execute(f"UPDATE creators SET classification_data_at=? WHERE channel_id IN ({cm})",tuple([at]+sorted(touched)))
            conn.commit()
        return {"processed":done,"requested":len(ids),"errors":errors}

    def _backup_dir(self) -> Path:
        p=Path(self.db_path).resolve()
        root=p.parent.parent if p.parent.name.lower()=="data" else p.parent
        d=root/"backups";d.mkdir(parents=True,exist_ok=True);return d

    def list_backups(self) -> list[dict[str, Any]]:
        d=self._backup_dir();out=[]
        for f in sorted(d.glob("*.sqlite"),key=lambda x:x.stat().st_mtime,reverse=True):
            out.append({"name":f.name,"path":str(f),"size_bytes":f.stat().st_size,"modified_at":datetime.fromtimestamp(f.stat().st_mtime,timezone.utc).isoformat().replace('+00:00','Z')})
        return out

    def database_health(self, *, full: bool = False, run_check: bool = True) -> dict[str, Any]:
        p=Path(self.db_path);wal=Path(str(p)+"-wal");shm=Path(str(p)+"-shm")
        with connect(self.db_path) as conn:
            check=conn.execute("PRAGMA integrity_check" if full else "PRAGMA quick_check").fetchone()[0] if run_check else "not_run"
            page_count=int(conn.execute("PRAGMA page_count").fetchone()[0]);page_size=int(conn.execute("PRAGMA page_size").fetchone()[0]);free=int(conn.execute("PRAGMA freelist_count").fetchone()[0])
            journal=conn.execute("PRAGMA journal_mode").fetchone()[0]
            counts={t:int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in ["creators","videos","video_snapshots","creator_snapshots","discovery_hits","sync_runs"]}
            last_write=conn.execute("SELECT MAX(x) FROM (SELECT MAX(COALESCE(last_sync_attempt_at,last_synced_at,created_at)) x FROM creators UNION ALL SELECT MAX(captured_at) FROM video_snapshots UNION ALL SELECT MAX(found_at) FROM discovery_hits)").fetchone()[0]
        return {"ok":(str(check).lower()=="ok" if run_check else None),"check":check,"db_path":str(p.resolve()),"db_size_bytes":p.stat().st_size if p.exists() else 0,"wal_size_bytes":wal.stat().st_size if wal.exists() else 0,"shm_size_bytes":shm.stat().st_size if shm.exists() else 0,"page_count":page_count,"page_size":page_size,"freelist_pages":free,"estimated_free_bytes":free*page_size,"journal_mode":journal,"counts":counts,"last_write_at":last_write,"backups":self.list_backups()[:20]}

    def backup_database(self, *, note: str = "manual", destination: str | Path | None = None) -> dict[str, Any]:
        dest=Path(destination) if destination else self._backup_dir()/f"creator_hub_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite"
        dest=dest.resolve();dest.parent.mkdir(parents=True,exist_ok=True)
        if dest==Path(self.db_path).resolve():raise ValueError("backup destination cannot be the live database")
        started=now_utc()
        with connect(self.db_path) as conn:
            rid=conn.execute("INSERT INTO maintenance_runs(kind,started_at,status,message) VALUES('backup',?,'running',?)",(started,note)).lastrowid;conn.commit()
        try:
            src=sqlite3.connect(self.db_path);dst=sqlite3.connect(dest)
            try: src.backup(dst);dst.commit();check=dst.execute("PRAGMA quick_check").fetchone()[0]
            finally: dst.close();src.close()
            if str(check).lower()!='ok':raise RuntimeError(f"backup quick_check failed: {check}")
            size=dest.stat().st_size
            with connect(self.db_path) as conn:
                conn.execute("INSERT OR REPLACE INTO backup_registry(file_path,created_at,size_bytes,quick_check,source_db,note) VALUES(?,?,?,?,?,?)",(str(dest),now_utc(),size,str(check),str(Path(self.db_path).resolve()),note))
                conn.execute("UPDATE maintenance_runs SET finished_at=?,status='complete',message=? WHERE id=?",(now_utc(),f"{dest.name}; {size} bytes",rid));conn.commit()
            return {"ok":True,"path":str(dest),"name":dest.name,"size_bytes":size,"quick_check":check}
        except Exception as e:
            with connect(self.db_path) as conn:
                conn.execute("UPDATE maintenance_runs SET finished_at=?,status='failed',message=? WHERE id=?",(now_utc(),f"{type(e).__name__}: {e}",rid));conn.commit()
            raise

    def restore_database(self, backup_path: str | Path, *, create_pre_backup: bool = True) -> dict[str, Any]:
        src_path=Path(backup_path)
        if not src_path.is_absolute(): src_path=self._backup_dir()/src_path
        src_path=src_path.resolve()
        if not src_path.exists():raise FileNotFoundError(src_path)
        probe=sqlite3.connect(src_path)
        try: check=probe.execute("PRAGMA quick_check").fetchone()[0]
        finally: probe.close()
        if str(check).lower()!='ok':raise RuntimeError(f"backup quick_check failed: {check}")
        pre=None
        if create_pre_backup: pre=self.backup_database(note="pre_restore")
        source=sqlite3.connect(src_path);target=sqlite3.connect(self.db_path)
        try: source.backup(target);target.commit()
        finally: target.close();source.close()
        init_db(self.db_path)
        # Restored DB may not know about the pre-restore safety backup; register it again.
        if pre:
            with connect(self.db_path) as conn:
                conn.execute("INSERT OR REPLACE INTO backup_registry(file_path,created_at,size_bytes,quick_check,source_db,note) VALUES(?,?,?,?,?,?)",(pre["path"],now_utc(),pre["size_bytes"],pre["quick_check"],str(Path(self.db_path).resolve()),"pre_restore"));conn.commit()
        return {"ok":True,"restored_from":str(src_path),"pre_restore_backup":pre,"health":self.database_health()}

    def _snapshot_compaction_candidates(self, conn: sqlite3.Connection, table: str, entity: str) -> int:
        return int(conn.execute(f"""WITH aged AS (SELECT id,{entity} entity,captured_at,CASE WHEN datetime(captured_at)>=datetime('now','-30 days') THEN NULL WHEN datetime(captured_at)>=datetime('now','-180 days') THEN 'D:'||date(captured_at) WHEN datetime(captured_at)>=datetime('now','-730 days') THEN 'W:'||strftime('%Y-%W',captured_at) ELSE 'M:'||strftime('%Y-%m',captured_at) END bucket FROM {table}), ranked AS (SELECT id,ROW_NUMBER() OVER(PARTITION BY entity,bucket ORDER BY datetime(captured_at) DESC,id DESC) rn FROM aged WHERE bucket IS NOT NULL) SELECT COUNT(*) FROM ranked WHERE rn>1""").fetchone()[0])

    def compact_snapshots(self, *, dry_run: bool = False, auto: bool = False) -> dict[str, Any]:
        if auto:
            with connect(self.db_path) as conn:
                row=conn.execute("SELECT value FROM meta WHERE key='last_snapshot_compaction_at'").fetchone()
            last=parse_iso(row[0]) if row else None;now=parse_iso(now_utc())
            if last and now and (now-last).total_seconds()<7*86400:return {"ok":True,"skipped":True,"reason":"last compaction < 7 days"}
        started=now_utc()
        with connect(self.db_path) as conn:
            video_candidates=self._snapshot_compaction_candidates(conn,"video_snapshots","video_id")
            creator_candidates=self._snapshot_compaction_candidates(conn,"creator_snapshots","channel_id")
            if dry_run:return {"ok":True,"dry_run":True,"video_snapshots_to_delete":video_candidates,"creator_snapshots_to_delete":creator_candidates,"total_to_delete":video_candidates+creator_candidates}
            rid=conn.execute("INSERT INTO maintenance_runs(kind,started_at,status,message) VALUES('snapshot_compaction',?,'running',?)",(started,f"video={video_candidates}; creator={creator_candidates}")).lastrowid
            for table,entity in (("video_snapshots","video_id"),("creator_snapshots","channel_id")):
                conn.execute(f"""WITH aged AS (SELECT id,{entity} entity,captured_at,CASE WHEN datetime(captured_at)>=datetime('now','-30 days') THEN NULL WHEN datetime(captured_at)>=datetime('now','-180 days') THEN 'D:'||date(captured_at) WHEN datetime(captured_at)>=datetime('now','-730 days') THEN 'W:'||strftime('%Y-%W',captured_at) ELSE 'M:'||strftime('%Y-%m',captured_at) END bucket FROM {table}), ranked AS (SELECT id,ROW_NUMBER() OVER(PARTITION BY entity,bucket ORDER BY datetime(captured_at) DESC,id DESC) rn FROM aged WHERE bucket IS NOT NULL) DELETE FROM {table} WHERE id IN (SELECT id FROM ranked WHERE rn>1)""")
            affected=video_candidates+creator_candidates
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('last_snapshot_compaction_at',?)",(now_utc(),))
            conn.execute("UPDATE maintenance_runs SET finished_at=?,status='complete',affected_rows=?,message=? WHERE id=?",(now_utc(),affected,f"deleted={affected}",rid));conn.commit()
            try: conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception: pass
        return {"ok":True,"dry_run":False,"video_snapshots_deleted":video_candidates,"creator_snapshots_deleted":creator_candidates,"total_deleted":video_candidates+creator_candidates}

    def _probe_public_channel_page(self, channel_id: str) -> dict[str, Any]:
        """Best-effort confirmation after channels.list no longer returns a channel.

        An API miss alone never becomes a policy-violation label. Terminal labels require an
        explicit public YouTube termination/deletion marker; otherwise the channel remains
        temporarily unavailable and is checked again later.
        """
        url=f"https://www.youtube.com/channel/{channel_id}"
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 YouTube-Creator-Data-Hub/3.10.3","Accept-Language":"en-US,en;q=0.9,zh-CN;q=0.7"})
        try:
            with urllib.request.urlopen(req,timeout=20) as resp:
                text=resp.read(2_000_000).decode("utf-8",errors="ignore")
        except urllib.error.HTTPError as exc:
            # YouTube may return a useful termination/deletion body together with 4xx.
            try: text=exc.read(2_000_000).decode("utf-8",errors="ignore")
            except Exception: text=""
            if not text:
                return {"status":"unavailable_pending","reason":f"公开频道页无法确认：HTTP {getattr(exc,'code','error')}","source":"public_page_http_error","terminal":False}
        except Exception as exc:
            return {"status":"unavailable_pending","reason":f"公开频道页无法确认：{type(exc).__name__}","source":"public_page_error","terminal":False}
        t=" ".join(re.sub(r"<[^>]+>"," ",text).casefold().split())
        community=[
            "terminated for violating youtube's community guidelines",
            "terminated due to multiple or severe violations of youtube's policy",
            "violating youtube’s community guidelines", "violating youtube's community guidelines",
            "违反 youtube 的《社区准则》", "违反 youtube 社区准则", "违反youtube的《社区准则》"
        ]
        copyright=[
            "terminated because we received multiple third-party claims of copyright infringement",
            "multiple copyright strikes", "copyright infringement", "因多次侵犯版权", "版权侵权"
        ]
        deleted=["this channel does not exist", "this page isn't available", "this page is not available", "该频道不存在", "此频道不存在", "此页面无法使用", "此页面不可用"]
        if any(x in t for x in community):
            return {"status":"terminated_community","reason":"YouTube 公开频道页明确显示因违反《社区准则》而终止","source":"public_page","terminal":True}
        if any(x in t for x in copyright):
            return {"status":"terminated_copyright","reason":"YouTube 公开频道页明确显示版权相关终止","source":"public_page","terminal":True}
        if any(x in t for x in deleted):
            return {"status":"deleted","reason":"YouTube 公开频道页显示频道不存在/页面不可用","source":"public_page","terminal":True}
        return {"status":"unavailable_pending","reason":"YouTube API 未返回频道；公开页面未提供可可靠识别的终止原因","source":"public_page","terminal":False}

    def _set_creator_availability(self, cid: str, status: str, reason: str, source: str, *, terminal: bool=False, failures: int | None=None) -> None:
        at=now_utc()
        with connect(self.db_path) as conn:
            vals=[status,reason[:1000],source[:80],at]; extra=""
            if failures is not None:
                extra=",availability_failures=?"; vals.append(int(failures))
            if terminal:
                extra += ",monitoring_enabled=0,sync_suspended=1,next_retry_at=NULL,next_sync_at=NULL"
            vals.append(cid)
            conn.execute(f"UPDATE creators SET availability_status=?,availability_reason=?,availability_source=?,availability_checked_at=?{extra} WHERE channel_id=?",tuple(vals));conn.commit()

    def set_creator_availability_override(self, channel_ids: list[str], *, availability_status: str="", content_status: str="", monitoring_policy: str="", note: str="", actor: str="dashboard") -> dict[str, Any]:
        """Apply an auditable human override without destroying the system-detected channel state."""
        ids=list(dict.fromkeys(str(x).strip() for x in channel_ids if str(x).strip()))
        allowed_av={"","available","unavailable_pending","terminated_community","terminated_copyright","deleted","unavailable_unknown"}
        allowed_content={"","normal","no_public_videos","history_cleared","long_inactive","unknown"}
        allowed_policy={"","normal","low_frequency","recovery_only","paused","stopped"}
        availability_status=str(availability_status or "");content_status=str(content_status or "");monitoring_policy=str(monitoring_policy or "")
        if availability_status not in allowed_av: raise ValueError("unsupported manual availability status")
        if content_status not in allowed_content: raise ValueError("unsupported manual content status")
        if monitoring_policy not in allowed_policy: raise ValueError("unsupported manual monitoring policy")
        at=now_utc(); processed=0
        with connect(self.db_path) as conn:
            for cid in ids:
                exists=conn.execute("SELECT 1 FROM creators WHERE channel_id=?",(cid,)).fetchone()
                if not exists: continue
                old=conn.execute("SELECT availability_status,content_status,monitoring_policy,note,actor,updated_at FROM creator_availability_overrides WHERE channel_id=?",(cid,)).fetchone()
                old_json=json_dump(dict(old)) if old else '{}'
                new={"availability_status":availability_status or None,"content_status":content_status or None,"monitoring_policy":monitoring_policy or None,"note":str(note or "")[:1000],"actor":str(actor or "dashboard")[:120],"updated_at":at}
                conn.execute("""INSERT INTO creator_availability_overrides(channel_id,availability_status,content_status,monitoring_policy,note,actor,updated_at) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(channel_id) DO UPDATE SET availability_status=excluded.availability_status,content_status=excluded.content_status,monitoring_policy=excluded.monitoring_policy,note=excluded.note,actor=excluded.actor,updated_at=excluded.updated_at""",
                    (cid,new["availability_status"],new["content_status"],new["monitoring_policy"],new["note"],new["actor"],at))
                conn.execute("INSERT INTO creator_availability_override_audit(channel_id,old_json,new_json,actor,changed_at) VALUES(?,?,?,?,?)",(cid,old_json,json_dump(new),new["actor"],at))
                terminal=availability_status in {"terminated_community","terminated_copyright","deleted","unavailable_unknown"}
                if terminal or monitoring_policy in {"stopped","recovery_only"}:
                    conn.execute("UPDATE creators SET monitoring_enabled=0,sync_suspended=1,next_retry_at=NULL,next_sync_at=NULL WHERE channel_id=?",(cid,))
                elif monitoring_policy=="paused":
                    conn.execute("UPDATE creators SET sync_suspended=1,next_retry_at=NULL WHERE channel_id=?",(cid,))
                elif monitoring_policy=="low_frequency":
                    conn.execute("UPDATE creators SET monitoring_enabled=1,priority='archive',sync_suspended=0 WHERE channel_id=?",(cid,))
                elif monitoring_policy=="normal" or availability_status=="available":
                    conn.execute("UPDATE creators SET monitoring_enabled=1,sync_suspended=0 WHERE channel_id=?",(cid,))
                processed+=1
            conn.commit()
        for cid in ids:
            try:
                if availability_status: self.contracts.assert_value("creator",cid,"availability.status","human",availability_status,source_ref=actor,observed_at=at)
                if content_status: self.contracts.assert_value("creator",cid,"content.status","human",content_status,source_ref=actor,observed_at=at)
                if monitoring_policy: self.contracts.assert_value("creator",cid,"monitoring.policy","human",monitoring_policy,source_ref=actor,observed_at=at)
            except Exception:
                pass
        return {"requested":len(ids),"processed":processed,"availability_status":availability_status,"content_status":content_status,"monitoring_policy":monitoring_policy}

    def clear_creator_availability_override(self, channel_ids: list[str], *, actor: str="dashboard") -> dict[str, Any]:
        ids=list(dict.fromkeys(str(x).strip() for x in channel_ids if str(x).strip()));at=now_utc();processed=0
        with connect(self.db_path) as conn:
            for cid in ids:
                old=conn.execute("SELECT availability_status,content_status,monitoring_policy,note,actor,updated_at FROM creator_availability_overrides WHERE channel_id=?",(cid,)).fetchone()
                if not old: continue
                conn.execute("INSERT INTO creator_availability_override_audit(channel_id,old_json,new_json,actor,changed_at) VALUES(?,?,?,?,?)",(cid,json_dump(dict(old)),'{}',str(actor or 'dashboard')[:120],at))
                conn.execute("DELETE FROM creator_availability_overrides WHERE channel_id=?",(cid,));processed+=1
            conn.commit()
        return {"requested":len(ids),"processed":processed}

    def recheck_channel_availability(self, channel_ids: list[str], *, restore_monitoring: bool=False, progress=None) -> dict[str, Any]:
        ids=list(dict.fromkeys(str(x).strip() for x in channel_ids if str(x).strip()));results=[];errors=[]
        if progress: progress(stage="重新检测频道状态",message=f"准备检测 {len(ids)} 个频道",current=0,total=len(ids))
        for idx,cid in enumerate(ids,1):
            try:
                try:
                    row=self.fetch_channel(cid)
                    self.upsert_creator(row, monitoring=(True if restore_monitoring else None), source="availability_recheck")
                    with connect(self.db_path) as conn:
                        conn.execute("UPDATE creators SET availability_status='available',availability_reason=NULL,availability_source='youtube_api',availability_checked_at=?,availability_failures=0,sync_suspended=0,next_retry_at=NULL,last_sync_error=NULL,sync_error_type=NULL WHERE channel_id=?",(now_utc(),cid))
                        if restore_monitoring: conn.execute("UPDATE creators SET monitoring_enabled=1 WHERE channel_id=?",(cid,))
                        conn.commit()
                    results.append({"channel_id":cid,"availability_status":"available","restored":bool(restore_monitoring)})
                except Exception as exc:
                    if self._sync_error_category(exc)!="channel_unavailable": raise
                    probe=self._probe_public_channel_page(cid)
                    with connect(self.db_path) as conn:
                        rr=conn.execute("SELECT availability_failures FROM creators WHERE channel_id=?",(cid,)).fetchone();fails=int(rr[0] or 0)+1 if rr else 1
                    status=str(probe.get("status") or "unavailable_pending");terminal=bool(probe.get("terminal"))
                    if status=="unavailable_pending" and fails>=3:
                        status="unavailable_unknown";terminal=True;probe["reason"]="连续 3 次检测均无法通过 API 获取频道，公开页面也未给出明确终止原因"
                    self._set_creator_availability(cid,status,str(probe.get("reason") or ""),str(probe.get("source") or "recheck"),terminal=terminal,failures=fails)
                    results.append({"channel_id":cid,"availability_status":status,"reason":probe.get("reason"),"terminal":terminal})
            except Exception as exc:
                errors.append(f"{cid}: {type(exc).__name__}: {exc}")
            if progress: progress(stage="重新检测频道状态",message=f"已检测 {idx}/{len(ids)} · 错误 {len(errors)}",current=idx,total=len(ids),errors_count=len(errors))
        return {"requested":len(ids),"processed":len(results),"results":results,"errors":errors}

    @staticmethod
    def _sync_error_category(exc: Exception) -> str:
        msg=f"{type(exc).__name__}: {exc}".lower();reason=str(getattr(exc,"reason","") or "").lower()
        if isinstance(exc,QuotaBudgetExceeded) or reason in {"quotaexceeded","dailylimitexceeded"} or "quota" in msg or "budget" in msg:return "quota"
        if any(x in msg for x in ["api key","keyinvalid","forbidden","unauthorized","401","403"]):return "auth"
        if any(x in msg for x in ["timed out","timeout","temporary failure","connection","network","urlerror"]):return "network"
        if any(x in msg for x in ["not found","404","channel not found","未找到频道"]):return "channel_unavailable"
        if isinstance(exc,YouTubeAPIError):return "youtube_api"
        return "unknown"

    def _record_sync_success(self, cid: str, *, mode: str, attempt_id: int | None, videos: int, priority: str) -> None:
        at=now_utc();cur=parse_iso(at);hours=self._sync_due_hours(priority,mode);nxt=(cur+timedelta(hours=hours)).isoformat().replace('+00:00','Z') if cur else None
        with connect(self.db_path) as conn:
            conn.execute("UPDATE creators SET last_synced_at=?,last_sync_attempt_at=?,last_sync_status='complete',last_sync_error=NULL,sync_error_type=NULL,consecutive_sync_failures=0,next_retry_at=NULL,next_sync_at=?,sync_suspended=0,availability_status='available',availability_reason=NULL,availability_source='youtube_api',availability_checked_at=?,availability_failures=0 WHERE channel_id=?",(at,at,nxt,at,cid))
            if attempt_id:conn.execute("UPDATE creator_sync_attempts SET finished_at=?,status='complete',videos_processed=? WHERE id=?",(at,int(videos),attempt_id))
            conn.commit()

    def _record_sync_failure(self, cid: str, *, mode: str, attempt_id: int | None, exc: Exception) -> dict[str, Any]:
        at=now_utc();cat=self._sync_error_category(exc);msg=f"{type(exc).__name__}: {exc}"[:3000]
        with connect(self.db_path) as conn:
            row=conn.execute("SELECT consecutive_sync_failures,availability_failures FROM creators WHERE channel_id=?",(cid,)).fetchone();fail=int(row[0] or 0)+1 if row else 1;availability_fail=int(row[1] or 0) if row else 0
        availability=None
        if cat=="channel_unavailable":
            probe=self._probe_public_channel_page(cid);availability_fail+=1
            av_status=str(probe.get("status") or "unavailable_pending");terminal=bool(probe.get("terminal"))
            if av_status=="unavailable_pending" and availability_fail>=3:
                av_status="unavailable_unknown";terminal=True;probe["reason"]="连续 3 次检测均无法通过 API 获取频道，公开页面也未给出明确终止原因"
            self._set_creator_availability(cid,av_status,str(probe.get("reason") or ""),str(probe.get("source") or "sync_failure"),terminal=terminal,failures=availability_fail)
            availability={"availability_status":av_status,"availability_reason":probe.get("reason"),"terminal":terminal}
        suspend=1 if (cat=="channel_unavailable" and availability and availability.get("terminal")) or (fail>=5 and cat not in {"quota","auth"}) else 0
        delays={1:1,2:6,3:24,4:48};delay=delays.get(fail,72)
        if cat=="quota":delay=6
        if cat=="auth":delay=24
        if cat=="channel_unavailable":delay=24
        cur=parse_iso(at);retry=(cur+timedelta(hours=delay)).isoformat().replace('+00:00','Z') if cur and not suspend else None
        with connect(self.db_path) as conn:
            conn.execute("UPDATE creators SET last_sync_attempt_at=?,last_sync_status='failed',last_sync_error=?,sync_error_type=?,consecutive_sync_failures=?,next_retry_at=?,sync_suspended=? WHERE channel_id=?",(at,msg,cat,fail,retry,suspend,cid))
            if attempt_id:conn.execute("UPDATE creator_sync_attempts SET finished_at=?,status='failed',error_type=?,error_message=? WHERE id=?",(at,cat,msg,attempt_id))
            conn.commit()
        return {"error_type":cat,"failures":fail,"next_retry_at":retry,"sync_suspended":bool(suspend),**(availability or {})}

    def monitoring_health(self, *, page: int = 1, page_size: int = 30, limit: int | None = None,
                          search: str = "", filters: dict[str, Any] | None = None,
                          sort: str = "attention", direction: str = "asc") -> dict[str, Any]:
        if limit is not None: page_size=int(limit)
        page=max(1,int(page or 1)); page_size=max(1,min(5000,int(page_size or 30)))
        search=str(search or "").strip().lower(); filters=dict(filters or {}); direction="desc" if str(direction).lower()=="desc" else "asc"
        now=parse_iso(now_utc());rows=[];counts={"normal":0,"due":0,"failed":0,"suspended":0,"stale":0,"retry_wait":0,"not_applicable":0}
        availability_counts={"available":0,"unavailable_pending":0,"terminated_community":0,"terminated_copyright":0,"deleted":0,"unavailable_unknown":0}
        terminal={"terminated_community","terminated_copyright","deleted","unavailable_unknown"}
        with connect(self.db_path) as conn:
            data=[dict(r) for r in conn.execute("""SELECT c.channel_id,c.channel_title,c.priority,c.monitoring_enabled,c.last_synced_at,c.last_sync_attempt_at,c.last_sync_status,c.last_sync_error,c.sync_error_type,c.consecutive_sync_failures,c.next_sync_at,c.next_retry_at,c.sync_suspended,c.channel_data_at,c.video_metrics_at,c.classification_data_at,c.contact_scraped_at,c.availability_status,c.availability_reason,c.availability_source,c.availability_checked_at,c.availability_failures,
                       o.availability_status AS manual_availability_status,o.content_status AS manual_content_status,o.monitoring_policy AS manual_monitoring_policy,o.note AS manual_availability_note,o.actor AS manual_availability_actor,o.updated_at AS manual_availability_updated_at
                FROM creators c LEFT JOIN creator_availability_overrides o ON o.channel_id=c.channel_id
                WHERE c.monitoring_enabled=1 OR COALESCE(c.availability_status,'available') IN ('unavailable_pending','terminated_community','terminated_copyright','deleted','unavailable_unknown') OR o.channel_id IS NOT NULL""").fetchall()]
        for r in data:
            system_av=r.get("availability_status") or "available"
            manual_av=r.get("manual_availability_status") or ""
            av=manual_av or system_av
            availability_counts[av]=availability_counts.get(av,0)+1
            last=parse_iso(r.get("last_synced_at"));hours=self._sync_due_hours(r.get("priority") or "normal","incremental");age=(now-last).total_seconds()/3600 if now and last else None
            retry=parse_iso(r.get("next_retry_at"));due=not last or (age is not None and age>=hours);stale=not last or (age is not None and age>hours+6)
            manual_policy=r.get("manual_monitoring_policy") or ""
            if av in terminal or manual_policy in {"stopped","recovery_only"} or not r.get("monitoring_enabled"):state="not_applicable";reason="频道已停止常规监控；不会进入普通同步重试队列"
            elif r.get("sync_suspended"):state="suspended";reason="连续失败达到暂停阈值；可恢复后重试"
            elif r.get("last_sync_status")=="failed" and retry and now and retry>now:state="retry_wait";reason="上次同步失败，尚未到 next_retry_at"
            elif r.get("last_sync_status")=="failed":state="failed";reason="上次同步失败且已到可再次尝试时间"
            elif stale:state="stale";reason=f"超过 {hours:g} 小时刷新周期并越过 6 小时调度宽限，或从未成功同步"
            elif due:state="due";reason=f"已达到 {hours:g} 小时刷新周期，等待常规同步"
            else:state="normal";reason=f"最近成功同步尚未达到 {hours:g} 小时刷新周期"
            channel_reason={
                "available":"频道可通过 YouTube API 正常获取",
                "unavailable_pending":r.get("availability_reason") or "API 暂时无法取得频道，等待再次确认",
                "terminated_community":r.get("availability_reason") or "频道因社区准则终止",
                "terminated_copyright":r.get("availability_reason") or "频道因版权问题终止",
                "deleted":r.get("availability_reason") or "频道已删除/不存在",
                "unavailable_unknown":r.get("availability_reason") or "多次无法取得频道且原因未知",
            }.get(av,r.get("availability_reason") or av)
            counts[state]=counts.get(state,0)+1
            r["health_state"]=state;r["health_state_reason"]=reason;r["channel_status"]=av;r["system_channel_status"]=system_av;r["channel_status_source"]="人工覆盖" if manual_av else "系统检测";r["channel_status_reason"]=(r.get("manual_availability_note") or channel_reason) if manual_av else channel_reason
            r["content_status"]=r.get("manual_content_status") or "normal"
            r["monitoring_policy"]=manual_policy or ("normal" if r.get("monitoring_enabled") else "stopped")
            r["monitoring_state"]="monitoring" if r.get("monitoring_enabled") and manual_policy not in {"stopped","recovery_only","paused"} else "stopped";r["due_hours"]=hours;r["age_hours"]=round(age,1) if age is not None else None
            rows.append(r)
        # Filter after deriving effective/manual-aware statuses.  This preserves the same semantics
        # for API, table filters, cards and exports without duplicating status logic in JS.
        def match(r: dict[str, Any]) -> bool:
            if search and search not in f"{r.get('channel_title') or ''} {r.get('channel_id') or ''}".lower(): return False
            exact={"channel_status":"channel_status","health_state":"health_state","monitoring_state":"monitoring_state","priority":"priority","content_status":"content_status","monitoring_policy":"monitoring_policy"}
            for fk,rk in exact.items():
                want=str(filters.get(fk) or "")
                if want and str(r.get(rk) or "")!=want:return False
            return True
        filtered=[r for r in rows if match(r)]
        attention_order={"failed":0,"retry_wait":1,"stale":2,"due":3,"suspended":4,"not_applicable":5,"normal":6}
        channel_order={"terminated_community":0,"terminated_copyright":1,"deleted":2,"unavailable_unknown":3,"unavailable_pending":4,"available":5}
        priority_order={"high":0,"normal":1,"low":2,"archive":3}
        def val(r: dict[str,Any]):
            if sort=="attention":return (attention_order.get(r.get("health_state"),9),-(r.get("consecutive_sync_failures") or 0),r.get("last_synced_at") or "")
            if sort=="channel_title":return str(r.get("channel_title") or r.get("channel_id") or "").lower()
            if sort=="channel_status":return channel_order.get(r.get("channel_status"),9)
            if sort=="health_state":return attention_order.get(r.get("health_state"),9)
            if sort=="priority":return priority_order.get(r.get("priority"),9)
            if sort=="age_hours":return float(r.get("age_hours") if r.get("age_hours") is not None else -1)
            if sort=="failures":return int(r.get("consecutive_sync_failures") or 0)
            if sort in {"last_synced_at","next_sync_at","next_retry_at"}:return str(r.get(sort) or "")
            return str(r.get(sort) or "")
        filtered.sort(key=val,reverse=(direction=="desc"))
        total=len(filtered); pages=max(1,(total+page_size-1)//page_size); page=min(page,pages); start=(page-1)*page_size
        return {"counts":counts,"availability_counts":availability_counts,"total":total,"rows":filtered[start:start+page_size],"page":page,"page_size":page_size,"pages":pages,"generated_at":now_utc(),"search":search,"filters":filters,"sort":sort,"dir":direction}

    def data_freshness(self, channel_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            r=conn.execute("SELECT channel_id,channel_data_at,video_metrics_at,classification_data_at,contact_scraped_at,last_synced_at FROM creators WHERE channel_id=?",(channel_id,)).fetchone()
            disc=conn.execute("SELECT last_seen_at FROM creator_discovery_summary WHERE channel_id=?",(channel_id,)).fetchone()
        if not r:return {}
        def item(at):
            d=parse_iso(at);n=parse_iso(now_utc());age=(n-d).total_seconds()/3600 if d and n else None
            return {"at":at,"age_hours":round(age,1) if age is not None else None}
        return {"channel":item(r["channel_data_at"]),"video_metrics":item(r["video_metrics_at"]),"classification":item(r["classification_data_at"]),"contact":item(r["contact_scraped_at"]),"sync":item(r["last_synced_at"]),"discovery":item(disc["last_seen_at"] if disc else None)}

    # ---------- query helpers ----------
    def status(self) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            creators = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
            monitored = conn.execute("SELECT COUNT(*) FROM creators WHERE monitoring_enabled=1").fetchone()[0]
            videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            snapshots = conn.execute("SELECT COUNT(*) FROM video_snapshots").fetchone()[0]
            pending = conn.execute("""SELECT COUNT(*) FROM label_suggestions s LEFT JOIN video_labels l ON l.video_id=s.video_id WHERE l.video_id IS NULL AND (s.suggested_role='pending' OR s.confidence='review')""").fetchone()[0]
            last_sync = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
            q = conn.execute("SELECT estimated_units FROM quota_daily WHERE quota_date=date('now')").fetchone()
        return {"creators": creators, "monitored": monitored, "videos": videos, "video_snapshots": snapshots, "classification_review": pending, "quota_today_estimated": int(q[0]) if q else 0, "last_sync": dict(last_sync) if last_sync else None}

    def list_creators(self, monitored_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            sql = "SELECT * FROM creators"
            params: list[Any] = []
            if monitored_only:
                sql += " WHERE monitoring_enabled=1"
            sql += " ORDER BY COALESCE(last_synced_at,discovered_at,created_at) DESC LIMIT ?"
            params.append(limit)
            return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]

    def list_pending_labels(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT v.video_id,v.title,v.channel_id,v.published_at,v.current_views,s.suggested_role,s.brands_json,s.confidence,s.evidence_json
                FROM videos v JOIN label_suggestions s ON s.video_id=v.video_id LEFT JOIN video_labels l ON l.video_id=v.video_id
                WHERE l.video_id IS NULL AND (s.suggested_role='pending' OR s.confidence='review') ORDER BY v.published_at DESC LIMIT ?""", (limit,)
            ).fetchall()
            out=[]
            for r in rows:
                d=dict(r); d["brands"]=json_load(d.pop("brands_json"),[]); d["evidence"]=json_load(d.pop("evidence_json"),[]); out.append(d)
            return out
