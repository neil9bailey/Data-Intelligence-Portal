[CmdletBinding()]
param(
    [string]$SubscriptionId = "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7",
    [string]$ResourceGroupName = "RG_DIP_VENDORLOGIC_TEST",
    [string]$ContainerAppName = "ca-dip-vl-test",
    [string]$ExpectedImageTag = "1.0.65-cof-value-layer",
    [string]$PublicUrl = "",
    [switch]$RunAdminCycle
)

$ErrorActionPreference = "Stop"

function Get-HttpStatus {
    param([string]$Uri)
    $status = curl.exe -k -s -o NUL -w "%{http_code}" --max-time 30 $Uri
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($status)) {
        throw "Failed to fetch HTTP status for $Uri"
    }
    return [int]$status
}

az account set --subscription $SubscriptionId | Out-Null

$app = az containerapp show -g $ResourceGroupName -n $ContainerAppName -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $null -eq $app) {
    throw "Container app '$ContainerAppName' was not found in '$ResourceGroupName'."
}

$fqdn = $app.properties.configuration.ingress.fqdn
if ([string]::IsNullOrWhiteSpace($fqdn)) {
    throw "Container app FQDN was not found."
}

$image = $app.properties.template.containers[0].image
if ([string]::IsNullOrWhiteSpace($image)) {
    throw "Container image was not found on the active template."
}

Write-Host "Active image: $image"
if (-not [string]::IsNullOrWhiteSpace($ExpectedImageTag) -and -not $image.EndsWith(":$ExpectedImageTag")) {
    throw "Expected image tag '$ExpectedImageTag', but active image is '$image'."
}

$revisions = az containerapp revision list -g $ResourceGroupName -n $ContainerAppName -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $null -eq $revisions) {
    throw "Failed to list Container App revisions."
}

$activeRevision = @($revisions | Where-Object { $_.properties.active -eq $true } | Select-Object -First 1)[0]
if ($null -eq $activeRevision) {
    throw "No active Container App revision was found."
}

$revisionName = $activeRevision.name
$runningState = $activeRevision.properties.runningState
$healthState = $activeRevision.properties.healthState

Write-Host "Active revision: $revisionName"
if (-not [string]::IsNullOrWhiteSpace($runningState)) {
    Write-Host "Revision running state: $runningState"
    if ($runningState -notin @("Running", "RunningAtMaxScale")) {
        throw "Expected active revision running state to be Running or RunningAtMaxScale."
    }
}

if (-not [string]::IsNullOrWhiteSpace($healthState)) {
    Write-Host "Revision health state: $healthState"
    if ($healthState -ne "Healthy") {
        throw "Expected active revision health state to be Healthy."
    }
}

$baseUrl = "https://$fqdn"
$healthStatus = Get-HttpStatus "$baseUrl/healthz"
$rootStatus = Get-HttpStatus "$baseUrl/"
$readyStatus = Get-HttpStatus "$baseUrl/readyz"

Write-Host "$baseUrl/healthz status: $healthStatus"
Write-Host "$baseUrl/readyz unauthenticated status: $readyStatus"
Write-Host "$baseUrl/ unauthenticated status: $rootStatus"

if ($healthStatus -ne 200) {
    throw "Expected /healthz to return 200."
}

if ($rootStatus -notin @(302, 401, 403)) {
    throw "Expected / to be protected by Entra auth with 302, 401 or 403."
}

if ($readyStatus -notin @(302, 401, 403)) {
    throw "Expected /readyz to be protected by Entra auth with 302, 401 or 403."
}

if (-not [string]::IsNullOrWhiteSpace($PublicUrl)) {
    $publicHealthStatus = Get-HttpStatus "$($PublicUrl.TrimEnd('/'))/healthz"
    Write-Host "$($PublicUrl.TrimEnd('/'))/healthz status: $publicHealthStatus"
    if ($publicHealthStatus -ne 200) {
        throw "Expected public /healthz to return 200."
    }
}

if ($RunAdminCycle) {
    Write-Host "Running live admin cycle in the active Container App revision."
    az containerapp exec `
        -g $ResourceGroupName `
        -n $ContainerAppName `
        --revision $revisionName `
        --container "data-intelligence-portal" `
        --command "/app/scripts/run-admin-cycle.sh"
    if ($LASTEXITCODE -ne 0) {
        throw "Live admin cycle failed."
    }
}

Write-Host "Azure live-test smoke checks passed for $baseUrl"
