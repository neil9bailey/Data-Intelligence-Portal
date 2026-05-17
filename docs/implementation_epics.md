# Implementation Epics

## Epic 1 - Product Shell And Core Data Model

Build the standalone app foundation.

Deliverables:

- FastAPI/Jinja/HTMX app scaffold
- Dockerfile and Docker Compose
- SQLite initialisation
- customer and business-unit models
- audit event model
- base UI shell and navigation
- pytest baseline

## Epic 2 - Source Catalogue

Create configurable public-sector source management.

Deliverables:

- YAML source catalogue
- source allow-list
- source status page
- source check snapshots
- source change detection
- official/public/commercial classification

## Epic 3 - Opportunity Pipeline

Normalise and deduplicate opportunities.

Deliverables:

- OCDS parser for Find a Tender and Contracts Finder
- adapter interface for future sources
- dedupe by OCID/reference/content hash
- customer/profile matching
- opportunity catalogue page
- opportunity status workflow

## Epic 4 - Customer Intelligence

Turn customer setup into a reusable account knowledge base.

Deliverables:

- customer profiles
- aliases and buying entities
- sector/domain taxonomy
- customer portal instances
- notes and account intelligence fields
- customer brief report

## Epic 5 - Portal Platform Intelligence

Track the "800 portals, four platforms" model.

Deliverables:

- platform catalogue for ProContract, In-Tend, Jaggaer and Delta eSourcing
- buyer portal instance records
- account registration status
- manual retrieval task queue
- guardrails preventing credential storage

## Epic 6 - Document And Requirement Intelligence

Capture and structure ITT content.

Deliverables:

- opportunity documents
- retrieval status
- quality-question extraction
- weighting extraction
- requirement theme tagging
- confidence and human review status
- clarification and addendum notes

## Epic 7 - Reporting

Generate useful intelligence outputs.

Deliverables:

- customer intelligence brief
- business-unit opportunity report
- source-health report
- requirement trend report
- document retrieval pack
- Markdown export

## Epic 8 - Governance And Production Readiness

Prepare controlled use beyond local MVP.

Deliverables:

- SSO design
- RBAC design
- secrets management approach
- immutable audit design
- backup/restore model
- retention policy
- deployment controls
- connector approval process
