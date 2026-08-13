param([string]$Time = "09:00")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $PSScriptRoot "sync-all.ps1"
$TaskName = "YouTube Creator Data Hub Daily Sync"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Refresh monitored YouTube creators and rebuild the static Dashboard." -Force | Out-Null
Write-Host "Scheduled task installed: $TaskName at $Time" -ForegroundColor Green
