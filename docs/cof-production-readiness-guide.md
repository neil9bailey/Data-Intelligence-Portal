# COF Production Readiness Guide

This guide explains how the Contracted Opportunity Finder runs the source-to-inbox opportunity workflow with advisory source health, human curation and weekly report output.

## Report Modes

COF supports two production report modes:

- `cof_internal_review_pack`: internal operational pack. It can always be generated and shows pending reviews, source warnings, KRA status, portal coverage, retrieval queues and send-readiness diagnostics.
- `cof_final_customer_pack`: weekly customer pack. It always generates and includes concise Source Health so stale or failed sources are visible without stopping download/export.

Legacy report types remain available for backwards compatibility:

- `cof_weekly_portfolio_report`
- `cof_weekly_client_report`

The legacy portfolio type maps to the weekly customer pack and keeps the COF workspace scope.

## Source Health And Weekly Send Readiness

The operating status engine checks:

- minimum configured COF customers, default 11 through `DIP_COF_MIN_CUSTOMERS`
- every COF customer has visible pipeline coverage
- required public sources exist and are active: Find a Tender, Contracts Finder, Public Contracts Scotland, Sell2Wales and TED
- Tenders Direct exists as the backup source
- required portal families exist: ProContract, In-Tend, Jaggaer and Delta eSourcing
- each COF customer has a portal route or route-to-confirm warning
- KRA agent profiles exist and any KRA output remains evidence support only
- stale, failed or inactive sources are ignored from customer opportunity sections
- opportunity records remain visible only when they are matched to COF clients and trusted active source families
- interested items have document retrieval tasks
- a Monday digest profile exists, is enabled, has recipients and has an export format

Report downloads always remain available. Email/send is guarded only by recipient and delivery configuration. File outbox delivery is acceptable for the current live customer-pilot environment.

## Source Validation

Internal packs may show source references that still need validation, but they are labelled as pending validation and appear as attention items.

Weekly customer packs include verified official/public source references or safe non-clickable source labels. They never show internal COF notice references as captured source evidence.

## Workflow Labels

Customer-facing output uses role labels only:

- Review Lead
- Account Lead
- Human Review Gate
- Client Action Queue
- Document Retrieval Queue
- Weekly Send Readiness

Review Lead approval means approved for COF report inclusion. It is not bid, legal, procurement or compliance approval.

## KRA Guardrails

KRA can support:

- broad market sweeps
- customer-scoped source review
- source-scoped checks
- match evidence and report-ready summaries

KRA does not make bid/no-bid, legal, procurement or compliance decisions. AI-assisted or deterministic outputs remain subject to human review.

## Portal And Document Guardrails

The portal workflow tracks portal family, access status and retrieval tasks. It does not store passwords, automate portal login, submit expressions of interest, contact customers or submit bids.

Document extraction uses permitted text, notes and summaries only. Storage references and portal references are not treated as raw document content.

## Getting From Attention To Ready

1. Open Admin and review the COF Source Health panel.
2. Generate the Internal Review Pack for operational diagnostics.
3. Resolve stale or failed source health, review-gate, document/question review and portal route attention items.
4. Configure the COF Monday report send digest profile with recipients.
5. Re-run the weekly customer pack.
6. Send or store the pack when it says `Ready for weekly send`; otherwise download/export remains available with warnings.

## Current Azure Operating Model

This phase stays on the existing Azure Container Apps, SQLite snapshot and Azure Files model to control cost. No new Azure resources, tenant migration, PostgreSQL deployment, Key Vault, storage account, scheduler or networking layer is required for these application changes.

The future production-infrastructure phase remains deferred and should cover the new tenant, PostgreSQL, immutable audit storage, stronger networking/security, formal backup/restore, monitoring and alerting.
