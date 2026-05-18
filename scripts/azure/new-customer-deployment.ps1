[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CustomerCode,
    [Parameter(Mandatory = $true)]
    [string]$EnvironmentCode,
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,
    [Parameter(Mandatory = $true)]
    [string]$TenantId,
    [Parameter(Mandatory = $true)]
    [string]$PublicDomain,
    [Parameter(Mandatory = $true)]
    [string]$SharedKeyVaultName,
    [Parameter(Mandatory = $true)]
    [string]$SharedKeyVaultResourceGroupName,
    [string]$Location = "uksouth",
    [string]$ImageTag = "",
    [string]$ContainerRegistryName = "",
    [string]$StorageAccountName = "",
    [string]$GeneratedDirectory = "infra/azure/generated",
    [switch]$PrepareEntra,
    [switch]$DeployInfra,
    [switch]$BuildPushImage,
    [switch]$DeployApp,
    [switch]$ShowDns,
    [switch]$BindDomain,
    [switch]$RunAll
)

$ErrorActionPreference = "Stop"

function Convert-ToToken {
    param(
        [string]$Value,
        [int]$MaxLength = 18,
        [switch]$LettersOnlyPrefix
    )
    $token = ($Value.ToLowerInvariant() -replace '[^a-z0-9]', '')
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Value '$Value' cannot be converted to an Azure-safe token."
    }
    if ($LettersOnlyPrefix -and $token[0] -notmatch '[a-z]') {
        $token = "x$token"
    }
    if ($token.Length -gt $MaxLength) {
        $token = $token.Substring(0, $MaxLength)
    }
    return $token
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Script)
    Write-Host ""
    Write-Host "== $Name =="
    & $Script
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Name"
    }
}

$customer = Convert-ToToken -Value $CustomerCode -MaxLength 12 -LettersOnlyPrefix
$environment = Convert-ToToken -Value $EnvironmentCode -MaxLength 8 -LettersOnlyPrefix
$suffix = "$customer-$environment"
$compact = Convert-ToToken -Value "$customer$environment" -MaxLength 13 -LettersOnlyPrefix

if ([string]::IsNullOrWhiteSpace($ImageTag)) {
    $ImageTag = "1.0.10-$environment"
}
if ([string]::IsNullOrWhiteSpace($ContainerRegistryName)) {
    $ContainerRegistryName = "acrdip$compact"
}
if ([string]::IsNullOrWhiteSpace($StorageAccountName)) {
    $StorageAccountName = "stdip$compact"
    if ($StorageAccountName.Length -gt 24) {
        $StorageAccountName = $StorageAccountName.Substring(0, 24)
    }
}

$resourceGroupName = "RG_DIP_$($customer.ToUpperInvariant())_$($environment.ToUpperInvariant())"
$managedIdentityName = "id-dip-$suffix"
$logAnalyticsWorkspaceName = "law-dip-$suffix"
$containerAppsEnvironmentName = "acae-dip-$suffix"
$containerAppName = "ca-dip-$suffix"
$appDisplayName = "Data Intelligence Portal $CustomerCode $EnvironmentCode"
$adminGroupName = "DIP $CustomerCode $EnvironmentCode Admin Users"
$standardGroupName = "DIP $CustomerCode $EnvironmentCode Standard Users"
$clientSecretName = "dip-$suffix-entra-client-secret"
$parameterFile = Join-Path $GeneratedDirectory "$suffix.sub.bicepparam"
$entraOutputFile = Join-Path $GeneratedDirectory "$suffix-entra.outputs.json"

New-Item -ItemType Directory -Force -Path $GeneratedDirectory | Out-Null

$parameterContent = @"
using '../main.sub.bicep'

param resourceGroupName = '$resourceGroupName'
param resourceGroupLocation = '$Location'
param deployApps = false

param containerRegistryName = '$ContainerRegistryName'
param managedIdentityName = '$managedIdentityName'
param logAnalyticsWorkspaceName = '$logAnalyticsWorkspaceName'
param storageAccountName = '$StorageAccountName'
param containerAppsEnvironmentName = '$containerAppsEnvironmentName'
param containerAppName = '$containerAppName'

param sharedKeyVaultName = '$SharedKeyVaultName'
param sharedKeyVaultResourceGroupName = '$SharedKeyVaultResourceGroupName'
param publicDomain = '$PublicDomain'
param dnsSubdomain = '$($PublicDomain.Split('.')[0])'
param customDomainBindingEnabled = false
param managedCertificateName = ''

param imageRepositoryPrefix = 'dip'
param imageTag = '$ImageTag'
param sqliteJournalMode = 'DELETE'
param minReplicas = 1

param entraAuthEnabled = true
param entraTenantId = '$TenantId'
param entraClientId = '00000000-0000-0000-0000-000000000000'
param entraClientSecretName = '$clientSecretName'
param entraAdminGroupId = '00000000-0000-0000-0000-000000000000'
param entraStandardGroupId = '00000000-0000-0000-0000-000000000000'

