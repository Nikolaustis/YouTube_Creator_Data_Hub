$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$PythonRun = Join-Path $PSScriptRoot "python-run.cmd"
& $PythonRun ".\hub.py" "sync" "--mode" "incremental"
if ($LASTEXITCODE -ne 0) { throw "Creator sync failed with exit code $LASTEXITCODE" }
& $PythonRun ".\hub.py" "maintenance" "snapshots" "--auto"
if ($LASTEXITCODE -ne 0) { Write-Warning "Snapshot maintenance returned exit code $LASTEXITCODE; continuing to rebuild Dashboard." }
& $PythonRun ".\hub.py" "dashboard"
if ($LASTEXITCODE -ne 0) { throw "Dashboard rebuild failed with exit code $LASTEXITCODE" }
