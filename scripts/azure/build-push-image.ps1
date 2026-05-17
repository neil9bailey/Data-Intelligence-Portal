[CmdletBinding()]
param(
    [string]$SubscriptionId = "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7",
    [string]$AcrName = "acrdipvltest01",
    [string]$Repository = "dip/app",
    [string]$ImageTag = "1.0.7-live-test"
)

$ErrorActionPreference = "Stop"

az account set --subscription $SubscriptionId | Out-Null

$loginServer = az acr show --name $AcrName --query loginServer -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($loginServer)) {
    throw "ACR '$AcrName' was not found. Deploy infra-only first."
}

az acr login --name $AcrName | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "ACR login failed."
}

$image = "$loginServer/$Repository`:$ImageTag"
Write-Host "Building $image"
docker build -t $image .
if ($LASTEXITCODE -ne 0) {
    throw "Docker build failed."
}

docker push $image
if ($LASTEXITCODE -ne 0) {
    throw "Docker push failed."
}

Write-Host "Pushed $image"
