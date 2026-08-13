from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect, json_dump
from .service import CreatorHub
from .util import now_utc, parse_duration_seconds


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try: yield json.loads(line)
            except Exception: continue


def import_v2(hub: CreatorHub, root: str | Path, *, monitoring: bool = True) -> dict[str, Any]:
    root = Path(root)
    creator_meta_files = list(root.rglob("channel_metadata.json"))
    creators = videos = snapshots = 0
    notes: list[str] = []
    for meta_file in creator_meta_files:
        folder = meta_file.parent
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception as e:
            notes.append(f"skip {meta_file}: {e}")
            continue
        cid = meta.get("channel_id") or meta.get("id")
        if not cid:
            notes.append(f"skip {meta_file}: missing channel_id")
            continue
        row = {
            "channel_id": cid,
            "channel_title": meta.get("title") or meta.get("channel_title") or "",
            "handle": meta.get("custom_url") or meta.get("handle") or "",
            "channel_url": meta.get("canonical_url") or f"https://www.youtube.com/channel/{cid}",
            "description": meta.get("description") or "",
            "country_api": meta.get("country") or meta.get("country_api") or "",
            "published_at": meta.get("published_at") or "",
            "subscriber_count": meta.get("subscriber_count"),
            "channel_view_count": meta.get("channel_view_count"),
            "channel_video_count": meta.get("channel_video_count"),
            "hidden_subscriber_count": 1 if meta.get("hidden_subscriber_count") else 0,
            "uploads_playlist_id": meta.get("uploads_playlist") or meta.get("uploads_playlist_id") or "",
            "thumbnail_url": meta.get("thumbnail_url") or "",
        }
        hub.upsert_creator(row, monitoring=monitoring, source="v2_import", snapshot=True)
        creators += 1
        vfile = folder / "videos_classified.jsonl"
        if vfile.exists():
            for item in _read_jsonl(vfile):
                vid = item.get("video_id")
                if not vid: continue
                collected = item.get("collected_at_utc") or item.get("last_metric_at") or now_utc()
                vrow = {
                    "video_id": vid,
                    "channel_id": item.get("channel_id") or cid,
                    "title": item.get("title") or "",
                    "description": item.get("description") or "",
                    "tags": item.get("tags") or [],
                    "published_at": item.get("published_at") or "",
                    "duration_iso8601": item.get("duration_iso8601") or item.get("duration_iso") or "",
                    "duration_seconds": item.get("duration_seconds") if item.get("duration_seconds") is not None else parse_duration_seconds(item.get("duration_iso8601")),
                    "live_broadcast_content": item.get("live_broadcast_content") or "none",
                    "category_id": item.get("category_id") or "",
                    "default_language": item.get("default_language") or "",
                    "privacy_status": item.get("privacy_status") or "",
                    "thumbnail_url": item.get("thumbnail_url") or "",
                    "current_views": item.get("views"),
                    "current_likes": item.get("likes"),
                    "current_comments": item.get("comments"),
                    "last_metric_at": collected,
                    "discovered_at": collected,
                }
                # Legacy classification is imported only as a machine suggestion, never as a human label.
                legacy_class = item.get("classification")
                mapping = {"unrelated":"daily", "ugphone":"ugphone", "competitor":"competitor", "multi_brand_cloud_phone":"multi_brand", "other_cloud_phone":"other_cloud_phone"}
                suggestion = None
                if legacy_class:
                    suggestion = {
                        "video_id": vid,
                        "suggested_role": mapping.get(legacy_class, "pending"),
                        "brands": item.get("matched_brands") or item.get("strong_matched_brands") or [],
                        "confidence": {"confirmed":"high", "probable":"medium", "review":"review"}.get(item.get("classification_confidence"), "review"),
                        "evidence": ["legacy_v2_suggestion"] + list(item.get("evidence") or []),
                        "generated_at": collected,
                        "rule_version": "legacy-v2",
                    }
                hub.upsert_video(vrow, snapshot=True, suggestion=suggestion)
                videos += 1
        sfile = folder / "video_snapshots.jsonl"
        if sfile.exists():
            with connect(hub.db_path) as conn:
                for item in _read_jsonl(sfile):
                    vid = item.get("video_id")
                    at = item.get("collected_at_utc") or item.get("captured_at")
                    if not vid or not at: continue
                    exists = conn.execute("SELECT video_id FROM videos WHERE video_id=?", (vid,)).fetchone()
                    if not exists: continue
                    cur = conn.execute("INSERT OR IGNORE INTO video_snapshots(video_id,captured_at,views,likes,comments) VALUES(?,?,?,?,?)",
                                       (vid,at,item.get("views"),item.get("likes"),item.get("comments")))
                    if cur.rowcount:
                        snapshots += 1
                conn.commit()
    with connect(hub.db_path) as conn:
        conn.execute("INSERT INTO imports(source_type,source_path,imported_at,creators,videos,snapshots,message) VALUES(?,?,?,?,?,?,?)",
                     ("youtube-kol-gmv-intelligence-v2", str(root.resolve()), now_utc(), creators, videos, snapshots, "\n".join(notes)[:10000]))
        conn.commit()
    return {"creators":creators,"videos":videos,"snapshots_added":snapshots,"notes":notes}
