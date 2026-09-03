from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..db import connect


def workspace_creator_indexes(hub: Any, workspace_id: str = "") -> dict[str, Any]:
    """Batch-load Workspace semantics for Creator-oriented AI/query operations.

    The function intentionally builds indexes in a handful of SQL queries instead of
    querying Taxonomy/Relationship tables once per Creator.
    """
    wid = workspace_id or hub.workspace.active_id()
    if not wid:
        return {"workspace_id": "", "relationships": {}, "taxonomy_counts": {}, "business": {}}

    relationships: dict[str, list[dict[str, Any]]] = defaultdict(list)
    taxonomy_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    business: dict[str, dict[str, float]] = defaultdict(dict)

    with connect(hub.db_path) as conn:
        for row in conn.execute(
            """SELECT r.channel_id,r.relationship_type,r.status,b.key brand_key,b.display_name brand_name
               FROM creator_relationships r
               LEFT JOIN workspace_brands b ON b.id=r.brand_id
               WHERE r.workspace_id=?""",
            (wid,),
        ).fetchall():
            relationships[str(row["channel_id"])].append(dict(row))

        for row in conn.execute(
            """SELECT v.channel_id,s.key scheme_key,l.key label_key,COUNT(*) n
               FROM video_taxonomy_assignments a
               JOIN videos v ON v.video_id=a.video_id
               JOIN taxonomy_schemes s ON s.id=a.scheme_id
               JOIN taxonomy_labels l ON l.id=a.label_id
               WHERE a.workspace_id=?
               GROUP BY v.channel_id,s.key,l.key""",
            (wid,),
        ).fetchall():
            key = f"{row['scheme_key']}::{row['label_key']}"
            taxonomy_counts[str(row["channel_id"])][key] = int(row["n"] or 0)

        definitions = {
            str(row["key"]): dict(row)
            for row in conn.execute(
                "SELECT * FROM business_metric_definitions WHERE workspace_id=?", (wid,)
            ).fetchall()
        }
        if definitions:
            keys = list(definitions)
            placeholders = ",".join("?" for _ in keys)
            rows = conn.execute(
                f"""SELECT channel_id,metric_key,metric_value,metric_value_usd,currency,captured_at,id
                    FROM creator_business_metrics
                    WHERE metric_key IN ({placeholders})
                    ORDER BY channel_id,metric_key,captured_at DESC,id DESC""",
                keys,
            ).fetchall()
            seen: set[tuple[str, str]] = set()
            for row in rows:
                pair = (str(row["channel_id"]), str(row["metric_key"]))
                if pair in seen:
                    continue
                seen.add(pair)
                value = row["metric_value_usd"] if row["metric_value_usd"] is not None else row["metric_value"]
                if value is not None:
                    business[pair[0]][pair[1]] = float(value)

    return {
        "workspace_id": wid,
        "relationships": dict(relationships),
        "taxonomy_counts": {k: dict(v) for k, v in taxonomy_counts.items()},
        "business": dict(business),
    }


def creator_workspace_context(hub: Any, channel_id: str, indexes: dict[str, Any] | None = None) -> dict[str, Any]:
    indexes = indexes or workspace_creator_indexes(hub)
    cid = str(channel_id)
    with connect(hub.db_path) as conn:
        creator = conn.execute(
            "SELECT channel_id,channel_title,handle,country_resolved,subscriber_count,channel_view_count,channel_video_count,last_synced_at FROM creators WHERE channel_id=?",
            (cid,),
        ).fetchone()
        if not creator:
            raise ValueError("creator not found")
        recent = [
            dict(row)
            for row in conn.execute(
                "SELECT video_id,title,published_at,current_views,current_likes,current_comments FROM videos WHERE channel_id=? ORDER BY published_at DESC LIMIT 12",
                (cid,),
            ).fetchall()
        ]
    return {
        "creator": dict(creator),
        "workspace_id": indexes.get("workspace_id"),
        "relationships": list((indexes.get("relationships") or {}).get(cid, [])),
        "taxonomy_counts": dict((indexes.get("taxonomy_counts") or {}).get(cid, {})),
        "business_metrics": dict((indexes.get("business") or {}).get(cid, {})),
        "recent_videos": recent,
    }
