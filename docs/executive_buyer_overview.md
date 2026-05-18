# Data Intelligence Portal

## Executive Overview for MD and Buyer Walkthrough

Data Intelligence Portal is an intelligence workspace for organisations that need to track customers, frameworks, procurement portals, public-sector opportunities, documents and emerging requirements in one place. It runs locally for MVP use and now has an Azure Container Apps live-test deployment path.

It is designed to help leadership, sales, bid, commercial, strategy and delivery teams move from scattered information to a structured, reviewable knowledge base that can be used to make better decisions, prepare stronger bids and understand customer direction earlier.

The platform includes a built-in **KRA Knowledge Research Agent**. KRA helps monitor approved public sources, identify changes, capture opportunity signals, extract requirement themes from documents and produce human-review-ready intelligence summaries.

The product is not a bid/no-bid decision engine, legal adviser, procurement adviser or customer-commitment tool. It is a decision-support and evidence-capture platform. Important conclusions remain subject to human review.

---

## The Problem It Solves

Many organisations lose valuable customer and opportunity intelligence because it is spread across:

- procurement portals
- framework notices
- emails and bid folders
- customer account notes
- document downloads
- spreadsheets
- service-line knowledge
- sales and delivery conversations
- individual subject matter experts

This creates several business issues:

- opportunities are discovered late
- frameworks are tracked inconsistently
- customer requirements are re-learned repeatedly
- bid teams start from a blank page
- delivery teams do not always see the early commercial context
- senior leaders lack a consolidated view of demand and risk
- knowledge leaves when individuals move roles

Data Intelligence Portal addresses this by creating a single customer, framework and requirement memory.

---

## What The Product Does

The platform provides a structured way to capture and analyse:

- customers and business units
- public-sector procurement sources
- procurement platforms and buyer portals
- opportunities and notices
- opportunity documents
- customer requirement themes
- quality questions and weighting signals
- document retrieval tasks
- KRA research runs
- source-change evidence
- audit events
- exportable intelligence reports

It gives users a practical opportunity inbox showing what is known, what changed, what needs review and where the next action should focus.

---

## How KRA Works

KRA stands for **Knowledge Research Agent**.

In the MVP, KRA operates as a controlled research agent. It uses configured rules and approved source lists rather than unrestricted browsing. In the live-demo Azure environment it can also use a Key Vault-backed OpenAI model to draft concise briefing summaries from the captured source data; those summaries remain review-required.

KRA can:

- check approved public procurement sources
- record when a source was last checked
- detect whether source content has changed
- store content hashes for comparison
- create reviewable source-change findings
- parse supported opportunity data
- create opportunity records
- extract requirement themes from opportunity and document text
- identify possible quality questions and weighting signals
- generate Markdown intelligence reports

The current MVP deliberately avoids unsafe automation:

- no portal passwords are stored
- no automated portal login
- no automated customer contact
- no automated bid submission
- no expression-of-interest automation
- no final bid/no-bid recommendation

This means the organisation gets useful intelligence automation without creating uncontrolled procurement or compliance risk.

---

## MCP Agent Concept

The solution has been designed around MCP-style agent roles and tool profiles.

The local MVP includes agent profiles such as:

- **Official Source Scout**: monitors public procurement and framework sources.
- **Customer Memory Curator**: links findings back to customer and business-unit context.
- **Portal Document Scout**: tracks document retrieval requirements without storing credentials.
- **Requirement Analyst**: extracts themes, service requirements and quality-question indicators.
- **Briefing Writer**: creates concise, review-ready summaries for leadership and bid teams.

This gives the platform a clean path to future agent orchestration, where approved MCP tools can be attached to specific jobs with clear guardrails.

---

## Typical Walkthrough For A Buyer

### 1. Opportunity Inbox

The buyer starts on the dashboard. This shows:

- number of customers being tracked
- active public sources
- opportunities captured
- document count
- requirement count
- KRA findings pending review
- source changes detected

