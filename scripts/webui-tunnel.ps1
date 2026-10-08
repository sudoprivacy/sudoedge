param(
    [string]$Box,
    [string]$IdentityFile,
    [int]$LocalPort = 12808
)
$ErrorActionPreference = 'Stop'
$logFile = Join-Path $PSScriptRoot 'webui-tunnel.log'
while ($true) {
    if ((Test-Path $logFile) -and (Get-Item $logFile).Length -gt 1048576) {
        Move-Item -LiteralPath $logFile -Destination "$logFile.old" -Force
    }
    "$(Get-Date -Format o) Connecting to $Box" | Out-File $logFile -Append
    try {
        & "$env:WINDIR\System32\OpenSSH\ssh.exe" -N -T `
            -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 `
            -o ServerAliveInterval=15 -o ServerAliveCountMax=3 `
            -i $IdentityFile -L "127.0.0.1:${LocalPort}:127.0.0.1:26808" $Box 2>> $logFile
    } catch {
        "$(Get-Date -Format o) SSH disconnected; retrying in 5 seconds." | Out-File $logFile -Append
    }
    Start-Sleep -Seconds 5
}
