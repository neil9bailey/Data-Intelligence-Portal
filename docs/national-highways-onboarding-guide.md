# National Highways Onboarding Guide

Use this runbook to configure National Highways as the first live customer in the Data Intelligence Portal, including the public source watchlist, National Highways Jaggaer portal access workflow, and an API-friendly official source connector example.

Checked date: 17 May 2026.

This is an operational setup guide. It does not store portal credentials and does not automate portal login, portal submission, customer contact or bid decisions. Retrieved or extracted information remains review-required until accepted by a human reviewer.

Fast path: open `/intelligence-packs`, preview **National Highways**, then apply the pack. DIP will create the core customer, Highways business unit, watch profile, public source monitors, Jaggaer portal record and disabled public API connector placeholder. Use the remaining sections of this guide to review and complete the human-confirmed fields.

## 1. Official Baseline Facts

Use these facts as the starting customer profile.

| Field | Value |
| --- | --- |
| Customer display name | National Highways |
| Legal name | National Highways Limited |
| Company number | 09346363 |
| Registered office | Three Snowhill, Snow Hill Queensway, Birmingham, England, B4 6GA |
| Operational contact address | National Traffic Operations Centre, 3 Ridgeway, Quinton Business Park, Birmingham, B32 1AF |
| General email | info@nationalhighways.co.uk |
| General enquiries | 0300 123 5000 |
| Customer type | Government-owned arm's-length company / strategic highways company |
| Sponsor context | Department for Transport |
| Oversight context | Office of Rail and Road; Transport Focus |
| Core operating role | Manages and improves England's motorways and major A-roads, known as the Strategic Road Network |
| Procurement model | Framework contracts, major schemes, maintenance arrangements and supplier/subsupplier opportunities |
| Main e-tendering route | National Highways eSourcing Portal on Jaggaer |
| National Highways Jaggaer URL | https://nationalhighways.ukp.app.jaggaer.com/ |
| Public notice sources | Find a Tender; Contracts Finder; National Highways supplier pages |
| Account model | Supplier registration, named user access and 2FA/MFA. No credentials stored in DIP. |

Official/public sources used for this guide are listed at the end.

## 2. Add Or Confirm Business Unit

Open:

```text
https://dip.vendorlogic.io/business-units
```

Create or confirm:

| Field | Value To Enter |
| --- | --- |
| Name | Highways |
| Parent business unit | Transport, if present |
| Description | National highways, strategic road network, roadside operational technology, traffic operations, maintenance, network communications, cyber resilience and asset management opportunities. |
| Active | Yes |

If you also want the broader transport structure:

| Field | Value To Enter |
| --- | --- |
| Top-level unit | Transport |
| Child units | Highways; Rail; SCADA; TfL |

## 3. Add The Customer

Open:

```text
https://dip.vendorlogic.io/customers
```

Use these values in **Add Customer**:

| Field | Value To Enter |
| --- | --- |
| Name | National Highways |
| Business unit | Highways |
| Region | England / UK |
| Sector | Public sector transport |
| Domain | highways; strategic road network; roadside technology; operational technology |
| Customer type | Government-owned arm's-length company / strategic highways company |
| Aliases | National Highways; National Highways Limited; Highways England; NH; HE |
| Buying entities | National Highways Limited; National Highways CCFT; Department for Transport sponsor context; regional and programme teams to be added when known |
| Strategic notes | National Highways manages and improves England's motorways and major A-roads. It is a government-owned arm's-length company and strategic highways company. Key intelligence themes: Strategic Road Network, Road Investment Strategy, safety, reliable journeys, asset management, roadside technology, operational resilience, cyber security, digital continuity, supplier information management, 24/7 network operations, traffic management, service continuity, environment and carbon reduction. |

After saving, confirm it appears in **Tracked Customers**.

## 4. Add Customer Watch Profile Notes

If the customer page exposes watch profile fields, use the following watch terms. If not, store these in the customer strategic notes until watch profiles are edited separately.

