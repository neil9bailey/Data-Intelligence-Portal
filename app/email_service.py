from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
import smtplib

from sqlmodel import Session, select

from app.audit import log_event
from app.export_service import report_export
from app.models import EmailConfiguration, EmailDeliveryLog, IntelligenceReport
from app.settings import get_settings


def get_email_configuration(session: Session) -> EmailConfiguration:
    config = session.exec(select(EmailConfiguration).order_by(EmailConfiguration.id)).first()
    if config:
        return config
    config = EmailConfiguration()
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def split_recipients(value: str) -> list[str]:
    recipients: list[str] = []
    for item in (value or "").replace(";", ",").split(","):
        address = item.strip()
        if address and address not in recipients:
            recipients.append(address)
    return recipients


def build_message(
    report: IntelligenceReport | None,
    config: EmailConfiguration,
    sender_name: str,
    sender_email: str,
    recipients: list[str],
    subject: str,
    message_body: str,
    export_format: str = "md",
) -> EmailMessage:
    msg = EmailMessage()
    sender_label = sender_name or config.sender_name or "Data Intelligence Portal"
    sender_address = sender_email or config.sender_email
    msg["From"] = f"{sender_label} <{sender_address}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(message_body or "Please find the Data Intelligence Portal report attached for review.")
    if report:
        payload, media_type, filename = report_export(report, export_format)
        maintype, subtype = media_type.split("/", 1)
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def send_or_store_email(
    session: Session,
    config: EmailConfiguration,
    recipients: list[str],
    subject: str,
    body: str,
    report: IntelligenceReport | None = None,
    sender_name: str = "",
    sender_email: str = "",
    export_format: str = "md",
) -> EmailDeliveryLog:
    msg = build_message(report, config, sender_name, sender_email, recipients, subject, body, export_format)
    log = EmailDeliveryLog(
        report_id=report.id if report else None,
        delivery_mode=config.delivery_mode,
        sender=msg["From"],
        recipients=", ".join(recipients),
        subject=subject,
        attachment_format=export_format,
    )
    try:
        if config.delivery_mode == "smtp" and config.enabled:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
                if config.use_tls:
                    smtp.starttls()
                if config.smtp_username:
                    smtp.login(config.smtp_username, config.smtp_password)
                smtp.send_message(msg)
            log.status = "sent"
        else:
            outbox = Path(get_settings().outbox_dir)
            outbox.mkdir(parents=True, exist_ok=True)
            filename = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{subject[:34].replace(' ', '-') or 'message'}.eml"
            path = outbox / filename
            path.write_text(msg.as_string(), encoding="utf-8")
            log.status = "stored"
            log.outbox_path = str(path)
    except Exception as exc:
        log.status = "failed"
        log.error = str(exc)
    session.add(log)
    session.flush()
    log_event(session, entity_type="EmailDeliveryLog", entity_id=log.id, action=log.status, summary=f"Email {log.status}: {subject}", after=log)
    session.commit()
    session.refresh(log)
    return log
