from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import false, or_
from sqlmodel import Session, col, select

from app.access_scope import interest_in_scope, opportunity_in_scope, scope_for_user
from app.audit import compact_snapshot, log_event
from app.auth import require_standard_or_admin
from app.cof import CLIENT_VISIBLE_STATUSES
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import ClientInterestSignal, DocumentRetrievalTask, ExtractedQualityQuestion, Opportunity
from app.route_utils import context, delete_with_audit, redirect, save_with_audit, scoped_reference_context, templates, update_with_audit


router = APIRouter()


@router.get("/client-portal", response_class=HTMLResponse)
def client_portal(request: Request, session: Session = Depends(get_session), user=Depends(require_standard_or_admin)):
    approved_statement = (
        select(Opportunity)
        .where(col(Opportunity.status).in_(CLIENT_VISIBLE_STATUSES), Opportunity.archived == False)  # noqa: E712
        .order_by(col(Opportunity.updated_at).desc())
    )
    all_statement = select(Opportunity).where(Opportunity.archived == False).order_by(col(Opportunity.updated_at).desc())  # noqa: E712
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
    opportunity_ids = [item.id for item in opportunities if item.id]
    questions_by_opportunity: dict[int, list[ExtractedQualityQuestion]] = {item_id: [] for item_id in opportunity_ids}
    if opportunity_ids:
        for question in session.exec(select(ExtractedQualityQuestion).where(col(ExtractedQualityQuestion.opportunity_id).in_(opportunity_ids))):
            questions_by_opportunity.setdefault(question.opportunity_id, []).append(question)
    metrics = {
        "pins": sum(1 for item in opportunities if item.status == "pin" or item.notice_type == "planning"),
        "live_tenders": sum(1 for item in opportunities if item.status in {"live", "closing_soon", "document_retrieval_required", "questions_extracted"}),
        "interested": sum(1 for item in opportunities if item.status == "interested"),
        "awarded": sum(1 for item in opportunities if item.status == "awarded" or item.notice_type == "award"),
    }
    return templates.TemplateResponse(
        request,
        "client_portal.html",
        context(
            request,
            opportunities=opportunities,
            all_opportunities=all_opportunities,
            interests=interests,
            client_metrics=metrics,
            questions_by_opportunity=questions_by_opportunity,
            **scoped_reference_context(session, user),
        ),
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
    customer_id = customer_id or (opportunity.customer_id if opportunity else None)
    requested_signal = str(form.get("signal") or "interested")
    signal = _upsert_interest_signal(
        session,
        opportunity_id,
        customer_id,
        requested_signal,
        str(form.get("contact_name") or ""),
        str(form.get("contact_email") or ""),
        str(form.get("notes") or ""),
    )
    _apply_cof_interest_workflow(session, opportunity, signal)
    session.commit()
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


def _upsert_interest_signal(
    session: Session,
    opportunity_id: int | None,
    customer_id: int | None,
    signal_value: str,
    contact_name: str,
    contact_email: str,
    notes: str,
) -> ClientInterestSignal:
    existing = None
    if opportunity_id and customer_id:
        existing = session.exec(
            select(ClientInterestSignal).where(
                ClientInterestSignal.opportunity_id == opportunity_id,
                ClientInterestSignal.customer_id == customer_id,
                ClientInterestSignal.signal == signal_value,
            )
        ).first()
    if existing:
        before = compact_snapshot(existing)
        existing.contact_name = contact_name
        existing.contact_email = contact_email
        existing.notes = notes
        existing.status = "account_lead_action_required" if signal_value == "interested" else "watching"
        session.add(existing)
        session.flush()
        log_event(session, entity_type="ClientInterestSignal", entity_id=existing.id, action="update", summary=f"Updated client {signal_value} signal", before=before, after=existing)
        return existing
    signal = ClientInterestSignal(
        opportunity_id=opportunity_id,
        customer_id=customer_id,
        contact_name=contact_name,
        contact_email=contact_email,
        signal=signal_value,
        notes=notes,
        status="account_lead_action_required" if signal_value == "interested" else "watching",
    )
    save_with_audit(session, signal, "create", "Created client interest signal")
    return signal


def _apply_cof_interest_workflow(session: Session, opportunity: Opportunity | None, signal: ClientInterestSignal) -> None:
    if not opportunity:
        return
    before = compact_snapshot(opportunity)
    if signal.signal == "interested":
        opportunity.status = "interested"
    elif signal.signal == "watch" and opportunity.status not in {"interested", "awarded"}:
        opportunity.status = "watch"
    session.add(opportunity)
    session.flush()
    log_event(session, entity_type="Opportunity", entity_id=opportunity.id, action=f"client_{signal.signal}", summary=f"Client marked opportunity as {signal.signal}", before=before, after=opportunity)
    if signal.signal != "interested":
        return
    existing_task = session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.opportunity_id == opportunity.id)).first()
    if existing_task:
        return
    task = DocumentRetrievalTask(
        opportunity_id=opportunity.id,
        task_name="Account Lead action: retrieve permitted tender documents",
        status="requested",
        owner="Client Action Queue",
        notes="Client interest triggered on-demand document retrieval. No portal login, expression of interest or submission is automated.",
    )
    session.add(task)
    session.flush()
    log_event(session, entity_type="DocumentRetrievalTask", entity_id=task.id, action="create", summary="Created client action document retrieval task", after=task)
