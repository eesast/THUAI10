$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../logic/mujoco'))
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.13 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python environment.' }
}
$arenaPython = Join-Path (Get-Location) '.venv/Scripts/python.exe'
& $arenaPython -c "import sys; assert sys.version_info[:2] == (3,13), 'The pinned Windows environment requires Python 3.13'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required for this launcher.' }
& $arenaPython -m pip install -r (Join-Path $PSScriptRoot '../../python/mujoco/requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed.' }
& $arenaPython -m pip install -e '.[demo,web,test]' --no-deps
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $arenaPython (Join-Path $PSScriptRoot 'fetch_assets.py')
if ($LASTEXITCODE -ne 0) { throw 'Asset download or checksum verification failed.' }
Write-Output 'Ready. Run the demo launcher or: .\.venv\Scripts\python.exe -m embodied_arena run --viewer --realtime'
