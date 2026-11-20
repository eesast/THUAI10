$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../logic/mujoco')).Path
$arenaPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $arenaPython)) {
    throw 'Run setup.cmd before configuring the runtime.'
}
Set-Location -LiteralPath $projectRoot
& $arenaPython -m embodied_arena.platform.deploy
if ($LASTEXITCODE -ne 0) { throw 'Runtime preparation failed.' }