| Watch Area | Terms |
| --- | --- |
| Buyer aliases | National Highways; National Highways Limited; Highways England; NH; HE |
| High-value keywords | strategic road network; roadside technology; operational technology; SCADA; traffic operations; network communications; cyber resilience; asset management; service management; maintenance and response; tunnels; traffic management; incident management; digital roads |
| Capability keywords | NOC; SOC; OT cyber; IoT; telemetry; data platform; cloud; service desk; field force; mobile workforce; safety critical; high availability; integration; legacy systems; real-time data |
| CPV themes | IT services; communications equipment; repair and maintenance; software; data services; security services; engineering services |
| Regions | England; Midlands; South East; North West; North East; South West; East; Yorkshire |
| Review owner | Bid intelligence owner or account lead |

## 5. Add The National Highways Jaggaer Portal

This is the main personal/supplier-account portal example. It is for account-assisted retrieval, not automated login.

Open:

```text
https://dip.vendorlogic.io/portals
```

Under **Add Portal Instance**, use:

| Field | Value To Enter |
| --- | --- |
| Portal instance name | National Highways - Jaggaer eSourcing |
| Platform family | Jaggaer |
| Access status | `registration_required` if not yet registered; `access_requested` if registration/access has been requested; `pending_mfa_owner` if 2FA ownership is not agreed; `registered` if supplier registration is complete; `active` if the team can access and retrieve documents today |
| Customer | National Highways |
| Business unit | Highways |
| Portal URL | https://nationalhighways.ukp.app.jaggaer.com/ |
| Account reference | Internal owner/reference only, for example: `Bid team supplier account owner - credentials held in corporate password manager, not in DIP` |
| Retrieval mode | `account_required_manual` |
| Operational notes | National Highways eSourcing Portal on Jaggaer. Supplier registration is required. Named users need 2FA/MFA. Use only authorised personal/supplier accounts. Do not store usernames, passwords, MFA seeds or recovery codes in DIP. Record the internal account owner, backup owner, registration status, and document retrieval owner. |

Expected readiness result:

- `active` or `registered`, with customer/platform/URL present, should show as ready or nearly ready.
- `registration_required`, `access_requested`, `pending_mfa_owner`, `blocked`, `expired` or `unknown` should show as needing action.

## 6. Personal Account Portal Workflow

Use this when a buyer portal requires a named user login, personal supplier account or MFA.

| Step | Action | DIP Record |
| --- | --- | --- |
| 1 | Confirm whether the organisation already has a National Highways Jaggaer supplier account. | Portal access status |
| 2 | Identify primary and backup portal owners. | Portal account reference and notes |
| 3 | Register or request access outside DIP. | Portal status `access_requested` |
| 4 | Complete MFA setup outside DIP using the approved corporate device/process. | Portal status `pending_mfa_owner` then `registered` |
| 5 | Human user logs in and retrieves permitted tender documents. | Document retrieval task |
| 6 | User records document title/reference and pastes permitted extract text. | Opportunity documents |
| 7 | KRA extracts requirement themes and quality questions. | Requirements and review queue |
| 8 | Human reviewer approves or rejects extracted intelligence. | Review queue and reports |

Never store:

- portal passwords
- MFA secret keys
- recovery codes
- personal mobile numbers unless the organisation has approved that record
- customer contact messages that have not been authorised for sharing

Safe to store:

- internal owner/team
- portal URL
- registration status
- retrieval task notes
- document title/reference
- permitted requirement text
- non-sensitive account reference, such as "Highways bid team portal owner"

## 7. Add Official/Public Source Catalogue Entries

The default source catalogue should already include public procurement sources. Add these National Highways-specific records so KRA has customer-focused pages to check.

Open:

```text
https://dip.vendorlogic.io/admin
```

Then choose **Sources**.

### Source A: National Highways Supplier Pages

| Field | Value To Enter |
| --- | --- |
| Name | National Highways supplier pages |
| Query URL | https://nationalhighways.co.uk/suppliers/ |
| Base URL | https://nationalhighways.co.uk |
| Type | web_page |
| Coverage | National Highways supplier guidance, supply chain themes, supplier-facing updates and portal references |
| Notes | Approved public website source. Use for supplier guidance, procurement themes and customer operating context. No portal login. |

### Source B: National Highways New And Prospective Suppliers

