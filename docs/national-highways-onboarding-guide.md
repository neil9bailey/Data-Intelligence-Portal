# National Highways Onboarding Guide

Use this runbook to configure National Highways as the first live customer in the Data Intelligence Portal.

Checked date: 17 May 2026.

This is an operational setup guide. It does not store portal credentials and does not automate portal login, portal submission, customer contact or bid decisions.

## 1. Source Facts To Use

Use these facts as the baseline customer record:

| Fact | Value |
| --- | --- |
| Legal name | National Highways Limited |
| Company number | 09346363 |
| Registered office | Three Snowhill, Snow Hill Queensway, Birmingham, England, B4 6GA |
| Operational contact address | National Traffic Operations Centre, 3 Ridgeway, Quinton Business Park, Birmingham, B32 1AF |
| General email | info@nationalhighways.co.uk |
| General enquiries | 0300 123 5000 |
| Customer type | Government-owned arm's-length company / strategic highways company |
| Core role | Manages and improves England's motorways and major A-roads, known as the Strategic Road Network |
| Shareholder / sponsor | Department for Transport |
| Oversight bodies | Office of Rail and Road; Transport Focus |
| Funding context | Road Investment Strategy / Road Investment Periods. Road Period 2 ended 31 March 2025. Road Period 3 was deferred until April 2026, with an interim 2025-26 settlement. |
| Main supplier portal identified | National Highways CCFT e-Sourcing Portal on Jaggaer |
| Supplier portal URL | https://nationalhighways.ukp.app.jaggaer.com/ |
| Portal access note | Suppliers need a Superuser account and two-factor authentication for the CCFT platform. |

## 2. Add The Customer

Open:

```text
https://dip.vendorlogic.io/customers
```

Use these values in **Add Customer**:

| Field | Value To Enter |
| --- | --- |
| Name | National Highways |
| Business unit | Highways if available. If the dropdown is empty, leave Not linked and add Highways in Strategic notes. |
| Region | England / UK |
| Sector | Public sector transport |
| Domain | highways; strategic road network; roadside technology; operational technology |
| Customer type | Government-owned arm's-length company / strategic highways company |
| Aliases | National Highways; National Highways Limited; Highways England; NH; HE |
| Buying entities | National Highways Limited; National Highways CCFT; Department for Transport sponsor context; regional and programme teams to be added when known |
| Strategic notes | National Highways manages and improves England's motorways and major A-roads. It is a government-owned arm's-length company and strategic highways company. Key intelligence themes: Strategic Road Network, Road Investment Strategy, safety, reliable journeys, asset management, roadside technology, operational resilience, cyber security, digital continuity, supplier information management, 24/7 network operations, traffic management, service continuity, environment and carbon reduction. |

After saving, confirm it appears in **Tracked Customers**.

## 3. Add The Buyer Portal Instance

Open:

```text
https://dip.vendorlogic.io/portals
```

Under **Add Portal Instance**, use:

| Field | Value To Enter |
| --- | --- |
| Portal instance name | National Highways - CCFT Jaggaer eSourcing |
| Platform family | Jaggaer |
| Access status | Choose one: `registration_required` if not yet registered; `pending_mfa_owner` if 2FA/Superuser ownership is not agreed; `registered` if supplier registration is done; `active` if the team can access and retrieve documents today. |
| Customer | National Highways |
| Business unit | Highways if available |
| Portal URL | https://nationalhighways.ukp.app.jaggaer.com/ |
| Operational notes | National Highways CCFT e-Sourcing Portal. Supplier registration is required. Maintain an active Superuser account. 2FA is required, typically using an authenticator app. Do not store credentials in this MVP. Record the internal account owner and retrieval owner here. Use this portal for manual document retrieval tasks linked to National Highways opportunities. |

Save the portal instance.

Expected readiness result:

- If `active` or `registered` and URL/customer/platform are present, the portal should show as ready.
- If `registration_required`, `pending_mfa_owner`, `blocked`, `expired` or `unknown`, the portal should show as needing action.

## 4. Add Useful Source Catalogue Entries

The default source catalogue should already include public procurement sources. Add these National Highways-specific source records so KRA has customer-focused pages to check.

Open:

```text
https://dip.vendorlogic.io/sources
```

### Source A: National Highways Supplier Page

| Field | Value To Enter |
| --- | --- |
| Name | National Highways supplier pages |
| Query URL | https://nationalhighways.co.uk/suppliers/ |
| Base URL | https://nationalhighways.co.uk |
| Type | web_page |
| Coverage | National Highways supplier guidance, supply chain themes, supplier-facing updates and portal references |
| Notes | Approved public website source. Use for supplier guidance, procurement themes and customer operating context. No portal login. |

### Source B: National Highways Becoming A Supplier

| Field | Value To Enter |
| --- | --- |
| Name | National Highways becoming a supplier |
| Query URL | https://nationalhighways.co.uk/suppliers/becoming-a-supplier/ |
| Base URL | https://nationalhighways.co.uk |
| Type | web_page |
| Coverage | Supplier onboarding, expectations, social enterprise DPS, standards and supplier requirements |
| Notes | Useful for account intelligence, supplier readiness and portal operating context. |