param seedReferenceData = true
param seedDemoData = false
"@

Set-Content -Path $parameterFile -Value $parameterContent -Encoding UTF8

Write-Host "Generated customer deployment parameter file:"
Write-Host "  $parameterFile"
Write-Host "Generated Entra output file path:"
Write-Host "  $entraOutputFile"
Write-Host ""
Write-Host "Derived Azure names:"
Write-Host "  Resource group: $resourceGroupName"
Write-Host "  ACR: $ContainerRegistryName"
Write-Host "  Container App: $containerAppName"
Write-Host "  Environment: $containerAppsEnvironmentName"
Write-Host "  Public domain: $PublicDomain"
Write-Host "  Image tag: $ImageTag"

$shouldPrepareEntra = $PrepareEntra -or $RunAll
$shouldDeployInfra = $DeployInfra -or $RunAll
$shouldBuildPushImage = $BuildPushImage -or $RunAll
$shouldDeployApp = $DeployApp -or $RunAll
$shouldShowDns = $ShowDns -or $RunAll

if ($shouldPrepareEntra) {
    Invoke-Step "Prepare Entra app registration and groups" {
        .\scripts\azure\prepare-entra.ps1 `
            -SubscriptionId $SubscriptionId `
            -TenantId $TenantId `
            -AppDisplayName $appDisplayName `
            -AdminGroupName $adminGroupName `
            -StandardGroupName $standardGroupName `
            -PublicDomain $PublicDomain `
            -KeyVaultName $SharedKeyVaultName `
            -ClientSecretName $clientSecretName `
            -OutputPath $entraOutputFile
    }
}

if ($shouldDeployInfra) {
    Invoke-Step "Deploy infrastructure only" {
        .\scripts\azure\deploy-dip.ps1 `
            -Mode apply `
            -InfraOnly `
            -SubscriptionId $SubscriptionId `
            -Location $Location `
            -ParameterFile $parameterFile `
            -GeneratedEntraFile $entraOutputFile
    }
}

if ($shouldBuildPushImage) {
    Invoke-Step "Build and push image" {
        .\scripts\azure\build-push-image.ps1 `
            -SubscriptionId $SubscriptionId `
            -AcrName $ContainerRegistryName `
            -Repository "dip/app" `
            -ImageTag $ImageTag
    }
}

if ($shouldDeployApp) {
    Invoke-Step "Deploy app" {
        .\scripts\azure\deploy-dip.ps1 `
            -Mode apply `
            -SubscriptionId $SubscriptionId `
            -Location $Location `
            -ParameterFile $parameterFile `
            -GeneratedEntraFile $entraOutputFile
    }
}

if ($shouldShowDns -or $BindDomain) {
    $dnsArgs = @{
        SubscriptionId = $SubscriptionId
        ResourceGroupName = $resourceGroupName
        ContainerAppName = $containerAppName
        EnvironmentName = $containerAppsEnvironmentName
        Hostname = $PublicDomain
    }
    if ($BindDomain) {
        Invoke-Step "Bind custom domain" {
            .\scripts\azure\show-dns-and-bind-domain.ps1 @dnsArgs -Bind
        }
    } else {
        Invoke-Step "Show DNS records" {
            .\scripts\azure\show-dns-and-bind-domain.ps1 @dnsArgs
        }
    }
}

Write-Host ""
Write-Host "Next commands if you did not use -RunAll:"
Write-Host ".\scripts\azure\prepare-entra.ps1 -SubscriptionId '$SubscriptionId' -TenantId '$TenantId' -AppDisplayName '$appDisplayName' -AdminGroupName '$adminGroupName' -StandardGroupName '$standardGroupName' -PublicDomain '$PublicDomain' -KeyVaultName '$SharedKeyVaultName' -ClientSecretName '$clientSecretName' -OutputPath '$entraOutputFile'"
Write-Host ".\scripts\azure\deploy-dip.ps1 -Mode apply -InfraOnly -SubscriptionId '$SubscriptionId' -ParameterFile '$parameterFile' -GeneratedEntraFile '$entraOutputFile'"
Write-Host ".\scripts\azure\build-push-image.ps1 -SubscriptionId '$SubscriptionId' -AcrName '$ContainerRegistryName' -Repository 'dip/app' -ImageTag '$ImageTag'"
Write-Host ".\scripts\azure\deploy-dip.ps1 -Mode apply -SubscriptionId '$SubscriptionId' -ParameterFile '$parameterFile' -GeneratedEntraFile '$entraOutputFile'"
Write-Host ".\scripts\azure\show-dns-and-bind-domain.ps1 -SubscriptionId '$SubscriptionId' -ResourceGroupName '$resourceGroupName' -ContainerAppName '$containerAppName' -EnvironmentName '$containerAppsEnvironmentName' -Hostname '$PublicDomain'"
