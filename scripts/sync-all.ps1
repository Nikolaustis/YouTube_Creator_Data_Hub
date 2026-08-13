$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python .\hub.py sync --mode incremental
python .\hub.py dashboard
