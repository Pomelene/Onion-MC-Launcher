# Reproducible Qt build: isolate native DLL discovery from unrelated tools in PATH.
param([string]$OutputName='OnionMinecraftLauncher.exe')
$ErrorActionPreference='Stop'
if ($OutputName -ne [IO.Path]::GetFileName($OutputName) -or $OutputName -notmatch '\.exe$') { throw 'OutputName must be an executable filename without a directory.' }
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'assets\native\onion_seedmap.dll'))) {
    & python (Join-Path $taskRoot 'scripts\build_seedmap.py')
    if ($LASTEXITCODE -ne 0) { throw 'Local seed-map component build failed.' }
}
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
Push-Location -LiteralPath $taskRoot
try {
    $env:PATH=@($taskPythonDir,$taskQt,$taskShiboken,(Join-Path $env:SystemRoot 'System32'),$env:SystemRoot)-join ';'
    $env:TEMP=Join-Path $taskRoot 'tmp\build-temp'
    $env:TMP=$env:TEMP
    $env:PYINSTALLER_CONFIG_DIR=Join-Path $taskRoot 'tmp\pyinstaller-cache'
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
    # Exercise qwindows and the raster painter without displaying any window.
    $taskRasterReport=Join-Path $taskRoot 'docs\qt-windows-raster-check.json'
    $taskRaster=Start-Process -FilePath $taskStage -ArgumentList @('--raster-check-output',('"'+$taskRasterReport+'"')) -WindowStyle Hidden -PassThru -Wait
    if ($taskRaster.ExitCode -ne 0) { throw 'Packaged Windows raster check failed; release executable has not been replaced.' }
    $taskRasterResult=Get-Content -LiteralPath $taskRasterReport -Raw | ConvertFrom-Json
    if ($taskRasterResult.result -ne 'pass' -or $taskRasterResult.visible_windows -ne $false) { throw 'Windows raster check did not report hidden-window success.' }
    & $taskPython -X utf8 scripts/check_bundle.py $taskStage --require-slim --max-bytes 38000000 --output docs/bundle-audit.json
    if ($LASTEXITCODE -ne 0) { throw 'Bundle size/dependency audit failed; release executable has not been replaced.' }
    $taskRelease=Join-Path $taskRoot 'release'
    New-Item -ItemType Directory -Path $taskRelease -Force | Out-Null
    $taskDestination=Join-Path $taskRelease $OutputName
    $taskStageHash=(Get-FileHash -LiteralPath $taskStage -Algorithm SHA256).Hash
    $taskCopied=$false
    for ($taskAttempt=0; $taskAttempt -lt 5; $taskAttempt++) {
        try {
            Copy-Item -LiteralPath $taskStage -Destination $taskDestination -Force
            $taskCopied=$true; break
        } catch [System.IO.IOException] {
            # Antivirus/indexers can hold a newly written file before Copy-Item
            # finishes its metadata update. Accept it only if content matches.
            if ((Test-Path -LiteralPath $taskDestination) -and (Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash -eq $taskStageHash) {
                $taskCopied=$true; break
            }
            if ($taskAttempt -eq 4) { throw }
            Start-Sleep -Milliseconds (200*($taskAttempt+1))
        }
    }
    if (-not $taskCopied -or (Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash -ne $taskStageHash) { throw 'Release copy checksum mismatch.' }
    Write-Output ('Ready: release\'+$OutputName)
} finally {
    $env:PATH=$taskSavedPath
    $env:TEMP=$taskSavedTemp
    $env:TMP=$taskSavedTmp
    $env:PYINSTALLER_CONFIG_DIR=$taskSavedCache
    Pop-Location
}
