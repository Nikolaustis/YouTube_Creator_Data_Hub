$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "[1/3] Checking Python..."
python --version
Write-Host "[2/3] Installing small Python dependency set (no Node/npm)..."
python -m pip install -r .\requirements.txt
Write-Host "[3/3] Initializing SQLite and running self-check..."
python .\hub.py init
python .\scripts\self_check.py
Write-Host "Installed. Next: run .\scripts\set-api-key.ps1 once, or ask Codex to configure the Skill." -ForegroundColor Green
