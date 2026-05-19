# Contracted Opportunity Finder: Procter Street Alignment

This page maps the current application to the Procter Street Contracted Opportunity Finder proposal. The current deployment remains a live customer-pilot workspace on the existing Azure Container Apps, SQLite snapshot and Azure Files model. It is not a throwaway demonstration, and it does not require new Azure resources for this phase.

## Service Positioning

Contracted Opportunity Finder helps Procter Street scale opportunity monitoring from the current 11-client operating model toward a larger portfolio without increasing manual effort in the same proportion.

The service captures public opportunity signals, matches them against client profiles, applies a human review gate, tracks client interest, triggers on-demand document retrieval tasks and generates branded weekly reports.

## Source-To-Inbox Pipeline

1. Public sources are configured in the COF pack.
2. Source checks and connector runs collect public metadata only.
3. OCDS-style records are normalised into opportunity records.
4. Stable references such as OCID, notice identifier and source URL are used for dedupe and traceability.
5. Client watch profiles match buyer names, aliases, sectors, keywords and CPV themes.
6. Low-confidence or mismatched records are held for review.
7. Approved records reach the client portal and weekly reports.

## Five Sources And Backup

The Procter Street COF pack creates source records for:

- Find a Tender
- Contracts Finder
- Public Contracts Scotland
- Sell2Wales
- TED
- Tenders Direct as a backup aggregator, disabled unless licensed and approved

Official and public sources are preferred. Tenders Direct is treated as a backup source and must not be activated without appropriate commercial access and secret handling.

## Four Portal Platform Families

The COF pack creates portal-family records for:

- ProContract
- In-Tend
- Jaggaer
- Delta eSourcing

These records document portal routing and document retrieval assumptions. The application does not store portal passwords, automate portal login, submit expressions of interest, contact customers or submit bids.

## Human Review Gate

The review page uses a human review gate. This is a workflow role, not a hard-coded authenticated person.

The queue shows the opportunity, buyer, value, deadline, matched client, score, matched terms and actions:

- Approve
- Reassign
- Reject
- Needs more evidence
- Hold

Nothing should be treated as client-ready until it has passed human review.

## Donna Action Queue

When a client marks an opportunity as interested, COF creates or updates a client interest signal and creates a Donna relationship/action queue item for on-demand document retrieval.

The action queue tracks:

- Interested client
- Opportunity
- Signal date
- Document retrieval status
- Follow-up status

This does not automate customer contact or portal action. It creates internal work for the authorised relationship or bid user.

## Client Portal

The client portal now exposes the proposal-aligned view:

- PINs
- Live tenders
- Interested
- Awarded
- I am interested action
- Watch action
- View questions where quality questions and weightings have been extracted

Interest creates a document retrieval task. Watch records the signal but does not trigger retrieval.

## Weekly Reports

COF adds two report types:

- `cof_weekly_portfolio_report`
- `cof_weekly_client_report`

Report sections include:

- Client / portfolio summary
- PINs
- Live tenders
- Closing soon
- Awards / market evidence
- Interested / Donna actions
- Documents retrieved
- Quality questions and weightings
- Review gaps
- Monday send readiness

Reports are available as PDF, HTML, Markdown, JSON and text. File outbox email remains the safe default unless SMTP is configured.

## Friday Review And Monday Send

Admin includes a Friday Review Readiness panel showing:

- Unreviewed opportunities
- Clients without visible items
- Missing source URLs
- Missing deadlines
- Interested items without document retrieval tasks
- Whether the Monday report profile exists

The COF pack also creates the default digest profile:

- Name: COF Monday report send
- Report type: `cof_weekly_portfolio_report`
- Frequency label: Monday
- Export format: PDF

Sending remains manual or externally scheduled in this phase; no new Azure scheduler or background infrastructure is required.

## Applying The Pack

1. Open Admin.
2. If preparing a clean customer walkthrough, use **Clean Generated Output** to remove old reports, email logs, source snapshots, KRA run history and stored outbox files. This preserves configured clients, sources, portals, opportunities, requirements, interest signals and review records.
3. Open Customer packs.
4. Select Procter Street COF.
5. Preview the 11 active client placeholders, sources and portal families.
6. Apply the pack.
7. Replace placeholder client names, aliases, regions, keywords, CPV codes and reporting notes with approved live client data when available.
8. Open Review to verify the human review gate and relationship action queue.
9. Open Client Feed to inspect PINs, live tenders, interested items and awards.
10. Generate a COF weekly portfolio report from Reports.
11. Download or send/store the report from the report detail page or digest profile.

## Guardrails

- No portal passwords are stored.
- No automated portal login is performed.
- No expressions of interest are submitted to buyer portals.
- No customer contact is sent automatically.
- No bid submission is automated.
- AI-assisted or agent-classified content remains human-review intelligence.
- Outputs must not be used as bid/no-bid, legal, procurement or compliance decisions without authorised review.

## Current Azure Position

The current customer-pilot environment deliberately uses the existing Azure resources to control cost. SQLite snapshot persistence is acceptable for this pilot scope, but it is not the final production data platform.

Deferred production migration items include a new tenant, PostgreSQL, immutable audit storage, stronger networking/security, monitoring/alerting and formal backup/restore controls.
