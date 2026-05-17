[CmdletBinding()]
param(
    [string]$SubscriptionId = "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7",
    [string]$ResourceGroupName = "RG_DIP_VENDORLOGIC_TEST",
    [string]$ContainerAppName = "ca-dip-vl-test",
    [string]$EnvironmentName = "acae-dip-vl-test",
    [string]$Hostname = "dip.vendorlogic.io",
    [switch]$Bind
)

$ErrorActionPreference = "Stop"

az account set --subscription $SubscriptionId | Out-Null

$fqdn = az containerapp show -g $ResourceGroupName -n $ContainerAppName --query "properties.configuration.ingress.fqdn" -o tsv
$verificationId = az containerapp show -g $ResourceGroupName -n $ContainerAppName --query "properties.customDomainVerificationId" -o tsv
$staticIp = az containerapp env show -g $ResourceGroupName -n $EnvironmentName --query "properties.staticIp" -o tsv

Write-Host "DNS records for $Hostname"
Write-Host "CNAME host: dip"
Write-Host "CNAME value: $fqdn"
Write-Host "TXT host: asuid.dip"
Write-Host "TXT value: $verificationId"
Write-Host "Container Apps environment static IP: $staticIp"
Write-Host "For this subdomain use the CNAME + TXT records before binding. A record is only needed for an apex/root domain."

if ($Bind) {
    Write-Host "Adding hostname and binding managed certificate. DNS must already be live."
    az containerapp hostname add --hostname $Hostname -g $ResourceGroupName -n $ContainerAppName
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to add hostname."
    }
    az containerapp hostname bind --hostname $Hostname -g $ResourceGroupName -n $ContainerAppName --environment $EnvironmentName --validation-method CNAME
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to bind managed certificate."
    }
}
