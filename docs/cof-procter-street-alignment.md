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

## Client Action Queue

When a client marks an opportunity as interested, COF creates or updates a client interest signal and creates an Account Lead action queue item for on-demand document retrieval.

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

COF adds two primary production report modes, while retaining the legacy weekly report names for backwards compatibility:

- `cof_internal_review_pack`
- `cof_final_customer_pack`
- `cof_weekly_portfolio_report`
- `cof_weekly_client_report`

Report sections include:

- Client / portfolio summary
- Client coverage for all 11 monitored clients
- PINs
- Watchlist
- Live tenders
- Closing soon
- Awards / market evidence
- Client Action Queue
- Documents retrieved
- Public notice evidence
- Quality questions and weightings
- Requirement themes
- Human Review Gate
- Review gaps
- Monday send readiness

Reports are available as PDF, HTML, Markdown, JSON and text. The PDF and HTML exports use the configured report brand, prepared-for label and footer caveat. File outbox email remains the safe default unless SMTP is configured.

The weekly customer pack now follows the source-to-inbox model: it always generates, includes a concise Source Health section, and ignores stale or failed source records from customer opportunity sections until the source is healthy again.

## Client Display Names

The database can keep temporary client records such as `COF Client 01` while reports present customer-safe names.

Use these environment variables:

- `DIP_COF_CLIENT_NAME_MODE=redacted` uses professional redacted names such as `Client A - Highways`. This is the default for customer-facing reports.
- `DIP_COF_CLIENT_NAME_MODE=configured` uses `DIP_COF_CLIENT_NAME_MAP_JSON` to map temporary names to approved client names.
- `DIP_COF_CLIENT_NAME_MODE=placeholder` shows the stored temporary names and should be used only for internal configuration checks.

Example configured mapping:

```json
{
  "COF Client 01": "Approved Highways Client",
  "COF Client 02": "Approved Estates Client"
}
```

The mapping affects report display only. It does not rewrite customer records; permanent customer names should be updated through the Admin UI when they are approved.

## Review Lead Status

COF report rows use one of four review statuses:

- Review Lead approved for report inclusion
- Awaiting Review Lead review
- Needs more evidence
- Rejected / excluded

Review Lead approval means approved for inclusion in the COF report. It does not mean bid, legal, procurement or compliance approval. The report keeps a single global caveat: human review is required and the pack is not a bid/no-bid, legal, procurement or compliance decision.

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
- Report type: `cof_final_customer_pack`
- Frequency label: Monday
- Export format: PDF

Sending remains manual or externally scheduled in this phase; no new Azure scheduler or background infrastructure is required.

The weekly report's Monday Send Readiness section now shows:

- Whether the COF Monday digest profile exists and is enabled
- Delivery mode, such as `file_outbox` or SMTP
- Recipient count
- Export format
- Latest report timestamp
- Latest email delivery status
- Number of clients with and without visible items
- Attention items including pending Human Review Gate items, pending document review, pending quality-question review, interested items without retrieval tasks and missing recipients

If recipients are not configured, report downloads and file-outbox review remain available, but email/send is not attempted until recipients are configured.

## Report Branding

Use environment variables to label customer-facing exports without code changes:

- `DIP_REPORT_BRAND_NAME`, default `Contracted Opportunity Finder`
- `DIP_REPORT_PREPARED_FOR`, default `Procter Street`
- `DIP_REPORT_FOOTER`, default `Human review required. Not a bid, legal, procurement or compliance decision.`

Do not place secrets in these values. They are rendered in HTML, PDF and JSON exports.

## Applying The Pack

1. Open Admin.
2. If preparing a clean customer review session, use **Clean Generated Output** to remove old reports, email logs, source snapshots, KRA run history and stored outbox files. This preserves configured clients, sources, portals, opportunities, requirements, interest signals and review records.
3. Use **Reset COF workspace to design brief** if you need to reapply only the 11 clients, five source families plus backup, and four portal families from the proposal baseline.
4. Open Customer packs if you want to preview the Procter Street COF pack before applying it manually.
5. Replace temporary client names, aliases, regions, keywords, CPV codes and reporting notes with approved live client data when available.
6. Open Review to verify the human review gate and relationship action queue.
7. Open Client Feed to inspect PINs, live tenders, interested items and awards.
8. Generate a COF weekly portfolio report from Reports.
9. Download or send/store the report from the report detail page or digest profile.

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