| Field | Value To Enter |
| --- | --- |
| Name | National Highways new and prospective suppliers |
| Query URL | https://nationalhighways.co.uk/suppliers/becoming-a-supplier/guide-for-new-and-prospective-suppliers/ |
| Base URL | https://nationalhighways.co.uk |
| Type | web_page |
| Coverage | Supplier onboarding, eSourcing portal reference, expectations, standards and procurement routes |
| Notes | Official National Highways supplier guidance. Useful for account intelligence, supplier readiness and portal operating context. |

### Source C: National Highways Social Enterprise DPS

| Field | Value To Enter |
| --- | --- |
| Name | National Highways social enterprise DPS |
| Query URL | https://nationalhighways.co.uk/suppliers/becoming-a-supplier/social-enterprises/ |
| Base URL | https://nationalhighways.co.uk |
| Type | web_page |
| Coverage | DPS joining process, Jaggaer references, supplier categories and social value themes |
| Notes | Official National Highways page naming Jaggaer as the eSourcing portal for the Social Enterprise DPS. |

### Source D: Find a Tender Search

| Field | Value To Enter |
| --- | --- |
| Name | Find a Tender - National Highways |
| Query URL | https://www.find-tender.service.gov.uk/Search/Results?Keywords=National%20Highways |
| Base URL | https://www.find-tender.service.gov.uk |
| Type | web_page |
| Coverage | UK public procurement notices mentioning National Highways |
| Notes | Official public notice source. Use alongside default Find a Tender source checks. |

### Source E: Contracts Finder Search

| Field | Value To Enter |
| --- | --- |
| Name | Contracts Finder - National Highways |
| Query URL | https://www.contractsfinder.service.gov.uk/Search/Results?Keywords=National%20Highways |
| Base URL | https://www.contractsfinder.service.gov.uk |
| Type | web_page |
| Coverage | UK lower-value opportunities, awards and notices mentioning National Highways |
| Notes | Official public notice source. Useful for earlier signals and award history. |

For each source, click **Check** after saving. Review the source-change snapshot result.

## 8. API-Friendly Portal/Source Example

Use this where you want a connector that can retrieve information without using a personal portal login.

### Option 1: Contracts Finder OCDS Search API

Contracts Finder provides official API endpoints for published notice retrieval. This is the safest first API connector because it can retrieve public notice data and does not require portal login for public search use.

Add a portal instance:

| Field | Value To Enter |
| --- | --- |
| Portal instance name | Contracts Finder - National Highways API |
| Platform family | Other, or create a platform family called Contracts Finder API |
| Access status | active |
| Customer | National Highways |
| Business unit | Highways |
| Portal URL | https://www.contractsfinder.service.gov.uk/ |
| Account reference | Public official API / no personal portal account used for retrieval |
| Retrieval mode | `public_api_no_key` |
| Operational notes | Official public Contracts Finder notice retrieval. Use only for read-only search/retrieval. Do not use publishing, draft or authenticated buyer endpoints unless separately authorised. |

Add a retrieval connector:

| Field | Value To Enter |
| --- | --- |
| Connector name | Contracts Finder - National Highways public notices |
| Portal instance | Contracts Finder - National Highways API |
| Default opportunity | Leave blank initially, or link to a confirmed opportunity |
| Integration method | `public_api_no_key` |
| Auth type | `none` |
| Endpoint URL | https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search?publishedFrom=2026-01-01T00:00:00&publishedTo=2026-12-31T23:59:59&stages=planning,tender,award&limit=50 |
| Enabled | No until tested, then Yes |
| Allowed operations | retrieve_metadata; retrieve_documents; detect_changes |
| Notes | Public read-only source. Filter or post-process for buyer names containing National Highways, National Highways Limited or Highways England. |

Suggested first test:

1. Save the connector disabled.
2. Run it manually from **Portals** after confirming the endpoint is reachable.
3. Check the retrieval run.
4. Review any created KRA findings or opportunity documents.
5. Enable it only after the result format and review process are accepted.

### Option 2: Find a Tender OCDS API

Find a Tender has official open data outputs, including OCDS JSON. This is suitable for read-only notice intelligence.

Add a retrieval connector:

