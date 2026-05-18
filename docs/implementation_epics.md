# Implementation Epics

This page records the current MVP delivery state and the next sensible epics.

## Delivered MVP

| Epic | Status | Notes |
| --- | --- | --- |
| Product shell and data model | Delivered | FastAPI, Jinja2, SQLModel, SQLite, Docker and pytest baseline. |
| Business units and customers | Delivered | Customer records, aliases, buying entities, BU links and CRUD controls. |
| Source catalogue | Delivered | YAML source config, source checks, snapshots and change detection. |
| Opportunity catalogue | Delivered | Manual and KRA-created opportunities, documents and review workflow. |
| Portal workbench | Delivered | Platform families, portal instances, access status, account reference, retrieval mode and tasks. |
| Read-only connectors | Delivered MVP | Public/API-key connector pattern with guardrails and retrieval runs. |
| Document and requirement intelligence | Delivered MVP | Permitted text extraction into requirements and quality questions. |
| KRA Knowledge Research Agent | Delivered MVP | Local deterministic agent profiles and controlled source runs. |
| Reporting and exports | Delivered | PDF, Markdown, HTML, JSON, text, local download and email sending. |
| Admin health dashboard | Delivered | Local/remote health, Entra status, DB status, source/portal/KRA/email health. |
| Admin autonomous COF workflow | Delivered MVP | One-click admin cycle for preconfigured packs, public-source refresh, KRA, review preparation, approved retrieval, report export, email and audit logging. |
| Audit log | Delivered MVP | Event log for key user and automation changes. |
| Azure live-test IaC | Delivered MVP | Container Apps, Entra auth, Key Vault reference, Azure Files and custom domain path. |
| CI quality gates | Delivered | GitHub Actions runs Python 3.12 pytest and conservative ruff linting on push and pull request. |
| Modular FastAPI routing | Delivered | Route groups are split into `app/routes/` modules with shared web helpers in `app/route_utils.py`; `app/main.py` now focuses on app setup and router registration. |

## Next Delivery Epics

### Epic 1 - Production Data Platform

- replace SQLite with Azure Database for PostgreSQL
- add Alembic migrations
- add backup/restore automation
- add environment-specific retention policies

### Epic 2 - Enterprise Security

- harden Entra group and role mapping
- add customer/environment-specific RBAC
- add audit export to immutable storage
- add security logging and alerting
- document connector approval and secret rotation

### Epic 3 - Connector Maturity

- build first-class Contracts Finder and Find a Tender connectors
- add provider-approved API-key connector templates
- add scheduling for source and connector checks
- add connector run dashboards and failure queues

### Epic 4 - Customer Knowledge Base

- add richer watch-profile editing
- add customer source packs
- add requirement trend analytics
- add customer/account briefing templates

### Epic 5 - Document Governance

- add document storage integration design
- add classification labels
- add attachment export policy
- add SharePoint or object-storage option

### Epic 6 - Advisor/Buyer Workflow

- add assignment and approval states
- add comments and review decisions
- add client-facing report pack curation
- add notification rules

### Epic 7 - AI/MCP Agent Expansion

- add approved MCP tool registry
- add guarded live web/API lookup workers
- add source-diff summarisation
- add human-approved autonomous schedules
- add prompt/version traceability for generated summaries
