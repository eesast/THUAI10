param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../logic/mujoco'))

Write-Output '[1/4] Preparing Python environment...'
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.13 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.13 and retry environment creation.' }
}
$arenaPython = (Resolve-Path '.venv\Scripts\python.exe').Path
& $arenaPython -c "import sys; assert sys.version_info[:2] == (3,13), 'The pinned Windows environment requires Python 3.13'"
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python version.' }

Write-Output '[2/4] Installing pinned platform dependencies...'
& $arenaPython -m pip install -r (Join-Path $PSScriptRoot '../../python/mujoco/requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $arenaPython -m pip install -e '.[demo,web]' --no-deps
if ($LASTEXITCODE -ne 0) { throw 'Platform installation failed.' }

Write-Output '[3/4] Preparing assets, runtime, and real simulation self-check...'
& $arenaPython -m embodied_arena.platform.deploy
if ($LASTEXITCODE -ne 0) { throw 'Runtime deployment failed. Review the error above and retry.' }

Write-Output '[4/4] Starting the portal...'
& (Join-Path $PSScriptRoot 'start_platform.ps1') -NoBrowser:$NoBrowser
if ($LASTEXITCODE -ne 0) { throw 'Portal startup failed.' }
