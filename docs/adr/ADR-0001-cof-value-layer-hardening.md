# ADR-0001: COF Value-Layer Hardening

**Epic ref:** EPIC-COF-INTEL-UX-OUTPUTS-001  
**Status:** Approved  
**Author role:** Enterprise Architect  
**EA reviewer:** Enterprise Architect  
**Date raised:** 2026-06-06  
**Date approved:** 2026-06-06

## Context

The Contracted Opportunity Finder has a working FastAPI/Jinja2/SQLModel baseline with source checks, KRA runs, opportunity matching, client actions, archive cleanup, reports and Azure live operation. The next improvement request targets UI clarity, report/output quality and intelligence value.

The affected areas are user-facing and design-altering because they change report structure, UI information architecture and intelligence explainability.

## Decision

Adopt a value-layer hardening approach that keeps the existing application architecture and infrastructure while introducing small, testable modules for:

- opportunity confidence, source freshness, urgency and next action signals
- portfolio-level operating insight summaries
- UI and report consumption of those signals

No new Azure resources, paid services, portal credential storage, portal login automation, customer-contact automation, expression-of-interest automation or bid-submission automation are approved by this ADR.

## Drift Assessment

- Deviates from baseline: yes, by adding a new application value layer and changing user-facing presentation.
- Still serves the epic: yes, it directly improves COF UI, outputs, reports and intelligence value.
- Impact on interfaces: internal Python module/API additions only; existing routes and data model remain compatible.

## Options Considered

| Option | Pros | Cons | Risk |
| --- | --- | --- | --- |
| Do nothing | No regression risk | Leaves reports and intelligence hard to evolve | Medium product credibility risk |
| Tactical UI/report edits | Fast visible improvements | Repeats previous string-level patching | Medium maintainability risk |
| Structured value-layer hardening | Improves UX and creates reusable intelligence signals | Requires careful incremental verification | Low/medium implementation risk |

Decision: structured value-layer hardening.

## Consequences

The app gains a clearer boundary between raw opportunity data and user-facing intelligence interpretation. Report and UI improvements can reuse the same signal calculations. Future work can split larger modules such as `app/reports.py` and `app/intelligence.py` with lower risk.

## Verification Plan

- Unit tests for opportunity value signals and portfolio summaries.
- Route tests for Opportunity Inbox and Client Feed rendering.
- Report tests for value summary content across Markdown, HTML and PDF exports.
- Existing `pytest` and `ruff` gates.
- Docker/Python 3.12 verification when Docker Desktop is available.
- Live end-user UAT before release approval: run COF Autopilot, inspect inbox/client feed, generate the weekly pack, download exports and confirm archive/source-health behaviour.

## ARB Checkpoint

- [x] EA has reviewed against the architecture baseline
- [x] Drift assessment complete and acceptable
- [x] Verification plan includes live end-user UAT
- [x] CTO consultation not required for this same-stack, no-new-resource change
- [x] Approved by human on 2026-06-06
