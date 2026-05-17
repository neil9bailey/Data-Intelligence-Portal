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
- a built-in KRA Knowledge Research Agent for guarded source checks, source-change tracking, customer memory and requirement extraction
- MCP-style local agent/tool profiles ready for future connector orchestration

## What It Is Not

- It is not a bid/no-bid decision engine.
- It is not a replacement for commercial, legal, procurement or compliance review.
- It does not automate customer contact, portal submissions or expressions of interest without explicit future governance.
- It does not store portal passwords or secrets in the MVP.

## Review Artefacts

- [Solution plan](docs/solution_plan.md)
- [Architecture blueprint](docs/architecture_blueprint.md)
- [Implementation epics](docs/implementation_epics.md)
- [Benefits case](docs/benefits_case.md)
- [Source and portal catalogue](docs/source_and_portal_catalogue.md)
- [Portal platform operating guide](docs/portal-platform-operating-guide.md)
- [National Highways onboarding guide](docs/national-highways-onboarding-guide.md)
- [UI mockup](docs/ui_mockups/data_intelligence_portal_mockup.html)

Open the mockup directly in a browser:

```text
F:\code\Data-Intelligence-Portal\docs\ui_mockups\data_intelligence_portal_mockup.html
```

## Proposed MVP Stack

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

Current KRA mode is deterministic/local by default. API-key-backed AI enhancement can be added behind the same review controls.

## KRA Knowledge Research Agent

KRA is available at `/kra`.

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

Use `/portals` to add a connector, link it to a buyer portal and optionally link it to a default opportunity. When linked to an opportunity, a successful retrieval creates or updates an opportunity document and runs requirement extraction. When not linked to an opportunity, the retrieval creates a KRA finding for review.

Reports can automatically run enabled read-only retrieval connectors before generation, so end-user briefing packs can include the latest retrieved information where provider permissions and guardrails allow it.

## COF Source-To-Inbox Workflow

Pages 2 and 3 of the COF design draft have been mapped into the product as a configurable workflow at `/workflow`.

The workflow covers:

- five public opportunity sources: Find a Tender, Contracts Finder, Public Contracts Scotland, Sell2Wales and TED
- one ingestion pipeline with OCDS/eForms normalisation and dedupe by OCID or stable notice reference
- customer matching using watch profiles, aliases, keywords, sectors, regions, CPV codes and value bands
- a human review gate at `/review` for approve, hold, reject and reassign actions
- branded report generation with local downloads in Markdown, HTML, JSON and text
- email delivery through `/admin`, using local `.eml` outbox mode by default or SMTP when configured
- a phase-2 style `/client-portal` interest tracker for "I'm interested" signals and pipeline follow-up

The MVP keeps the important COF guardrail: nothing should reach a client or recipient without human review.

## Data Maintenance

The main operational sections now expose user-managed create, edit and delete controls where live data is entered or curated:

- Business Units
- Customers
- Sources
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

See [Azure live-test hosting](docs/azure-live-test-hosting.md) and [infra/azure/README.md](infra/azure/README.md).

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

Configure the first live customers, tune source/watch keywords, refresh the official feed, then run KRA against approved public sources.
