from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import Opportunity
from app.route_utils import context, paged, redirect, reference_context, templates


router = APIRouter()


@router.get("/review", response_class=HTMLResponse)
def review_queue(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunities, pagination = paged(session, select(Opportunity).order_by(col(Opportunity.updated_at).desc()), request)
    return templates.TemplateResponse(
        request,
        "review.html",
        context(request, opportunities=opportunities, opportunities_pagination=pagination, **reference_context(session)),
    )


@router.post("/opportunities/{opportunity_id}/review")
async def update_opportunity_review(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/review")
    form = await request.form()
    errors: list[str] = []
    action = str(form.get("action") or "").strip()
    allowed = {"approve": "approved", "reject": "rejected", "reassign": "pending_review", "hold": "pending_review"}
    if action not in allowed:
        errors.append("Review action must be approve, reject, reassign or hold.")
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    if errors:
        return validation_error_response(errors, "/review")
    before = compact_snapshot(opportunity)
    opportunity.status = allowed[action]
    if action == "reassign":
        opportunity.customer_id = customer_id
        opportunity.business_unit_id = business_unit_id
    opportunity.relevance_rationale = str(form.get("review_notes") or opportunity.relevance_rationale or "")
    session.add(opportunity)
    log_event(
        session,
        entity_type="Opportunity",
        entity_id=opportunity.id,
        action=f"review_{action}",
        summary=f"Review action {action} for {opportunity.title}",
        before=before,
        after=opportunity,
    )
    session.commit()
    return redirect("/review")
