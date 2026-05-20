from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import ClientInterestSignal, DocumentRetrievalTask, Opportunity, OpportunityMatchEvidence
from app.route_utils import context, paged, redirect, reference_context, templates


router = APIRouter()


@router.get("/review", response_class=HTMLResponse)
def review_queue(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunities, pagination = paged(
        session,
        select(Opportunity)
        .where(Opportunity.archived == False)  # noqa: E712
        .order_by(col(Opportunity.updated_at).desc()),
        request,
    )
    opportunity_ids = [item.id for item in opportunities if item.id]
    match_evidence_by_opportunity: dict[int, list[OpportunityMatchEvidence]] = {item_id: [] for item_id in opportunity_ids}
    if opportunity_ids:
        for evidence in session.exec(select(OpportunityMatchEvidence).where(col(OpportunityMatchEvidence.opportunity_id).in_(opportunity_ids))):
            match_evidence_by_opportunity.setdefault(evidence.opportunity_id or 0, []).append(evidence)
    client_action_signals = list(
        session.exec(select(ClientInterestSignal).where(ClientInterestSignal.signal == "interested").order_by(col(ClientInterestSignal.created_at).desc()).limit(50))
    )
    retrieval_tasks = list(session.exec(select(DocumentRetrievalTask).order_by(col(DocumentRetrievalTask.created_at).desc()).limit(100)))
    tasks_by_opportunity = {task.opportunity_id: task for task in retrieval_tasks if task.opportunity_id}
    return templates.TemplateResponse(
        request,
        "review.html",
        context(
            request,
            opportunities=opportunities,
            all_opportunities=opportunities,
            opportunities_pagination=pagination,
            match_evidence_by_opportunity=match_evidence_by_opportunity,
            client_action_signals=client_action_signals,
            tasks_by_opportunity=tasks_by_opportunity,
            **reference_context(session),
        ),
    )


@router.post("/opportunities/{opportunity_id}/review")
async def update_opportunity_review(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/review")
    form = await request.form()
    errors: list[str] = []
    action = str(form.get("action") or "").strip()
    allowed = {"approve": "approved", "reject": "rejected", "reassign": "pending_review", "hold": "pending_review", "needs_more_evidence": "review_required"}
    if action not in allowed:
        errors.append("Review action must be approve, reject, reassign, needs more evidence or hold.")
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
