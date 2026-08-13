$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python .\hub.py dashboard
$index = Join-Path $Root "output\dashboard\index.html"
if (!(Test-Path $index)) { throw "Dashboard not generated: $index" }
Start-Process $index
