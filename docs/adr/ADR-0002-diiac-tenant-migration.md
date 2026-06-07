# ADR-0002: DIIAC Tenant Migration

**Epic ref:** EPIC-DIP-DIIAC-TENANT-MIGRATION-001  
**Status:** Approved  
**Author role:** Enterprise Architect  
**EA reviewer:** Enterprise Architect  
**Date raised:** 2026-06-07  
**Date approved:** 2026-06-07

## Context

The Contracted Opportunity Finder live pilot is currently running in the Vendorlogic tenant at `https://dip.vendorlogic.io`. The requested next step is to migrate the same DIP/COF capability into the DIIAC tenant and serve it from `https://dip.diiac.io`.

This is design-altering because it changes the Azure tenant, Entra app registration, security groups, Key Vault boundary, Container Apps runtime resources, ACR, storage account, DNS target and operational rollback model.

## Decision

Create an isolated DIIAC live-test stack for DIP/COF using the existing Azure Container Apps, ACR, managed identity, Log Analytics and Azure Files architecture.

The DIIAC deployment will:

- use subscription `9ae9da49-de67-443b-af55-ce9db33ed8f4` and tenant `67f8be6c-07da-4a7c-bb0a-d6bcb38cd6da`
- create/use dedicated DIP resources under `RG_DIP_DIIAC_TEST`
- use a dedicated DIIAC DIP Key Vault, not unrelated existing product vaults
- create DIIAC Entra app registration and DIP Admin/Standard/Auditor groups
- deploy the current image tag `1.0.65-cof-value-layer`
- keep Vendorlogic live and untouched as rollback until DIIAC UAT is complete
- bind `dip.diiac.io` only after DNS validation records are confirmed

No portal password storage, portal login automation, customer contact automation, expression-of-interest automation, bid submission automation, or automated bid/no-bid/legal/procurement/compliance decisions are approved by this ADR.

## Drift Assessment

- Deviates from baseline: yes, by creating a new tenant-specific Azure runtime boundary.
- Still serves the epic: yes, it directly implements the approved move from Vendorlogic to DIIAC.
- Impact on interfaces: public hostname, Entra login boundary and Azure resource IDs change. Application routes and data model remain compatible.

## Options Considered

| Option | Pros | Cons | Risk |
| --- | --- | --- | --- |
| Keep Vendorlogic only | No migration risk | Does not satisfy DIIAC tenant requirement | High delivery drift |
| Reuse an existing DIIAC product vault/resource group | Faster setup | Blurs ownership and rollback boundaries | Medium operational risk |
| Dedicated DIIAC DIP stack | Clear ownership, clean rollback, matches existing IaC | Creates new Azure resources and DNS work | Low/medium migration risk |

Decision: dedicated DIIAC DIP stack.

## Consequences

The DIIAC tenant becomes the forward path for DIP/COF after signed-in UAT. Vendorlogic remains available during migration as rollback. Operational scripts and generated deployment inputs remain environment-specific and must not contain raw secrets.

## Verification Plan

- Back up Vendorlogic Azure Files before any data copy.
- Prepare DIIAC Entra app/groups and Key Vault secret references without logging raw secrets.
- Deploy DIIAC infrastructure and app through Bicep with what-if before apply.
- Build and push current container image to the DIIAC ACR.
- Smoke test generated Container App FQDN: active image tag, revision health, `/healthz`, protected `/readyz`, protected `/`.
- Configure DNS validation records for `dip.diiac.io`, bind managed certificate, then smoke test public URL.
- Complete real signed-in DIIAC end-user UAT before release approval.

## ARB Checkpoint

- [x] EA has reviewed against the architecture baseline
- [x] Drift assessment complete and acceptable
- [x] Verification plan includes live end-user UAT
- [x] Dedicated DIIAC resource boundary selected to reduce cross-product risk
- [x] Vendorlogic rollback retained until DIIAC acceptance
- [x] Approved by human request on 2026-06-07
