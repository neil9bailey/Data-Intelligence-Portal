# DIIAC Migration Runbook

This runbook keeps the current Vendorlogic live test separate from the later DIIAC tenant migration. Do not create, update or delete Azure resources until the target subscription, resource group, Key Vault and DNS window are explicitly approved.

Checked date: 7 June 2026.

## Current Baseline

| Item | Value |
| --- | --- |
| Repo branch | `main` |
| Current commit | `5c6fbc9 harden Docker dependency pins` |
| Current image tag | `1.0.65-cof-value-layer` |
| Vendorlogic URL | `https://dip.vendorlogic.io` |
| Vendorlogic tenant | `1384b1c5-2bae-45a1-a4b4-e94e3315eb41` |
| Vendorlogic subscription | `3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7` |
| DIIAC tenant | `67f8be6c-07da-4a7c-bb0a-d6bcb38cd6da` |
| DIIAC subscription | `9ae9da49-de67-443b-af55-ce9db33ed8f4` |
| Proposed DIIAC URL | `https://dip.diiac.io` |

## Phase 1: Prove Vendorlogic Is Current

Sign into the Vendorlogic tenant and subscription:

```powershell
az login --tenant "1384b1c5-2bae-45a1-a4b4-e94e3315eb41"
az account set --subscription "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7"
az group show --name "RG_DIP_VENDORLOGIC_TEST"
```

Back up the current Azure Files share before any update:

```powershell
.\scripts\azure\backup-dip-data-share.ps1 `
  -SubscriptionId "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7" `
  -ResourceGroupName "RG_DIP_VENDORLOGIC_TEST" `
  -StorageAccountName "stdipvltest01" `
  -ShareName "dip-data" `
  -AuthMode login
```

If OAuth file-share access is not configured, rerun with `-AuthMode key`. The script does not print the account key.

Build and push the current image, then deploy the existing Container App only:

```powershell
.\scripts\azure\build-push-image.ps1 `
  -SubscriptionId "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7" `
  -AcrName "acrdipvltest01" `
  -Repository "dip/app" `
  -ImageTag "1.0.65-cof-value-layer"

.\scripts\azure\deploy-dip.ps1 `
  -Mode apply `
  -SubscriptionId "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7" `
  -ParameterFile "infra/azure/dip-live-test.sub.bicepparam" `
  -GeneratedEntraFile "infra/azure/generated/dip-entra.outputs.json"
```

Run the post-deploy smoke check:

```powershell
.\scripts\azure\test-azure-dip.ps1 `
  -SubscriptionId "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7" `
  -ResourceGroupName "RG_DIP_VENDORLOGIC_TEST" `
  -ContainerAppName "ca-dip-vl-test" `
  -ExpectedImageTag "1.0.65-cof-value-layer" `
  -PublicUrl "https://dip.vendorlogic.io"
```

Only run the live admin cycle when you are ready to refresh live source health, reports, outbox files and audit records:

```powershell
.\scripts\azure\test-azure-dip.ps1 `
  -SubscriptionId "3ed9fa77-6bf2-4ffc-bd67-f5a442d3e5e7" `
  -ResourceGroupName "RG_DIP_VENDORLOGIC_TEST" `
  -ContainerAppName "ca-dip-vl-test" `
  -ExpectedImageTag "1.0.65-cof-value-layer" `
  -PublicUrl "https://dip.vendorlogic.io" `
  -RunAdminCycle
```

## Phase 2: Prepare DIIAC Without DNS Cutover

Before deployment, decide whether DIIAC will use an approved existing Key Vault or a newly approved DIP-specific Key Vault. The current Bicep path expects a Key Vault to already exist and never stores raw secrets in parameter files.

Generate DIIAC parameters with the customer bootstrap script:

```powershell
.\scripts\azure\new-customer-deployment.ps1 `
  -CustomerCode "diiac" `
  -EnvironmentCode "test" `
  -SubscriptionId "9ae9da49-de67-443b-af55-ce9db33ed8f4" `
  -TenantId "67f8be6c-07da-4a7c-bb0a-d6bcb38cd6da" `
  -PublicDomain "dip.diiac.io" `
  -SharedKeyVaultName "<approved-existing-diiac-key-vault>" `
  -SharedKeyVaultResourceGroupName "<key-vault-resource-group>" `
  -ImageTag "1.0.65-cof-value-layer" `
  -KraLlmProvider "disabled" `
  -AutoApplyCustomerPacks $true
```

The committed file `infra/azure/dip-diiac-test.template.sub.bicepparam` is a review scaffold only. Copy it to `infra/azure/generated/` or use the generated file from the command above once the Key Vault choice is approved.

Deploy DIIAC in the standard order:

```powershell
.\scripts\azure\prepare-entra.ps1 <generated command arguments>
.\scripts\azure\deploy-dip.ps1 -Mode apply -InfraOnly <generated command arguments>
.\scripts\azure\build-push-image.ps1 <generated command arguments>
.\scripts\azure\deploy-dip.ps1 -Mode apply <generated command arguments>
.\scripts\azure\show-dns-and-bind-domain.ps1 <generated command arguments>
```

Do not bind `dip.diiac.io` until DNS validation records are live.

## Phase 3: Data Choice

Clean DIIAC pilot:

- Do not restore Vendorlogic Azure Files data.
- Keep `seedReferenceData=true`, `seedDemoData=false` and `autoApplyCustomerPacks=true`.

Copy current Vendorlogic pilot data:

1. Stop or pause live writes during the backup window.
2. Run `backup-dip-data-share.ps1` against the Vendorlogic storage account.
3. Deploy the DIIAC infrastructure and storage share.
4. Upload the backup folder into the DIIAC share:

```powershell
.\scripts\azure\restore-dip-data-share.ps1 `
  -SourcePath ".tmp\azure-backups\<backup-folder>" `
  -SubscriptionId "9ae9da49-de67-443b-af55-ce9db33ed8f4" `
  -ResourceGroupName "RG_DIP_DIIAC_TEST" `
  -StorageAccountName "stdipdiiactest" `
  -ShareName "dip-data" `
  -AuthMode login
```

If OAuth file-share access is not configured, rerun with `-AuthMode key`.

## Phase 4: DNS Cutover And Rollback

`dip.diiac.io` currently must be changed from its existing DNS target to the new Azure Container App CNAME target printed by `show-dns-and-bind-domain.ps1`.

Cutover:

1. Add the `TXT asuid.dip` validation record.
2. Change `CNAME dip` to the new Container App FQDN.
3. Run `show-dns-and-bind-domain.ps1 -Bind`.
4. Run `test-azure-dip.ps1 -PublicUrl "https://dip.diiac.io"`.
5. Complete real signed-in end-user testing before declaring migration complete.

Rollback:

1. Keep the Vendorlogic deployment untouched until DIIAC is accepted.
2. Repoint DNS to the previous known-good target if DIIAC fails acceptance.
3. Do not delete Vendorlogic Azure Files or Container Apps resources until backup restore and end-user testing are signed off.
