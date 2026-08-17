param([string]$StartTime = "00:00")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $PSScriptRoot "sync-all.ps1"
$TaskName = "YouTube Creator Data Hub Sync"
$LegacyTaskName = "YouTube Creator Data Hub Daily Sync"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$base = [datetime]::ParseExact($StartTime, "HH:mm", $null)
$Triggers = @()
foreach ($offset in @(0,6,12,18)) {
  $Triggers += New-ScheduledTaskTrigger -Daily -At $base.AddHours($offset)
}
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Unregister-ScheduledTask -TaskName $LegacyTaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -Description "Run every 6 hours; the Skill refresh policy decides which monitored creators are due." -Force | Out-Null
Write-Host "Scheduled task installed: $TaskName (every 6 hours from $StartTime)." -ForegroundColor Green
