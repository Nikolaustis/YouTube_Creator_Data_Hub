# Installation and first run

## Requirements

- Windows 10/11
- Python 3.10 or newer available as `python`, or through the Windows Python Launcher as `py -3`
- Internet access for YouTube discovery/sync
- A YouTube Data API v3 API key for API enrichment and sync
- Node/npm is **not** required

## Recommended first run

From the Skill root, double-click `setup.cmd`, or run:

```powershell
.\setup.cmd
```

The setup flow checks Python, installs `requirements.txt`, initializes/upgrades the local SQLite schema, offers to configure `YOUTUBE_API_KEY`, runs diagnostics, and builds the Dashboard. When setup finishes, a next-step menu can start the interactive Dashboard, open the static Dashboard, install automatic monitoring, or validate the API key online. The launchers prefer `python` and automatically fall back to the Windows Python Launcher (`py -3`) when available.

## Configure the YouTube API key

Recommended Windows entry point:

```powershell
.\scripts\set-api-key.cmd
```

The key is stored as the Windows **user environment variable** `YOUTUBE_API_KEY`. The Skill does not require the key to be written into source/config files.

Verify that the variable exists:

```powershell
python .\hub.py doctor
```

Validate the key online with one low-cost API request:

```powershell
python .\hub.py doctor --online
```

## Static Dashboard vs interactive Dashboard

### Interactive Dashboard — recommended for normal work

```powershell
.\start-dashboard.cmd
```

This starts a local Python HTTP service at `http://127.0.0.1:8765/`. The browser talks only to Python/SQLite on the same computer. It enables:

- YouTube discovery and Query Expansion
- writing creators/videos to SQLite
- full server-side filtering/pagination over the local database
- human review/corrections
- contact scraping
- full XLSX export of filtered results

### Static Dashboard — read-only snapshot

```powershell
.\open-static-dashboard.cmd
```

This opens the generated HTML directly. It does **not** start the Python service. It is useful for offline/read-only review, but write operations and full XLSX export require interactive mode.

The Dashboard header shows the current runtime mode and, in interactive mode, Python/SQLite/API-key status.

## Diagnose local interaction problems

Run:

```powershell
python .\hub.py doctor
```

If `python` is not a recognized command but the Windows Python Launcher is installed, use:

```powershell
.\scripts\python-run.cmd hub.py doctor
```

It checks:

- Python >= 3.10
- pip
- openpyxl
- SQLite/database schema
- write access to data/output directories
- presence of `YOUTUBE_API_KEY`
- the actual Python executable in use
- whether local port `8765` is currently available for the interactive Dashboard

For API validation:

```powershell
python .\hub.py doctor --online
```

If `start-dashboard.cmd` cannot open the interactive Dashboard, run `scripts\python-run.cmd hub.py doctor`. The output reports `python_executable`, `interactive_port_available`, and any port error. If port `8765` is occupied, stop the conflicting local process and retry.

## Optional automatic monitoring

Install the Windows scheduled task:

```powershell
.\scripts\install-sync-task.cmd
```

The task wakes every six hours. The Skill then refreshes only monitored creators whose priority cadence is due: high 6h, normal 24h, low 72h, archive 168h.

## v2.1.0 long-running operation

After first installation, use **数据更新** in the interactive Dashboard for monitoring health, database backup/restore and Snapshot maintenance. Secondary Metrics / Rules and Query Expansion profiles are persisted in SQLite in interactive mode so a database backup also carries these business configurations.

For operational commands and retention/retry details, see `docs/OPERATIONS.md`.
