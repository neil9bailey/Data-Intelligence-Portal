# Source And Portal Catalogue

Checked on 2026-05-17 against official/public source routes where available.

## Official Notice Sources

| Source | Coverage | Format | MVP Status |
| --- | --- | --- | --- |
| Find a Tender | UK high-value public procurement notices | OCDS/API where available | Priority connector |
| Contracts Finder | UK lower-value, future, live, early engagement and award notices | API/OCDS/data export routes | Priority connector |
| Public Contracts Scotland | Scottish public-sector procurement notices | OCDS API | Configurable connector |
| Sell2Wales | Welsh public-sector procurement notices | Web/bulk/OCDS route to validate | Configurable source |
| TED / eForms | EU and Ireland horizon scanning where relevant | eForms/TED developer tooling | Future connector |

## Commercial Backup Sources

Commercial aggregators such as Tenders Direct can be configured only if the organisation has a licence and approval. They should be treated as backup or enrichment sources, not the primary trusted source of record.

## Buyer Portal Platforms

| Platform | Role | MVP Handling |
| --- | --- | --- |
| ProContract | Buyer-side portal family | Manual portal instance and retrieval task tracking |
| In-Tend | Buyer-side portal family | Manual portal instance and retrieval task tracking |
| Jaggaer | Buyer-side portal family | Manual portal instance and retrieval task tracking |
| Delta eSourcing | Buyer-side portal family | Manual portal instance and retrieval task tracking |

## Guardrails

- No credentials in the MVP.
- No automated portal login in the MVP.
- No automated expression of interest or submission.
- Human approval required before any future portal action.
- Extracted document intelligence remains pending until reviewed.

## Official Reference Links

- [GOV.UK Contracts Finder](https://www.gov.uk/contracts-finder)
- [GOV.UK public-sector procurement guidance](https://www.gov.uk/guidance/public-sector-procurement/)
- [Find a Tender](https://www.find-tender.service.gov.uk/Search)
- [Find a Tender developer documentation](https://www.find-tender.service.gov.uk/Developer/Documentation)
- [Contracts Finder API documentation](https://www.contractsfinder.service.gov.uk/apidocumentation)
- [Public Contracts Scotland API](https://api.publiccontractsscotland.gov.uk/)
- [TED eForms](https://ted.europa.eu/en/simap/eforms)
