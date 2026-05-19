from __future__ import annotations

from sqlmodel import Session

from app.email_service import get_email_configuration, send_or_store_email, split_recipients
from app.models import DigestProfile, EmailDeliveryLog
from app.reports import create_report


def send_digest(session: Session, profile: DigestProfile) -> EmailDeliveryLog:
    config = get_email_configuration(session)
    recipients = split_recipients(profile.recipients or config.default_recipients)
    if not recipients:
        raise ValueError("Digest profile has no recipients.")
    report = create_report(
        session,
        f"{profile.name} digest",
        profile.report_type,
        profile.customer_id,
        profile.business_unit_id,
    )
    return send_or_store_email(
        session,
        config,
        recipients=recipients,
        subject=f"{profile.name} digest",
        body="Please find the attached Data Intelligence Portal digest for human review.",
        report=report,
        export_format=profile.export_format,
    )
