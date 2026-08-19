# Operations and data safety

This document covers routine operation for YouTube Creator Data Hub v2.1.0. All commands are run from the Skill root. On Windows, `scripts\python-run.cmd` automatically resolves `python` or `py -3`.

## Database health

Quick operational summary:

```powershell
.\scripts\python-run.cmd hub.py db-health
```

The Data Update Dashboard exposes the same database size/count information. The page loads lightweight metadata first; use **运行完整性检查** when you explicitly want SQLite `quick_check`. A full `integrity_check` is available from CLI:

```powershell
.\scripts\python-run.cmd hub.py db-health --full
```

## Consistent backup and restore

Create a consistent SQLite backup with the SQLite Backup API:

```powershell
.\scripts\python-run.cmd hub.py backup
```

Backups are stored under `backups/` by default. The live database is not copied into release/cover packages.

Restore from a backup:

```powershell
.\scripts\python-run.cmd hub.py restore .\backups\creator_hub_YYYYMMDD_HHMMSS.sqlite --yes
```

Restore validates the source and creates a pre-restore safety backup first. Stop other write jobs while restoring. The interactive Dashboard also provides backup/restore controls under **数据更新 → 数据库健康 / 备份**.

## Monitoring health and retry behavior

```powershell
.\scripts\python-run.cmd hub.py monitoring-health --limit 200
```

Creator sync state records last attempt/status/error, error category, consecutive failure count, next normal sync, next retry and suspension. Retry delay increases from 1h → 6h → 24h → 48h → 72h. Repeated non-quota/non-auth failures suspend after five failures to avoid repeatedly spending quota. Resume from the Dashboard or a batch Creator action after correcting the cause.

Priority cadence remains high 6h, normal 24h, low 72h, archive 168h. The Windows task wakes every six hours and only processes due/retry-eligible creators.

## Snapshot lifecycle

Estimate reclaimable redundant snapshots without deleting anything:

```powershell
.\scripts\python-run.cmd hub.py maintenance snapshots --dry-run
```

Compact:

```powershell
.\scripts\python-run.cmd hub.py maintenance snapshots
```

Retention policy:

- <=30 days: keep all snapshots
- 31–180 days: keep one per entity per day
- 181–730 days: keep one per entity per week
- older than 730 days: keep one per entity per month

The scheduled sync invokes `maintenance snapshots --auto`; auto mode skips when the previous compaction was less than seven days ago.

## Business configuration persistence

In interactive mode, Secondary Metrics / Rules and Discovery Query profiles are stored in SQLite `app_settings`. Existing browser configuration is migrated when no SQLite value exists. Static read-only mode may still use browser-local fallback.

Metric deletion is blocked when another ratio metric, rule, or active filter depends on it. Use the Dashboard dependency information before editing/deleting shared metrics.

## Discovery workflow

Discovery creators can be marked:

- 未处理 (`unreviewed`)
- 感兴趣 (`interested`)
- 待联系 (`to_contact`)
- 已入库 (`added`)
- 暂不考虑 (`defer`)
- 永久排除 (`excluded`)

Permanent exclusions are hidden from new live discovery results by default but can be shown explicitly. Workflow changes are audited. Discovery history also records first seen, last seen and number of discovery runs.

## Unified freshness

Creator rows/details distinguish the freshness of channel facts, video metrics, classification, contacts, discovery and complete sync. Do not treat one recent timestamp as proof that every data category is fresh.
