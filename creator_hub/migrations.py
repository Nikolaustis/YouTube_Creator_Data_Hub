from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
import sqlite3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _add(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    if col not in _cols(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]
    checksum: str


def _m17(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
        version INTEGER PRIMARY KEY,name TEXT NOT NULL,checksum TEXT NOT NULL,applied_at TEXT NOT NULL
    )""")
    for col,ddl in [
        ('payload_json',"TEXT NOT NULL DEFAULT '{}'"),('resource_class',"TEXT NOT NULL DEFAULT 'local'"),
        ('cancel_requested',"INTEGER NOT NULL DEFAULT 0"),('checkpoint_json',"TEXT NOT NULL DEFAULT '{}'"),
        ('resumable',"INTEGER NOT NULL DEFAULT 0"),('retry_count',"INTEGER NOT NULL DEFAULT 0"),
        ('parent_job_id',"TEXT"),('worker_id',"TEXT")
    ]:_add(conn,'job_runs',col,ddl)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_resource_state ON job_runs(resource_class,state,updated_at DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS run_specs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        spec_type TEXT NOT NULL,
        title TEXT NOT NULL,
        spec_version INTEGER NOT NULL DEFAULT 1,
        spec_json TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        source_ai_run_id INTEGER,
        source_result_set_id INTEGER,
        parent_spec_id INTEGER,
        created_at TEXT NOT NULL,
        UNIQUE(fingerprint,source_result_set_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_specs_type_time ON run_specs(spec_type,created_at DESC)")
    _add(conn,'ai_result_sets','run_spec_id','INTEGER')
    conn.execute("""CREATE TABLE IF NOT EXISTS data_assertions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        field_id TEXT NOT NULL,
        layer TEXT NOT NULL CHECK(layer IN ('fact','derived','ai','human')),
        value_json TEXT NOT NULL,
        confidence REAL,
        source_ref TEXT,
        rule_version TEXT,
        observed_at TEXT,
        created_at TEXT NOT NULL,
        supersedes_id INTEGER
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_assertions_entity_field ON data_assertions(entity_type,entity_id,field_id,created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_assertions_layer ON data_assertions(layer,created_at DESC)")



def _m18(conn: sqlite3.Connection) -> None:
    """Generic Creator Intelligence workspace foundation.

    Migration 18 is deliberately domain-neutral: it creates only generic entities.
    Brand/industry-specific defaults are installed later by WorkspaceService templates.
    """
    conn.execute("""CREATE TABLE IF NOT EXISTS workspaces(
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL,
        template_id TEXT NOT NULL DEFAULT 'blank',
        status TEXT NOT NULL DEFAULT 'active',
        is_default INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug)")
    conn.execute("""CREATE TABLE IF NOT EXISTS workspace_settings(
        workspace_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id,key),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS workspace_brands(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        key TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'brand',
        aliases_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,key),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_brands_workspace ON workspace_brands(workspace_id,role,display_name)")
    conn.execute("""CREATE TABLE IF NOT EXISTS brand_groups(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,key),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS brand_group_members(
        group_id TEXT NOT NULL,
        brand_id TEXT NOT NULL,
        PRIMARY KEY(group_id,brand_id),
        FOREIGN KEY(group_id) REFERENCES brand_groups(id) ON DELETE CASCADE,
        FOREIGN KEY(brand_id) REFERENCES workspace_brands(id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS taxonomy_schemes(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        entity_type TEXT NOT NULL DEFAULT 'video',
        multi_select INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,key),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS taxonomy_labels(
        id TEXT PRIMARY KEY,
        scheme_id TEXT NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        parent_label_id TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(scheme_id,key),
        FOREIGN KEY(scheme_id) REFERENCES taxonomy_schemes(id) ON DELETE CASCADE,
        FOREIGN KEY(parent_label_id) REFERENCES taxonomy_labels(id) ON DELETE SET NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS video_taxonomy_assignments(
        workspace_id TEXT NOT NULL,
        video_id TEXT NOT NULL,
        scheme_id TEXT NOT NULL,
        label_id TEXT NOT NULL,
        layer TEXT NOT NULL DEFAULT 'derived' CHECK(layer IN ('fact','derived','ai','human')),
        source_ref TEXT,
        assigned_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id,video_id,scheme_id,label_id,layer),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
        FOREIGN KEY(video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
        FOREIGN KEY(scheme_id) REFERENCES taxonomy_schemes(id) ON DELETE CASCADE,
        FOREIGN KEY(label_id) REFERENCES taxonomy_labels(id) ON DELETE CASCADE
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_taxonomy_workspace_video ON video_taxonomy_assignments(workspace_id,video_id,scheme_id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS creator_relationships(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        brand_id TEXT,
        relationship_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        source_ref TEXT,
        note TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,channel_id,brand_id,relationship_type,status),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
        FOREIGN KEY(channel_id) REFERENCES creators(channel_id) ON DELETE CASCADE,
        FOREIGN KEY(brand_id) REFERENCES workspace_brands(id) ON DELETE CASCADE
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_relationships_workspace ON creator_relationships(workspace_id,channel_id,relationship_type,status)")
    conn.execute("""CREATE TABLE IF NOT EXISTS business_metric_definitions(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        value_type TEXT NOT NULL DEFAULT 'number',
        unit TEXT,
        currency TEXT,
        aggregation TEXT NOT NULL DEFAULT 'sum',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,key),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS discovery_profiles(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        profile_json TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,key),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS workspace_presets(
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        preset_type TEXT NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,preset_type,key),
        FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    )""")

def _checksum(name: str, version: int) -> str:
    return hashlib.sha256(f'{version}:{name}:v1'.encode()).hexdigest()

MIGRATIONS=[
    Migration(17,'core_architecture_foundation',_m17,_checksum('core_architecture_foundation',17)),
    Migration(18,'generic_workspace_foundation',_m18,_checksum('generic_workspace_foundation',18)),
]


def run_migrations(conn: sqlite3.Connection, current_version: int, target_version: int) -> list[int]:
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
        version INTEGER PRIMARY KEY,name TEXT NOT NULL,checksum TEXT NOT NULL,applied_at TEXT NOT NULL
    )""")
    if current_version>0 and current_version<17 and not conn.execute("SELECT 1 FROM schema_migrations WHERE version=?",(current_version,)).fetchone():
        base_name=f"legacy_schema_{current_version}_baseline"
        conn.execute("INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",(current_version,base_name,hashlib.sha256(base_name.encode()).hexdigest(),_now()))
    applied=[]
    for m in MIGRATIONS:
        if m.version>target_version: continue
        row=conn.execute('SELECT checksum FROM schema_migrations WHERE version=?',(m.version,)).fetchone()
        if row:
            if str(row[0])!=m.checksum: raise RuntimeError(f'migration checksum mismatch: {m.version}')
            continue
        if current_version < m.version or current_version == 0:
            m.apply(conn)
            conn.execute('INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)',(m.version,m.name,m.checksum,_now()))
            applied.append(m.version)
    return applied
