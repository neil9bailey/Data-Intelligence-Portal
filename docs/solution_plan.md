# Data Intelligence Portal - Solution Plan

## Product Intent

Data Intelligence Portal is a dedicated, general-purpose intelligence workspace for collecting, normalising and reviewing public-sector customer and procurement information. It is designed as its own product, with no specialist tax or claim-preparation workflow.

The platform is designed for bid, sales, account, strategy, service design, engineering and delivery teams who need a single view of customer demand, procurement activity, document requirements and emerging themes.

## Core Problem

Public-sector opportunity intelligence is fragmented:

- notices are spread across multiple official sources
- buyer documents often sit behind portal logins
- account knowledge lives in inboxes, Teams, spreadsheets and individual memory
- quality questions, weightings and clarifications are not consistently structured
- customer requirement themes are hard to compare across frameworks and accounts
- leadership reporting often requires manual consolidation

The result is duplicated effort, late bid awareness, missed requirements, weak account memory and slower strategic decision-making.

## Proposed Solution

Create a dedicated Data Intelligence Portal with two coordinated intelligence pipelines.

### 1. Official Notice Pipeline

Normalise public procurement notices from official/public sources into a single opportunity catalogue.

Initial configurable sources:

- Find a Tender
- Contracts Finder
- Public Contracts Scotland
- Sell2Wales
- TED / eForms where relevant
- Tenders Direct or similar commercial aggregator only if licensed and approved

The system should:

- track source configuration and connector health
- deduplicate opportunities by OCID, notice reference and content hash
- detect source/schema/content changes
- match notices to customers, aliases, sectors, business units, CPV codes and keywords
- record opportunity stage, deadline, value, buyer, source and relevance rationale

### 2. Buyer Portal Document Pipeline

Track buyer portal platforms and customer portal instances where ITT documents and supporting materials are accessed.

Initial portal families:

- ProContract
- In-Tend
- Jaggaer
- Delta eSourcing

The MVP should remain manual-assisted:

- record portal instance and account status
- create document retrieval tasks
- capture permitted document links, file paths, summaries and text excerpts
- extract quality questions, weightings, mandatory requirements and clarification themes
- route low-confidence extraction to human review

No portal credentials should be stored in the MVP.

## Main User Journeys

1. **Customer Intelligence Setup**
   Capture customers, sectors, business units, aliases, frameworks, buying entities, portal instances and strategic notes.

2. **Source Catalogue Setup**
   Configure official notice feeds, commercial backup sources, review frequencies, approved domains, data formats and connector status.

3. **Opportunity Catalogue**
   View all captured opportunities, matched customers, deadlines, values, stages, relevance scores and source-change signals.

4. **Portal And Document Intelligence**
   Track where ITT documents live, what needs retrieving, what has been reviewed and which quality questions or requirements were extracted.

5. **Requirement Knowledge Base**
   Consolidate recurring themes such as cyber, resilience, service management, legacy integration, cloud, data, asset management, operational technology, social value and commercial constraints.

6. **Reports And Briefings**
   Generate customer briefs, business-unit opportunity reports, requirement trend reports and source-health summaries.

## Guardrails

- Use official/public sources first.
- Keep source and portal configuration versioned.
- Require explicit human approval for any future authenticated portal automation.
- Do not store passwords or secrets in the MVP.
- Do not automate bid/no-bid, customer contact, portal submission or expression of interest in the MVP.
- Label AI-extracted requirements as review-required until accepted by a human.
- Maintain an audit trail of source checks, document captures, extraction decisions and report generation.

## Success Measures

- faster visibility of relevant public-sector opportunities
- reduced duplicated searching across teams
- clearer account and customer requirement memory
- better bid/no-bid preparation evidence
- earlier identification of document retrieval tasks
- consistent executive and business-unit reporting
- reusable knowledge base of customer needs and market signals
