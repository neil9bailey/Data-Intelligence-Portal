# Data Intelligence Portal

Dedicated product concept for a general public-sector customer, framework, procurement-source and requirement intelligence platform.

This repo now contains a runnable local MVP for a standalone intelligence product. The solution focuses on gathering, normalising, tracking and reporting useful customer and opportunity intelligence for bid, sales, strategy, service design, delivery and account teams.

## What It Is

Data Intelligence Portal is a configurable information-gathering workspace for:

- public-sector customers and account profiles
- procurement frameworks and opportunity notices
- official/public procurement data sources
- buyer portal platforms and customer portal instances
- ITT documents, quality questions, weightings and clarification records
- requirement themes and customer demand signals
- source-change monitoring and connector health
- official GOV.UK policy/news feed monitoring
- executive summaries and exportable intelligence reports
- COF-style source-to-inbox workflow, review queue, local downloads and controlled email delivery
- Intelligence Packs that preconfigure public-sector customers, watch profiles, source monitors and portal assumptions from one guided screen
- Admin-side autonomous workflow that can apply packs, refresh public sources, run KRA, prepare review queues, run approved read-only retrieval, generate/store/email a report and log the cycle
- simplified user-facing opportunity inbox, client feed and report download experience
- a built-in KRA Knowledge Research Agent for guarded source checks, source-change tracking, customer memory and requirement extraction
- MCP-style local agent/tool profiles ready for future connector orchestration

## What It Is Not

- It is not a bid/no-bid decision engine.
- It is not a replacement for commercial, legal, procurement or compliance review.
- It does not automate customer contact, portal submissions or expressions of interest without explicit future governance.
- It does not store portal passwords or secrets in the MVP.

## Review Artefacts

- [Documentation index](docs/README.md)
- [Solution plan](docs/solution_plan.md)
- [Architecture blueprint](docs/architecture_blueprint.md)
- [Implementation epics](docs/implementation_epics.md)
- [Benefits case](docs/benefits_case.md)
- [Source and portal catalogue](docs/source_and_portal_catalogue.md)
- [Portal platform operating guide](docs/portal-platform-operating-guide.md)
- [End user operating process](docs/end-user-operating-process.md)
- [National Highways onboarding guide](docs/national-highways-onboarding-guide.md)
- [Azure deployment guide](docs/azure-deployment-guide.md)
- [UI mockup](docs/ui_mockups/data_intelligence_portal_mockup.html)

Open the mockup directly in a browser:

```text
F:\code\Data-Intelligence-Portal\docs\ui_mockups\data_intelligence_portal_mockup.html
```

## Current MVP Stack

- Python 3.12
- FastAPI
- SQLModel / SQLAlchemy
- SQLite for local MVP persistence
- Jinja2 server-rendered HTML
- HTMX for dynamic interactions
- YAML-backed source and extraction configuration
- pytest
- Docker Desktop

## Running Locally

```powershell
docker compose up --build
```

Open:

```text
http://localhost:8091
```

Run tests:

```powershell
docker compose run --rm app pytest -q
```

Stop:

```powershell
docker compose down
```

## Clean Start And Demo Data

The default local run is now a clean operational baseline:

- `SEED_REFERENCE_DATA=true` keeps configurable source definitions, portal platform families, KRA agent profiles and official feed sources available.
- `SEED_DEMO_DATA=false` prevents demo customers, opportunities, extracted requirements and findings from being created.
- `AUTO_APPLY_CUSTOMER_PACKS=true` applies the built-in customer packs automatically at startup for a live demo. Set it to `false` when you need a clean-start workspace.

To reset local captured content completely:

```powershell
docker compose down
Remove-Item .\data\data-intelligence-portal.sqlite
docker compose up --build
```

To deliberately load demo customer/opportunity data for a show-and-tell run:

```powershell
$env:SEED_DEMO_DATA="true"
docker compose up --build
```

## Local API Keys

The MVP works without API keys. Optional future KRA provider settings can be kept in a local `.env` file copied from `.env.example`.

Do not commit `.env`.

```powershell
Copy-Item .env.example .env
```

Supported placeholders:

- `KRA_LLM_PROVIDER`
- `KRA_API_KEY`
- `KRA_MODEL`
- `KRA_MCP_MODE`
- `DIP_PUBLIC_DOMAIN`
- `DIP_REMOTE_HEALTH_URL`
- `DIP_DEPLOYMENT_LABEL`

Current KRA mode is deterministic/local by default. API-key-backed AI enhancement can be added behind the same review controls.

## Admin Control Centre

Admin and configuration tasks are consolidated under `/admin` and are reached from the dedicated **Admin** button in the header. The main navigation stays deliberately simple for end users: Opportunity Inbox, Client Feed and Reports.

