from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import false, or_
from sqlmodel import Session, col, select

from app.access_scope import report_in_scope, scope_for_user
from app.audit import compact_snapshot
from app.auth import require_admin, require_report_viewer
from app.database import get_session
from app.email_service import get_email_configuration, send_or_store_email, split_recipients
from app.export_service import report_export
from app.form_utils import parse_bool, parse_optional_int, validation_error_response
from app.models import EmailDeliveryLog, IntelligenceReport
from app.portal_connectors import run_enabled_portal_connectors
from app.reports import create_report
from app.route_utils import clear_links, context, delete_with_audit, paged, redirect, reference_context, templates, update_with_audit


router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
def reports(request: Request, session: Session = Depends(get_session), user=Depends(require_report_viewer)):
    statement = select(IntelligenceReport).order_by(col(IntelligenceReport.generated_at).desc())
    scope = scope_for_user(user)
    if scope.restricted:
        conditions = []
        if scope.customer_ids:
            conditions.append(col(IntelligenceReport.customer_id).in_(scope.customer_ids))
        if scope.business_unit_ids:
            conditions.append(col(IntelligenceReport.business_unit_id).in_(scope.business_unit_ids))
        statement = statement.where(or_(*conditions) if conditions else false())
    items, pagination = paged(session, statement, request)
    return templates.TemplateResponse(request, "reports.html", context(request, reports=items, reports_pagination=pagination, **reference_context(session)))


@router.post("/reports")
async def create_intelligence_report(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    name = str(form.get("report_name") or "Data intelligence summary").strip()
    if errors:
        return validation_error_response(errors, "/reports")
    if parse_bool(form.get("auto_retrieve")):
        run_enabled_portal_connectors(session, customer_id=customer_id, business_unit_id=business_unit_id)
    report = create_report(session, name, str(form.get("report_type") or "executive_summary"), customer_id, business_unit_id)
    return redirect(f"/reports/{report.id}")


@router.post("/reports/{report_id}/update")
async def update_report(report_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    form = await request.form()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    name = str(form.get("report_name") or "").strip()
    if not name:
        errors.append("Report name is required.")
    if errors:
        return validation_error_response(errors, f"/reports/{report_id}")
    before = compact_snapshot(report)
    report.report_name = name
    report.report_type = str(form.get("report_type") or "executive_summary")
    report.customer_id = customer_id
    report.business_unit_id = business_unit_id
    report.markdown = str(form.get("markdown") or report.markdown or "")
    update_with_audit(session, report, f"Updated report {report.report_name}", before)
    return redirect(f"/reports/{report.id}")


@router.post("/reports/{report_id}/delete")
def delete_report(report_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    clear_links(session, EmailDeliveryLog, "report_id", report.id)
    delete_with_audit(session, report, f"Deleted report {report.report_name}")
    return redirect("/reports")


@router.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(report_id: int, request: Request, format: str | None = None, session: Session = Depends(get_session), user=Depends(require_report_viewer)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    if not report_in_scope(report, user):
        return Response("Report is outside your configured access scope.", status_code=403)
    if format in {"md", "html", "json", "txt", "pdf"}:
        payload, media_type, filename = report_export(report, format)
        return Response(payload, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    email_config = get_email_configuration(session)
    return templates.TemplateResponse(request, "report_detail.html", context(request, report=report, email_config=email_config, **reference_context(session)))


@router.post("/reports/{report_id}/send-email")
async def send_report_email(report_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    form = await request.form()
    config = get_email_configuration(session)
    recipients = split_recipients(str(form.get("recipients") or config.default_recipients))
    if not recipients:
        return validation_error_response(["Add at least one recipient before sending the report."], f"/reports/{report_id}")
    send_or_store_email(
        session,
        config,
        recipients=recipients,
        subject=str(form.get("subject") or report.report_name),
        body=str(form.get("message") or "Please find the attached Data Intelligence Portal report for review."),
        report=report,
        sender_name=str(form.get("sender_name") or config.sender_name),
        sender_email=str(form.get("sender_email") or config.sender_email),
        export_format=str(form.get("export_format") or "pdf"),
    )
    return redirect(f"/reports/{report_id}")
