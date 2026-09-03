from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from creator_hub.dashboard import build_dashboard
from creator_hub.db import connect
from creator_hub.service import CreatorHub

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_DB = ROOT / "data" / "demo_creator_hub.sqlite"
DEFAULT_DEMO_OUTPUT = ROOT / "output" / "demo-dashboard"

COUNTRIES = ["US", "GB", "CA", "AU", "DE", "FR", "BR", "MX", "JP", "KR", "PH", "ID"]
THEMES = ["tutorial", "review", "gaming", "productivity", "tech", "lifestyle"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _channel_id(index: int) -> str:
    return f"UCDEMO{index:018d}"[:24]


def _video_id(index: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    value = index + 1
    chars = []
    while value:
        value, rem = divmod(value, len(alphabet))
        chars.append(alphabet[rem])
    token = "".join(reversed(chars)) or "0"
    return ("D" + token.rjust(10, "0"))[-11:]


def _safe_demo_target(path: Path) -> None:
    name = path.name.lower()
    if "demo" not in name and "synthetic" not in name:
        raise ValueError(f"refusing to replace non-demo database: {path}")


def _install_portfolio_workspace(hub: CreatorHub, now: str) -> dict[str, Any]:
    existing = [x for x in hub.workspace.list() if x.get("template_id") == "brand_influencer" and x.get("name") == "Portfolio Demo"]
    ws = hub.workspace.get(existing[0]["id"]) if existing else hub.workspace.install_template("brand_influencer", name="Portfolio Demo")
    assert ws
    wid = str(ws["id"])
    brands = [
        ("nova", "Nova Labs", "primary"),
        ("orbit", "Orbit Systems", "competitor"),
        ("pixelworks", "PixelWorks", "partner"),
    ]
    with connect(hub.db_path) as conn:
        for key, name, role in brands:
            bid = f"{wid}:brand:{key}"
            conn.execute(
                """INSERT OR REPLACE INTO workspace_brands
                   (id,workspace_id,key,display_name,role,aliases_json,metadata_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (bid, wid, key, name, role, "[]", "{}", now, now),
            )
        scheme_id = f"{wid}:taxonomy:content_theme"
        conn.execute(
            """INSERT OR REPLACE INTO taxonomy_schemes
               (id,workspace_id,key,name,entity_type,multi_select,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (scheme_id, wid, "content_theme", "Content Theme", "video", 0, now, now),
        )
        for pos, theme in enumerate(THEMES, 1):
            conn.execute(
                """INSERT OR REPLACE INTO taxonomy_labels
                   (id,scheme_id,key,name,parent_label_id,sort_order,metadata_json)
                   VALUES(?,?,?,?,?,?,?)""",
                (f"{scheme_id}:label:{theme}", scheme_id, theme, theme.title(), None, pos, "{}"),
            )
        conn.commit()
    hub.workspace.set_active(wid)
    hub.brand_cfg = hub.workspace.classifier_config(hub.legacy_brand_cfg)
    return hub.workspace.get(wid) or {"id": wid}


def create_demo(
    db_path: str | Path = DEFAULT_DEMO_DB,
    *,
    creators: int = 100,
    videos: int = 3000,
    seed: int = 20260903,
    output_dir: str | Path | None = None,
    build: bool = False,
) -> dict[str, Any]:
    db = Path(db_path).resolve()
    _safe_demo_target(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    for candidate in [db, Path(str(db) + "-wal"), Path(str(db) + "-shm")]:
        if candidate.exists():
            candidate.unlink()

    rng = random.Random(seed)
    now_dt = datetime(2026, 9, 3, 0, 0, tzinfo=timezone.utc)
    now = _iso(now_dt)
    hub = CreatorHub(db)
    workspace = _install_portfolio_workspace(hub, now)
    wid = str(workspace["id"])

    creators = max(1, int(creators))
    videos = max(creators, int(videos))
    base_per_creator, remainder = divmod(videos, creators)
    video_index = 0

    with connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        discovery_run = "demo-discovery-001"
        conn.execute(
            """INSERT INTO discovery_runs(
               run_id,base_query,base_query_source,search_source,search_language,query_language,
               queries_requested_json,queries_executed_json,target_group,target_country,region,
               lookback_days,max_results,started_at,finished_at,status,hits,unique_creators,errors_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                discovery_run, "creator technology review", "exact", "synthetic", "en", "en",
                json.dumps(["technology creator review", "creator tutorial"], ensure_ascii=False),
                json.dumps(["technology creator review", "creator tutorial"], ensure_ascii=False),
                "portfolio-demo", "", "", 365, videos, now, now, "complete", videos, creators, "[]",
            ),
        )

        ai_run_id = conn.execute(
            """INSERT INTO ai_runs(task,provider,model,prompt_version,source_fingerprint,started_at,finished_at,status,input_tokens,output_tokens)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("portfolio_demo", "mock", "offline-fixture", "portfolio-v1", "synthetic-demo", now, now, "complete", 0, 0),
        ).lastrowid

        for i in range(creators):
            cid = _channel_id(i)
            country = COUNTRIES[i % len(COUNTRIES)]
            subscribers = int(5_000 * (1.045 ** (i % 70)) + rng.randint(0, 15_000))
            channel_views = subscribers * rng.randint(18, 130)
            channel_video_count = rng.randint(80, 800)
            title = f"Demo Creator {i + 1:03d}"
            handle = f"@demo_creator_{i + 1:03d}"
            created_at = _iso(now_dt - timedelta(days=1200 - i))
            last_sync = _iso(now_dt - timedelta(hours=i % 36))
            conn.execute(
                """INSERT INTO creators(
                   channel_id,channel_title,handle,channel_url,description,country_api,country_resolved,country_source,
                   country_evidence_json,published_at,subscriber_count,channel_view_count,channel_video_count,
                   hidden_subscriber_count,uploads_playlist_id,thumbnail_url,monitoring_enabled,priority,source,
                   discovered_at,created_at,last_synced_at,social_links_json,discovery_pre_score,discovery_opportunity_tier,
                   discovery_score_updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cid, title, handle, f"https://www.youtube.com/channel/{cid}",
                    "Synthetic portfolio demonstration creator. No real person or business data.",
                    country, country, "synthetic", json.dumps([{"source": "synthetic", "country": country}]),
                    created_at, subscribers, channel_views, channel_video_count, 0, f"UU{cid[2:]}", "",
                    1 if i % 5 else 0, ["high", "normal", "normal", "low"][i % 4], "synthetic_demo",
                    now, now, last_sync, "[]", round(50 + rng.random() * 45, 2), ["A", "B", "B", "C"][i % 4], now,
                ),
            )
            for snap in range(4):
                snap_at = _iso(now_dt - timedelta(days=(3 - snap) * 30))
                factor = 0.88 + 0.04 * snap
                conn.execute(
                    "INSERT INTO creator_snapshots(channel_id,captured_at,subscriber_count,channel_view_count,channel_video_count,hidden_subscriber_count) VALUES(?,?,?,?,?,?)",
                    (cid, snap_at, int(subscribers * factor), int(channel_views * factor), channel_video_count - (3 - snap) * 4, 0),
                )

            rel_brand = ["nova", "orbit", "pixelworks"][i % 3]
            if i % 4 != 3:
                conn.execute(
                    """INSERT OR IGNORE INTO creator_relationships
                       (workspace_id,channel_id,brand_id,relationship_type,status,source_ref,note,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        wid, cid, f"{wid}:brand:{rel_brand}", "partnership",
                        "active" if i % 6 else "historical", "synthetic-demo", "Synthetic relationship", now, now,
                    ),
                )

            revenue = round((i + 1) * rng.uniform(180.0, 950.0), 2)
            orders = float(rng.randint(15, 900))
            for metric_key, value, currency in [("revenue", revenue, "USD"), ("orders", orders, "")]:
                conn.execute(
                    """INSERT INTO creator_business_metrics(
                       channel_id,metric_key,metric_value,currency,metric_value_usd,fx_status,snapshot_kind,
                       source_type,source_ref,import_batch,captured_at,note,raw_json
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        cid, metric_key, value, currency, value if currency == "USD" else None,
                        "not_applicable", "point_in_time_total", "synthetic_demo", f"demo-{metric_key}-{i}",
                        "portfolio-demo", now, "Synthetic portfolio metric", "{}",
                    ),
                )

            per_creator = base_per_creator + (1 if i < remainder else 0)
            best_video_id = None
            best_video_title = None
            best_views = -1
            for j in range(per_creator):
                vid = _video_id(video_index)
                video_index += 1
                theme = THEMES[(i + j) % len(THEMES)]
                published = _iso(now_dt - timedelta(days=(j * 7 + i) % 730, hours=j % 24))
                views = int(max(50, subscribers * rng.uniform(0.08, 3.5)))
                likes = int(views * rng.uniform(0.015, 0.085))
                comments = int(views * rng.uniform(0.001, 0.012))
                vtitle = f"{theme.title()} workflow #{j + 1} — {title}"
                conn.execute(
                    """INSERT INTO videos(
                       video_id,channel_id,title,description,tags_json,published_at,duration_iso8601,duration_seconds,
                       live_broadcast_content,category_id,default_language,privacy_status,thumbnail_url,current_views,
                       current_likes,current_comments,last_metric_at,discovered_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        vid, cid, vtitle, "Synthetic video for public portfolio testing.",
                        json.dumps([theme, "creator-intelligence", "synthetic"]), published, "PT8M20S", 500,
                        "none", "28", "en", "public", "", views, likes, comments, now, now,
                    ),
                )
                conn.execute(
                    "INSERT INTO video_snapshots(video_id,captured_at,views,likes,comments) VALUES(?,?,?,?,?)",
                    (vid, now, views, likes, comments),
                )
                # Legacy classification stays neutral; Workspace Taxonomy carries demo semantics.
                conn.execute(
                    """INSERT INTO label_suggestions(video_id,suggested_role,brands_json,confidence,evidence_json,generated_at,rule_version)
                       VALUES(?,?,?,?,?,?,?)""",
                    (vid, "daily", "[]", "confirmed", json.dumps(["synthetic_demo"]), now, "portfolio-demo-v1"),
                )
                scheme_id = f"{wid}:taxonomy:content_theme"
                label_id = f"{scheme_id}:label:{theme}"
                conn.execute(
                    """INSERT OR IGNORE INTO video_taxonomy_assignments
                       (workspace_id,video_id,scheme_id,label_id,layer,source_ref,assigned_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (wid, vid, scheme_id, label_id, "derived", "synthetic-demo", now),
                )
                if views > best_views:
                    best_views = views
                    best_video_id = vid
                    best_video_title = vtitle

            score = round(60 + rng.random() * 38, 2)
            conn.execute(
                """INSERT INTO discovery_creator_results(
                   run_id,channel_id,channel_title,channel_url,subscribers,country_resolved,country_source,
                   best_video_id,best_video_title,best_video_views,best_discovery_score,opportunity_tier,
                   query_coverage,matched_queries_json,hit_video_count,found_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    discovery_run, cid, title, f"https://www.youtube.com/channel/{cid}", subscribers, country,
                    "synthetic", best_video_id, best_video_title, best_views, score,
                    "A" if score >= 85 else "B" if score >= 70 else "C", 2,
                    json.dumps(["technology creator review", "creator tutorial"]), per_creator, now,
                ),
            )
            conn.execute(
                """INSERT INTO creator_discovery_summary(
                   channel_id,first_seen_at,last_seen_at,discovery_run_count,hit_video_count_total,
                   best_discovery_score,last_base_query,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (cid, now, now, 1, per_creator, score, "creator technology review", now),
            )
            if i < min(25, creators):
                finding_id = conn.execute(
                    """INSERT INTO ai_findings(run_id,finding_type,channel_id,title,summary,confidence,result_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        ai_run_id, "creator_brief", cid, f"Synthetic brief — {title}",
                        "Offline mock finding generated from synthetic evidence for portfolio demonstration.",
                        0.82, json.dumps({"priority": ["high", "medium", "low"][i % 3], "synthetic": True}), now,
                    ),
                ).lastrowid
                for evidence_key, evidence_value in [
                    ("subscriber_count", subscribers),
                    ("best_discovery_score", score),
                    ("revenue", revenue),
                ]:
                    conn.execute(
                        """INSERT INTO ai_evidence(finding_id,evidence_key,evidence_value_json,source_type,source_ref,captured_at)
                           VALUES(?,?,?,?,?,?)""",
                        (finding_id, evidence_key, json.dumps(evidence_value), "synthetic_demo", cid, now),
                    )

        conn.commit()

    output_path = None
    if build:
        output_path = Path(output_dir or DEFAULT_DEMO_OUTPUT).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        build_dashboard(db, output_path, hub.settings)

    return {
        "ok": True,
        "synthetic": True,
        "seed": seed,
        "db": str(db),
        "workspace_id": wid,
        "creators": creators,
        "videos": video_index,
        "dashboard": str(output_path) if output_path else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a deterministic synthetic Creator Intelligence demo database")
    parser.add_argument("--db", default=str(DEFAULT_DEMO_DB))
    parser.add_argument("--creators", type=int, default=100)
    parser.add_argument("--videos", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--output", default=str(DEFAULT_DEMO_OUTPUT))
    parser.add_argument("--build-dashboard", action="store_true")
    args = parser.parse_args()
    result = create_demo(
        args.db,
        creators=args.creators,
        videos=args.videos,
        seed=args.seed,
        output_dir=args.output,
        build=args.build_dashboard,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
