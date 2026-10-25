param([string]$Python='python')
$ErrorActionPreference='Stop'
$taskRoot=$PSScriptRoot
$taskDeps=Join-Path $taskRoot '.build-deps'
& $Python -m pip install --target $taskDeps -r (Join-Path $taskRoot 'requirements-build.txt')
if($LASTEXITCODE -ne 0){throw 'Dependency installation failed'}
$taskOldPythonPath=$env:PYTHONPATH
try {
  $env:PYTHONPATH=$taskDeps
  & $Python (Join-Path $taskRoot 'app.py') --self-test (Join-Path $taskRoot 'test-report.txt')
  if($LASTEXITCODE -ne 0){throw 'Offline checks failed'}
  & $Python -m PyInstaller --noconfirm --onefile --windowed --name GoutouWechat `
    --distpath (Join-Path $taskRoot 'dist') --workpath (Join-Path $taskRoot 'build') --specpath $taskRoot `
    --paths $taskRoot --paths $taskDeps --add-data "$taskRoot\skill;skill" `
    --add-data "$taskRoot\vendor;vendor" --add-data "$taskRoot\tests;tests" `
    --collect-all cryptography --collect-all zstandard --collect-all uiautomation --collect-all comtypes `
    --hidden-import unittest --hidden-import unittest.mock (Join-Path $taskRoot 'app.py')
  if($LASTEXITCODE -ne 0){throw 'Packaging failed'}
} finally {$env:PYTHONPATH=$taskOldPythonPath}
