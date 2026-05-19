from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.auth import get_current_user, require_admin
from app.database import get_session
from app.form_utils import parse_float, parse_optional_date, parse_optional_int, validation_error_response
from app.intelligence import extract_document_intelligence
from app.models import (
    ClientInterestSignal,
    DocumentRetrievalTask,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    KRAFinding,
    KRAResearchRun,
    Opportunity,
    OpportunityDocument,
    OpportunityFeedback,
    OpportunityMatchEvidence,
    PortalInformationConnector,
    PortalRetrievalRun,
    utc_now,
)
from app.route_utils import (
    clear_links,
    context,
    delete_children,
    delete_with_audit,
    paged,
    redirect,
    reference_context,
    save_with_audit,
    templates,
    update_with_audit,
)


router = APIRouter()


@router.get("/opportunities", response_class=HTMLResponse)
def opportunities(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    items, pagination = paged(session, select(Opportunity).order_by(col(Opportunity.updated_at).desc()), request)
    documents = list(session.exec(select(OpportunityDocument)))
    evidence = list(session.exec(select(OpportunityMatchEvidence)))
    evidence_map: dict[int, list[OpportunityMatchEvidence]] = {}
    for item in evidence:
        if item.opportunity_id:
            evidence_map.setdefault(item.opportunity_id, []).append(item)
    doc_counts: dict[int, int] = {}
    for doc in documents:
        doc_counts[doc.opportunity_id] = doc_counts.get(doc.opportunity_id, 0) + 1
    return templates.TemplateResponse(
        request,
        "opportunities.html",
        context(request, opportunities=items, opportunities_pagination=pagination, doc_counts=doc_counts, evidence_map=evidence_map, **reference_context(session)),
    )


@router.post("/opportunities")
async def create_opportunity(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    title = str(form.get("title") or "").strip()
    if not title:
        errors.append("Opportunity title is required.")
    source_id = parse_optional_int(form.get("source_id"), "Source", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    deadline_date = parse_optional_date(form.get("deadline_date"), "Deadline date", errors)
    value_high = parse_float(form.get("value_high"), "Value high", errors, default=0)
    relevance_score = parse_float(form.get("relevance_score"), "Relevance score", errors, default=0)
    if errors:
        return validation_error_response(errors, "/opportunities")
    opportunity = Opportunity(
        title=title,
        source_id=source_id,
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        buyer_name=str(form.get("buyer_name") or ""),
        notice_identifier=str(form.get("notice_identifier") or ""),
        notice_type=str(form.get("notice_type") or ""),
        procurement_stage=str(form.get("procurement_stage") or ""),
        deadline_date=deadline_date,
        value_high=value_high,
        cpv_codes=str(form.get("cpv_codes") or ""),
        location=str(form.get("location") or ""),
        source_url=str(form.get("source_url") or ""),
        summary=str(form.get("summary") or ""),
        status=str(form.get("status") or "new"),
        relevance_score=relevance_score,
        relevance_rationale=str(form.get("relevance_rationale") or ""),
    )
    save_with_audit(session, opportunity, "create", f"Created opportunity {opportunity.title}")
    return redirect("/opportunities")


@router.post("/opportunities/{opportunity_id}")
async def update_opportunity(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    form = await request.form()
    errors: list[str] = []
    title = str(form.get("title") or "").strip()
    if not title:
        errors.append("Opportunity title is required.")
    source_id = parse_optional_int(form.get("source_id"), "Source", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    deadline_date = parse_optional_date(form.get("deadline_date"), "Deadline date", errors)
    value_high = parse_float(form.get("value_high"), "Value high", errors, default=0)
    relevance_score = parse_float(form.get("relevance_score"), "Relevance score", errors, default=0)
    if errors:
        return validation_error_response(errors, "/opportunities")
    before = compact_snapshot(opportunity)
    opportunity.title = title
    opportunity.source_id = source_id
    opportunity.customer_id = customer_id
    opportunity.business_unit_id = business_unit_id
    opportunity.buyer_name = str(form.get("buyer_name") or "")
    opportunity.notice_identifier = str(form.get("notice_identifier") or "")
    opportunity.notice_type = str(form.get("notice_type") or "")
    opportunity.procurement_stage = str(form.get("procurement_stage") or "")
    opportunity.deadline_date = deadline_date
    opportunity.value_high = value_high
    opportunity.cpv_codes = str(form.get("cpv_codes") or "")
    opportunity.location = str(form.get("location") or "")
    opportunity.source_url = str(form.get("source_url") or "")
    opportunity.summary = str(form.get("summary") or "")
    opportunity.status = str(form.get("status") or "new")
    opportunity.relevance_score = relevance_score
    opportunity.relevance_rationale = str(form.get("relevance_rationale") or "")
    opportunity.updated_at = utc_now()
    update_with_audit(session, opportunity, f"Updated opportunity {opportunity.title}", before)
    return redirect("/opportunities")


@router.post("/opportunities/{opportunity_id}/delete")
def delete_opportunity(opportunity_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    delete_children(session, ExtractedQualityQuestion, "opportunity_id", opportunity.id)
    delete_children(session, OpportunityDocument, "opportunity_id", opportunity.id)
    delete_children(session, DocumentRetrievalTask, "opportunity_id", opportunity.id)
    clear_links(session, PortalInformationConnector, "default_opportunity_id", opportunity.id)
    clear_links(session, PortalRetrievalRun, "opportunity_id", opportunity.id)
    clear_links(session, ClientInterestSignal, "opportunity_id", opportunity.id)
    clear_links(session, ExtractedRequirement, "opportunity_id", opportunity.id)
    clear_links(session, KRAFinding, "opportunity_id", opportunity.id)
    clear_links(session, KRAResearchRun, "opportunity_id", opportunity.id)
    delete_children(session, OpportunityMatchEvidence, "opportunity_id", opportunity.id)
    delete_children(session, OpportunityFeedback, "opportunity_id", opportunity.id)
    delete_with_audit(session, opportunity, f"Deleted opportunity {opportunity.title}")
    return redirect("/opportunities")


@router.post("/opportunities/{opportunity_id}/feedback")
async def create_opportunity_feedback(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    form = await request.form()
    feedback_type = str(form.get("feedback_type") or "other")
    allowed = {"relevant", "not_relevant", "wrong_customer", "wrong_business_unit", "duplicate", "stale", "other"}
    if feedback_type not in allowed:
        return validation_error_response(["Feedback type is not recognised."], "/opportunities")
    feedback = OpportunityFeedback(
        opportunity_id=opportunity.id,
        reviewer=get_current_user(request).username,
        feedback_type=feedback_type,
        notes=str(form.get("notes") or ""),
    )
    if feedback_type in {"not_relevant", "wrong_customer", "wrong_business_unit", "duplicate", "stale"}:
        opportunity.status = "needs_review"
        opportunity.relevance_rationale = f"{opportunity.relevance_rationale}\nReviewer feedback: {feedback_type}".strip()
        session.add(opportunity)
    save_with_audit(session, feedback, "create", f"Feedback {feedback_type} for opportunity {opportunity.title}")
    return redirect("/opportunities")


@router.get("/opportunities/{opportunity_id}/documents", response_class=HTMLResponse)
def opportunity_documents(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    documents = list(session.exec(select(OpportunityDocument).where(OpportunityDocument.opportunity_id == opportunity_id)))
    questions = list(session.exec(select(ExtractedQualityQuestion).where(ExtractedQualityQuestion.opportunity_id == opportunity_id)))
    tasks = list(session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.opportunity_id == opportunity_id)))
    return templates.TemplateResponse(
        request,
        "documents.html",
        context(
            request,
            opportunity=opportunity,
            documents=documents,
            questions=questions,
            tasks=tasks,
            task_status_options=["requested", "in_progress", "blocked", "review_required", "completed"],
            **reference_context(session),
        ),
    )


@router.post("/opportunities/{opportunity_id}/documents")
async def create_document(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    form = await request.form()
    title = str(form.get("title") or "").strip()
    if not title:
        return validation_error_response(["Document title is required."], f"/opportunities/{opportunity_id}/documents")
    document = OpportunityDocument(
        opportunity_id=opportunity_id,
        title=title,
        document_type=str(form.get("document_type") or "itt_extract"),
        url_or_path=str(form.get("url_or_path") or ""),
        retrieval_status=str(form.get("retrieval_status") or "linked"),
        platform_name=str(form.get("platform_name") or ""),
        content_summary=str(form.get("content_summary") or ""),
        notes=str(form.get("notes") or ""),
    )
    session.add(document)
    session.flush()
    log_event(session, entity_type="OpportunityDocument", entity_id=document.id, action="create", summary=f"Created document {document.title}", after=document)
    extract_document_intelligence(session, opportunity, document, str(form.get("document_text") or ""))
    session.commit()
    return redirect(f"/opportunities/{opportunity_id}/documents")


@router.post("/opportunities/{opportunity_id}/documents/{document_id}")
async def update_document(opportunity_id: int, document_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    document = session.get(OpportunityDocument, document_id)
    if not document or document.opportunity_id != opportunity_id:
        return redirect(f"/opportunities/{opportunity_id}/documents")
    form = await request.form()
    title = str(form.get("title") or "").strip()
    if not title:
        return validation_error_response(["Document title is required."], f"/opportunities/{opportunity_id}/documents")
    before = compact_snapshot(document)
    document.title = title
    document.document_type = str(form.get("document_type") or "itt_extract")
    document.url_or_path = str(form.get("url_or_path") or "")
    document.retrieval_status = str(form.get("retrieval_status") or "linked")
    document.human_review_status = str(form.get("human_review_status") or document.human_review_status or "pending")
    document.platform_name = str(form.get("platform_name") or "")
    document.content_summary = str(form.get("content_summary") or "")
    document.notes = str(form.get("notes") or "")
    update_with_audit(session, document, f"Updated document {document.title}", before)
    return redirect(f"/opportunities/{opportunity_id}/documents")


@router.post("/opportunities/{opportunity_id}/documents/{document_id}/delete")
def delete_document(opportunity_id: int, document_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    document = session.get(OpportunityDocument, document_id)
    if not document or document.opportunity_id != opportunity_id:
        return redirect(f"/opportunities/{opportunity_id}/documents")
    delete_children(session, ExtractedQualityQuestion, "document_id", document.id)
    delete_with_audit(session, document, f"Deleted document {document.title}")
    return redirect(f"/opportunities/{opportunity_id}/documents")


@router.post("/opportunities/{opportunity_id}/tasks")
async def create_document_task(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    portal_id = parse_optional_int(form.get("portal_instance_id"), "Portal instance", errors)
    due_date = parse_optional_date(form.get("due_date"), "Due date", errors)
    if errors:
        return validation_error_response(errors, f"/opportunities/{opportunity_id}/documents")
    task = DocumentRetrievalTask(
        opportunity_id=opportunity_id,
        portal_instance_id=portal_id,
        task_name=str(form.get("task_name") or "Manual portal document retrieval"),
        status=str(form.get("status") or "requested"),
        due_date=due_date,
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, task, "create", f"Created document retrieval task {task.task_name}")
    return redirect(f"/opportunities/{opportunity_id}/documents")


@router.post("/tasks/{task_id}")
async def update_task(task_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    task = session.get(DocumentRetrievalTask, task_id)
    if not task:
        return redirect("/portals")
    form = await request.form()
    errors: list[str] = []
    portal_id = parse_optional_int(form.get("portal_instance_id"), "Portal instance", errors)
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    due_date = parse_optional_date(form.get("due_date"), "Due date", errors)
    return_to = str(form.get("return_to") or "/portals")
    task_name = str(form.get("task_name") or "").strip()
    if not task_name:
        errors.append("Task name is required.")
    if errors:
        return validation_error_response(errors, return_to)
    before = compact_snapshot(task)
    task.task_name = task_name
    task.opportunity_id = opportunity_id
    task.portal_instance_id = portal_id
    task.status = str(form.get("status") or "requested")
    task.owner = str(form.get("owner") or "local-user")
    task.due_date = due_date
    task.notes = str(form.get("notes") or "")
    update_with_audit(session, task, f"Updated retrieval task {task.task_name}", before)
    return redirect(return_to)


@router.post("/tasks/{task_id}/delete")
async def delete_task(task_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    task = session.get(DocumentRetrievalTask, task_id)
    form = await request.form()
    return_to = str(form.get("return_to") or "/portals")
    if not task:
        return redirect(return_to)
    delete_with_audit(session, task, f"Deleted retrieval task {task.task_name}")
    return redirect(return_to)
