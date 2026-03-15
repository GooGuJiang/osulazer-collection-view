Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$appName = "osulazer-collection-view"
$buildRoot = Join-Path $projectRoot "build"
$extractorOut = Join-Path $buildRoot "extractor_runtime"
$pyinstallerWork = Join-Path $buildRoot "pyinstaller"
$distRoot = Join-Path $projectRoot "dist"
$distApp = Join-Path $distRoot $appName
$legacyDistApp = Join-Path $distRoot "collection-view"

Write-Host "Building self-contained C# extractor..."
if (Test-Path $extractorOut) {
    Remove-Item $extractorOut -Recurse -Force
}
dotnet publish extractor\CollectionRealmExtractor.csproj `
    -c Release `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=false `
    -p:PublishTrimmed=false `
    -o $extractorOut

Write-Host "Installing Python dependencies..."
python -m pip install -r requirements.txt pyinstaller

Write-Host "Cleaning old packaged app..."
if (Test-Path $distApp) {
    Remove-Item $distApp -Recurse -Force
}
if ((Test-Path $legacyDistApp) -and ($legacyDistApp -ne $distApp)) {
    Remove-Item $legacyDistApp -Recurse -Force
}
if (Test-Path $pyinstallerWork) {
    Remove-Item $pyinstallerWork -Recurse -Force
}

Write-Host "Building Python desktop app..."
python -m PyInstaller osulazer-collection-view.spec `
    --noconfirm `
    --clean `
    --distpath $distRoot `
    --workpath $pyinstallerWork

$runtimeDir = Join-Path $distApp "runtime"
$coversDir = Join-Path $runtimeDir "covers"
New-Item -ItemType Directory -Force -Path $coversDir | Out-Null
Copy-Item README.md (Join-Path $distApp "README.md") -Force

Write-Host ""
Write-Host "Build completed:" -ForegroundColor Green
Write-Host "  $distApp"
Write-Host ""
Write-Host "Usage:"
Write-Host "  1. Put client.realm next to $appName.exe"
Write-Host "  2. Double-click $appName.exe"
