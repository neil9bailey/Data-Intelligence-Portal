# COF Production Readiness Guide

This guide explains how the Contracted Opportunity Finder now separates internal operating output from final customer-facing weekly packs.

## Report Modes

COF supports two production report modes:

- `cof_internal_review_pack`: internal operational pack. It can always be generated and shows blockers, pending reviews, source warnings, KRA status, portal coverage, retrieval queues and send-readiness diagnostics.
- `cof_final_customer_pack`: final customer pack. It is generated only when the readiness gate passes. If blockers exist, the app creates a blocked internal report named `COF Final Customer Pack - blocked` instead.

Legacy report types remain available for backwards compatibility:

- `cof_weekly_portfolio_report`
- `cof_weekly_client_report`

The legacy portfolio type follows the same readiness logic: final if ready, otherwise internal.

## Final Pack Readiness

The readiness engine checks:

- minimum configured COF customers, default 11 through `DIP_COF_MIN_CUSTOMERS`
- every COF customer has visible pipeline coverage
- required public sources exist and are active: Find a Tender, Contracts Finder, Public Contracts Scotland, Sell2Wales and TED
- Tenders Direct exists as the backup source
- required portal families exist: ProContract, In-Tend, Jaggaer and Delta eSourcing
- each COF customer has a portal route or route-to-confirm warning
- KRA agent profiles exist and any KRA output remains evidence support only
- no final included opportunities have missing, invalid or internal source references
- no final included opportunities, retrieved documents or quality questions are pending review
- interested items have document retrieval tasks
- a Monday digest profile exists, is enabled, has recipients and has an export format

File outbox delivery is acceptable for the current live customer-pilot environment, but recipients must still be configured so the weekly send route is explicit.

## Source Validation

Internal packs may show source references that still need validation, but they are labelled as pending validation and appear as blockers.

Final customer packs include only verified official/public source references or safe non-clickable source labels. They never show internal COF notice references as captured source evidence.

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

## Getting From Blocked To Ready

1. Open Admin and review the COF Production Readiness panel.
2. Generate the Internal Review Pack to see all blockers.
3. Resolve source URL validation, review-gate, document/question review and portal route blockers.
4. Configure the COF Monday report send digest profile with recipients.
5. Re-run the Final Customer Pack.
6. Send or store the final pack only when it says `Ready for weekly send`.

## Current Azure Operating Model

This phase stays on the existing Azure Container Apps, SQLite snapshot and Azure Files model to control cost. No new Azure resources, tenant migration, PostgreSQL deployment, Key Vault, storage account, scheduler or networking layer is required for these application changes.

The future production-infrastructure phase remains deferred and should cover the new tenant, PostgreSQL, immutable audit storage, stronger networking/security, formal backup/restore, monitoring and alerting.