| Field | Value To Enter |
| --- | --- |
| Connector name | Find a Tender - National Highways open data |
| Portal instance | Create or select Find a Tender - National Highways |
| Integration method | `public_api_no_key` |
| Auth type | `none` |
| Endpoint URL | https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages |
| Enabled | No until tested |
| Allowed operations | retrieve_metadata; detect_changes |
| Notes | Official open notice data. Use read-only retrieval only. Filter in the review process for National Highways buyer/party names and relevant CPV/key terms. |

### Option 3: API Key Connector Where A Provider Grants Access

Use this pattern only if a portal provider or buyer grants a documented API for supplier-side read-only information retrieval.

| Field | Value To Enter |
| --- | --- |
| Portal instance name | [Provider] - [Customer] approved API |
| Access status | active |
| Account reference | API approval reference or integration owner, not the key value |
| Retrieval mode | `api_key_header` or `api_key_query` |
| Connector integration method | `api_key_header` or `api_key_query` |
| Auth type | `api_key_header` or `api_key_query` |
| Endpoint URL | Provider-approved read-only endpoint |
| API key secret environment variable | Example: `NATIONAL_HIGHWAYS_PORTAL_API_KEY` |
| Header name | Provider value, for example `X-API-Key` |
| Enabled | No until tested and approved |
| Notes | Store the actual secret outside DIP, for example local `.env` for local testing or Azure Key Vault mapping for hosted deployment. DIP stores only the environment variable or secret name. |

Do not use a personal account to bypass portal terms or MFA. If the provider only supports browser login, use the manual retrieval task workflow.

## 9. Run KRA For National Highways

Open:

```text
https://dip.vendorlogic.io/admin
```

Then choose **Run KRA**.

Run these initial checks.

### KRA Run 1: Official Source Scout

| Field | Value |
| --- | --- |
| Agent | Official Source Scout |
| Source | Find a Tender - National Highways, Contracts Finder - National Highways, or all active sources |
| Customer | National Highways |
| Research query | National Highways highways operational technology roadside technology cyber resilience asset management service management SCADA network communications maintenance response framework |

### KRA Run 2: Customer Memory Curator

| Field | Value |
| --- | --- |
| Agent | Customer Memory Curator |
| Source | National Highways new and prospective suppliers |
| Customer | National Highways |
| Research query | National Highways supplier requirements strategic road network Road Investment Strategy information security digital continuity supplier expectations framework procurement |

### KRA Run 3: Portal Document Scout

| Field | Value |
| --- | --- |
| Agent | Portal Document Scout |
| Source | National Highways social enterprise DPS or supplier pages |
| Customer | National Highways |
| Research query | National Highways Jaggaer eSourcing portal supplier registration two factor authentication PQQ ITT tender documents |

Review the KRA findings. Anything extracted remains review-required.

## 10. Create Portal Retrieval Tasks

Open:

```text
https://dip.vendorlogic.io/portals
```

Find **National Highways - Jaggaer eSourcing** and open **Create retrieval task**.

Use these starter values:

| Field | Value |
| --- | --- |
| Task | Confirm National Highways Jaggaer portal access and retrieve current opportunity pack |
| Opportunity | Select the National Highways opportunity if one exists. If not, leave Not linked yet. |
| Status | requested |
| Owner | Bid team / Commercial owner / authorised portal user |
| Due date | Use the bid or internal review deadline |
| Notes | Confirm supplier account registration, portal owner and MFA owner. Retrieve permitted ITT documents from the National Highways Jaggaer portal. Do not store credentials in DIP. Paste permitted requirement or quality-question text into the opportunity document extractor. |

## 11. Add Opportunity Document Evidence

When a National Highways opportunity exists, open:

```text
https://dip.vendorlogic.io/opportunities
```

Then click the **Docs** link for that opportunity.

In **Add Document / Extract**, use:

| Field | Value |
| --- | --- |
| Title | National Highways ITT extract - [opportunity / ITT reference] |
| Type | itt_extract |
| Status | review_required |
| URL or file path | Portal URL, document path or internal reference. Do not paste credentials. |
| Platform | Jaggaer / National Highways eSourcing |
| Summary | Briefly describe the document, lots, evaluation themes, submission deadline and key service areas. |
| Permitted text for extraction | Paste only permitted text from the ITT, quality questions, scope, requirements, technical schedules, service levels, information security requirements or clarification responses. |