The purpose is to give a senior user an immediate view of the intelligence estate.

### 1a. Admin Control Centre

Admin users can see local runtime health, remote Azure health, Entra status, database persistence status, source checks, portal connector health, email configuration, KRA runtime and audit links in one place.

### 2. Customers

Customers are added with business-unit, sector, domain, aliases, portal notes and strategic context.

This helps an organisation build a reusable account memory across sales, delivery and bid teams.

### 3. Sources

Approved sources are configured and tracked. These can include public procurement sources, framework sources and official publication routes.

The platform records checks and changes so the organisation can see what changed, when it changed and whether it requires review.

### 4. Portals

The portal catalogue records buyer portals and platform types. It does not store login credentials in the MVP.

This helps teams understand where documents are likely to be held and what manual retrieval actions are needed.

### 5. Opportunities

Opportunities can be captured from source checks or entered manually.

Each opportunity can be linked to:

- customer
- business unit
- source
- portal
- value
- deadline
- status
- extracted requirements
- documents

### 6. Documents

Users can register opportunity documents and paste permitted text extracts.

KRA analyses the text and creates requirement themes and quality-question indicators for review.

### 7. Requirements

Extracted requirements are grouped into useful themes such as:

- cyber security
- resilience
- asset management
- service management
- data and reporting
- integration
- sustainability
- safety and compliance
- mobilisation and transition

This helps the organisation see repeated customer demand across multiple frameworks and bids.

### 8. Reports

Users can generate Markdown intelligence reports that summarise:

- customer context
- opportunity pipeline
- source findings
- document signals
- requirement themes
- quality-question indicators
- recommended review areas

These reports can support leadership briefings, bid kick-offs, account planning and market reviews.

---

## Business Benefits

### Earlier Opportunity Awareness

The platform helps teams detect and structure new opportunities earlier by monitoring approved sources and creating a searchable opportunity catalogue.

### Stronger Bid Preparation

Bid teams can reuse captured requirements, quality-question themes, customer language and previous source intelligence rather than starting from scratch.

### Better Customer Understanding

Customer needs become visible across opportunities and documents. This helps account teams understand where demand is moving and what themes are recurring.

### Reduced Knowledge Loss

The organisation becomes less dependent on individual memory. Customer and framework knowledge is stored in a shared, auditable workspace.

### Better Executive Visibility

Senior leaders can see framework activity, requirement trends, portal workload and source-change signals in one place.

### More Consistent Governance

KRA findings are marked for human review, and the audit log records key activity. This supports a more controlled intelligence process.

### Improved Delivery Alignment

Delivery and service teams can see what customers are asking for before contracts are awarded. This can improve readiness, solution shaping and mobilisation planning.

### Reusable Market Intelligence

Over time, the platform becomes a knowledge base of market demand, public-sector priorities and customer-specific procurement patterns.

---

## Example Buyer Value Story

An organisation supporting public-sector infrastructure customers may monitor many procurement routes and customer portals.

Without a system, opportunity knowledge is usually fragmented. One team sees a notice, another downloads documents, another interprets requirements, and leadership receives a late summary.

With Data Intelligence Portal:

1. KRA checks approved public sources.
2. A new opportunity is captured.
3. The opportunity is linked to a customer and business unit.
4. Portal retrieval tasks are created for documents.
5. Document extracts are analysed.
6. Requirements and quality questions are structured.
7. High-confidence findings are agent-classified into the catalogue; lower-confidence records are flagged for override.
8. A summary report is generated for the bid or leadership team.

The result is a faster, clearer and more repeatable route from market signal to informed action.

---

## Why This Is Different From A Spreadsheet

A spreadsheet can list opportunities, but it does not naturally:

- monitor source changes
- maintain source-check evidence
- link customers, portals, documents and requirements
- extract requirement themes
- track human-review status
- create repeatable reports
- maintain an audit trail
- support agent-driven research workflows

