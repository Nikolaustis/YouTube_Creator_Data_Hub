from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 17
LEGACY_DISCOVERY_INFERENCE_VERSION = 2
DISCOVERY_SUMMARY_VERSION = 1

SCHEMA_SQL = r'''
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_specs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, spec_type TEXT NOT NULL, title TEXT NOT NULL, spec_version INTEGER NOT NULL DEFAULT 1,
  spec_json TEXT NOT NULL, fingerprint TEXT NOT NULL, source_ai_run_id INTEGER, source_result_set_id INTEGER, parent_spec_id INTEGER, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_specs_type_time ON run_specs(spec_type,created_at DESC);

CREATE TABLE IF NOT EXISTS data_assertions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, field_id TEXT NOT NULL,
  layer TEXT NOT NULL CHECK(layer IN ('fact','derived','ai','human')), value_json TEXT NOT NULL, confidence REAL, source_ref TEXT,
  rule_version TEXT, observed_at TEXT, created_at TEXT NOT NULL, supersedes_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_data_assertions_entity_field ON data_assertions(entity_type,entity_id,field_id,created_at DESC);

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
CREATE INDEX IF NOT EXISTS idx_videos_published ON videos(published_at DESC, video_id ASC);
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
  run_id TEXT,
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

CREATE TABLE IF NOT EXISTS discovery_runs (
  run_id TEXT PRIMARY KEY,
  base_query TEXT NOT NULL,
  base_query_source TEXT NOT NULL DEFAULT 'exact',
  search_source TEXT,
  search_language TEXT,
  query_language TEXT,
  queries_requested_json TEXT NOT NULL DEFAULT '[]',
  queries_executed_json TEXT NOT NULL DEFAULT '[]',
  target_group TEXT,
  target_country TEXT,
  region TEXT,
  lookback_days INTEGER,
  from_date TEXT,
  to_date TEXT,
  max_results INTEGER,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  hits INTEGER NOT NULL DEFAULT 0,
  unique_creators INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_discovery_runs_started ON discovery_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS discovery_creator_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  channel_title TEXT,
  channel_url TEXT,
  subscribers INTEGER,
  country_resolved TEXT,
  country_source TEXT,
  best_video_id TEXT,
  best_video_title TEXT,
  best_video_views INTEGER,
  best_discovery_score REAL,
  opportunity_tier TEXT,
  query_coverage INTEGER NOT NULL DEFAULT 0,
  matched_queries_json TEXT NOT NULL DEFAULT '[]',
  hit_video_count INTEGER NOT NULL DEFAULT 0,
  found_at TEXT NOT NULL,
  UNIQUE(run_id, channel_id),
  FOREIGN KEY(run_id) REFERENCES discovery_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_discovery_creator_run ON discovery_creator_results(run_id);
CREATE INDEX IF NOT EXISTS idx_discovery_creator_channel ON discovery_creator_results(channel_id);
CREATE INDEX IF NOT EXISTS idx_discovery_creator_score ON discovery_creator_results(best_discovery_score DESC);

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

CREATE INDEX IF NOT EXISTS idx_label_suggestions_role ON label_suggestions(suggested_role);
CREATE INDEX IF NOT EXISTS idx_label_suggestions_confidence ON label_suggestions(confidence);

CREATE TABLE IF NOT EXISTS video_labels (
  video_id TEXT PRIMARY KEY,
  human_role TEXT NOT NULL,
  brands_json TEXT NOT NULL DEFAULT '[]',
  labeled_by TEXT,
  note TEXT,
  labeled_at TEXT NOT NULL,
  FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_video_labels_role ON video_labels(human_role);

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



CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  source_fingerprint TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  response_id TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_runs_started ON ai_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_runs_task ON ai_runs(task, started_at DESC);

CREATE TABLE IF NOT EXISTS ai_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  finding_type TEXT NOT NULL,
  channel_id TEXT,
  title TEXT,
  summary TEXT,
  confidence REAL,
  result_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES ai_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ai_findings_channel ON ai_findings(channel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_findings_run ON ai_findings(run_id);

CREATE TABLE IF NOT EXISTS ai_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  finding_id INTEGER NOT NULL,
  evidence_key TEXT NOT NULL,
  evidence_value_json TEXT,
  source_type TEXT NOT NULL DEFAULT 'local_db',
  source_ref TEXT,
  captured_at TEXT NOT NULL,
  FOREIGN KEY(finding_id) REFERENCES ai_findings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ai_evidence_finding ON ai_evidence(finding_id);

CREATE TABLE IF NOT EXISTS ai_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  finding_id INTEGER NOT NULL,
  rating TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(finding_id) REFERENCES ai_findings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ai_feedback_finding ON ai_feedback(finding_id);

CREATE TABLE IF NOT EXISTS ai_cache (
  cache_key TEXT PRIMARY KEY,
  task TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  source_fingerprint TEXT,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_cache_task ON ai_cache(task, updated_at DESC);

CREATE TABLE IF NOT EXISTS ai_result_sets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ai_run_id INTEGER,
  result_type TEXT NOT NULL,
  title TEXT,
  input_text TEXT,
  source_type TEXT NOT NULL DEFAULT 'local_db',
  request_json TEXT NOT NULL DEFAULT '{}',
  plan_json TEXT NOT NULL DEFAULT '{}',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  discovery_run_id TEXT,
  run_spec_id INTEGER,
  total_items INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(ai_run_id) REFERENCES ai_runs(id) ON DELETE SET NULL,
  FOREIGN KEY(discovery_run_id) REFERENCES discovery_runs(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_result_sets_created ON ai_result_sets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_result_sets_type ON ai_result_sets(result_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_result_sets_ai_run ON ai_result_sets(ai_run_id);
CREATE INDEX IF NOT EXISTS idx_ai_result_sets_discovery ON ai_result_sets(discovery_run_id);

CREATE TABLE IF NOT EXISTS ai_result_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  result_set_id INTEGER NOT NULL,
  item_index INTEGER NOT NULL,
  item_type TEXT NOT NULL DEFAULT 'creator',
  item_key TEXT,
  channel_id TEXT,
  snapshot_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE(result_set_id, item_index),
  FOREIGN KEY(result_set_id) REFERENCES ai_result_sets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ai_result_items_set ON ai_result_items(result_set_id, item_index);
CREATE INDEX IF NOT EXISTS idx_ai_result_items_channel ON ai_result_items(channel_id);


CREATE TABLE IF NOT EXISTS creator_workflow (
  channel_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'unreviewed',
  note TEXT,
  updated_by TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_creator_workflow_status ON creator_workflow(status);

CREATE TABLE IF NOT EXISTS creator_workflow_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id TEXT NOT NULL,
  old_status TEXT,
  new_status TEXT NOT NULL,
  note TEXT,
  actor TEXT,
  changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_creator_workflow_audit_channel_time ON creator_workflow_audit(channel_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS creator_discovery_summary (
  channel_id TEXT PRIMARY KEY,
  first_seen_at TEXT,
  last_seen_at TEXT,
  discovery_run_count INTEGER NOT NULL DEFAULT 0,
  hit_video_count_total INTEGER NOT NULL DEFAULT 0,
  best_discovery_score REAL,
  last_base_query TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_creator_discovery_summary_last_seen ON creator_discovery_summary(last_seen_at DESC);

CREATE TABLE IF NOT EXISTS creator_sync_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sync_run_id INTEGER,
  channel_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  error_type TEXT,
  error_message TEXT,
  videos_processed INTEGER NOT NULL DEFAULT 0,
  quota_units INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_creator_sync_attempts_channel_time ON creator_sync_attempts(channel_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_creator_sync_attempts_run ON creator_sync_attempts(sync_run_id);

CREATE TABLE IF NOT EXISTS maintenance_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  affected_rows INTEGER NOT NULL DEFAULT 0,
  message TEXT
);
CREATE INDEX IF NOT EXISTS idx_maintenance_runs_started ON maintenance_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS backup_registry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  quick_check TEXT,
  source_db TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_backup_registry_created ON backup_registry(created_at DESC);

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

CREATE TABLE IF NOT EXISTS creator_business_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id TEXT NOT NULL,
  metric_key TEXT NOT NULL,
  metric_value REAL NOT NULL,
  currency TEXT,
  metric_value_usd REAL,
  fx_rate_to_usd REAL,
  fx_rate_date TEXT,
  fx_provider TEXT,
  fx_status TEXT NOT NULL DEFAULT 'not_applicable',
  snapshot_kind TEXT NOT NULL DEFAULT 'point_in_time_total',
  period_start TEXT NOT NULL DEFAULT '',
  period_end TEXT NOT NULL DEFAULT '',
  campaign TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL DEFAULT 'manual_import',
  source_ref TEXT NOT NULL DEFAULT '',
  import_batch TEXT,
  captured_at TEXT NOT NULL,
  note TEXT,
  raw_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(channel_id,metric_key,period_start,period_end,campaign,region,source_type,source_ref),
  FOREIGN KEY(channel_id) REFERENCES creators(channel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_business_metric_channel_key ON creator_business_metrics(channel_id,metric_key);
CREATE INDEX IF NOT EXISTS idx_business_metric_period ON creator_business_metrics(metric_key,period_end,period_start);
CREATE INDEX IF NOT EXISTS idx_business_metric_capture ON creator_business_metrics(captured_at DESC);

CREATE TABLE IF NOT EXISTS saved_views (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_key TEXT NOT NULL,
  name TEXT NOT NULL,
  config_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(page_key,name)
);
CREATE INDEX IF NOT EXISTS idx_saved_views_page ON saved_views(page_key,updated_at DESC);

CREATE TABLE IF NOT EXISTS job_runs (
  job_id TEXT PRIMARY KEY,
  task TEXT NOT NULL,
  title TEXT NOT NULL,
  state TEXT NOT NULL,
  stage TEXT,
  message TEXT,
  current_value REAL,
  total_value REAL,
  percent REAL,
  started_at TEXT,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  elapsed_seconds REAL NOT NULL DEFAULT 0,
  result_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  resource_class TEXT NOT NULL DEFAULT 'local',
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  checkpoint_json TEXT NOT NULL DEFAULT '{}',
  resumable INTEGER NOT NULL DEFAULT 0,
  retry_count INTEGER NOT NULL DEFAULT 0,
  parent_job_id TEXT,
  worker_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_runs_updated ON job_runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_state ON job_runs(state,updated_at DESC);

CREATE TABLE IF NOT EXISTS creator_availability_overrides (
  channel_id TEXT PRIMARY KEY,
  availability_status TEXT,
  content_status TEXT,
  monitoring_policy TEXT,
  note TEXT,
  actor TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(channel_id) REFERENCES creators(channel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_creator_availability_override_status ON creator_availability_overrides(availability_status,updated_at DESC);

CREATE TABLE IF NOT EXISTS creator_availability_override_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id TEXT NOT NULL,
  old_json TEXT NOT NULL DEFAULT '{}',
  new_json TEXT NOT NULL DEFAULT '{}',
  actor TEXT,
  changed_at TEXT NOT NULL,
  FOREIGN KEY(channel_id) REFERENCES creators(channel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_creator_availability_override_audit_channel ON creator_availability_override_audit(channel_id,changed_at DESC);
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
    "channel_data_at": "TEXT",
    "video_metrics_at": "TEXT",
    "classification_data_at": "TEXT",
    "last_sync_attempt_at": "TEXT",
    "last_sync_status": "TEXT",
    "last_sync_error": "TEXT",
    "sync_error_type": "TEXT",
    "consecutive_sync_failures": "INTEGER NOT NULL DEFAULT 0",
    "next_sync_at": "TEXT",
    "next_retry_at": "TEXT",
    "sync_suspended": "INTEGER NOT NULL DEFAULT 0",
    "availability_status": "TEXT NOT NULL DEFAULT 'available'",
    "availability_reason": "TEXT",
    "availability_source": "TEXT",
    "availability_checked_at": "TEXT",
    "availability_failures": "INTEGER NOT NULL DEFAULT 0",
}


BUSINESS_METRIC_COLUMNS = {
    "metric_value_usd": "REAL",
    "fx_rate_to_usd": "REAL",
    "fx_rate_date": "TEXT",
    "fx_provider": "TEXT",
    "fx_status": "TEXT NOT NULL DEFAULT 'not_applicable'",
    "snapshot_kind": "TEXT NOT NULL DEFAULT 'point_in_time_total'",
}

AI_RUN_COLUMNS = {
    "source_json": "TEXT NOT NULL DEFAULT '{}'",
    "result_json": "TEXT NOT NULL DEFAULT '{}'",
    "cache_hit": "INTEGER NOT NULL DEFAULT 0",
}

DISCOVERY_RUN_COLUMNS = {
    "base_query_source": "TEXT NOT NULL DEFAULT 'exact'",
    "ai_run_id": "INTEGER",
}

DISCOVERY_COLUMNS = {
    "run_id": "TEXT",
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


def _clean_query(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _legacy_query_terms() -> list[str]:
    """Known Query Pack tails, longest first, used only for historical inference."""
    try:
        from .config import load_query_packs
        cfg = load_query_packs()
        terms: dict[str, str] = {}
        for pack in cfg.get("packs") or []:
            for vals in (pack.get("terms") or {}).values():
                for raw in vals or []:
                    term = _clean_query(raw)
                    if term:
                        terms.setdefault(term.casefold(), term)
        return sorted(terms.values(), key=lambda x: (-len(x), x.casefold()))
    except Exception:
        return []


def _strip_known_tail(query: str, terms: list[str]) -> str | None:
    q = _clean_query(query)
    folded = q.casefold()
    for term in terms:
        suffix = " " + term.casefold()
        if folded.endswith(suffix):
            base = q[: len(q) - len(suffix)].strip()
            if base:
                return base
    return None


def _infer_legacy_query_map(rows: list[sqlite3.Row]) -> dict[str, tuple[str, str]]:
    """Map each historical actual query to (base_query, provenance).

    Pre-v1.3 rows never stored base_query/run boundaries.  We therefore infer only the
    keyword family, never a historical execution boundary.  Known Query Pack tails are
    stripped first.  For old custom tails, an exact shorter query that was also observed
    can act as the root.  Every recovered value is labelled `inferred` rather than exact.
    """
    terms = _legacy_query_terms()
    raw_queries: dict[str, str] = {}
    for r in rows:
        q = _clean_query(r["query"])
        if q:
            raw_queries.setdefault(q.casefold(), q)
    roots = list(raw_queries.values())
    result: dict[str, tuple[str, str]] = {}
    for folded, original in raw_queries.items():
        base = _strip_known_tail(original, terms)
        if not base:
            # Custom expansions were not persisted as a vocabulary.  If the actual base
            # query was also searched (normal discovery behaviour), reuse the longest
            # observed prefix rather than inventing a time-based run boundary.
            candidates = [r for r in roots if len(r) < len(original) and original.casefold().startswith(r.casefold() + " ") and _strip_known_tail(r, terms) is None]
            base = max(candidates, key=len) if candidates else original
        base = _clean_query(base)
        result[folded] = (base or "无法可靠还原", "inferred" if base else "unknown")
    return result


def _rebuild_legacy_discovery(conn: sqlite3.Connection) -> None:
    """Rebuild pre-v1.3 creator discovery summaries by inferred base keyword.

    Raw discovery hits are preserved.  The old single `legacy-history` derived run is
    removed, then historical hits are attached to stable keyword-family aggregate runs.
    This intentionally does not claim to reconstruct old search-run timing boundaries.
    """
    current = conn.execute("SELECT value FROM meta WHERE key='legacy_discovery_inference_version'").fetchone()
    if current and str(current[0]) == str(LEGACY_DISCOVERY_INFERENCE_VERSION):
        return

    # Include untouched pre-v1.3 hits and any partially-created v1.4 inferred runs so the
    # migration is safe to retry after an interrupted upgrade.
    rows = conn.execute("""SELECT * FROM discovery_hits
                           WHERE run_id IS NULL OR run_id='' OR run_id='legacy-history' OR run_id LIKE 'legacy-keyword-%'
                           ORDER BY found_at,id""").fetchall()

    # Delete only derived legacy summaries.  Exact v1.3+ runs are never touched.
    conn.execute("DELETE FROM discovery_runs WHERE run_id='legacy-history' OR run_id LIKE 'legacy-keyword-%'")
    if not rows:
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('legacy_discovery_inference_version',?)", (str(LEGACY_DISCOVERY_INFERENCE_VERSION),))
        return

    query_map = _infer_legacy_query_map(rows)
    grouped: dict[str, dict[str, Any]] = {}
    for r in rows:
        q = _clean_query(r["query"])
        base, source = query_map.get(q.casefold(), (q or "无法可靠还原", "unknown"))
        key = base.casefold()
        g = grouped.setdefault(key, {"base": base, "source": source, "rows": [], "queries": []})
        g["rows"].append(r)
        if q and q not in g["queries"]:
            g["queries"].append(q)

    for key, g in grouped.items():
        run_id = "legacy-keyword-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        gr: list[sqlite3.Row] = g["rows"]
        started = min((r["found_at"] or "" for r in gr), default="")
        finished = max((r["found_at"] or "" for r in gr), default="")
        creators = {r["channel_id"] for r in gr if r["channel_id"]}
        queries = g["queries"]
        conn.execute("""INSERT INTO discovery_runs(run_id,base_query,base_query_source,search_source,queries_requested_json,queries_executed_json,started_at,finished_at,status,hits,unique_creators,errors_json)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (run_id,g["base"],g["source"],"legacy-inferred",json_dump(queries),json_dump(queries),started,finished,"legacy",len(gr),len(creators),'[]'))
        # run_id is a derived association; every original evidence field remains unchanged.
        conn.executemany("UPDATE discovery_hits SET run_id=? WHERE id=?", [(run_id, r["id"]) for r in gr])

        by_creator: dict[str, list[sqlite3.Row]] = {}
        for r in gr:
            if r["channel_id"]:
                by_creator.setdefault(r["channel_id"], []).append(r)
        payload = []
        for cid, cr in by_creator.items():
            cr_sorted = sorted(cr, key=lambda r: ((r["pre_score"] if r["pre_score"] is not None else -1), r["found_at"] or "", r["id"]), reverse=True)
            best = cr_sorted[0]
            matched: list[str] = []
            videos: set[str] = set()
            for r in cr:
                q = _clean_query(r["query"])
                if q and q not in matched:
                    matched.append(q)
                if r["video_id"]:
                    videos.add(r["video_id"])
            payload.append((run_id,cid,best["channel_title"],best["channel_url"],best["subscribers"],best["country_resolved"],best["country_source"],best["video_id"],best["title"],best["views"],best["pre_score"],best["opportunity_tier"],len(matched),json_dump(matched),len(videos),max((r["found_at"] or "" for r in cr),default="")))
        if payload:
            conn.executemany("""INSERT INTO discovery_creator_results(run_id,channel_id,channel_title,channel_url,subscribers,country_resolved,country_source,best_video_id,best_video_title,best_video_views,best_discovery_score,opportunity_tier,query_coverage,matched_queries_json,hit_video_count,found_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", payload)

    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('legacy_discovery_inference_version',?)", (str(LEGACY_DISCOVERY_INFERENCE_VERSION),))



def _rebuild_discovery_summary(conn: sqlite3.Connection) -> None:
    current = conn.execute("SELECT value FROM meta WHERE key='discovery_summary_version'").fetchone()
    if current and str(current[0]) == str(DISCOVERY_SUMMARY_VERSION):
        return
    conn.execute("DELETE FROM creator_discovery_summary")
    rows = conn.execute("""SELECT r.channel_id,r.found_at,r.hit_video_count,r.best_discovery_score,dr.base_query,r.run_id
                           FROM discovery_creator_results r
                           LEFT JOIN discovery_runs dr ON dr.run_id=r.run_id
                           WHERE COALESCE(r.channel_id,'')<>''
                           ORDER BY r.channel_id,r.found_at,r.id""").fetchall()
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        cid=r["channel_id"]
        a=agg.setdefault(cid,{"first":r["found_at"] or "","last":r["found_at"] or "","runs":set(),"hits":0,"best":None,"last_query":""})
        at=r["found_at"] or ""
        if at and (not a["first"] or at<a["first"]): a["first"]=at
        if at and (not a["last"] or at>=a["last"]):
            a["last"]=at; a["last_query"]=r["base_query"] or ""
        if r["run_id"]: a["runs"].add(r["run_id"])
        a["hits"] += int(r["hit_video_count"] or 0)
        score=r["best_discovery_score"]
        if score is not None and (a["best"] is None or float(score)>float(a["best"])): a["best"]=float(score)
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat().replace('+00:00','Z')
    payload=[(cid,a["first"],a["last"],len(a["runs"]),a["hits"],a["best"],a["last_query"],now) for cid,a in agg.items()]
    if payload:
        conn.executemany("""INSERT INTO creator_discovery_summary(channel_id,first_seen_at,last_seen_at,discovery_run_count,hit_video_count_total,best_discovery_score,last_base_query,updated_at)
                            VALUES(?,?,?,?,?,?,?,?)""",payload)
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('discovery_summary_version',?)",(str(DISCOVERY_SUMMARY_VERSION),))

def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def init_db(db_path: str | Path) -> None:
    from .migrations import run_migrations
    with connect(db_path) as conn:
        before=conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() if _table_exists(conn,'meta') else None
        old_version=int(before[0]) if before and str(before[0]).isdigit() else 0
        conn.executescript(SCHEMA_SQL)
        _ensure_columns(conn, "creators", CREATOR_COLUMNS)
        _ensure_columns(conn, "discovery_hits", DISCOVERY_COLUMNS)
        _ensure_columns(conn, "discovery_runs", DISCOVERY_RUN_COLUMNS)
        _ensure_columns(conn, "ai_runs", AI_RUN_COLUMNS)
        _ensure_columns(conn, "creator_business_metrics", BUSINESS_METRIC_COLUMNS)
        run_migrations(conn, old_version, SCHEMA_VERSION)
        #  business rule: UgPhone backend GMV is already a USD cumulative snapshot.
        # Backfill every historical GMV row so legacy FX/pending states disappear without re-import.
        conn.execute("UPDATE creator_business_metrics SET currency='USD',metric_value_usd=metric_value,fx_rate_to_usd=1.0,fx_rate_date=substr(captured_at,1,10),fx_provider='ugphone_backend_usd',fx_status='native_usd' WHERE metric_key='gmv'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_run ON discovery_hits(run_id)")
        _rebuild_legacy_discovery(conn)
        _rebuild_discovery_summary(conn)
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
