from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import ExtractedQualityQuestion, ExtractedRequirement, Opportunity, OpportunityDocument
from app.requirement_taxonomy import assess_requirement_confidence, classify_requirement_category
from app.route_utils import context, delete_with_audit, paged, redirect, reference_context, save_with_audit, templates, update_with_audit


router = APIRouter()


@router.get("/requirements", response_class=HTMLResponse)
def requirements(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    reqs, req_pagination = paged(
        session,
        select(ExtractedRequirement).order_by(col(ExtractedRequirement.created_at).desc()),
        request,
        param="requirements_page",
    )
    questions, question_pagination = paged(
        session,
        select(ExtractedQualityQuestion).order_by(col(ExtractedQualityQuestion.created_at).desc()),
        request,
        param="questions_page",
    )
    opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(300)))
    documents = list(session.exec(select(OpportunityDocument).order_by(col(OpportunityDocument.extracted_at).desc()).limit(300)))
    opportunity_map = {item.id: item for item in opportunities}
    return templates.TemplateResponse(
        request,
        "requirements.html",
        context(
            request,
            requirements=reqs,
            questions=questions,
            opportunities=opportunities,
            opportunity_map=opportunity_map,
            documents=documents,
            requirements_pagination=req_pagination,
            questions_pagination=question_pagination,
            **reference_context(session),
        ),
    )


