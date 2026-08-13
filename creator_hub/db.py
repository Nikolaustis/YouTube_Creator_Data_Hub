from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 2

SCHEMA_SQL = r'''
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS creators (
  channel_id TEXT PRIMARY KEY,
  channel_title TEXT,
  handle TEXT,
  channel_url TEXT,
  description TEXT,
  country_api TEXT,
  country_resolved TEXT,
  country_source TEXT,
  country_evidence_json TEXT NOT NULL DEFAULT '[]',
  published_at TEXT,
  subscriber_count INTEGER,
  channel_view_count INTEGER,
  channel_video_count INTEGER,
  hidden_subscriber_count INTEGER,
  uploads_playlist_id TEXT,
  thumbnail_url TEXT,
  monitoring_enabled INTEGER NOT NULL DEFAULT 0,
  priority TEXT NOT NULL DEFAULT 'normal',
  source TEXT,
  discovered_at TEXT,
  created_at TEXT NOT NULL,
  last_synced_at TEXT,
  public_email TEXT,
  social_links_json TEXT NOT NULL DEFAULT '[]',
  website_url TEXT,
  contactability_score REAL,
  contact_status TEXT,
  contact_scraped_at TEXT,
  discovery_pre_score REAL,
  discovery_opportunity_tier TEXT,
  discovery_score_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS creator_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  subscriber_count INTEGER,
  channel_view_count INTEGER,
  channel_video_count INTEGER,
  hidden_subscriber_count INTEGER,
  UNIQUE(channel_id, captured_at),
  FOREIGN KEY(channel_id) REFERENCES creators(channel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_creator_snapshots_channel_time ON creator_snapshots(channel_id, captured_at);

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL,
  title TEXT,
  description TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  published_at TEXT,
  duration_iso8601 TEXT,
  duration_seconds INTEGER,
  live_broadcast_content TEXT,
  category_id TEXT,
  default_language TEXT,
  privacy_status TEXT,
  thumbnail_url TEXT,
  current_views INTEGER,
  current_likes INTEGER,
  current_comments INTEGER,
  last_metric_at TEXT,
  discovered_at TEXT NOT NULL,
  FOREIGN KEY(channel_id) REFERENCES creators(channel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_videos_channel_published ON videos(channel_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_videos_last_metric ON videos(last_metric_at);

CREATE TABLE IF NOT EXISTS video_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  views INTEGER,
  likes INTEGER,
  comments INTEGER,
  UNIQUE(video_id, captured_at),
  FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_video_snapshots_video_time ON video_snapshots(video_id, captured_at);

CREATE TABLE IF NOT EXISTS discovery_hits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query TEXT NOT NULL,
  source TEXT NOT NULL,
  rank INTEGER,
  video_id TEXT,
  channel_id TEXT,
  channel_title TEXT,
  channel_url TEXT,
  title TEXT,
  published_at TEXT,
  views INTEGER,
  likes INTEGER,
  comments INTEGER,
  subscribers INTEGER,
  country_resolved TEXT,
  country_source TEXT,
  pre_score REAL,
  opportunity_tier TEXT,
  engagement_rate REAL,
  comment_rate REAL,
  view_sub_ratio REAL,
  relative_velocity REAL,
  public_email TEXT,
  social_links_json TEXT NOT NULL DEFAULT '[]',
  website_url TEXT,
  contactability_score REAL,
  contact_status TEXT,
  found_at TEXT NOT NULL,
  raw_json TEXT,
  UNIQUE(query, source, video_id, channel_id, found_at)
);
CREATE INDEX IF NOT EXISTS idx_discovery_found ON discovery_hits(found_at DESC);
CREATE INDEX IF NOT EXISTS idx_discovery_channel ON discovery_hits(channel_id);

CREATE TABLE IF NOT EXISTS label_suggestions (
  video_id TEXT PRIMARY KEY,
  suggested_role TEXT NOT NULL,
  brands_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '[]',
  generated_at TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_labels (
  video_id TEXT PRIMARY KEY,
  human_role TEXT NOT NULL,
  brands_json TEXT NOT NULL DEFAULT '[]',
  labeled_by TEXT,
  note TEXT,
  labeled_at TEXT NOT NULL,
  FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_label_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  old_value_json TEXT,
  new_value_json TEXT,
  actor TEXT,
  changed_at TEXT NOT NULL,
  FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_label_audit_video_time ON video_label_audit(video_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS creator_tags (
  channel_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  created_by TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY(channel_id, tag),
  FOREIGN KEY(channel_id) REFERENCES creators(channel_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mode TEXT NOT NULL,
  target TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  creators_processed INTEGER NOT NULL DEFAULT 0,
  videos_processed INTEGER NOT NULL DEFAULT 0,
  quota_units INTEGER NOT NULL DEFAULT 0,
  message TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_runs_started ON sync_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS quota_daily (
  quota_date TEXT PRIMARY KEY,
  estimated_units INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS captions (
  video_id TEXT NOT NULL,
  language TEXT NOT NULL,
  source TEXT NOT NULL,
  is_auto INTEGER,
  text TEXT,
  captured_at TEXT NOT NULL,
  PRIMARY KEY(video_id, language, source),
  FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS imports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT NOT NULL,
  source_path TEXT,
  imported_at TEXT NOT NULL,
  creators INTEGER NOT NULL DEFAULT 0,
  videos INTEGER NOT NULL DEFAULT 0,
  snapshots INTEGER NOT NULL DEFAULT 0,
  message TEXT
);
'''

CREATOR_COLUMNS = {
    "country_resolved": "TEXT",
    "country_source": "TEXT",
    "country_evidence_json": "TEXT NOT NULL DEFAULT '[]'",
    "public_email": "TEXT",
    "social_links_json": "TEXT NOT NULL DEFAULT '[]'",
    "website_url": "TEXT",
    "contactability_score": "REAL",
    "contact_status": "TEXT",
    "contact_scraped_at": "TEXT",
    "discovery_pre_score": "REAL",
    "discovery_opportunity_tier": "TEXT",
    "discovery_score_updated_at": "TEXT",
}

DISCOVERY_COLUMNS = {
    "channel_title": "TEXT",
    "channel_url": "TEXT",
    "views": "INTEGER",
    "likes": "INTEGER",
    "comments": "INTEGER",
    "subscribers": "INTEGER",
    "country_resolved": "TEXT",
    "country_source": "TEXT",
    "pre_score": "REAL",
    "opportunity_tier": "TEXT",
    "engagement_rate": "REAL",
    "comment_rate": "REAL",
    "view_sub_ratio": "REAL",
    "relative_velocity": "REAL",
    "public_email": "TEXT",
    "social_links_json": "TEXT NOT NULL DEFAULT '[]'",
    "website_url": "TEXT",
    "contactability_score": "REAL",
    "contact_status": "TEXT",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_columns(conn, "creators", CREATOR_COLUMNS)
        _ensure_columns(conn, "discovery_hits", DISCOVERY_COLUMNS)
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()


def rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    r = conn.execute(sql, tuple(params)).fetchone()
    return dict(r) if r is not None else None


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        conn.execute("BEGIN")
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
