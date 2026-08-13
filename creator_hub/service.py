from __future__ import annotations

import json
import re
import urllib.request
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
        self.brand_cfg = load_brands(brands_path)
        init_db(self.db_path)
        self._api: YouTubeAPI | None = None
        self.unit_budget = unit_budget

    @property
    def api(self) -> YouTubeAPI:
        if self._api is None:
            self._api = YouTubeAPI(self.db_path, self.settings, unit_budget=self.unit_budget)
        return self._api

    # ---------- normalization / persistence ----------
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
            old = conn.execute("SELECT monitoring_enabled, priority, created_at, discovered_at, source FROM creators WHERE channel_id=?", (row["channel_id"],)).fetchone()
            mon = int(monitoring) if monitoring is not None else (int(old["monitoring_enabled"]) if old else 0)
            pr = priority or (old["priority"] if old else "normal")
            created = old["created_at"] if old else captured_at
            discovered = old["discovered_at"] if old and old["discovered_at"] else captured_at
            src = source or (old["source"] if old else "youtube")
            conn.execute(
                """INSERT INTO creators(channel_id, channel_title, handle, channel_url, description, country_api, published_at,
                subscriber_count, channel_view_count, channel_video_count, hidden_subscriber_count, uploads_playlist_id,
                thumbnail_url, monitoring_enabled, priority, source, discovered_at, created_at, last_synced_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(channel_id) DO UPDATE SET
                  channel_title=excluded.channel_title, handle=excluded.handle, channel_url=excluded.channel_url,
                  description=excluded.description, country_api=excluded.country_api, published_at=excluded.published_at,
                  subscriber_count=excluded.subscriber_count, channel_view_count=excluded.channel_view_count,
                  channel_video_count=excluded.channel_video_count, hidden_subscriber_count=excluded.hidden_subscriber_count,
                  uploads_playlist_id=excluded.uploads_playlist_id, thumbnail_url=excluded.thumbnail_url,
                  monitoring_enabled=excluded.monitoring_enabled, priority=excluded.priority, source=excluded.source,
                  last_synced_at=excluded.last_synced_at""",
                (
                    row["channel_id"], row.get("channel_title"), row.get("handle"), row.get("channel_url"), row.get("description"),
                    row.get("country_api"), row.get("published_at"), row.get("subscriber_count"), row.get("channel_view_count"),
                    row.get("channel_video_count"), row.get("hidden_subscriber_count"), row.get("uploads_playlist_id"),
                    row.get("thumbnail_url"), mon, pr, src, discovered, created, captured_at,
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
                 from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
        """Search related videos first, then resolve the creators that published them.

        Web search is preferred (related-video to creator discovery) and does not spend search.list quota. API search remains a fallback.
        Discovery results are persisted in discovery_hits but do not enter the creator library unless add=True.
        """
        max_results = max(1, min(int(max_results), 500))
        found_at = now_utc(); candidates: list[dict[str, Any]] = []
        source = search_source.lower().replace("-", "_")
        if source in {"web", "youtube_web_search"}:
            try:
                raw = youtube_web_search(query, max_results=max_results, timeout=int(self.settings["api"].get("timeout_seconds", 30)))
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
                """INSERT OR IGNORE INTO discovery_hits(query,source,rank,video_id,channel_id,channel_title,channel_url,title,published_at,
                   views,likes,comments,subscribers,country_resolved,country_source,pre_score,opportunity_tier,engagement_rate,comment_rate,
                   view_sub_ratio,relative_velocity,found_at,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(c["query"],c["source"],c.get("rank"),c.get("video_id"),c.get("channel_id"),c.get("channel_title"),c.get("channel_url"),c.get("title"),c.get("published_at"),
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
        with connect(self.db_path) as conn:
            conn.execute("UPDATE creators SET last_synced_at=? WHERE channel_id=?",(now_utc(),cid)); conn.commit()
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

    def sync_creator(self, ref: str, *, mode: str = "incremental", metric_days: int | None = None, all_videos: bool = False, priority: str | None = None) -> dict[str, Any]:
        mode = mode.replace("_", "-")
        cid = self.resolve_channel_id(ref)
        row = self.fetch_channel(cid)
        with connect(self.db_path) as conn:
            old = conn.execute("SELECT monitoring_enabled,priority FROM creators WHERE channel_id=?", (cid,)).fetchone()
        self.upsert_creator(row, monitoring=bool(old["monitoring_enabled"]) if old else True, priority=priority or (old["priority"] if old else "normal"), source="sync")
        processed = 0
        if mode in {"full-history", "full"}:
            ids, _ = self._playlist_video_ids(cid, full=True)
            processed += self.hydrate_videos(ids)
        elif mode in {"incremental", "new"}:
            ids, _ = self._playlist_video_ids(cid, full=False)
            processed += self.hydrate_videos(ids)
            # Also refresh recent known videos so current metrics stay fresh.
            processed += self.refresh_metrics(cid, days=metric_days, all_videos=False)
        elif mode in {"metrics-only", "metrics"}:
            processed += self.refresh_metrics(cid, days=metric_days, all_videos=all_videos)
        elif mode in {"channel-only", "channel"}:
            pass
        else:
            raise ValueError(f"未知同步模式：{mode}")
        with connect(self.db_path) as conn:
            conn.execute("UPDATE creators SET last_synced_at=? WHERE channel_id=?", (now_utc(), cid))
            conn.commit()
        return {"channel_id": cid, "mode": mode, "videos_processed": processed}

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

    def sync_all(self, *, mode: str = "incremental", priority: str | None = None, metric_days: int | None = None, all_videos: bool = False, limit: int | None = None) -> dict[str, Any]:
        started = now_utc()
        with connect(self.db_path) as conn:
            run_id = conn.execute("INSERT INTO sync_runs(mode,target,started_at,status) VALUES(?,?,?,?)", (mode, priority or "all_monitored", started, "running")).lastrowid
            sql = "SELECT channel_id FROM creators WHERE monitoring_enabled=1"
            params: list[Any] = []
            if priority:
                sql += " AND priority=?"
                params.append(priority)
            sql += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 WHEN 'low' THEN 2 ELSE 3 END, COALESCE(last_synced_at,'') ASC"
            if limit:
                sql += " LIMIT ?"
                params.append(limit)
            channels = [r[0] for r in conn.execute(sql, tuple(params)).fetchall()]
            conn.commit()
        creators_done = 0
        videos_done = 0
        errors: list[str] = []
        try:
            for cid in channels:
                try:
                    res = self.sync_creator(cid, mode=mode, metric_days=metric_days, all_videos=all_videos)
                    creators_done += 1
                    videos_done += int(res["videos_processed"])
                except (YouTubeAPIError, QuotaBudgetExceeded) as e:
                    errors.append(f"{cid}: {e}")
                    if isinstance(e, QuotaBudgetExceeded) or getattr(e, "reason", None) in {"quotaExceeded", "dailyLimitExceeded"}:
                        break
                except Exception as e:
                    errors.append(f"{cid}: {type(e).__name__}: {e}")
            status = "complete" if not errors else ("partial" if creators_done else "failed")
        except Exception as e:
            status = "failed"
            errors.append(str(e))
        units = self.api.usage.units if self._api else 0
        with connect(self.db_path) as conn:
            conn.execute("UPDATE sync_runs SET finished_at=?,status=?,creators_processed=?,videos_processed=?,quota_units=?,message=? WHERE id=?",
                         (now_utc(), status, creators_done, videos_done, units, "\n".join(errors)[:10000], run_id))
            conn.commit()
        return {"run_id": run_id, "status": status, "creators_processed": creators_done, "videos_processed": videos_done, "quota_units": units, "errors": errors}

    # ---------- offline classification ----------
    def reclassify_videos(self, *, only_missing: bool = False, limit: int | None = None, batch_size: int = 2000) -> dict[str, Any]:
        """Re-run the deterministic UgPhone/competitor/daily classifier from stored metadata.

        No YouTube API request is made. Human corrections in video_labels are not
        changed; only label_suggestions is refreshed.
        """
        processed = 0
        offset = 0
        while True:
            with connect(self.db_path) as conn:
                sql = """SELECT v.video_id,v.title,v.description,v.tags_json
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
                payload.append((
                    r["video_id"], suggestion["suggested_role"], json_dump(suggestion.get("brands") or []),
                    suggestion["confidence"], json_dump(suggestion.get("evidence") or []),
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
                conn.commit()
            processed += len(rows)
            if only_missing:
                # Missing rows disappear from the filtered result after insertion, so keep offset at zero.
                offset = 0
            else:
                offset += len(rows)
            if len(rows) < take:
                break
        return {"videos_reclassified": processed, "only_missing": only_missing, "api_calls": 0, "rule_version": self.brand_cfg.get("rule_version")}

    # ---------- video classification / review ----------
    def classification_list(self, *, page: int = 1, page_size: int = 30, search: str = "", role: str = "", brand: str = "", conditions: list[dict[str,Any]] | None = None, sort: str = "published", direction: str = "desc") -> dict[str, Any]:
        """List all locally stored videos with system classification and optional human override.

        The classification page is an all-video management surface. "Pending review" is
        only one filter state, not the base dataset.
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
            if field=="role": return "COALESCE(l.human_role,s.suggested_role,'pending')=?",[value]
            if field=="system_role": return "COALESCE(s.suggested_role,'pending')=?",[value]
            if field=="brand": return "instr(lower(COALESCE(l.brands_json,s.brands_json,'')),?)>0",[value.lower()]
            if field=="review_status":
                if value=="pending_review": return "(l.video_id IS NULL AND (COALESCE(s.suggested_role,'pending')='pending' OR s.confidence='review'))",[]
                if value=="manual_reviewed": return "l.video_id IS NOT NULL",[]
                if value=="not_manual_reviewed": return "l.video_id IS NULL",[]
                if value=="system_only": return "(l.video_id IS NULL AND s.video_id IS NOT NULL AND COALESCE(s.suggested_role,'pending')<>'pending' AND COALESCE(s.confidence,'')<>'review')",[]
                return "1=1",[]
            if field=="confidence": return "COALESCE(s.confidence,'low')=?",[value]
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
            "published":"v.published_at", "views":"v.current_views", "creator":"c.channel_title",
            "title":"v.title", "role":"COALESCE(l.human_role,s.suggested_role,'pending')",
            "review_status":"CASE WHEN l.video_id IS NOT NULL THEN 2 WHEN COALESCE(s.suggested_role,'pending')='pending' OR s.confidence='review' THEN 1 ELSE 0 END"
        }
        order=order_map.get(sort,"v.published_at"); d="ASC" if str(direction).lower()=="asc" else "DESC"
        where_sql=" AND ".join(where)
        base_from="""FROM videos v LEFT JOIN label_suggestions s ON s.video_id=v.video_id JOIN creators c ON c.channel_id=v.channel_id LEFT JOIN video_labels l ON l.video_id=v.video_id"""
        with connect(self.db_path) as conn:
            totals=conn.execute(f"""SELECT COUNT(*) AS all_total,
                SUM(CASE WHEN s.video_id IS NOT NULL THEN 1 ELSE 0 END) AS classified_total,
                SUM(CASE WHEN l.video_id IS NULL AND (COALESCE(s.suggested_role,'pending')='pending' OR s.confidence='review') THEN 1 ELSE 0 END) AS pending_total,
                SUM(CASE WHEN l.video_id IS NOT NULL THEN 1 ELSE 0 END) AS reviewed_total
                {base_from}""").fetchone()
            total=conn.execute(f"SELECT COUNT(*) {base_from} WHERE {where_sql}",tuple(params)).fetchone()[0]
            pages=max(1,(int(total)+page_size-1)//page_size); page=min(page,pages); offset=(page-1)*page_size
            rows=conn.execute(f"""SELECT v.video_id,v.title,v.channel_id,v.published_at,v.current_views,v.current_likes,v.current_comments,
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
            x["final_role"]=x.get("human_role") or x.get("suggested_role") or "pending"
            x["manual_reviewed"]=bool(x.get("human_role"))
            x["requires_review"]=(not x["manual_reviewed"] and ((x.get("suggested_role") or "pending")=="pending" or x.get("confidence")=="review"))
            x["review_status"]="manual_reviewed" if x["manual_reviewed"] else ("pending_review" if x["requires_review"] else "system_only")
            out.append(x)
        return {
            "rows":out,"total":int(total),"page":page,"page_size":page_size,"pages":pages,
            "all_total":int(totals["all_total"] or 0),"classified_total":int(totals["classified_total"] or 0),
            "pending_total":int(totals["pending_total"] or 0),"reviewed_total":int(totals["reviewed_total"] or 0),
        }

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
        return self.label_video(video_id,use_role,brands=use_brands,actor=actor,note=note)

    def reclassify_review_queue(self, *, batch_size: int = 500) -> dict[str, Any]:
        """Re-run the current deterministic classifier for every unresolved review item.

        This is fully offline and does not consume YouTube API quota. Items that still
        have weak evidence remain in the review queue; items resolved by the current
        rules leave the queue automatically.
        """
        with connect(self.db_path) as conn:
            ids=[r[0] for r in conn.execute("""SELECT s.video_id FROM label_suggestions s LEFT JOIN video_labels l ON l.video_id=s.video_id WHERE l.video_id IS NULL AND (s.suggested_role='pending' OR s.confidence='review') ORDER BY s.video_id""").fetchall()]
        before=len(ids);processed=0
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
        with connect(self.db_path) as conn:
            after=conn.execute("""SELECT COUNT(*) FROM label_suggestions s LEFT JOIN video_labels l ON l.video_id=s.video_id WHERE l.video_id IS NULL AND (s.suggested_role='pending' OR s.confidence='review')""").fetchone()[0]
        return {"videos_reclassified":processed,"before":before,"after":int(after),"api_calls":0,"rule_version":self.brand_cfg.get("rule_version")}

    def discovery_history(self, *, page:int=1, page_size:int=30, search:str="", conditions:list[dict[str,Any]]|None=None, sort:str="score", direction:str="desc") -> dict[str,Any]:
        page=max(1,int(page or 1));page_size=max(1,min(5000,int(page_size or 30)))
        where=[];params:list[Any]=[]
        if search:
            q=f"%{search.lower()}%";where.append("(lower(COALESCE(d.query,'')) LIKE ? OR lower(COALESCE(d.channel_title,'')) LIKE ? OR lower(COALESCE(d.title,'')) LIKE ? OR lower(COALESCE(d.country_resolved,'')) LIKE ? OR lower(COALESCE(d.channel_id,'')) LIKE ?)");params.extend([q,q,q,q,q])
        def expr(cond:dict[str,Any]):
            field=str(cond.get('field') or '')
            value=str(cond.get('value') or '')
            if field=='status':
                return ("c.channel_id IS NOT NULL" if value=='library' else "c.channel_id IS NULL"),[]
            if field=='tier': return "COALESCE(d.opportunity_tier,'')=?",[value]
            if field=='country': return "COALESCE(NULLIF(c.country_resolved,''),NULLIF(d.country_resolved,''),NULLIF(c.country_api,''),'')=?",[value.upper()]
            return "1=1",[]
        conds=[c for c in (conditions or []) if c.get('field') and c.get('value')]
        if conds:
            e,p=expr(conds[0]);group=f"({e})";params.extend(p)
            for c in conds[1:]:
                e,p=expr(c);join=str(c.get('join') or 'AND').upper()
                if join=='OR':group=f"({group} OR ({e}))"
                elif join=='NOT':group=f"({group} AND NOT ({e}))"
                else:group=f"({group} AND ({e}))"
                params.extend(p)
            where.append(group)
        w=' AND '.join(where) if where else '1=1'
        sortmap={'score':'d.pre_score','found':'d.found_at','subs':'COALESCE(c.subscriber_count,d.subscribers)','views':'d.views','title':'d.channel_title'}
        order=sortmap.get(sort,'d.pre_score');d='ASC' if str(direction).lower()=='asc' else 'DESC'
        with connect(self.db_path) as conn:
            base="FROM discovery_hits d LEFT JOIN creators c ON c.channel_id=d.channel_id"
            total=conn.execute(f"SELECT COUNT(*) {base} WHERE {w}",tuple(params)).fetchone()[0]
            pages=max(1,(int(total)+page_size-1)//page_size);page=min(page,pages);offset=(page-1)*page_size
            rows=conn.execute(f"""SELECT d.*,c.channel_id AS library_channel_id,c.country_api,c.country_resolved AS library_country,c.subscriber_count AS library_subscribers {base} WHERE {w} ORDER BY {order} {d},d.found_at DESC,d.id DESC LIMIT ? OFFSET ?""",tuple(params+[page_size,offset])).fetchall()
        return {'rows':[dict(r) for r in rows],'total':int(total),'page':page,'page_size':page_size,'pages':pages}

    def evaluate_metric_spec(self, spec:dict[str,Any]) -> dict[str,Any]:
        """Evaluate an exact-date objective metric (or ratio of two objective specs) from SQLite.
        Used only for custom date ranges so the browser does not need all raw videos.
        """
        allowed_fields={'current_views','current_likes','current_comments','duration_seconds'}
        allowed_aggs={'count','sum','avg','median','min','max'}
        def side(s:dict[str,Any])->dict[str,float|None]:
            field=str(s.get('source_field') or 'current_views');agg=str(s.get('aggregation') or 'count')
            if field not in allowed_fields:raise ValueError('unsupported objective field')
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