@router.post("/requirements")
async def create_requirement(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    theme = str(form.get("requirement_theme") or "").strip()
    text = str(form.get("requirement_text") or "").strip()
    if not theme or not text:
        errors.append("Requirement theme and text are required.")
    if errors:
        return validation_error_response(errors, "/requirements")
    opportunity = session.get(Opportunity, opportunity_id) if opportunity_id else None
    if opportunity and not customer_id:
        customer_id = opportunity.customer_id
    category = str(form.get("requirement_category") or classify_requirement_category(text, theme))
    confidence, confidence_reason = assess_requirement_confidence(
        text,
        theme=theme,
        category=category,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        source_reference=str(form.get("requirement_source") or ""),
    )
    submitted_confidence = str(form.get("confidence") or "").strip()
    requirement = ExtractedRequirement(
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        requirement_theme=theme,
        requirement_category=category,
        requirement_text=text,
        requirement_source=str(form.get("requirement_source") or ""),
        confidence=submitted_confidence if submitted_confidence and submitted_confidence != "agent" else confidence,
        confidence_reason=confidence_reason,
        human_review_status=str(form.get("human_review_status") or "pending"),
    )
    save_with_audit(session, requirement, "create", f"Created requirement {requirement.requirement_theme}")
    return redirect("/requirements")


@router.post("/requirements/{requirement_id}")
async def update_requirement(requirement_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    requirement = session.get(ExtractedRequirement, requirement_id)
    if not requirement:
        return redirect("/requirements")
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    theme = str(form.get("requirement_theme") or "").strip()
    text = str(form.get("requirement_text") or "").strip()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    if not theme or not text:
        errors.append("Requirement theme and text are required.")
    if errors:
        return validation_error_response(errors, return_to)
    opportunity = session.get(Opportunity, opportunity_id) if opportunity_id else None
    if opportunity and not customer_id:
        customer_id = opportunity.customer_id
    category = str(form.get("requirement_category") or classify_requirement_category(text, theme))
    confidence, confidence_reason = assess_requirement_confidence(
        text,
        theme=theme,
        category=category,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        source_reference=str(form.get("requirement_source") or ""),
    )
    submitted_confidence = str(form.get("confidence") or "").strip()
    before = compact_snapshot(requirement)
    requirement.customer_id = customer_id
    requirement.opportunity_id = opportunity_id
    requirement.requirement_theme = theme
    requirement.requirement_category = category
    requirement.requirement_text = text
    requirement.requirement_source = str(form.get("requirement_source") or "")
    requirement.confidence = submitted_confidence if submitted_confidence and submitted_confidence != "agent" else confidence
    requirement.confidence_reason = confidence_reason
    requirement.human_review_status = str(form.get("human_review_status") or "pending")
    update_with_audit(session, requirement, f"Updated requirement {requirement.requirement_theme}", before)
    return redirect(return_to)


@router.post("/requirements/{requirement_id}/delete")
async def delete_requirement(requirement_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    requirement = session.get(ExtractedRequirement, requirement_id)
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    if not requirement:
        return redirect(return_to)
    delete_with_audit(session, requirement, f"Deleted requirement {requirement.requirement_theme}")
    return redirect(return_to)


@router.post("/quality-questions")
async def create_quality_question(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    document_id = parse_optional_int(form.get("document_id"), "Document", errors)
    text = str(form.get("question_text") or "").strip()
    if opportunity_id is None:
        errors.append("Opportunity is required for a quality question.")
    if not text:
        errors.append("Question text is required.")
    if errors:
        return validation_error_response(errors, "/requirements")
    opportunity = session.get(Opportunity, opportunity_id) if opportunity_id else None
    if opportunity and not customer_id:
        customer_id = opportunity.customer_id
    theme = str(form.get("requirement_theme") or "")
    category = str(form.get("requirement_category") or classify_requirement_category(text, theme))
    confidence, confidence_reason = assess_requirement_confidence(
        text,
        theme=theme,
        category=category,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        source_reference=str(form.get("section_reference") or ""),
        weighting=str(form.get("weighting") or ""),
    )
    submitted_confidence = str(form.get("confidence") or "").strip()
    question = ExtractedQualityQuestion(
        opportunity_id=opportunity_id,
        customer_id=customer_id,
        document_id=document_id,
        section_reference=str(form.get("section_reference") or ""),
        question_text=text,
        weighting=str(form.get("weighting") or ""),
        requirement_theme=theme,
        requirement_category=category,
        confidence=submitted_confidence if submitted_confidence and submitted_confidence != "agent" else confidence,
        confidence_reason=confidence_reason,
        human_review_status=str(form.get("human_review_status") or "pending"),
    )
    save_with_audit(session, question, "create", "Created quality question")
    return redirect("/requirements")


@router.post("/quality-questions/{question_id}")
async def update_quality_question(question_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    question = session.get(ExtractedQualityQuestion, question_id)
    if not question:
        return redirect("/requirements")
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    text = str(form.get("question_text") or "").strip()
    if not text:
        return validation_error_response(["Question text is required."], return_to)
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors) or question.opportunity_id
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    document_id = parse_optional_int(form.get("document_id"), "Document", errors)
    if errors:
        return validation_error_response(errors, return_to)
    opportunity = session.get(Opportunity, opportunity_id) if opportunity_id else None
    if opportunity and not customer_id:
        customer_id = opportunity.customer_id
    theme = str(form.get("requirement_theme") or "")
    category = str(form.get("requirement_category") or classify_requirement_category(text, theme))
    confidence, confidence_reason = assess_requirement_confidence(
        text,
        theme=theme,
        category=category,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        source_reference=str(form.get("section_reference") or ""),
        weighting=str(form.get("weighting") or ""),
    )
    submitted_confidence = str(form.get("confidence") or "").strip()
    before = compact_snapshot(question)
    question.opportunity_id = opportunity_id
    question.customer_id = customer_id
    question.document_id = document_id
    question.section_reference = str(form.get("section_reference") or "")
    question.question_text = text
    question.weighting = str(form.get("weighting") or "")
    question.requirement_theme = theme
    question.requirement_category = category
    question.confidence = submitted_confidence if submitted_confidence and submitted_confidence != "agent" else confidence
    question.confidence_reason = confidence_reason
    question.human_review_status = str(form.get("human_review_status") or "pending")
    update_with_audit(session, question, "Updated quality question", before)
    return redirect(return_to)


@router.post("/quality-questions/{question_id}/delete")
async def delete_quality_question(question_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    question = session.get(ExtractedQualityQuestion, question_id)
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    if not question:
        return redirect(return_to)
    delete_with_audit(session, question, "Deleted quality question")
    return redirect(return_to)
