# Architecture Blueprint

This document describes the current Data Intelligence Portal build and the intended production evolution.

## Current MVP Architecture

```mermaid
flowchart LR
  A["Official/public sources"] --> B["Source checks + snapshots"]
  C["Buyer portal instances"] --> D["Manual retrieval tasks"]
  E["Approved read-only connectors"] --> F["Portal retrieval runs"]
  B --> G["Opportunity catalogue"]
  F --> H["Opportunity documents"]
  D --> H
  H --> I["Requirement extraction"]
  G --> I
  J["Customers + business units"] --> G
  J --> I
  I --> K["Review queue"]
  K --> L["Reports + exports + email"]
  M["Admin Control Centre"] --> B
  M --> E
  M --> N["Health, KRA, email, audit"]
```

## Current Stack

- Python 3.12
- FastAPI
- SQLModel / SQLAlchemy
- SQLite for local and live-test MVP persistence
- Jinja2 server-rendered HTML
- HTMX-ready templates with minimal vanilla CSS
- YAML-backed source, platform, extraction, workflow and KRA configuration
- pytest
- Docker Desktop
- Azure Container Apps live-test path

## Runtime Areas

| Area | Current Implementation |
| --- | --- |
| Command View | Dashboard with customer/source/connector/news/opportunity summary. |
| Workflow | Live operating workflow with source, portal, review and report metrics. |
| Admin | Consolidated health dashboard, source/KRA/audit links and email configuration. |
| Customers | Customer records, business-unit links, aliases, buying entities and notes. |
| Sources | Approved public source catalogue and source-change snapshots. |
| Portals | Buyer portal instances, retrieval mode, account reference, tasks and connectors. |
| Opportunities | Opportunity catalogue linked to customers, sources, business units and documents. |
| Documents | Document metadata and permitted text extraction. |
| Requirements | Extracted requirement themes and quality questions pending review. |
| Reports | Markdown/HTML/JSON/text exports and controlled email delivery. |
| Audit | MVP event log for key create/update/delete and automation events. |

## Key Code Modules

| Module | Purpose |
| --- | --- |
| `app/main.py` | Routes, page rendering and orchestration. |
| `app/models.py` | Data model for customers, sources, portals, opportunities, documents, reports and audit. |
| `app/intelligence.py` | Source checks, KRA runs, deterministic parsing and extraction. |
| `app/portal_connectors.py` | Read-only connector guardrails and retrieval runs. |
| `app/reports.py` | Markdown report generation. |
| `app/email_service.py` | Local outbox and SMTP delivery. |
| `app/auth.py` | Local user mode and Container Apps EasyAuth/Entra header handling. |
| `app/audit.py` | Audit event creation and compact snapshots. |
| `app/database.py` | SQLite setup, schema updates and Azure Files snapshot handling. |
| `app/rules/` | YAML configuration for sources, platforms, KRA, extraction, feeds and workflow. |

## Data Objects

- `BusinessUnit`
- `Customer`
- `CustomerWatchProfile`
- `ProcurementSource`
- `SourceCheckSnapshot`
- `NewsFeedSource`
- `NewsFeedItem`
- `ProcurementPlatform`
- `BuyerPortalInstance`
- `PortalInformationConnector`
- `PortalRetrievalRun`
- `Opportunity`
- `OpportunityDocument`
- `DocumentRetrievalTask`
- `ExtractedRequirement`
- `ExtractedQualityQuestion`
- `KRAAgentProfile`
- `KRAResearchRun`
- `KRAFinding`
- `IntelligenceReport`
- `EmailConfiguration`
- `EmailDeliveryLog`
- `AuditEvent`

## Source Change Tracking

Each source check stores:

- source id
- query URL
- timestamp
- HTTP status
- content hash
- previous hash
- detected schema
- change type: first seen, unchanged, changed, failed
- connector status
- notes

## Portal Retrieval Model

The MVP supports:

- manual account-required retrieval tasks
- public no-key API retrieval
- API-key header/query references where provider-approved
- read-only connector runs
- requirement extraction from retrieved or manually pasted text

The MVP does not store portal passwords, automate portal login, submit expressions of interest or send customer messages.

## Deployment View

Local:

- Docker Compose
- one FastAPI container
- mounted local `./data` folder
- no cloud services
- no secrets required

Azure live-test:

- Azure Container Apps
- Microsoft Entra built-in auth
- Admin and Standard security groups
- existing Key Vault for DIP-specific secrets
- Azure Files snapshot/outbox persistence
- Container-local SQLite active DB copied to Azure Files after writes
- dedicated ACR, managed identity and Log Analytics workspace

Reusable customer deployments are supported by:

- `infra/azure/main.sub.bicep`
- `infra/azure/main.rg.bicep`
- `scripts/azure/new-customer-deployment.ps1`

## Production Evolution

Before full production use:

- move persistence to Azure Database for PostgreSQL
- formalise backup, restore and retention
- add immutable audit/event export
- add stronger RBAC and data governance
- add reviewed connector secrets and rotation policy
- add monitoring alerts and operational runbooks
- add private networking/WAF/Front Door decisions where required
- add deployment approvals between test and production
