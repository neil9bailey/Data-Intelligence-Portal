from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import ClientInterestSignal, Opportunity
from app.route_utils import context, delete_with_audit, redirect, reference_context, save_with_audit, templates, update_with_audit


router = APIRouter()


@router.get("/client-portal", response_class=HTMLResponse)
def client_portal(request: Request, session: Session = Depends(get_session)):
    opportunities = list(session.exec(select(Opportunity).where(Opportunity.status == "approved").order_by(col(Opportunity.updated_at).desc()).limit(100)))
    all_opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(300)))
    interests = list(session.exec(select(ClientInterestSignal).order_by(col(ClientInterestSignal.created_at).desc()).limit(100)))
    return templates.TemplateResponse(
        request,
        "client_portal.html",
        context(request, opportunities=opportunities, all_opportunities=all_opportunities, interests=interests, **reference_context(session)),
    )


@router.post("/client-portal/interests")
async def create_interest_signal(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/client-portal")
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
async def update_interest_signal(signal_id: int, request: Request, session: Session = Depends(get_session)):
    signal = session.get(ClientInterestSignal, signal_id)
    if not signal:
        return redirect("/client-portal")
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/client-portal")
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
def delete_interest_signal(signal_id: int, session: Session = Depends(get_session)):
    signal = session.get(ClientInterestSignal, signal_id)
    if not signal:
        return redirect("/client-portal")
    delete_with_audit(session, signal, "Deleted client interest signal")
    return redirect("/client-portal")
