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

## Retrieval Mode Patterns

Use the portal instance **Retrieval mode** field to show how information can be gathered.

| Mode | Use When | Credential Handling |
| --- | --- | --- |
| `account_required_manual` | The portal requires a named supplier account, browser login or MFA. | Store only owner/reference notes in DIP. Keep credentials in the approved corporate password/identity process. |
| `public_api_no_key` | The source offers official/public read-only data, such as Contracts Finder or Find a Tender open data. | No personal account or key stored. Use source URLs and connector guardrails. |
| `api_key_header` | The provider grants a read-only API key sent in a request header. | Store only the environment variable or Key Vault secret name in DIP. |
| `api_key_query` | The provider grants a read-only API key sent as a query parameter. | Store only the environment variable or Key Vault secret name in DIP. |
| `approved_api` | The provider grants an approved machine-to-machine retrieval route. | Store only integration reference details; secrets stay outside DIP. |
| `not_available` | No retrieval route exists yet. | Create a human task to confirm registration/access. |

## Personal Account Portal Example

National Highways uses a Jaggaer eSourcing portal. Where a portal needs personal or supplier-account login:

1. Add a portal instance, for example `National Highways - Jaggaer eSourcing`.
2. Set `Retrieval mode` to `account_required_manual`.
3. Put only a safe account reference in the account field, for example `Bid team portal owner - credentials held outside DIP`.
4. Set the access status to `registration_required`, `access_requested`, `pending_mfa_owner`, `registered` or `active`.
5. Create a retrieval task for a named owner.
6. The owner logs in outside DIP and retrieves permitted documents.
7. The owner pastes permitted text into opportunity documents for KRA extraction and human review.

## API Key Or Public API Example

For official/public APIs such as Contracts Finder or Find a Tender open data:

1. Create a portal/source instance for the official API.
2. Set `Retrieval mode` to `public_api_no_key` where no credential is needed.
3. Create a read-only connector with `Integration method` set to `public_api_no_key`.
4. Keep the connector disabled until it has been manually tested.
5. Enable only after the retrieval output and review process are accepted.

For provider-approved API keys:

1. Store the actual API key outside DIP, for example in local `.env` for local development or Azure Key Vault for hosted environments.
2. In DIP, store only the environment variable or Key Vault secret name.
3. Set connector method/auth to `api_key_header` or `api_key_query`.
4. Document the provider approval and allowed operations in connector notes.
5. Never enable write-capable actions, expressions of interest, submissions or customer messages in the MVP.

## Guardrails

- No portal passwords are stored.
- No automated portal login is performed.
- No automated customer contact or portal submission is performed.
- Retrieval tasks are work instructions for humans.
- Extracted requirements remain review-required.
- API keys are not stored in SQLite or shown in reports.
- Automated retrieval is read-only and must use approved endpoints only.

## Why It Matters

Many important bid requirements sit behind buyer-side portals rather than public notices. The portal workbench makes those portals visible, measurable and action-led so teams can avoid last-minute access issues and turn document content into reusable intelligence.
