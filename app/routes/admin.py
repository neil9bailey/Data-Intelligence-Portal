from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.auth import require_admin
from app.automation import automation_summary, create_queued_automation_run, run_admin_full_cycle_background
from app.database import get_session
from app.email_service import get_email_configuration, send_or_store_email, split_recipients
from app.form_utils import parse_bool, parse_optional_int, validation_error_response
from app.models import EmailDeliveryLog
from app.route_utils import context, health_dashboard_context, redirect, reference_context, templates


router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    email_config = get_email_configuration(session)
    email_logs = list(session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc()).limit(50)))
    automation = automation_summary(session)
    return templates.TemplateResponse(
        request,
        "admin.html",
        context(
            request,
            email_config=email_config,
            email_logs=email_logs,
            health=health_dashboard_context(session, request),
            automation=automation,
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
    password = str(form.get("smtp_password") or "")
    if password:
        config.smtp_password = password
    config.use_tls = parse_bool(form.get("use_tls"))
    config.enabled = parse_bool(form.get("enabled"))
    config.sender_name = str(form.get("sender_name") or "Data Intelligence Portal")
    config.sender_email = str(form.get("sender_email") or "no-reply@local.test")
    config.default_recipients = str(form.get("default_recipients") or "")
    config.notes = str(form.get("notes") or "")
    session.add(config)
    log_event(session, entity_type="EmailConfiguration", entity_id=config.id, action="update", summary="Updated email configuration", before=before, after=config)
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
