# Current-Cost Operating Model

Last updated: 20 May 2026.

The Data Intelligence Portal is currently operated on the existing Azure live-pilot resources to control cost while the product workflow, data quality, reports and review model are hardened.

## Current Position

- The app remains compatible with Azure Container Apps.
- The deployed environment continues to use SQLite with Azure Files snapshot persistence.
- The current live Container App is sized at `2.0` CPU / `4Gi` memory so the COF Autopilot, PDF export and email-outbox cycle complete reliably without adding new Azure services.
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
python -m app.jobs archive-opportunities
python -m app.jobs send-digests
python -m app.jobs admin-cycle
```

These jobs write `AutomationRun` records and audit events. They are intentionally not tied to new cloud scheduling infrastructure in the current-cost phase.

`archive-opportunities` moves records out of the live pipeline when they are past deadline, terminal/closed, old award evidence or stale. It does not permanently delete records. Admin users can search, export, restore or purge archived records from `/archive`.

The current COF Autopilot profile keeps the expensive parts bounded:

| Setting | Current default | Effect |
| --- | --- | --- |
| `DIP_AUTOPILOT_KRA_CUSTOMER_LIMIT` | `3` | Runs live customer-source KRA for a rotating batch of three customers per one-click cycle; the next cycle prioritises customers with no or older KRA runs |
| `DIP_AUTOPILOT_MARKET_SWEEP_ENABLED` | `false` | Skips broad market keyword sweep unless explicitly enabled |
| `DIP_AUTOPILOT_KRA_MAX_PAGES` | `1` | Caps live KRA source pages when KRA is enabled |
| `DIP_AUTOPILOT_KRA_CANDIDATES_PER_PAGE` | `10` | Caps candidates per source page when KRA is enabled |
| `DIP_NOTICE_PAGE_LIMIT` | `10` | Limits official-source response size for current-opportunity cycles |
| `DIP_NOTICE_LOOKBACK_DAYS` | `45` | Keeps source ingestion focused on current and recent opportunities |

This keeps the same-resource Azure deployment viable while still producing refreshed source health, connector results, report exports, file-outbox email and audit evidence.

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