Data Intelligence Portal is designed as a structured intelligence operating model, not just a register.

---

## Why This Is Different From A CRM

A CRM is strong for relationship management and sales pipeline ownership.

Data Intelligence Portal focuses on the knowledge layer around customers, frameworks, sources, portals, documents and requirements.

It can complement a CRM by creating better upstream intelligence that informs account plans, opportunity qualification and bid strategy.

---

## Why This Is Different From A Bid Tool

Bid tools usually help manage the production of a response.

Data Intelligence Portal helps before and around the bid:

- what sources are changing
- what customers are asking for
- what documents say
- what requirements repeat
- what themes need subject matter expert review
- what leadership should know before committing effort

It supports better bid readiness, not just bid writing.

---

## Governance And Guardrails

The MVP has been designed with sensible boundaries:

- human review remains required
- findings are not automatically treated as fact
- source checks are restricted to approved public sources
- portal credentials are not stored
- no submissions are automated
- reports are decision-support outputs
- audit events record key local changes

Future production use should add:

- Entra ID authentication
- role-based access control
- Azure Key Vault
- immutable audit storage
- backup and restore
- retention policies
- document classification
- integration governance
- security monitoring

---

## Azure/Vendorlogic Evolution

The local MVP now has a secure Azure live-test path using the Vendorlogic Azure environment. The current live-test uses Azure Container Apps, Microsoft Entra authentication, a dedicated ACR, a dedicated resource group, an existing Key Vault for DIP-specific secrets and Azure Files for SQLite snapshot/outbox persistence.

Current live-test architecture:

- Azure Container Apps
- Microsoft Entra ID authentication using `vendorlogic.io`
- Admin and Standard user groups
- Azure Key Vault secret reference for the Entra client secret
- Azure Files snapshot/outbox persistence
- dedicated Azure Container Registry
- managed logging through Log Analytics
- custom domain and managed certificate for `dip.vendorlogic.io`

Reusable customer deployment scripts can generate customer-specific parameter files and deployment commands. Production should still move to PostgreSQL, stronger RBAC, immutable audit export, backup/restore and formal connector governance.

---

## Buyer Conversation Points

Useful questions to ask an MD or buyer:

- How many public-sector customers or frameworks do you currently track?
- How many procurement portals does your team monitor?
- Where is framework intelligence stored today?
- How do you know when source information changes?
- How much bid preparation starts from previous knowledge versus a blank page?
- How are customer requirements reused across bids?
- How do leadership teams get a consolidated view of demand?
- What evidence do you have for why opportunities were pursued, parked or reviewed?
- How much time is spent manually searching portals and documents?
- Which business units would benefit most from a shared intelligence memory?

---

## Suggested Demonstration Flow

1. Open the dashboard and show the opportunity inbox.
2. Show the customer catalogue and explain the shared account memory.
3. Open Admin, then Sources, and explain approved public-source monitoring and health.
4. Open portals and explain manual-safe portal tracking.
5. Open opportunities and show how source signals become structured records.
6. Open documents and show how extracts become requirement intelligence.
7. Open requirements and quality questions.
8. Run or explain KRA research.
9. Generate a report.
10. Open audit to show traceability.

The key message: the platform turns fragmented public-sector opportunity information into structured, reusable and reviewable organisational intelligence.

---

## One-Minute Summary

Data Intelligence Portal gives organisations a single place to track public-sector customers, frameworks, procurement sources, portals, opportunities, documents and requirement themes.

The built-in KRA Knowledge Research Agent helps monitor approved sources, detect changes, capture opportunity signals and generate review-ready intelligence.

It improves early opportunity awareness, bid readiness, customer understanding, executive visibility and knowledge retention.

The MVP is deliberately safe, with no credential storage or automated submissions. It is ready for demonstration locally or in Azure live-test, and has a clear path to a fuller Entra ID-secured enterprise platform.
