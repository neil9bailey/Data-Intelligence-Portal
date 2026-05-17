[CmdletBinding()]
param(
    [string]$SubscriptionId = "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7",
    [string]$TenantId = "1384b1c5-2bae-45a1-a4b4-e94e3315eb41",
    [string]$AppDisplayName = "Data Intelligence Portal Live Test",
    [string]$AdminGroupName = "Data Intelligence Portal Admin Users",
    [string]$StandardGroupName = "Data Intelligence Portal Standard Users",
    [string]$PublicDomain = "dip.vendorlogic.io",
    [string]$DefaultFqdn = "",
    [string]$KeyVaultName = "kv-diiac-vendorlogic",
    [string]$ClientSecretName = "dip-entra-client-secret",
    [string]$OutputPath = "infra/azure/generated/dip-entra.outputs.json",
    [switch]$RotateSecret
)

$ErrorActionPreference = "Stop"

function Invoke-AzJson {
    param([string[]]$Arguments)
    $raw = & az @Arguments -o json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return $raw | ConvertFrom-Json
}

function Get-OrCreate-Group {
    param([string]$DisplayName, [string]$MailNickname)
    $group = Invoke-AzJson @("ad", "group", "list", "--filter", "displayName eq '$DisplayName'", "--query", "[0]")
    if ($null -eq $group) {
        Write-Host "Creating Entra group: $DisplayName"
        $group = Invoke-AzJson @(
            "ad", "group", "create",
            "--display-name", $DisplayName,
            "--mail-nickname", $MailNickname
        )
    } else {
        Write-Host "Using existing Entra group: $DisplayName"
    }
    return $group
}

az account set --subscription $SubscriptionId | Out-Null

$redirectUris = @("https://$PublicDomain/.auth/login/aad/callback")
if (-not [string]::IsNullOrWhiteSpace($DefaultFqdn)) {
    $redirectUris += "https://$DefaultFqdn/.auth/login/aad/callback"
}

$adminGroup = Get-OrCreate-Group -DisplayName $AdminGroupName -MailNickname "dip-admin-users"
$standardGroup = Get-OrCreate-Group -DisplayName $StandardGroupName -MailNickname "dip-standard-users"

$app = Invoke-AzJson @("ad", "app", "list", "--display-name", $AppDisplayName, "--query", "[0]")
if ($null -eq $app) {
    Write-Host "Creating Entra app registration: $AppDisplayName"
    $args = @(
        "ad", "app", "create",
        "--display-name", $AppDisplayName,
        "--sign-in-audience", "AzureADMyOrg",
        "--enable-id-token-issuance", "true",
        "--web-redirect-uris"
    )
    $args += $redirectUris
    $app = Invoke-AzJson $args
} else {
    Write-Host "Using existing Entra app registration: $AppDisplayName"
}

$appId = [string]$app.appId
$updateArgs = @(
    "ad", "app", "update",
    "--id", $appId,
    "--identifier-uris", "api://$appId",
    "--enable-id-token-issuance", "true",
    "--set", "groupMembershipClaims=SecurityGroup",
    "--web-redirect-uris"
)
$updateArgs += $redirectUris
Invoke-AzJson $updateArgs | Out-Null

$secretExists = $false
try {
    & az keyvault secret show --vault-name $KeyVaultName --name $ClientSecretName --query id -o tsv 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $secretExists = $true
    }
} catch {
    $secretExists = $false
}

if ($RotateSecret -or -not $secretExists) {
    Write-Host "Creating Entra client secret and storing it in Key Vault secret '$ClientSecretName'."
    $secret = & az ad app credential reset --id $appId --append --display-name "container-apps-auth" --years 1 --query password -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($secret)) {
        throw "Failed to create Entra client secret."
    }
    & az keyvault secret set --vault-name $KeyVaultName --name $ClientSecretName --value $secret -o none
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to store Entra client secret in Key Vault."
    }
} else {
    Write-Host "Using existing Key Vault secret '$ClientSecretName'. Use -RotateSecret to replace it."
}

$output = [pscustomobject]@{
    tenantId = $TenantId
    appDisplayName = $AppDisplayName
    appId = $appId
    appObjectId = [string]$app.id
    adminGroupName = $AdminGroupName
    adminGroupId = [string]$adminGroup.id
    standardGroupName = $StandardGroupName
    standardGroupId = [string]$standardGroup.id
    publicDomain = $PublicDomain
    redirectUris = $redirectUris
    clientSecretName = $ClientSecretName
}

$fullOutputPath = Join-Path (Get-Location) $OutputPath
New-Item -ItemType Directory -Force -Path (Split-Path $fullOutputPath -Parent) | Out-Null
$output | ConvertTo-Json -Depth 6 | Set-Content -Path $fullOutputPath -Encoding UTF8

Write-Host "Wrote Entra deployment inputs to $fullOutputPath"
Write-Host "Admin group id: $($output.adminGroupId)"
Write-Host "Standard group id: $($output.standardGroupId)"
Write-Host "App client id: $($output.appId)"
