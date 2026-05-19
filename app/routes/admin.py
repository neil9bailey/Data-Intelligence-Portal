from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.auth import require_admin
from app.automation import automation_summary, create_queued_automation_run, run_admin_full_cycle_background
from app.database import get_session
from app.digests import send_digest
from app.email_service import get_email_configuration, send_or_store_email, split_recipients
from app.form_utils import parse_bool, parse_optional_int, validation_error_response
from app.models import DigestProfile, EmailDeliveryLog, utc_now
from app.route_utils import context, health_dashboard_context, redirect, reference_context, templates


router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    email_config = get_email_configuration(session)
    email_logs = list(session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc()).limit(50)))
    automation = automation_summary(session)
    digest_profiles = list(session.exec(select(DigestProfile).order_by(col(DigestProfile.created_at).desc()).limit(20)))
    return templates.TemplateResponse(
        request,
        "admin.html",
        context(
            request,
            email_config=email_config,
            email_logs=email_logs,
            health=health_dashboard_context(session, request),
            automation=automation,
            digest_profiles=digest_profiles,
            **reference_context(session),
        ),
    )


@router.post("/admin/automation/run")
async def run_admin_automation(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user=Depends(require_admin),
):
    form = await request.form()
    run = create_queued_automation_run(session, actor=user.username)
    background_tasks.add_task(
        run_admin_full_cycle_background,
        run.id,
        user.username,
        str(form.get("email_recipients") or ""),
        str(form.get("export_format") or "pdf"),
    )
    return redirect(f"/admin?automation=queued&run_id={run.id}")


@router.post("/admin/email")
async def update_email_configuration(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    config = get_email_configuration(session)
    smtp_port = parse_optional_int(form.get("smtp_port"), "SMTP port", errors) or 587
    if errors:
        return validation_error_response(errors, "/admin")
    before = compact_snapshot(config)
    config.profile_name = str(form.get("profile_name") or "Default local profile")
    config.delivery_mode = str(form.get("delivery_mode") or "file_outbox")
    config.smtp_host = str(form.get("smtp_host") or "")
    config.smtp_port = smtp_port
    config.smtp_username = str(form.get("smtp_username") or "")
    config.smtp_password_secret_name = str(form.get("smtp_password_secret_name") or "")
    config.smtp_password = ""
    config.use_tls = parse_bool(form.get("use_tls"))
    config.enabled = parse_bool(form.get("enabled"))
    config.sender_name = str(form.get("sender_name") or "Data Intelligence Portal")
    config.sender_email = str(form.get("sender_email") or "no-reply@local.test")
    config.default_recipients = str(form.get("default_recipients") or "")
    config.notes = str(form.get("notes") or "")
    session.add(config)
    log_event(session, entity_type="EmailConfiguration", entity_id=config.id, action="update", summary="Updated email configuration secret reference", before=before, after=config)
    session.commit()
    return redirect("/admin")


@router.post("/admin/email/test")
async def send_test_email(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    config = get_email_configuration(session)
    recipients = split_recipients(str(form.get("recipients") or config.default_recipients))
    if not recipients:
        return validation_error_response(["At least one recipient is required for a test email."], "/admin")
    send_or_store_email(
        session,
        config,
        recipients=recipients,
        subject=str(form.get("subject") or "Data Intelligence Portal test email"),
        body=str(form.get("message") or "This is a local MVP email configuration test."),
        sender_name=str(form.get("sender_name") or config.sender_name),
        sender_email=str(form.get("sender_email") or config.sender_email),
    )
    return redirect("/admin")


@router.post("/admin/digests")
async def create_digest_profile(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("name") or "").strip()
    if not name:
        errors.append("Digest name is required.")
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    if errors:
        return validation_error_response(errors, "/admin")
    profile = DigestProfile(
        name=name,
        report_type=str(form.get("report_type") or "executive_summary"),
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        recipients=str(form.get("recipients") or ""),
        frequency_label=str(form.get("frequency_label") or "manual"),
        enabled=parse_bool(form.get("enabled")) if form.get("enabled") is not None else True,
        export_format=str(form.get("export_format") or "pdf"),
    )
    session.add(profile)
    session.flush()
    log_event(session, entity_type="DigestProfile", entity_id=profile.id, action="create", summary=f"Created digest profile {profile.name}", after=profile)
    session.commit()
    return redirect("/admin")


@router.post("/admin/digests/{profile_id}/send")
def send_digest_profile(profile_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    profile = session.get(DigestProfile, profile_id)
    if not profile or not profile.enabled:
        return redirect("/admin")
    log = send_digest(session, profile)
    before = compact_snapshot(profile)
    profile.updated_at = utc_now()
    session.add(profile)
    log_event(session, entity_type="DigestProfile", entity_id=profile.id, action="send", summary=f"Sent digest profile {profile.name}; email {log.status}", before=before, after=profile)
    session.commit()
    return redirect("/admin")