### Source C: National Highways Information Management System

| Field | Value To Enter |
| --- | --- |
| Name | National Highways information management system |
| Query URL | https://nationalhighways.co.uk/ims/ |
| Base URL | https://nationalhighways.co.uk |
| Type | web_page |
| Coverage | Supplier information governance, data handling, information security and digital continuity requirements |
| Notes | Important for digital, cyber, service management, operational technology and document governance opportunities. |

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

## 5. Run KRA For National Highways

Open:

```text
https://dip.vendorlogic.io/kra
```

Run three initial KRA checks.

### KRA Run 1: Official Source Scout

| Field | Value |
| --- | --- |
| Agent | Official Source Scout |
| Source | All active sources, or Find a Tender - National Highways |
| Customer | National Highways |
| Research query | National Highways highways operational technology roadside technology cyber resilience asset management service management SCADA network communications |

### KRA Run 2: Customer Memory Curator

| Field | Value |
| --- | --- |
| Agent | Customer Memory Curator |
| Source | National Highways supplier pages |
| Customer | National Highways |
| Research query | National Highways supplier requirements strategic road network Road Investment Strategy information security digital continuity supplier expectations |

### KRA Run 3: Portal Document Scout

| Field | Value |
| --- | --- |
| Agent | Portal Document Scout |
| Source | National Highways becoming a supplier |
| Customer | National Highways |
| Research query | National Highways CCFT Jaggaer eSourcing portal supplier registration Superuser two factor authentication ITT tender documents |

Review the KRA findings. Anything extracted remains review-required.

## 6. Create Portal Retrieval Tasks

Open:

```text
https://dip.vendorlogic.io/portals
```

Find **National Highways - CCFT Jaggaer eSourcing** and open **Create retrieval task**.

Use these starter values:

| Field | Value |
| --- | --- |
| Task | Confirm National Highways CCFT portal access and retrieve current opportunity pack |
| Opportunity | Select the National Highways opportunity if one exists. If not, leave Not linked yet. |
| Status | requested |
| Owner | Name or team responsible, for example Bid team / Commercial owner / Portal superuser |
| Due date | Use the bid or internal review deadline |
| Notes | Confirm supplier account registration, Superuser ownership and 2FA owner. Retrieve permitted ITT documents from the National Highways CCFT Jaggaer portal. Do not store credentials in the MVP. Paste permitted requirement or quality-question text into the opportunity document extractor. |

## 7. Add Opportunity Document Evidence

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
| Platform | Jaggaer / National Highways CCFT |
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

## 8. Example National Highways Opportunity Placeholder

If you need a placeholder for manual discussion before KRA creates or imports a live notice, use this wording in notes and tasks:

| Field | Value |
| --- | --- |
| Opportunity title | National Highways roadside technology and operational resilience opportunity |
| Buyer | National Highways |
| Stage | Watch / early intelligence / portal document retrieval pending |
| Themes | roadside technology; operational technology; SCADA; cyber resilience; network communications; asset management; service management; safety critical operations |
| Source reference | Find a Tender / Contracts Finder / National Highways CCFT portal |
| Portal | National Highways - CCFT Jaggaer eSourcing |
| Immediate action | Confirm portal access, identify ITT reference, retrieve permitted documents, paste quality questions for extraction |

Do not treat a placeholder as a live bid record unless a real notice or portal opportunity has been confirmed.

## 9. Ongoing Weekly Operating Rhythm

1. Open **Sources** and run checks for National Highways-specific sources.
2. Open **KRA** and run the three National Highways queries.
3. Open **Portals** and update access status for the CCFT Jaggaer portal.
4. Review open portal retrieval tasks.
5. Open **Opportunities** and inspect new or updated National Highways items.
6. Paste permitted document text into **Documents / Extract**.
7. Review **Requirements** and mark anything needing human validation.
8. Generate **Reports** for bid, account or leadership review.

## 10. Source Links

- National Highways about us: https://nationalhighways.co.uk/about-us/
- National Highways corporate governance: https://nationalhighways.co.uk/about-us/corporate-governance/
- National Highways funding and Road Investment Strategy context: https://nationalhighways.co.uk/about-us/how-we-are-funded/
- National Highways suppliers: https://nationalhighways.co.uk/suppliers/
- National Highways becoming a supplier: https://nationalhighways.co.uk/suppliers/becoming-a-supplier/
- National Highways information management system: https://nationalhighways.co.uk/ims/
- Companies House: https://find-and-update.company-information.service.gov.uk/company/09346363
- National Highways CCFT / Jaggaer portal reference in public notice attachment: https://www.contractsfinder.service.gov.uk/Notice/Attachment/5024e4da-678c-4e86-bb2b-37366fb99507
- Example Find a Tender National Highways notice showing CCFT portal instructions: https://www.find-tender.service.gov.uk/Notice/042492-2025/PDF
