# Reproducible Qt build: isolate native DLL discovery from unrelated tools in PATH.
param([string]$OutputName='OnionMinecraftLauncher.exe')
$ErrorActionPreference='Stop'
if ($OutputName -ne [IO.Path]::GetFileName($OutputName) -or $OutputName -notmatch '\.exe$') { throw 'OutputName must be an executable filename without a directory.' }
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskAppManifest=Join-Path $taskRoot 'assets\microsoft-app.json'
if (-not (Test-Path -LiteralPath $taskAppManifest)) {
    Copy-Item -LiteralPath (Join-Path $taskRoot 'assets\microsoft-app.example.json') -Destination $taskAppManifest
}
$taskPython=(Get-Command python.exe).Source
$taskPythonDir=Split-Path -Parent $taskPython
$taskQt=Join-Path $taskRoot '.deps\qt\PySide6'
$taskShiboken=Join-Path $taskRoot '.deps\qt\shiboken6'
if (-not (Test-Path -LiteralPath $taskQt)) { throw 'Install project-local Qt: python -m pip install --target .deps/qt PySide6-Essentials==6.12.0' }
$taskSavedPath=$env:PATH
$taskSavedTemp=$env:TEMP
$taskSavedTmp=$env:TMP
$taskSavedCache=$env:PYINSTALLER_CONFIG_DIR
$taskSavedPythonPath=$env:PYTHONPATH
Push-Location -LiteralPath $taskRoot
try {
    $env:PATH=@($taskPythonDir,$taskQt,$taskShiboken,(Join-Path $env:SystemRoot 'System32'),$env:SystemRoot)-join ';'
    $env:TEMP=Join-Path $taskRoot 'tmp\build-temp'
    $env:TMP=$env:TEMP
    $env:PYINSTALLER_CONFIG_DIR=Join-Path $taskRoot 'tmp\pyinstaller-cache'
    if (Test-Path -LiteralPath (Join-Path $taskRoot '.deps\pillow')) {
        $env:PYTHONPATH=(Join-Path $taskRoot '.deps\pillow')+[IO.Path]::PathSeparator+$env:PYTHONPATH
    }
    New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
    # A cached PYZ can retain old code even after Analysis reruns. Clean only
    # the project-local build/cache paths before producing a reviewable binary.
    $taskWorkPath=[IO.Path]::GetFullPath((Join-Path $taskRoot 'build\qt-isolated'))
    $taskCachePath=[IO.Path]::GetFullPath($env:PYINSTALLER_CONFIG_DIR)
    foreach ($taskBuildPath in @($taskWorkPath,$taskCachePath)) {
        if (-not $taskBuildPath.StartsWith($taskRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Build cleanup path must remain inside the project.' }
    }
    & $taskPython -m PyInstaller --clean --noconfirm --distpath dist/qt --workpath $taskWorkPath packaging/craftbridge.spec
    if ($LASTEXITCODE -ne 0) { throw 'Qt build failed; existing launcher has been retained.' }
    $taskStage=Join-Path $taskRoot 'dist\qt\OnionMinecraftLauncher.exe'
    $taskReport=Join-Path $taskRoot 'docs\qt-frozen-check.json'
    $taskProcess=Start-Process -FilePath $taskStage -ArgumentList @('--self-check-output',('"'+$taskReport+'"')) -WindowStyle Hidden -PassThru -Wait
    if ($taskProcess.ExitCode -ne 0) { throw 'Packaged Qt self-check failed; release executable has not been replaced.' }
    $taskResult=Get-Content -LiteralPath $taskReport -Raw | ConvertFrom-Json
    if ($taskResult.result -ne 'pass') { throw 'Packaged Qt self-check did not report success.' }
    Copy-Item -LiteralPath $taskStage -Destination (Join-Path (Join-Path $taskRoot 'dist') $OutputName) -Force
    Write-Output ('Ready: dist\'+$OutputName)
} finally {
    $env:PATH=$taskSavedPath
    $env:TEMP=$taskSavedTemp
    $env:TMP=$taskSavedTmp
    $env:PYINSTALLER_CONFIG_DIR=$taskSavedCache
    $env:PYTHONPATH=$taskSavedPythonPath
    Pop-Location
}