Suggested permitted-text headings to capture:

- Scope of services
- Lots
- Evaluation criteria and weightings
- Quality questions
- Technical requirements
- Service management requirements
- Cyber / information security requirements
- Data / integration requirements
- Mobilisation and transition requirements
- SLA / KPI / performance requirements
- Clarifications and addenda

After saving, review extracted requirements and quality questions under **Requirements**.

## 12. Example National Highways Opportunity Placeholder

If you need a placeholder for manual discussion before KRA creates or imports a live notice, use this wording in notes and tasks:

| Field | Value |
| --- | --- |
| Opportunity title | National Highways roadside technology and operational resilience opportunity |
| Buyer | National Highways |
| Stage | Watch / early intelligence / portal document retrieval pending |
| Themes | roadside technology; operational technology; SCADA; cyber resilience; network communications; asset management; service management; safety critical operations |
| Source reference | Find a Tender / Contracts Finder / National Highways Jaggaer portal |
| Portal | National Highways - Jaggaer eSourcing |
| Immediate action | Confirm portal access, identify ITT reference, retrieve permitted documents, paste quality questions for extraction |

Do not treat a placeholder as a live bid record unless a real notice or portal opportunity has been confirmed.

## 13. Weekly Operating Rhythm

1. Open **Admin** and check local/remote health, source warnings and connector warnings.
2. Open **Sources** from Admin and run checks for National Highways-specific sources.
3. Open **Run KRA** from Admin and run the three National Highways queries.
4. Open **Portals** and update National Highways Jaggaer access status.
5. Review open portal retrieval tasks.
6. Run approved read-only API connectors, such as Contracts Finder or Find a Tender, where configured.
7. Open **Opportunities** and inspect new or updated National Highways items.
8. Paste permitted document text into **Documents / Extract**.
9. Review **Requirements** and mark anything needing human validation.
10. Generate **Reports** for bid, account or leadership review.

## 14. What Good Looks Like

| Area | Ready State |
| --- | --- |
| Customer | National Highways exists, linked to Highways BU, with aliases and strategic notes |
| Portal | Jaggaer portal exists with URL, account owner reference, status and retrieval mode |
| Sources | National Highways public pages, Find a Tender and Contracts Finder sources are active |
| KRA | Initial findings exist and have been reviewed |
| Opportunity | Real notices are linked to National Highways and Highways BU |
| Documents | ITT extracts are captured with source references and review status |
| Requirements | Quality questions and requirement themes are extracted and reviewed |
| Reports | Executive report generated with source, portal and requirement evidence |
| Audit | Customer, portal, document and report changes visible in audit log |

## 15. Source Links

- National Highways new/prospective supplier guide: https://nationalhighways.co.uk/suppliers/becoming-a-supplier/guide-for-new-and-prospective-suppliers/
- National Highways social enterprise DPS / Jaggaer reference: https://nationalhighways.co.uk/suppliers/becoming-a-supplier/social-enterprises/
- National Highways Jaggaer portal: https://nationalhighways.ukp.app.jaggaer.com/
- National Highways registration and 2FA guidance PDF: https://prod-upgrade.nationalhighways.co.uk/media/azddckju/low-carbon-footbridge-contest-how-to-register-guidance.pdf
- Example Find a Tender notice with National Highways Jaggaer instructions: https://www.find-tender.service.gov.uk/Notice/060400-2025
- Contracts Finder GOV.UK overview: https://www.gov.uk/contracts-finder
- Contracts Finder API documentation: https://www.contractsfinder.service.gov.uk/apidocumentation
- Find a Tender search: https://www.find-tender.service.gov.uk/Search
- Find a Tender data and API documentation: https://www.find-tender.service.gov.uk/Developer/Documentation
- Find a Tender REST API specification: https://www.find-tender.service.gov.uk/apidocumentation
- Companies House National Highways Limited: https://find-and-update.company-information.service.gov.uk/company/09346363
