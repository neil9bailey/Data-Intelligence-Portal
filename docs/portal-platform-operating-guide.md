# Portal Platform Operating Guide

The portal workbench turns buyer portals into an operational data source without storing credentials or automating restricted portal actions.

## Purpose

Use `/portals` to track where customer documents are published, whether access is ready, who owns manual retrieval, and what content has been captured for KRA extraction and reporting.

## Activation Workflow

1. Create or confirm the customer record.
2. Add one portal instance per buyer/customer portal.
3. Select the platform family: ProContract, In-Tend, Jaggaer or Delta eSourcing.
4. Add the portal URL and business unit.
5. Set the access status:
   - `registration_required`
   - `access_requested`
   - `pending_mfa_owner`
   - `registered`
   - `active`
   - `blocked`
   - `expired`
   - `unknown`
6. Record operational notes such as account owner, MFA owner, registration blockers and framework areas.
7. Create manual retrieval tasks when an opportunity requires portal documents.
8. A human retrieves documents outside the app.
9. Paste permitted text into the opportunity document screen so KRA can extract requirements and quality questions.
10. Review extracted content before using it in reports.

## Guardrails

- No portal passwords are stored.
- No automated portal login is performed.
- No automated customer contact or portal submission is performed.
- Retrieval tasks are work instructions for humans.
- Extracted requirements remain review-required.

## Why It Matters

Many important bid requirements sit behind buyer-side portals rather than public notices. The portal workbench makes those portals visible, measurable and action-led so teams can avoid last-minute access issues and turn document content into reusable intelligence.
