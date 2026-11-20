param(
    [ValidateRange(1024, 65535)][int]$Port = 8767,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../logic/mujoco')).Path
$pythonWindowless = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$entryPoint = Join-Path $PSScriptRoot 'serve_platform.py'
$localUrl = "http://127.0.0.1:$Port"

function Test-PortalReady {
    $response = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create("$localUrl/api/status")
        $request.Proxy = $null
        $request.Timeout = 1000
        $response = $request.GetResponse()
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        try {
            $status = $reader.ReadToEnd() | ConvertFrom-Json
            return $status.name -eq 'THUAI10 MuJoCo'
        } finally {
            $reader.Dispose()
        }
    } catch {
        return $false
    } finally {
        if ($null -ne $response) { $response.Dispose() }
    }
}

if (-not (Test-PortalReady)) {
    if (-not (Test-Path -LiteralPath $pythonWindowless)) {
        throw 'Missing .venv\Scripts\pythonw.exe. Install the project environment first.'
    }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $identityBytes = [Text.Encoding]::UTF8.GetBytes("$($projectRoot.ToLowerInvariant())|$Port")
        $suffix = ([BitConverter]::ToString($hasher.ComputeHash($identityBytes))).Replace('-', '').Substring(0, 12)
    } finally {
        $hasher.Dispose()
    }
    $taskName = "THUAI10-MuJoCo-Portal-$suffix"
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $arguments = '"' + $entryPoint + '" --host 0.0.0.0 --port ' + $Port
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $existing -and ($existing.Actions.Execute -ne $pythonWindowless -or $existing.Actions.Arguments -ne $arguments)) {
        throw 'A different task already uses this service identity; it was not changed.'
    }
    if ($null -eq $existing) {
        $action = New-ScheduledTaskAction -Execute $pythonWindowless -Argument $arguments -WorkingDirectory $projectRoot
        $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
        # No trigger: starts only when this launcher is invoked, not on login.
        Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings `
            -Description "On-demand THUAI10 MuJoCo portal for $projectRoot" | Out-Null
    }
    Start-ScheduledTask -TaskName $taskName
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while (-not (Test-PortalReady)) {
        if ([DateTime]::UtcNow -ge $deadline) {
            $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
            throw "Portal did not become ready. Task result: $($taskInfo.LastTaskResult). See var\platform\service.err.log."
        }
        Start-Sleep -Milliseconds 400
    }
}

Write-Output "THUAI10 MuJoCo is ready: $localUrl"
if (-not $NoBrowser) {
    Start-Process -FilePath $localUrl
}
