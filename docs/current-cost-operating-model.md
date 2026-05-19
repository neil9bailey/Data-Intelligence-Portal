# Current-Cost Operating Model

Last updated: 19 May 2026.

The Data Intelligence Portal is currently operated on the existing Azure live-pilot resources to control cost while the product workflow, data quality, reports and review model are hardened.

## Current Position

- The app remains compatible with Azure Container Apps.
- The deployed environment continues to use SQLite with Azure Files snapshot persistence.
- Existing environment variables remain backwards-compatible.
- KRA can use the existing Key Vault-backed API key already wired into the current Container App.
- Jobs are CLI/manual/external-scheduler friendly and do not require Celery, Redis, Azure Functions or another paid scheduler.
- No new Azure tenant, Container Apps environment, Key Vault, storage account, Front Door, WAF, private networking layer or Azure Database for PostgreSQL is required for the current phase.

## Access Control

| Area | Public | Standard | Auditor | Admin |
| --- | --- | --- | --- | --- |
| `/healthz` | yes | yes | yes | yes |
| `/readyz` | yes, for Azure probes | yes | yes | yes |
| Opportunity inbox `/` | no | scoped | no | all |
| Client feed `/client-portal` | no | scoped | no | all |
| Reports `/reports` | no | scoped | all reports unless scoped later | all |
| Audit `/audit` | no | no | read/export | read/export |
| Admin/configuration routes | no | no | no | yes |
| Sources, portals, customers, KRA, requirements and automation | no | no | no | yes |

Standard-user scopes are controlled by `DIP_ACCESS_SCOPES_JSON`. Scoped users should only see customer, business-unit, opportunity, report and reference data inside their configured scope.

## Current Data And Workflow Guardrails

- Official/public procurement sources are preferred.
- Buyer portal credentials are not stored.
- Portal login is not automated.
- Expressions of interest, customer contact and bid submission are not automated.
- AI-assisted KRA summaries remain review-required.
- The portal does not make bid/no-bid, legal, procurement or compliance decisions.
- Secrets must not be rendered in templates, reports, audit exports, logs or error output.

## Jobs

The current app supports manual/CLI-friendly jobs:

```powershell
python -m app.jobs refresh-sources
python -m app.jobs refresh-feeds
python -m app.jobs run-connectors
python -m app.jobs send-digests
python -m app.jobs admin-cycle
```

These jobs write `AutomationRun` records and audit events. They are intentionally not tied to new cloud scheduling infrastructure in the current-cost phase.

## Deferred Production Infrastructure Phase

When the solution moves to the future tenant, production infrastructure work should be revisited separately:

- new tenant and production subscriptions
- Azure Database for PostgreSQL
- immutable or append-only audit storage
- backup and restore design
- stronger networking, ingress and WAF options
- central monitoring and alerting
- production Key Vault and managed identity model
- production-grade job runner or scheduled workload model
- customer/business-unit scoped access backed by production identity groups

Until that phase, app changes should preserve the current low-cost deployment path.
