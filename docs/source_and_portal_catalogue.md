# Source And Portal Catalogue

Checked on 2026-05-18 against official/public source routes where available.

## Official Notice Sources

| Source | Coverage | Format | MVP Status |
| --- | --- | --- | --- |
| Find a Tender | UK high-value public procurement notices | OCDS/API where available | Priority connector |
| Contracts Finder | UK lower-value, future, live, early engagement and award notices | API/OCDS/data export routes | Priority connector |
| Public Contracts Scotland | Scottish public-sector procurement notices | OCDS API | Configurable connector |
| Sell2Wales | Welsh public-sector procurement notices | Web/bulk/OCDS route to validate | Configurable source |
| TED / eForms | EU and Ireland horizon scanning where relevant | eForms/TED developer tooling | Future connector |

These five public sources are now preconfigured as the live-demo source-to-inbox baseline. Buyer portals that require supplier accounts remain tracked as portal tasks unless the provider exposes an approved read-only public/API route.

## Commercial Backup Sources

Commercial aggregators such as Tenders Direct can be configured only if the organisation has a licence and approval. They should be treated as backup or enrichment sources, not the primary trusted source of record.

## Buyer Portal Platforms

| Platform | Role | MVP Handling |
| --- | --- | --- |
| ProContract | Buyer-side portal family | Account-required manual retrieval by default; approved API only if provider grants it |
| In-Tend | Buyer-side portal family | Account-required manual retrieval by default; approved API only if provider grants it |
| Jaggaer | Buyer-side portal family | Account-required manual retrieval by default; approved API only if provider grants it |
| Delta eSourcing | Buyer-side portal family | Account-required manual retrieval by default; approved API only if provider grants it |

## Retrieval Modes

| Mode | Meaning |
| --- | --- |
| `account_required_manual` | A named supplier account, browser login or MFA is required; use a human retrieval task. |
| `public_api_no_key` | Official/public read-only API, such as Contracts Finder or Find a Tender open data. |
| `api_key_header` | Provider-approved read-only API key sent in a header; store only the secret reference. |
| `api_key_query` | Provider-approved read-only API key sent as a query parameter; store only the secret reference. |
| `approved_api` | Provider-approved machine-to-machine route. |
| `not_available` | No confirmed retrieval route yet. |

## Guardrails

- No credentials in the MVP.
- No automated portal login in the MVP.
- No automated expression of interest or submission.
- Human approval required before any future portal action.
- Extracted document intelligence remains pending until reviewed.
- API keys and portal credentials are not stored in SQLite.
- Admin health checks surface source, portal and connector issues.

## Official Reference Links

- [GOV.UK Contracts Finder](https://www.gov.uk/contracts-finder)
- [GOV.UK public-sector procurement guidance](https://www.gov.uk/guidance/public-sector-procurement/)
- [Find a Tender](https://www.find-tender.service.gov.uk/Search)
- [Find a Tender developer documentation](https://www.find-tender.service.gov.uk/Developer/Documentation)
- [Contracts Finder API documentation](https://www.contractsfinder.service.gov.uk/apidocumentation)
- [Public Contracts Scotland API](https://api.publiccontractsscotland.gov.uk/)
- [Sell2Wales OCDS data access](https://www.sell2wales.gov.wales/helpandresources/ocds/dataaccessinfo)
- [TED eForms](https://ted.europa.eu/en/simap/eforms)
- [TED Search API documentation](https://docs.ted.europa.eu/api/latest/search.html)
