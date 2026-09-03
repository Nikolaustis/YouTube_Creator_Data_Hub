# Operations and data safety

This document covers routine operation for YouTube Creator Data Hub v3.10.0. All commands are run from the Skill root. On Windows, `scripts\python-run.cmd` automatically resolves `python` or `py -3`.

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

v3.5.0 separately tracks **channel availability**. A `channels.list` miss first becomes `unavailable_pending`; it does **not** by itself imply a Community Guidelines violation. The Hub performs a best-effort public channel-page check. Explicit public-page markers can produce `terminated_community`, `terminated_copyright`, or `deleted`. Repeated unresolved misses become `unavailable_unknown`. Terminal availability states stop ordinary monitoring/retry while preserving all local Creator/Video history. Use **数据更新 → 监控健康 → 重新检测频道状态** to recheck; if the channel is available again, the Dashboard can restore monitoring.

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


## AI operations

Use `hub.py ai-status` to inspect AI availability without making a model call. AI run history and token counts are stored in `ai_runs`; cached results avoid repeated calls when source data, model and prompt version have not changed. The daily request soft limit is local and only affects AI features.


## Long-running Dashboard jobs (v3.9.0)

Interactive Dashboard operations that may take noticeable time run through the local background Job Center. Job state is mirrored into SQLite `job_runs`, so page navigation and browser refresh restore active/recent progress automatically. The Job Center reports task stage, current/total when available, percentage, elapsed time and completion/failure. A Python worker thread itself cannot survive a Dashboard server restart; any queued/running record left by a stopped server is therefore marked `已中断` on next startup and must be explicitly rerun. Already committed business data is not rolled back.

## Manual Creator availability overrides (v3.9.0)

In **数据更新 → 监控健康**, operators can batch-set an auditable manual channel status, content status and monitoring policy. Use this when YouTube/API detection remains `暂时不可用 · 待确认` but a human has verified termination, deletion, all-public-videos-cleared, long inactivity, or another lifecycle state. The system-detected status is retained separately; clearing the manual override returns the effective display to the system result. Terminal/stopped policies preserve all local history while preventing wasteful ordinary synchronization retries.

## Creator commercial metrics (v3.6.0)

Use **数据更新 → 商业表现数据** to import CSV/XLSX/XLSM containing Creator identity plus GMV / 拉新 / orders / revenue / commission / cost columns. Matching is deterministic: Channel ID, YouTube channel URL, unique Handle, or unique exact channel title. Unmatched rows are reported and are not guessed into the database. Re-importing the same source row updates the existing fact.

CLI equivalent:

```powershell
.\scripts\python-run.cmd hub.py import-business "C:\path\creator-business.xlsx"
```

The facts remain separate from YouTube facts and preserve capture-time/source lineage. GMV is treated as a USD cumulative snapshot. Use the Creator Inspector or Creator Library GMV/拉新 columns to review the latest snapshot.

## Saved Views (v3.6.0)

Creator Library and Video Classification can save the current filter/sort/page-size state to SQLite. Saved Views persist across browser sessions and are stored separately from the underlying facts.


## Release visual regression（v3.9.3）

维护者在封包前可运行 `python scripts/visual_regression.py --strict`。脚本需要 Playwright Python 包和 Chromium；普通用户的 `upgrade.cmd` / `self_check.py` 不依赖 Playwright。测试覆盖主要 Dashboard 页面、常见桌面分辨率与125%缩放，并拒绝非预期页面/表格横向溢出和可见子元素越出单元格。
