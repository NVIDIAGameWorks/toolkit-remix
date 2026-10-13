$ErrorActionPreference = "Stop"
$packageManifestPattern = "_build/packages/rtx_remix@*+latest.txt"
Get-ChildItem $packageManifestPattern -ErrorAction SilentlyContinue | Remove-Item
$staging = Join-Path $PWD "_build/toolkit-package"
try {
  .\repo.bat package --mode main_package --platform windows-x86_64 --config release --stage-only --temp-dir $staging
  if ($LASTEXITCODE -ne 0) { throw "Toolkit package staging failed" }
  $packageNames = @(Get-ChildItem $packageManifestPattern | Get-Content | Sort-Object -Unique)
  if ($packageNames.Count -ne 1 -or $packageNames[0] -notlike "rtx_remix@*.windows-x86_64.release.zip") {
    throw "Expected one toolkit release ZIP filename from repo package"
  }
  $archive = Join-Path "_build/packages" $packageNames[0]
  if (Test-Path $archive) { Remove-Item $archive }
  lightspeed-uploader.exe pack $staging --format zip --output $archive
  if ($LASTEXITCODE -ne 0) { throw "Toolkit package compression failed" }
} finally {
  if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
}
