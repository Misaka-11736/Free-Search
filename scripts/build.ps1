param(
  [ValidateSet('offline','api')][string]$Edition='offline',
  [string]$OutputRoot='dist'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
Set-Location $taskRoot
$taskOutput = [IO.Path]::GetFullPath((Join-Path $taskRoot $OutputRoot))
if (-not $taskOutput.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
  throw 'OutputRoot must be inside the workspace.'
}
$env:TEMP = Join-Path $taskRoot 'private\tmp'
$env:TMP = $env:TEMP
$env:PYTHONUTF8 = '1'
# Keep unrelated bundled tools (for example Poppler's incompatible ICU DLL)
# out of PyInstaller's native dependency search.
$taskOriginalPath = $env:PATH
$env:PATH = (Join-Path $env:WINDIR 'System32') + ';' + $env:WINDIR + ';' + (Join-Path $taskRoot '.venv\Scripts')
New-Item -ItemType Directory -Force -Path $env:TEMP,(Join-Path $taskRoot 'build') | Out-Null
$taskEditionFile = Join-Path $taskRoot "build\edition-$Edition.json"
@{edition=$Edition} | ConvertTo-Json | Set-Content -Encoding utf8 $taskEditionFile
# Use a per-edition input directory so concurrent builds cannot swap edition flags.
$taskEditionDir = Join-Path $taskRoot "build\config-$Edition"
New-Item -ItemType Directory -Force -Path $taskEditionDir | Out-Null
Copy-Item -LiteralPath $taskEditionFile -Destination (Join-Path $taskEditionDir 'edition.json')
$taskArgs = @(
  '--noconfirm','--onedir','--windowed','--name',"FreeSearch-$Edition",
  '--paths',(Join-Path $taskRoot 'src'),'--specpath','build','--distpath',$taskOutput,
  '--add-data',((Join-Path $taskEditionDir 'edition.json') + ';.'),
  '--collect-all','rapidocr_onnxruntime',
  '--collect-data','jieba','--collect-all','lancedb',
  '--collect-data','transformers','--collect-submodules','transformers.models.bert',
  '--collect-submodules','transformers.models.xlm_roberta',
  '--collect-submodules','transformers.models.chinese_clip',
  '--collect-all','faster_whisper',
  '--hidden-import','keyring.backends.Windows',
  '--exclude-module','sounddevice','--exclude-module','soundfile',
  '--exclude-module','PySide6.QtWebEngineCore',
  '--exclude-module','PySide6.QtWebEngineWidgets',
  '--exclude-module','sentence_transformers',
  '--exclude-module','pytest',(Join-Path $taskRoot 'packaging\launcher.py')
)
try { & .\.venv\Scripts\python.exe -m PyInstaller @taskArgs }
finally { $env:PATH = $taskOriginalPath }
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
# Qt uses the ICU API supplied by Windows 11. A DLL named icuuc.dll from a
# third-party tool has version-suffixed exports and makes QtCore fail to load.
# Remove it even when PyInstaller reuses an older cached dependency analysis.
$taskProgram = Join-Path $taskOutput "FreeSearch-$Edition"
$taskIcu = Join-Path $taskProgram '_internal\icuuc.dll'
if (Test-Path -LiteralPath $taskIcu) { Remove-Item -LiteralPath $taskIcu }
# These plugins are unused: PDF renders through pypdfium2, video through PyAV,
# and the Widgets UI has no virtual keyboard. Omit their separate native builds.
Get-ChildItem -LiteralPath (Join-Path $taskProgram '_internal') -Recurse -File |
  Where-Object { $_.Name -in @('Qt6VirtualKeyboard.dll','qtvirtualkeyboardplugin.dll','Qt6Pdf.dll','qpdf.dll') -or $_.Name -like 'opencv_videoio_ffmpeg*_64.dll' } |
  Remove-Item
Copy-Item -LiteralPath LICENSE,THIRD_PARTY_NOTICES.md,BINARY_LICENSE.txt -Destination $taskProgram
Write-Host "Built $taskProgram. Place the separately prepared models folder alongside the EXE."
