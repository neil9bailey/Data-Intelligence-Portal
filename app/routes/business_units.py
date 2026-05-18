from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.audit import compact_snapshot
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_bool, parse_optional_int, validation_error_response
from app.models import BusinessUnit, BuyerPortalInstance, Customer, CustomerWatchProfile, IntelligenceReport, Opportunity
from app.route_utils import clear_links, context, delete_with_audit, redirect, reference_context, save_with_audit, templates, update_with_audit


router = APIRouter()


@router.get("/business-units", response_class=HTMLResponse)
def business_units(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    return templates.TemplateResponse(request, "business_units.html", context(request, **reference_context(session)))


@router.post("/business-units")
async def create_business_unit(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("name") or "").strip()
    parent_id = parse_optional_int(form.get("parent_id"), "Parent business unit", errors)
    if not name:
        errors.append("Business unit name is required.")
    if errors:
        return validation_error_response(errors, "/business-units")
    unit = BusinessUnit(
        name=name,
        parent_id=parent_id,
        description=str(form.get("description") or ""),
        active=parse_bool(form.get("active")) if form.get("active") is not None else True,
    )
    save_with_audit(session, unit, "create", f"Created business unit {unit.name}")
    return redirect("/business-units")


@router.post("/business-units/{unit_id}")
async def update_business_unit(unit_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    unit = session.get(BusinessUnit, unit_id)
    if not unit:
        return redirect("/business-units")
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("name") or "").strip()
    parent_id = parse_optional_int(form.get("parent_id"), "Parent business unit", errors)
    if parent_id == unit.id:
        errors.append("A business unit cannot be its own parent.")
    if not name:
        errors.append("Business unit name is required.")
    if errors:
        return validation_error_response(errors, "/business-units")
    before = compact_snapshot(unit)
    unit.name = name
    unit.parent_id = parent_id
    unit.description = str(form.get("description") or "")
    unit.active = parse_bool(form.get("active"))
    update_with_audit(session, unit, f"Updated business unit {unit.name}", before)
    return redirect("/business-units")


@router.post("/business-units/{unit_id}/delete")
def delete_business_unit(unit_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    unit = session.get(BusinessUnit, unit_id)
    if not unit:
        return redirect("/business-units")
    clear_links(session, BusinessUnit, "parent_id", unit.id)
    clear_links(session, Customer, "business_unit_id", unit.id)
    clear_links(session, CustomerWatchProfile, "business_unit_id", unit.id)
    clear_links(session, BuyerPortalInstance, "business_unit_id", unit.id)
    clear_links(session, Opportunity, "business_unit_id", unit.id)
    clear_links(session, IntelligenceReport, "business_unit_id", unit.id)
    delete_with_audit(session, unit, f"Deleted business unit {unit.name}")
    return redirect("/business-units")
