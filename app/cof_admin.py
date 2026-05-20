from __future__ import annotations

from sqlmodel import Session, col, select

from app.cof_readiness import REQUIRED_PORTAL_FAMILIES, REQUIRED_SOURCE_KEYS, cof_operating_status
from app.email_service import get_email_configuration, split_recipients
from app.models import (
    AuditEvent,
    AutomationRun,
    BusinessUnit,
    Customer,
    DigestProfile,
    IntelligenceReport,
    KRAAgentProfile,
    KRAResearchRun,
    PortalInformationConnector,
    ProcurementPlatform,
    ProcurementSource,
    Opportunity,
)
from app.reports import COF_BUSINESS_UNIT_NAME, COF_CLIENT_PREFIX


def cof_admin_function_audit(session: Session) -> list[dict[str, str]]:
    """Summarise whether each admin function contributes to the automated COF outcome."""

    operating = cof_operating_status(session)
    unit = session.exec(select(BusinessUnit).where(BusinessUnit.name == COF_BUSINESS_UNIT_NAME)).first()
    customers = list(session.exec(select(Customer).where(col(Customer.customer_name).startswith(COF_CLIENT_PREFIX))))
    sources = list(session.exec(select(ProcurementSource)))
    source_keys = {source.source_key for source in sources if source.active}
    platforms = {platform.name for platform in session.exec(select(ProcurementPlatform))}
    connectors = list(session.exec(select(PortalInformationConnector)))
    kra_profiles = list(session.exec(select(KRAAgentProfile).where(KRAAgentProfile.active == True)))  # noqa: E712
    latest_kra = session.exec(select(KRAResearchRun).order_by(col(KRAResearchRun.started_at).desc())).first()
    latest_automation = session.exec(select(AutomationRun).order_by(col(AutomationRun.created_at).desc())).first()
    latest_report = session.exec(select(IntelligenceReport).order_by(col(IntelligenceReport.generated_at).desc())).first()
    digest = session.exec(select(DigestProfile).where(DigestProfile.name == "COF Monday report send")).first()
    email_config = get_email_configuration(session)
    recipients = split_recipients((digest.recipients if digest else "") or email_config.default_recipients)
    audit_event = session.exec(select(AuditEvent).order_by(col(AuditEvent.created_at).desc())).first()
    archived_count = len(list(session.exec(select(Opportunity).where(Opportunity.archived == True))))  # noqa: E712

    required_sources = set(REQUIRED_SOURCE_KEYS)
    required_platforms = set(REQUIRED_PORTAL_FAMILIES)
    source_ready = required_sources.issubset(source_keys)
    platform_ready = required_platforms.issubset(platforms)
    digest_ready = bool(digest and digest.enabled and recipients)

    return [
        {
            "function": "COF workspace pack",
            "mode": "Self-healing in Autopilot",
            "status": "ready" if unit and len(customers) >= 11 else "attention",
            "value": "Maintains the 11-client Contracted Opportunity Finder workspace and design-brief baseline.",
            "detail": f"{len(customers)} client(s); business unit {'configured' if unit else 'missing'}.",
        },
        {
            "function": "Official source ingestion",
            "mode": "Automated",
            "status": "ready" if source_ready and operating.status != "Needs source attention" else "attention",
            "value": "Refreshes the five public procurement sources and excludes stale or untrusted records from output.",
            "detail": f"{len(required_sources & source_keys)} of {len(required_sources)} required source families active.",
        },
        {
            "function": "KRA matching and explanation",
            "mode": "Automated evidence support",
            "status": "ready" if kra_profiles else "attention",
            "value": "Runs guarded matching, classification and explanation. It supports, but does not make, bid/legal/compliance decisions.",
            "detail": f"{len(kra_profiles)} profile(s); latest run {latest_kra.status if latest_kra else 'not yet run'}.",
        },
        {
            "function": "Portal and document workflow",
            "mode": "On-demand / read-only only",
            "status": "ready" if platform_ready else "attention",
            "value": "Tracks the four portal families and creates retrieval tasks only when a client action needs documents.",
            "detail": f"{len(required_platforms & platforms)} of {len(required_platforms)} portal families; {sum(1 for item in connectors if item.enabled)} enabled connector(s).",
        },
        {
            "function": "Weekly report generation",
            "mode": "Automated",
            "status": "ready" if latest_report else "attention",
            "value": "Creates the customer-facing opportunity pack and export without manual report assembly.",
            "detail": f"Latest report {latest_report.generated_at.strftime('%Y-%m-%d %H:%M') if latest_report else 'not generated'}.",
        },
        {
            "function": "Digest and delivery",
            "mode": "Automated when recipients exist",
            "status": "ready" if digest_ready else "attention",
            "value": "Stores or sends the weekly PDF using file-outbox or SMTP configuration.",
            "detail": f"{len(recipients)} recipient(s); delivery mode {email_config.delivery_mode}.",
        },
        {
            "function": "Opportunity archive and cleanup",
            "mode": "Automated in Autopilot",
            "status": "ready",
            "value": "Moves closed, past-deadline and stale records out of live output while keeping them searchable and exportable.",
            "detail": f"{archived_count} archived record(s); cleanup also available from Archive.",
        },
        {
            "function": "Audit and operational trace",
            "mode": "Automatic",
            "status": "ready" if audit_event else "attention",
            "value": "Records configuration, automation, report and delivery events for traceability.",
            "detail": f"Latest event {audit_event.created_at.strftime('%Y-%m-%d %H:%M') if audit_event else 'not yet recorded'}.",
        },
        {
            "function": "Advanced configuration screens",
            "mode": "Rare-use only",
            "status": "ready",
            "value": "Kept for governance and exception handling; not needed for normal COF operation.",
            "detail": f"Latest Autopilot run {latest_automation.status if latest_automation else 'not yet run'}.",
        },
    ]
