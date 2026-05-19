[CmdletBinding()]
param(
    [ValidateSet("validate", "plan", "apply")]
    [string]$Mode = "plan",
    [switch]$InfraOnly,
    [string]$SubscriptionId = "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7",
    [string]$Location = "uksouth",
    [string]$TemplateFile = "infra/azure/main.sub.bicep",
    [string]$ParameterFile = "infra/azure/dip-live-test.sub.bicepparam",
    [string]$GeneratedEntraFile = "infra/azure/generated/dip-entra.outputs.json"
)

$ErrorActionPreference = "Stop"

az account set --subscription $SubscriptionId | Out-Null

$deployApps = -not $InfraOnly
$parameterArgs = @("deployApps=$($deployApps.ToString().ToLowerInvariant())")

if (Test-Path $GeneratedEntraFile) {
    $entra = Get-Content -Raw $GeneratedEntraFile | ConvertFrom-Json
    $parameterArgs += "entraTenantId=$($entra.tenantId)"
    $parameterArgs += "entraClientId=$($entra.appId)"
    $parameterArgs += "entraAdminGroupId=$($entra.adminGroupId)"
    $parameterArgs += "entraStandardGroupId=$($entra.standardGroupId)"
    if ($entra.PSObject.Properties.Name -contains "auditorGroupId") {
        $parameterArgs += "entraAuditorGroupId=$($entra.auditorGroupId)"
    }
    $parameterArgs += "entraClientSecretName=$($entra.clientSecretName)"
} elseif ($deployApps) {
    throw "Missing $GeneratedEntraFile. Run scripts/azure/prepare-entra.ps1 before deploying apps."
}

$commonArgs = @(
    "--location", $Location,
    "--template-file", $TemplateFile,
    "--parameters", $ParameterFile
)
$commonArgs += $parameterArgs

Write-Host "Validating Bicep deployment..."
$validateArgs = @("deployment", "sub", "validate") + $commonArgs
& az @validateArgs
if ($LASTEXITCODE -ne 0) {
    throw "Validation failed."
}

if ($Mode -eq "validate") {
    return
}

Write-Host "Running what-if..."
$whatIfArgs = @("deployment", "sub", "what-if") + $commonArgs
& az @whatIfArgs
if ($LASTEXITCODE -ne 0) {
    throw "What-if failed."
}

if ($Mode -eq "apply") {
    Write-Host "Applying deployment..."
    $createArgs = @("deployment", "sub", "create") + $commonArgs
    & az @createArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Deployment failed."
    }
}
