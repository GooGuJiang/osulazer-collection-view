Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$buildRoot = Join-Path $projectRoot "build"
$extractorOut = Join-Path $buildRoot "extractor_runtime"

Write-Host "Building C# extractor..."
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

Write-Host "C# extractor built successfully at: $extractorOut" -ForegroundColor Green
