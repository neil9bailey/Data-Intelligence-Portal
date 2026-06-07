[CmdletBinding()]
param(
    [string]$SubscriptionId = "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7",
    [string]$ResourceGroupName = "RG_DIP_VENDORLOGIC_TEST",
    [string]$StorageAccountName = "stdipvltest01",
    [string]$ShareName = "dip-data",
    [string]$DestinationRoot = ".tmp/azure-backups",
    [ValidateSet("login", "key")]
    [string]$AuthMode = "login",
    [switch]$DryRun,
    [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"

az account set --subscription $SubscriptionId | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destination = Join-Path $DestinationRoot "$StorageAccountName-$ShareName-$timestamp"
New-Item -ItemType Directory -Force -Path $destination | Out-Null

$downloadArgs = @(
    "storage", "file", "download-batch",
    "--account-name", $StorageAccountName,
    "--source", $ShareName,
    "--destination", $destination,
    "--no-progress"
)

if ($DryRun) {
    $downloadArgs += "--dryrun"
}

if ($AuthMode -eq "login") {
    $downloadArgs += @("--auth-mode", "login", "--backup-intent")
} else {
    $accountKey = az storage account keys list `
        --resource-group $ResourceGroupName `
        --account-name $StorageAccountName `
        --query "[0].value" `
        -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($accountKey)) {
        throw "Failed to retrieve a storage account key for '$StorageAccountName'."
    }
    $downloadArgs += @("--account-key", $accountKey)
}

Write-Host "Downloading Azure Files share '$ShareName' from '$StorageAccountName' to '$destination'."
if ($DryRun) {
    Write-Host "Dry run only. No files will be downloaded."
}

& az @downloadArgs
if ($LASTEXITCODE -ne 0) {
    throw "Azure Files backup download failed."
}

if (-not $DryRun -and -not $SkipArchive) {
    $archivePath = "$destination.zip"
    $downloadedItems = @(Get-ChildItem -LiteralPath $destination -Force)
    if ($downloadedItems.Count -gt 0) {
        Compress-Archive -Path (Join-Path $destination "*") -DestinationPath $archivePath -Force
        Write-Host "Backup archive written to $archivePath"
    } else {
        Write-Host "No files were downloaded, so no archive was created."
    }
}

Write-Host "Azure Files backup step completed."
