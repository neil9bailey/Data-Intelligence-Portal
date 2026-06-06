# Intelligence Value Layer

The COF value layer turns raw opportunity records into reusable, user-facing operating signals. It does not make bid, legal, procurement or compliance decisions.

## What It Adds

For each visible opportunity, the application can now derive:

- confidence band: strong, good, review, weak or unscored
- source traceability: official source traced, source reference pending, missing or needs validation
- deadline urgency: closing soon, deadline passed, no deadline or normal timing
- stage label: readable status/procurement-stage summary
- next action: review, source validation, document retrieval, question extraction or monitoring
- evidence summary: linked documents, quality questions and client interest signals

The Opportunity Inbox, Client Feed and COF weekly reports use these same signals so users see consistent guidance across the product.

## Portfolio Insights

The dashboard and reports also show portfolio-level insights:

- live opportunity volume
- near-term deadline attention
- source traceability workload
- review workload
- high-confidence match count

These are operating cues for human review and account action. They are not automated bid/no-bid decisions.

## Guardrails

The value layer:

- does not store portal passwords
- does not automate portal login
- does not automate customer contact
- does not automate expression of interest or bid submission
- keeps human review caveats visible
- reuses existing source, archive, access-scope and report controls

## Verification

Covered by:

- `tests/test_intelligence_value.py`
- COF route tests for Opportunity Inbox and Client Feed rendering
- COF report tests for value-summary and export output

Docker/Python 3.12 remains the preferred runtime verification path. Local Python versions outside the supported runtime may show dependency or framework deprecation differences.
