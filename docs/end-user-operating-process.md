# End User Operating Process

This is the simple start-to-finish process for using the Data Intelligence Portal.

The portal is decision support only. All intelligence, extracted requirements and reports must be reviewed by a human before they are used for sales, bid, commercial, legal or procurement decisions.

## 1. Open The Portal

Open the portal:

- Local: `http://localhost:8091`
- Live test: `https://dip.vendorlogic.io`

Start from **Opportunity Inbox** to see the current source-to-inbox pipeline, matched opportunities, KRA findings and downloadable reports.

## 2. Standard User Flow

Standard users use the simplified front door:

1. Open **Opportunity Inbox**.
2. Review the latest matched opportunities and KRA signals.
3. Open **Client Feed** to view approved opportunities and record interest where enabled.
4. Open **Reports** to download the latest reviewed report packs.

Standard users do not configure sources, customers, portals, KRA or email delivery.

## 3. Admin: Run The Automated COF Cycle

Go to **Admin**.

Use **Run full cycle** to automate the normal operating rhythm:

1. Apply or update preconfigured customer packs.
2. Refresh active public sources and official feeds.
3. Run KRA checks.
4. Prepare opportunities and requirements for review.
5. Run approved read-only portal/source retrieval connectors.
6. Confirm only automated retrieval tasks where a completed run exists.
7. Generate a report.
8. Store the report export in the configured outbox/report folder.
9. Email or locally store the report email using the Admin email configuration.
10. Record the audit trail.

In Azure live-test, **Run full cycle** queues the work and returns to Admin immediately. Refresh Admin after a short pause to see whether the latest run is queued, running, completed or failed. This avoids the browser appearing frozen while source checks, KRA calls and report generation continue in the background worker.

The automation uses the broad official Find a Tender and Contracts Finder OCDS APIs for live matching, then filters by customer aliases and watch terms inside DIP. Customer-specific web search URLs are stored as reference links for human drill-through, but they are not used as high-frequency automation targets because public search pages can rate-limit automated bursts.

The automation does not log into buyer portals, submit expressions of interest, send portal messages or make bid/no-bid decisions.

## 4. Admin: Add Or Configure A Customer

Go to **Admin** then **Customer packs**.

Use one of these options:

- **Preconfigured pack**: choose an existing pack such as **National Highways**, then select **Preview** and **Apply**.
- **Discover any public-sector organisation**: enter the organisation name, choose the closest template, then select **Preview generated pack** and **Generate and apply**.

The pack creates the customer baseline, business unit, watch profile, public-source searches, portal assumptions and KRA prompts.

After applying the pack, review:

- **Customers**
- **Business Units**
- **Sources**
- **Portals**

Correct anything that is missing or wrong.

## 5. Admin: Confirm Portal Access

Go to **Admin** then **Portals / connectors**.

For each portal record, confirm:

- portal URL
- platform family
- access status
- internal portal owner
- retrieval mode
- operational notes

Do not store usernames, passwords, MFA secrets or recovery codes in the portal.

If the portal needs human login, create a retrieval task for the authorised portal owner.

## 6. Admin: Run Source And KRA Checks

Go to **Admin** or **KRA**.

Run checks against approved public sources and customer-specific reference sources.

Use KRA to:

- check official public sources
- detect source changes
- create findings
- structure opportunity intelligence
- extract requirement themes from permitted text

KRA findings stay review-required until a user reviews them.

For live-demo automation, KRA prioritises broad official OCDS APIs and review-required customer matching. Inactive `search_reference` records remain available for a human to open when validating a specific customer or notice.

## 7. Admin: Review Opportunities And Requirements

Go to **Review Queue**.

Review new or changed opportunities.

Choose the correct action:

- approve
- hold
- reject
- reassign

Then go to **Requirements** and review extracted requirement themes and quality questions.

Only approved and reviewed intelligence should be used in reports.

## 8. Admin: Add Document Extracts If Needed

Go to **Opportunities** and open **Docs** for the relevant opportunity.

Add permitted text from:

- ITT extracts
- quality questions
- scope sections
- service requirements
- technical schedules
- clarifications

Do not paste restricted information unless your organisation has permission to store and process it in DIP.

## 9. Admin: Create A Report

Go to **Reports**.

In **Create Report**:

1. Enter a report name.
2. Choose the report type:
   - **Executive intelligence pack** for MD, account, bid, buyer-facing or demo discussion.
   - **Admin automation run log** for source-check, connector, KRA runtime and data-quality traceability.
3. Select a customer, or leave as **All customers**.
4. Select a business unit, or leave as **All business units**.
5. Leave **Run enabled read-only retrieval connectors before report generation** ticked if you want the report to refresh approved connectors first.
6. Select **Generate report**.

The report opens after generation.

The executive pack applies a credibility gate before publishing the opportunity list. Buyer mismatches and very low-confidence records are moved to **Data Quality Exclusions** instead of being presented as current opportunity signals.

## 10. Review The Report

On the report page:

1. Read the report content.
2. Use **Edit report** if you need to update the title, scope, customer, business unit or report text.
3. Save any changes.

Treat the report as review-required until the responsible team has approved it. Use the admin run log to diagnose source failures, KRA runtime warnings, connector status and excluded records.

## 11. Download The Report

On the report detail page, use the download buttons at the top:

- **Download PDF**
- **Download Markdown**
- **Download HTML**
- **Download JSON**
- **Download Text**

The Reports list also provides the same download formats for each generated report.

Use PDF for client-style packs, Markdown or HTML for human review, JSON for system handoff, and Text for simple notes or email bodies.

## 12. Admin: Email The Report

On the report detail page, use **Send Report Email**.

Complete:

- recipients
- sender name
- sender email
- subject
- attachment format
- message

Select **Send / store email**.

In local safe mode, the portal stores an `.eml` file in the local outbox instead of sending externally. In SMTP mode, it sends using the configuration in **Admin**.

The live-demo Azure configuration preloads the default recipient as `neil.bailey@gmail.com` and stores messages in the Azure Files outbox until an approved SMTP sender secret is added. When SMTP is enabled, the same test form performs a real delivery test and the delivery log should show `sent`.

## 13. Admin: Check Email Configuration

Go to **Admin**.

Review **Email Configuration**:

- delivery mode
- SMTP host and port, if used
- sender name and email
- default recipients
- enabled status

Use the test email function before relying on SMTP sending.

## 14. Admin: Keep The Audit Trail

Go to **Admin** then **Audit**.

Use the audit log to confirm important changes, including:

- customer creation
- pack application
- portal updates
- opportunity review actions
- report changes
- email delivery records

## Good Operating Rhythm

Use this weekly or before a bid review:

1. Apply or update customer packs.
2. Refresh public sources.
3. Run KRA checks.
4. Review opportunities and requirements.
5. Confirm portal tasks are complete.
6. Generate a report.
7. Download the report for file storage.
8. Email the report to the agreed recipients.
9. Check the audit log.