The Admin Control Centre shows:

- one-click autonomous COF workflow runner, queued in the background on Azure so Admin can refresh status instead of waiting on a long browser request
- local runtime/database persistence status
- remote `/healthz` status for the configured public domain
- Entra/local auth status and group configuration signals
- public-source and portal connector health
- latest source checks and retrieval runs
- KRA runtime configuration
- email profile, local outbox/SMTP test sending and delivery logs
- an Admin Configuration Workspace containing the previous setup/configuration screens, including workflow, customer packs, business units, customers, sources, portals/connectors, opportunities, review queue, requirements, KRA, reports/exports and audit

Detailed setup and data-entry screens are Admin-only when Entra authentication is enabled. Standard users see the simplified Opportunity Inbox, Client Feed and report downloads.

Local Docker uses `DIP_DEPLOYMENT_LABEL=local-docker` by default. Azure live-test should set `DIP_DEPLOYMENT_LABEL=azure-live-test`, `DIP_PUBLIC_DOMAIN=dip.vendorlogic.io` and `DIP_REMOTE_HEALTH_URL=https://dip.vendorlogic.io/healthz`.

## KRA Knowledge Research Agent

KRA is operated from the Admin Control Centre and remains directly available at `/kra`.

It provides local MCP-style agent profiles:

- Official Source Scout
- Customer Memory Curator
- Portal Document Scout
- Requirement Analyst
- Briefing Writer

KRA can:

- fetch approved official/public HTTPS sources
- record source status, schema and content hashes
- detect first-seen, unchanged, changed and failed source states
- create reviewable research findings
- parse public opportunity notices where the data format is supported
- create opportunity and requirement records
- extract quality questions and weighting signals from permitted document text
- generate Markdown reports

## Intelligence Packs

Open `/admin`, then **Customer packs**, to reduce manual customer setup.

The page supports:

- preconfigured customer packs for live-demo public-sector accounts including National Highways, Transport for London, Network Rail, Department for Transport, Crown Commercial Service and NHS England
- semi-configured packs for any public-sector organisation using templates such as local authority, transport authority, NHS body, emergency services, education, housing and regulated infrastructure
- one-action creation of the customer, business unit, watch profile, official public-source searches, portal assumptions and KRA prompt guidance
- idempotent apply behaviour, so reapplying a pack updates or skips existing records instead of duplicating them

Packs are runtime YAML configuration:

- `app/rules/public_sector_templates.yml`
- `app/rules/customer_packs.yml`

The pack engine is a setup accelerator, not a substitute for review. It still requires humans to confirm portal access, supplier registrations, account ownership, live opportunity references and permitted document extracts.

## Read-Only Portal Retrieval Connectors

The Portal Workbench supports approved automated information retrieval where a portal or source provider offers a permitted API/public endpoint.

Connector principles:

- retrieval only; no expressions of interest, portal submissions, messages or customer contact automation
- read-only by design
- endpoint host must be on an approved source domain or the configured portal/platform domain
- API keys are referenced by environment variable / Key Vault secret name only
- secret values are not stored in SQLite, displayed in the UI or written into reports
- retrieved information is marked pending human review before onward use

Supported MVP auth modes:

- no key / public API
- API key in header
- API key in query string

Use `/admin`, then **Portals / connectors**, to add a connector, link it to a buyer portal and optionally link it to a default opportunity. When linked to an opportunity, a successful retrieval creates or updates an opportunity document and runs requirement extraction. When not linked to an opportunity, the retrieval creates a KRA finding for review.

Reports can automatically run enabled read-only retrieval connectors before generation, so end-user briefing packs can include the latest retrieved information where provider permissions and guardrails allow it.

## Portal Activation Workflow

The portal workflow assumes that Delta eSourcing, In-Tend, JAGGAER and ProContract generally require a buyer/supplier portal account for full tender pack retrieval unless the provider has approved a read-only API/public endpoint.

For each buyer portal instance, capture:

- customer and business unit
- platform family and portal URL
- access status, including registration, blocked, expired and MFA-owner states
- account reference or internal account owner notes, never passwords
- retrieval mode, such as account-required manual, approved API or API-key header/query
- operational notes and manual retrieval tasks

The optimal workflow is to configure portal access before an opportunity lands, run approved read-only connectors where available, and use manual human retrieval tasks where login/MFA is required.

## COF Source-To-Inbox Workflow

Pages 2 and 3 of the COF design draft have been mapped into the product as the user-facing Opportunity Inbox and the Admin configurable workflow at `/workflow`.

The workflow covers:

