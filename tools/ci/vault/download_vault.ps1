$ErrorActionPreference = "Stop"

echo "Running on $([Environment]::MachineName)..."

& {
    $PSNativeCommandUseErrorActionPreference = $true
    $ProgressPreference = 'SilentlyContinue'
    $Url = "https://urm.nvidia.com/artifactory/sw-kaizen-data-generic/com/nvidia/vault/vault-agent/1.5.2/nvidia_vault_agent_v1.5.2_windows_amd64.zip"
    $DownloadZipFile = [IO.Path]::Combine((Get-Location).path, $(Split-Path -Path $Url -Leaf))
    mkdir tempbin
    Invoke-WebRequest -Uri $Url -OutFile $DownloadZipFile
    Expand-Archive $DownloadZipFile -DestinationPath tempbin -Force
    Remove-Item -Path $DownloadZipFile -Force
    $Env:PATH += ";"
    $Env:PATH += [IO.Path]::Combine((Get-Location).path, "tempbin")
}

$ProgressPreference = 'Continue'

if(!$?) { Exit $LASTEXITCODE }
