param([string]$IsccPath='ISCC.exe')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskStage = Join-Path $taskRoot 'dist\installer-stage\FreeSearch'
$taskRelease = Join-Path $taskRoot 'dist\installer-release'
if (-not (Test-Path -LiteralPath (Join-Path $taskStage 'models\manifest.json'))) {
  throw 'Run stage_installer.py first; full models are required.'
}
& $IsccPath "/DStagingDir=$taskStage" "/DSetupOutput=$taskRelease" (Join-Path $taskRoot 'packaging\FreeSearch.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed' }
Write-Host "Installer and all data slices: $taskRelease"
