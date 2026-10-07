param(
    [string]$Box = 'taolei@192.168.1.11',
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\dgx_spark",
    [int]$LocalPort = 12808,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $IdentityFile)) { throw "SSH identity not found: $IdentityFile" }
if ($LocalPort -lt 1024 -or $LocalPort -gt 65535) { throw 'LocalPort must be between 1024 and 65535.' }
if ($Box -notmatch '^[a-zA-Z0-9_.@:-]+$' -or $Box.StartsWith('-')) { throw 'Invalid SSH destination.' }
if ($IdentityFile.Contains('"')) { throw 'Invalid SSH identity path.' }
$taskName = "SudoEdge-WebUI-$LocalPort"
$installDir = Join-Path $env:LOCALAPPDATA $taskName
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
$helper = Join-Path $installDir 'webui-tunnel.ps1'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'webui-tunnel.ps1') -Destination $helper -Force
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$helper`" -Box `"$Box`" -IdentityFile `"$IdentityFile`" -LocalPort $LocalPort"
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
$isReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$LocalPort/health/live" -TimeoutSec 2
        if ($health.status -eq 'ok') { $isReady = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $isReady) { throw "WebUI is not ready. Check $installDir\webui-tunnel.log and SSH access to $Box." }
Write-Output "WebUI ready: http://localhost:$LocalPort (automatic reconnect; task $taskName)"
if (-not $NoBrowser) { Start-Process "http://localhost:$LocalPort" }
