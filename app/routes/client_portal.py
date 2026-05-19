from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import false, or_
from sqlmodel import Session, col, select

from app.access_scope import interest_in_scope, opportunity_in_scope, scope_for_user
from app.audit import compact_snapshot
from app.auth import require_standard_or_admin
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import ClientInterestSignal, Opportunity
from app.route_utils import context, delete_with_audit, redirect, reference_context, save_with_audit, templates, update_with_audit


router = APIRouter()


@router.get("/client-portal", response_class=HTMLResponse)
def client_portal(request: Request, session: Session = Depends(get_session), user=Depends(require_standard_or_admin)):
    approved_statement = select(Opportunity).where(Opportunity.status == "approved").order_by(col(Opportunity.updated_at).desc())
    all_statement = select(Opportunity).order_by(col(Opportunity.updated_at).desc())
    scope = scope_for_user(user)
    if scope.restricted:
        conditions = []
        if scope.customer_ids:
            conditions.append(col(Opportunity.customer_id).in_(scope.customer_ids))
        if scope.business_unit_ids:
            conditions.append(col(Opportunity.business_unit_id).in_(scope.business_unit_ids))
        scope_filter = or_(*conditions) if conditions else false()
        approved_statement = approved_statement.where(scope_filter)
        all_statement = all_statement.where(scope_filter)
    opportunities = list(session.exec(approved_statement.limit(100)))
    all_opportunities = list(session.exec(all_statement.limit(300)))
    opportunities_by_id = {item.id: item for item in all_opportunities if item.id}
    raw_interests = list(session.exec(select(ClientInterestSignal).order_by(col(ClientInterestSignal.created_at).desc()).limit(200)))
    interests = [item for item in raw_interests if interest_in_scope(item, user, opportunities_by_id)][:100]
    return templates.TemplateResponse(
        request,
        "client_portal.html",
        context(request, opportunities=opportunities, all_opportunities=all_opportunities, interests=interests, **reference_context(session)),
    )


@router.post("/client-portal/interests")
async def create_interest_signal(request: Request, session: Session = Depends(get_session), user=Depends(require_standard_or_admin)):
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/client-portal")
    opportunity = session.get(Opportunity, opportunity_id) if opportunity_id else None
    if opportunity and not opportunity_in_scope(opportunity, user):
        return validation_error_response(["The selected opportunity is outside your configured access scope."], "/client-portal")
    signal = ClientInterestSignal(
        opportunity_id=opportunity_id,
        customer_id=customer_id,
        contact_name=str(form.get("contact_name") or ""),
        contact_email=str(form.get("contact_email") or ""),
        signal=str(form.get("signal") or "interested"),
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, signal, "create", "Created client interest signal")
    return redirect("/client-portal")


@router.post("/client-portal/interests/{signal_id}")
async def update_interest_signal(signal_id: int, request: Request, session: Session = Depends(get_session), user=Depends(require_standard_or_admin)):
    signal = session.get(ClientInterestSignal, signal_id)
    if not signal:
        return redirect("/client-portal")
    current_opportunity = session.get(Opportunity, signal.opportunity_id) if signal.opportunity_id else None
    current_opportunities = {current_opportunity.id: current_opportunity} if current_opportunity and current_opportunity.id else {}
    if not interest_in_scope(signal, user, current_opportunities):
        return validation_error_response(["This interest signal is outside your configured access scope."], "/client-portal")
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/client-portal")
    opportunity = session.get(Opportunity, opportunity_id) if opportunity_id else None
    if opportunity and not opportunity_in_scope(opportunity, user):
        return validation_error_response(["The selected opportunity is outside your configured access scope."], "/client-portal")
    before = compact_snapshot(signal)
    signal.opportunity_id = opportunity_id
    signal.customer_id = customer_id
    signal.contact_name = str(form.get("contact_name") or "")
    signal.contact_email = str(form.get("contact_email") or "")
    signal.signal = str(form.get("signal") or "interested")
    signal.status = str(form.get("status") or "new")
    signal.notes = str(form.get("notes") or "")
    update_with_audit(session, signal, "Updated client interest signal", before)
    return redirect("/client-portal")


@router.post("/client-portal/interests/{signal_id}/delete")
def delete_interest_signal(signal_id: int, session: Session = Depends(get_session), user=Depends(require_standard_or_admin)):
    signal = session.get(ClientInterestSignal, signal_id)
    if not signal:
        return redirect("/client-portal")
    current_opportunity = session.get(Opportunity, signal.opportunity_id) if signal.opportunity_id else None
    current_opportunities = {current_opportunity.id: current_opportunity} if current_opportunity and current_opportunity.id else {}
    if not interest_in_scope(signal, user, current_opportunities):
        return validation_error_response(["This interest signal is outside your configured access scope."], "/client-portal")
    delete_with_audit(session, signal, "Deleted client interest signal")
    return redirect("/client-portal")
