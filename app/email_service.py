from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
import os
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
        if apply_email_environment_defaults(config):
            session.add(config)
            session.commit()
            session.refresh(config)
        return config
    config = EmailConfiguration()
    apply_email_environment_defaults(config)
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def apply_email_environment_defaults(config: EmailConfiguration) -> bool:
    settings = get_settings()
    changed = False

    def set_if_blank(attr: str, value: str) -> None:
        nonlocal changed
        if value and not str(getattr(config, attr) or "").strip():
            setattr(config, attr, value)
            changed = True

    set_if_blank("delivery_mode", settings.email_delivery_mode)
    set_if_blank("sender_name", settings.email_sender_name)
    if config.sender_email in {"", "no-reply@local.test"}:
        set_if_blank("sender_email", settings.email_sender)
    set_if_blank("default_recipients", settings.email_default_recipients)
    set_if_blank("smtp_host", settings.smtp_host)
    set_if_blank("smtp_username", settings.smtp_username)
    set_if_blank("smtp_password_secret_name", settings.smtp_password_secret_name)
    if settings.smtp_password and not config.smtp_password_secret_name:
        config.smtp_password_secret_name = "DIP_SMTP_PASSWORD"
        changed = True
    if settings.smtp_port and config.smtp_port == 587:
        try:
            config.smtp_port = int(settings.smtp_port)
            changed = True
        except ValueError:
            pass
    if settings.email_delivery_mode and config.delivery_mode in {"", "file_outbox"} and config.delivery_mode != settings.email_delivery_mode:
        config.delivery_mode = settings.email_delivery_mode
        changed = True
    if settings.smtp_enabled and (not config.enabled or config.use_tls != settings.smtp_use_tls):
        config.enabled = True
        config.use_tls = settings.smtp_use_tls
        changed = True
    return changed


def resolve_smtp_password(config: EmailConfiguration) -> str:
    settings = get_settings()
    secret_ref = (config.smtp_password_secret_name or "").strip()
    if secret_ref:
        return os.getenv(secret_ref, "")
    if settings.smtp_password:
        return settings.smtp_password
    return config.smtp_password or ""


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
    export_format: str = "pdf",
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
    export_format: str = "pdf",
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
                    smtp.login(config.smtp_username, resolve_smtp_password(config))
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
