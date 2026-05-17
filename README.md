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
- executive summaries and exportable intelligence reports
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

Guardrails:

- no portal passwords stored in the MVP
- no automated portal login
- no customer contact automation
- no portal submission or expression of interest automation
- extracted intelligence remains review-required until accepted by a human

## Azure Evolution Path

The next phase can migrate this local MVP to the Vendorlogic test Azure tenant and `vendorlogic.io` Entra ID:

- Entra ID authentication
- RBAC roles for viewers, contributors, reviewers and administrators
- Azure Key Vault for API keys and connector secrets
- Azure Container Apps or Azure Container Instances for hosting
- Azure Database for PostgreSQL
- managed storage for documents
- scheduled KRA source checks
- immutable audit/event storage

## Official Source Baseline

The plan references official/public procurement routes checked on 2026-05-17:

- GOV.UK Contracts Finder
- GOV.UK public-sector procurement guidance
- Find a Tender service and developer documentation
- Contracts Finder API documentation
- Public Contracts Scotland API
- TED eForms developer material

## Recommended Next Step

Approve the product scope and UI direction, then build the MVP app in this repo using the architecture and epics described in `docs/`.
