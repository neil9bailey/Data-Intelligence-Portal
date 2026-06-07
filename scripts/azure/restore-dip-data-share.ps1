[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [string]$SubscriptionId = "9ae9da49-de67-443b-af55-ce9db33ed8f4",
    [string]$ResourceGroupName = "RG_DIP_DIIAC_TEST",
    [string]$StorageAccountName = "stdipdiiactest",
    [string]$ShareName = "dip-data",
    [string]$DestinationPath = "",
    [ValidateSet("login", "key")]
    [string]$AuthMode = "login",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SourcePath)) {
    throw "Source path '$SourcePath' was not found."
}

az account set --subscription $SubscriptionId | Out-Null

$uploadArgs = @(
    "storage", "file", "upload-batch",
    "--account-name", $StorageAccountName,
    "--source", $SourcePath,
    "--destination", $ShareName,
    "--no-progress"
)

if (-not [string]::IsNullOrWhiteSpace($DestinationPath)) {
    $uploadArgs += @("--destination-path", $DestinationPath)
}

if ($DryRun) {
    $uploadArgs += "--dryrun"
}

if ($AuthMode -eq "login") {
    $uploadArgs += @("--auth-mode", "login", "--backup-intent")
} else {
    $accountKey = az storage account keys list `
        --resource-group $ResourceGroupName `
        --account-name $StorageAccountName `
        --query "[0].value" `
        -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($accountKey)) {
        throw "Failed to retrieve a storage account key for '$StorageAccountName'."
    }
    $uploadArgs += @("--account-key", $accountKey)
}

Write-Host "Uploading '$SourcePath' to Azure Files share '$ShareName' in '$StorageAccountName'."
if ($DryRun) {
    Write-Host "Dry run only. No files will be uploaded."
}

& az @uploadArgs
if ($LASTEXITCODE -ne 0) {
    throw "Azure Files restore upload failed."
}

Write-Host "Azure Files restore step completed."
