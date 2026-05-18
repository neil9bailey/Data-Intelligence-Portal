# Data Intelligence Portal Documentation

This folder is the single home for Data Intelligence Portal guides, operating notes and architecture documentation.

## Start Here

| Document | Purpose |
| --- | --- |
| [Executive buyer overview](executive_buyer_overview.md) | Walkthrough for MD, buyer or stakeholder conversations. |
| [Solution plan](solution_plan.md) | Product intent, user journeys and operating guardrails. |
| [Architecture blueprint](architecture_blueprint.md) | Current MVP architecture and production evolution. |
| [Benefits case](benefits_case.md) | Business value and user benefits. |
| [Implementation epics](implementation_epics.md) | Delivery status and future roadmap epics. |
| [Intelligence pack engine](intelligence-pack-engine.md) | How DIP preconfigures public-sector customers, watch profiles and source monitors. |

## Operating Guides

| Document | Purpose |
| --- | --- |
| [National Highways onboarding guide](national-highways-onboarding-guide.md) | Full setup guide for National Highways, Jaggaer and public API examples. |
| [End user operating process](end-user-operating-process.md) | Simple start-to-finish user guide from customer setup to report download and email. |
| [Portal platform operating guide](portal-platform-operating-guide.md) | Portal access, personal account, API-key and retrieval guardrails. |
| [Source and portal catalogue](source_and_portal_catalogue.md) | Supported official sources and buyer portal families. |

## Azure And Deployment

| Document | Purpose |
| --- | --- |
| [Azure deployment guide](azure-deployment-guide.md) | Full local-to-Azure deployment guide for live-test and customer environments. |
| [Azure live-test hosting notes](azure-live-test-hosting.md) | Current Vendorlogic live-test architecture and operational notes. |

## Visual Reference

| Document | Purpose |
| --- | --- |
| [UI mockup HTML](ui_mockups/data_intelligence_portal_mockup.html) | Early visual mockup kept for design reference only. |
| [UI mockup PNG](ui_mockups/data_intelligence_portal_mockup.png) | Static image of the early visual direction. |

## Documentation Rules

- Keep all product guides in `docs/`.
- Keep scripts in `scripts/` and infrastructure code in `infra/`.
- Do not commit generated Entra output files or customer parameter files from `infra/azure/generated/`.
- Keep customer-specific secrets out of the repo; use environment variables locally and Key Vault for hosted deployments.
- For live demos, KRA AI summaries can be enabled through Key Vault-backed `KRA_API_KEY` plus `KRA_LLM_PROVIDER=openai_direct`; generated intelligence still requires human review.
