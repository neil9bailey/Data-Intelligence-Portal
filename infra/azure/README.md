# Data Intelligence Portal Azure Live-Test IaC

This folder contains an isolated Azure Container Apps live-test deployment for `dip.vendorlogic.io`.

## Scope

The templates create a new dedicated resource group and do not modify existing DIIaC live services. They share only the existing Key Vault `kv-diiac-vendorlogic` for uniquely named DIP secrets.

Created resources:

- Azure Container Registry
- User-assigned managed identity
- Log Analytics workspace
- Storage account and Azure Files share for SQLite snapshot/outbox persistence
- Azure Container Apps managed environment
- Data Intelligence Portal container app
- Container Apps built-in Microsoft Entra authentication
- Container Apps custom domain binding to the existing managed certificate after DNS is live
- Key Vault Secrets User role assignment for the dedicated managed identity

## Official Microsoft Guidance Used

- Container Apps Entra authentication: <https://learn.microsoft.com/azure/container-apps/authentication-entra>
- Container Apps authConfig Bicep schema: <https://learn.microsoft.com/azure/templates/microsoft.app/2024-03-01/containerapps/authconfigs>
- Container Apps custom domain and managed certificates: <https://learn.microsoft.com/azure/container-apps/custom-domains-managed-certificates>
- Container Apps Azure Files storage: <https://learn.microsoft.com/azure/templates/microsoft.app/2024-03-01/managedenvironments/storages>

## Deployment Order

Run from the repo root.

1. Prepare Entra groups, app registration and Key Vault client secret:

   ```powershell
   .\scripts\azure\prepare-entra.ps1
   ```

2. Deploy isolated infrastructure only:

   ```powershell
   .\scripts\azure\deploy-dip.ps1 -Mode apply -InfraOnly
   ```

3. Build and push the container image:

   ```powershell
   .\scripts\azure\build-push-image.ps1
   ```

4. Deploy the app:

   ```powershell
   .\scripts\azure\deploy-dip.ps1 -Mode apply
   ```

5. Print DNS records:

   ```powershell
   .\scripts\azure\show-dns-and-bind-domain.ps1
   ```

6. After the DNS CNAME and TXT records have propagated, bind the managed certificate:

   ```powershell
   .\scripts\azure\show-dns-and-bind-domain.ps1 -Bind
   ```

   After the first successful bind, set `customDomainBindingEnabled=true` and `managedCertificateName` in the parameter file so later IaC applies preserve the hostname binding.

7. Run Azure smoke checks:

   ```powershell
   .\scripts\azure\test-azure-dip.ps1
   ```

## DNS For `dip.vendorlogic.io`

For this subdomain, create:

- `CNAME dip` to the generated Container App FQDN.
- `TXT asuid.dip` to the Container App domain verification ID.

The script also prints the Container Apps environment static IP. An A record is normally only required for an apex/root domain, not for `dip.vendorlogic.io`.

## Security Notes

This live-test uses Container Apps built-in authentication and the application reads the EasyAuth principal header to distinguish Admin from Standard users. Admin-only app areas currently include `/admin` and `/audit`.

The app still uses SQLite for live-test simplicity, but the active database runs on container-local storage and is copied to the Azure Files share after write operations. This avoids SQLite SMB locking issues while keeping a recoverable MVP snapshot. Before production use, move persistence to Azure Database for PostgreSQL, add backup/restore, immutable audit export, RBAC hardening, data retention controls and formal operational runbooks.
