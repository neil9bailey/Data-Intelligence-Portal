from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import (
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    CustomerWatchProfile,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    KRAFinding,
    KRAResearchRun,
    Opportunity,
)
from app.route_utils import clear_links, context, delete_with_audit, paged, redirect, reference_context, save_with_audit, templates, update_with_audit


router = APIRouter()


@router.get("/customers", response_class=HTMLResponse)
def customers(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    items, pagination = paged(session, select(Customer).order_by(col(Customer.customer_name)), request)
    data = reference_context(session)
    data["customers"] = items
    data["customers_pagination"] = pagination
    return templates.TemplateResponse(request, "customers.html", context(request, **data))


@router.post("/customers")
async def create_customer(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("customer_name") or "").strip()
    if not name:
        errors.append("Customer name is required.")
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    if errors:
        return validation_error_response(errors, "/customers")
    customer = Customer(
        customer_name=name,
        business_unit_id=business_unit_id,
        sector=str(form.get("sector") or "Public sector"),
        domain=str(form.get("domain") or ""),
        customer_type=str(form.get("customer_type") or ""),
        region=str(form.get("region") or "UK"),
        buying_entities=str(form.get("buying_entities") or ""),
        aliases=str(form.get("aliases") or ""),
        strategic_notes=str(form.get("strategic_notes") or ""),
        portal_notes=str(form.get("portal_notes") or ""),
    )
    save_with_audit(session, customer, "create", f"Created customer {customer.customer_name}")
    return redirect("/customers")


@router.post("/customers/{customer_id}")
async def update_customer(customer_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    customer = session.get(Customer, customer_id)
    if not customer:
        return redirect("/customers")
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("customer_name") or "").strip()
    if not name:
        errors.append("Customer name is required.")
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    if errors:
        return validation_error_response(errors, "/customers")
    before = compact_snapshot(customer)
    customer.customer_name = name
    customer.business_unit_id = business_unit_id
    customer.sector = str(form.get("sector") or "Public sector")
    customer.domain = str(form.get("domain") or "")
    customer.customer_type = str(form.get("customer_type") or "")
    customer.region = str(form.get("region") or "UK")
    customer.buying_entities = str(form.get("buying_entities") or "")
    customer.aliases = str(form.get("aliases") or "")
    customer.strategic_notes = str(form.get("strategic_notes") or "")
    customer.portal_notes = str(form.get("portal_notes") or "")
    update_with_audit(session, customer, f"Updated customer {customer.customer_name}", before)
    return redirect("/customers")


@router.post("/customers/{customer_id}/delete")
def delete_customer(customer_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    customer = session.get(Customer, customer_id)
    if not customer:
        return redirect("/customers")
    clear_links(session, CustomerWatchProfile, "customer_id", customer.id)
    clear_links(session, BuyerPortalInstance, "customer_id", customer.id)
    clear_links(session, Opportunity, "customer_id", customer.id)
    clear_links(session, ClientInterestSignal, "customer_id", customer.id)
    clear_links(session, ExtractedRequirement, "customer_id", customer.id)
    clear_links(session, ExtractedQualityQuestion, "customer_id", customer.id)
    clear_links(session, KRAResearchRun, "customer_id", customer.id)
    clear_links(session, KRAFinding, "customer_id", customer.id)
    delete_with_audit(session, customer, f"Deleted customer {customer.customer_name}")
    return redirect("/customers")
