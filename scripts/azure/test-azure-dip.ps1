[CmdletBinding()]
param(
    [string]$SubscriptionId = "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7",
    [string]$ResourceGroupName = "RG_DIP_VENDORLOGIC_TEST",
    [string]$ContainerAppName = "ca-dip-vl-test"
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

$fqdn = az containerapp show -g $ResourceGroupName -n $ContainerAppName --query "properties.configuration.ingress.fqdn" -o tsv
if ([string]::IsNullOrWhiteSpace($fqdn)) {
    throw "Container app FQDN was not found."
}

$baseUrl = "https://$fqdn"
$healthStatus = Get-HttpStatus "$baseUrl/healthz"
$rootStatus = Get-HttpStatus "$baseUrl/"

Write-Host "Health endpoint status: $healthStatus"
Write-Host "Root unauthenticated status: $rootStatus"

if ($healthStatus -ne 200) {
    throw "Expected /healthz to return 200."
}

if ($rootStatus -notin @(302, 401, 403)) {
    throw "Expected / to be protected by Entra auth with 302, 401 or 403."
}

Write-Host "Azure live-test smoke checks passed for $baseUrl"
