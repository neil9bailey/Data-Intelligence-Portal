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
| App-level RBAC | Delivered | Health remains public; standard, auditor, admin and local-admin roles are enforced in route dependencies with explicit `LOCAL_ADMIN_MODE` for local-only fallback. |
| Secret references | Delivered | Email configuration now stores SMTP password references rather than raw values; send-time resolution uses environment/Key Vault-backed variables with legacy compatibility. |
| PostgreSQL and Alembic support | Delivered MVP | SQLite remains default; PostgreSQL URLs are supported and Alembic has an initial SQLModel metadata migration. |
| Observability and readiness | Delivered MVP | `/healthz` remains liveness, `/readyz` checks database/templates/static, request IDs are echoed in responses and Admin shows DB mode. |
| Official source connectors | Delivered MVP | Contracts Finder and Find a Tender now have provider-specific connector classes for query construction, parsing and pagination hooks. |
| Jobs and evaluation | Delivered MVP | CLI jobs support source/feed/connector/admin cycles; offline evaluation fixtures measure matching precision and recall. |
| Match explainability and feedback | Delivered MVP | Opportunity matches record rationale evidence and Admin users can submit feedback that moves risky records back to review. |
| Branded report exports | Delivered MVP | HTML/PDF exports now carry a clearer branded wrapper and human-review caveat, with JSON including the same caveat metadata. |
| Document governance metadata | Delivered MVP | Opportunity documents can record storage provider/reference, classification label, retention status, reviewer and source-access notes. |
| Customer onboarding wizard | Delivered MVP | Intelligence Packs provide a guided preview/apply flow for built-in and generated public-sector account baselines. |
| AI provenance and finding review | Delivered MVP | AI-assisted KRA findings carry provider/model/prompt version/hash metadata and can be approved or rejected by Admin users. |
| Digest notifications | Delivered MVP | Admin digest profiles can create and send/store scoped report exports through the existing email channel. |
| Audit export | Delivered MVP | Audit events can be exported as JSON or CSV with existing snapshot redaction. |
| Scoped standard-user access | Delivered MVP | `DIP_ACCESS_SCOPES_JSON` can restrict standard users to configured customer or business-unit report/client-feed records. |

## Next Delivery Epics

### Epic 1 - Production Data Platform

- move live environments from SQLite snapshot persistence to Azure Database for PostgreSQL
- add backup/restore automation
- add environment-specific retention policies

### Epic 2 - Enterprise Security

- harden Entra group and role mapping
- expand customer/business-unit scoping across every read and write surface
- add audit export to immutable storage
- add security logging and alerting
- document connector approval and secret rotation

### Epic 3 - Connector Maturity

- deepen first-class Contracts Finder and Find a Tender connectors with production paging/rate-limit telemetry
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
- improve AI review queues and explainability dashboards beyond the MVP provenance hashes