- five public opportunity sources: Find a Tender, Contracts Finder, Public Contracts Scotland, Sell2Wales and TED
- one ingestion pipeline with OCDS/eForms normalisation and dedupe by OCID or stable notice reference
- customer matching using watch profiles, aliases, keywords, sectors, regions, CPV codes and value bands
- a human review gate at `/review` for approve, hold, reject and reassign actions
- branded report generation with local downloads in Markdown, HTML, JSON and text
- email delivery through `/admin`, using local `.eml` outbox mode by default or SMTP when configured
- a phase-2 style `/client-portal` interest tracker for "I'm interested" signals and pipeline follow-up

The Admin automation can run the full operating rhythm in one cycle, but the MVP keeps the important COF guardrail: generated intelligence remains review-required and no portal login, expression of interest, submission or customer contact is automated.

## Data Maintenance

The main operational sections now expose user-managed create, edit and delete controls where live data is entered or curated:

- Business Units
- Customers
- Intelligence Packs for rapid customer baseline creation
- Sources, managed through Admin
- Opportunities
- Portal instances and retrieval tasks
- Opportunity documents
- Requirement themes and quality questions
- Client interest signals
- Intelligence reports

Delete actions are deliberately conservative: linked records are either unassigned or child records are removed where they only make sense under the deleted parent, and each change is written to the local audit log.

## Email And Exports

Admin email configuration is available at `/admin`.

Default mode is `file_outbox`, which creates `.eml` files in `.outbox` for safe local testing. SMTP sending can be enabled only after host, port, sender, credentials and recipients are configured.

Report export options:

- Markdown
- HTML
- JSON
- Text

Report emails allow a local sender override and recipient input for now. Future production flow should move recipient selection and sender identity to Entra ID / RBAC.

## Official Intelligence Feed

The dashboard includes a configurable official intelligence feed area. Press **Refresh** on the homepage to pull active Atom feeds from `app/rules/news_feeds.yml`.

Default active feeds are GOV.UK/Government Commercial Agency and legacy Crown Commercial Service feeds. A broader transport procurement GOV.UK search feed is included but inactive until the watch terms are tuned.

Feed items are treated as market and policy signals only. They remain subject to human review and do not replace commercial, legal, procurement or compliance review.

Guardrails:

- no portal passwords stored in the MVP
- no automated portal login
- no customer contact automation
- no portal submission or expression of interest automation
- extracted intelligence remains review-required until accepted by a human

## Azure Evolution Path

The repo now includes an isolated Azure Container Apps live-test path for `dip.vendorlogic.io` under `infra/azure`.

Live-test additions:

- Entra ID authentication
- Standard and Admin Entra groups
- Azure Key Vault secret reference for Container Apps auth
- dedicated Azure Container Registry
- dedicated Azure Container Apps environment and app
- Azure Files persistence for SQLite live-test snapshots and the email outbox
- managed certificate flow for `dip.vendorlogic.io`
- Azure-only SQLite snapshot persistence for the MVP live-test container

Start with:

```powershell
.\scripts\azure\prepare-entra.ps1
.\scripts\azure\deploy-dip.ps1 -Mode apply -InfraOnly
.\scripts\azure\build-push-image.ps1
.\scripts\azure\deploy-dip.ps1 -Mode apply
.\scripts\azure\show-dns-and-bind-domain.ps1
```

See [Azure deployment guide](docs/azure-deployment-guide.md) and [Azure live-test hosting notes](docs/azure-live-test-hosting.md).

For a new customer environment, generate customer-specific Azure parameters and commands with:

```powershell
.\scripts\azure\new-customer-deployment.ps1 `
  -CustomerCode "customer" `
  -EnvironmentCode "test" `
  -SubscriptionId "<subscription-id>" `
  -TenantId "<tenant-id>" `
  -PublicDomain "dip.customer.example" `
  -SharedKeyVaultName "<existing-key-vault-name>" `
  -SharedKeyVaultResourceGroupName "<key-vault-resource-group>"
```

Production should still move beyond the MVP choices:

- Azure Database for PostgreSQL instead of SQLite snapshot persistence
- stronger RBAC and data governance
- backup/restore and retention controls
- immutable audit/event storage
- scheduled KRA source checks
- reviewed connector secrets and outbound network controls

## Official Source Baseline

The plan references official/public procurement routes checked on 2026-05-17:

- GOV.UK Contracts Finder
- GOV.UK public-sector procurement guidance
- Find a Tender service and developer documentation
- Contracts Finder API documentation
- Public Contracts Scotland API
- TED eForms developer material

## Recommended Next Step

Start with `/intelligence-packs`, apply a preconfigured or generated pack, tune the resulting source/watch keywords, refresh the official feed, then run KRA against approved public sources.
