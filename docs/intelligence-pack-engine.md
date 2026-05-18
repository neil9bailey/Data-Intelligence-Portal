# Intelligence Pack Engine

The Intelligence Pack engine reduces the amount of manual setup needed before DIP can track a public-sector customer.

Instead of asking an operator to paste a long onboarding guide into separate screens, `/intelligence-packs` can create a reviewed starting point from either:

- a preconfigured customer pack, currently including National Highways
- a public-sector organisation template plus the organisation name

## What A Pack Creates

When applied, a pack can create or update:

- business unit and optional parent business unit
- customer record
- customer watch profile with aliases, keywords, domains and CPV themes
- official/public procurement source monitors
- portal instance assumptions where known
- read-only connector placeholders where provider permissions allow
- KRA research prompts and missing-action guidance
- audit event showing the pack application

The operation is idempotent. Reapplying a pack should not duplicate customers, sources, portals or connectors.

## Preconfigured Pack

The National Highways pack creates the Highways business unit, National Highways customer memory, supplier-page monitors, Find a Tender and Contracts Finder monitors, Jaggaer portal tracking and a disabled Contracts Finder public notice connector.

This replaces most of the previous manual National Highways onboarding steps. Operators still need to confirm portal registration, account ownership, MFA ownership, live opportunity references and permitted document extracts.

## Any Public-Sector Organisation

For other public-sector organisations, an operator enters the organisation name and selects the closest template, such as:

- Central government department
- Arm's-length public body
- Local authority
- Mayoral or combined authority
- Transport authority
- NHS or health body
- Emergency services
- Education, college or university
- Housing association or social landlord
- Public corporation or public company
- Regulated infrastructure operator

DIP then generates a semi-configured pack with official public notice searches, watch terms, CPV themes and a missing-action list. This gives the KRA and review teams enough structure to begin source checks without requiring a complete customer runbook first.

## Guardrails

Packs do not:

- store portal usernames, passwords, MFA seeds or API key values
- automate portal login
- submit expressions of interest
- contact customers
- make bid/no-bid, legal, procurement or compliance decisions

Packs do:

- create public-source monitoring baselines
- identify missing private facts
- mark portal access as human-confirmed where required
- support review-ready report creation once findings are accepted

## Configuration

Runtime configuration lives in:

- `app/rules/public_sector_templates.yml`
- `app/rules/customer_packs.yml`

New templates can be added for industry or account types. New preconfigured packs can be added for strategic accounts once official/public facts have been reviewed.

## Operating Pattern

1. Open `/intelligence-packs`.
2. Preview a preconfigured pack or generate one from an organisation name.
3. Apply the pack.
4. Review created customers, watch terms, sources and portal assumptions.
5. Run KRA against the approved public sources.
6. Review findings and requirements before producing reports.

