from __future__ import annotations

import re

from sqlmodel import Session, select

from app.audit import compact_snapshot, log_event
from app.models import BusinessUnit, Customer, ExtractedQualityQuestion, ExtractedRequirement, Opportunity, utc_now
from app.requirement_taxonomy import assess_requirement_confidence, classify_requirement_category


AUTO_APPROVE_SCORE = 70
REVIEW_SCORE = 45
AUTO_CLASSIFY_STATUSES = {"", "new", "matched", "watching", "pending_review", "review_required", "early_engagement"}
TERMINAL_STATUSES = {"approved", "rejected", "blocked", "needs_review", "award_notice"}
HIGH_CONFIDENCE = {"high", "strong", "medium", "moderate"}


def agent_classify_catalogue(session: Session, actor: str = "classification-agent") -> dict[str, int]:
    result = {
        "opportunities": 0,
        "auto_approved": 0,
        "review_required": 0,
        "assigned_customers": 0,
        "assigned_business_units": 0,
        "requirements": 0,
        "questions": 0,
    }
    for opportunity in session.exec(select(Opportunity)):
        outcome = agent_classify_opportunity(session, opportunity, actor=actor)
        for key, value in outcome.items():
            result[key] = result.get(key, 0) + value

    for requirement in session.exec(select(ExtractedRequirement)):
        if classify_requirement_record(session, requirement, actor=actor):
            result["requirements"] += 1

    for question in session.exec(select(ExtractedQualityQuestion)):
        if classify_quality_question(session, question, actor=actor):
            result["questions"] += 1

    return result


def agent_classify_opportunity(session: Session, opportunity: Opportunity, actor: str = "classification-agent") -> dict[str, int]:
    result = {
        "opportunities": 0,
        "auto_approved": 0,
        "review_required": 0,
        "assigned_customers": 0,
        "assigned_business_units": 0,
    }
    if not opportunity.id:
        return result

    before = compact_snapshot(opportunity)
    changed = False
    notes: list[str] = []

    customer, customer_reason = _infer_customer(session, opportunity)
    if customer and opportunity.customer_id != customer.id:
        opportunity.customer_id = customer.id
        result["assigned_customers"] += 1
        changed = True
        notes.append(customer_reason)

    unit, unit_reason = _infer_business_unit(session, opportunity, customer)
    if unit and opportunity.business_unit_id != unit.id:
        opportunity.business_unit_id = unit.id
        result["assigned_business_units"] += 1
        changed = True
        notes.append(unit_reason)

    if (opportunity.status or "") in AUTO_CLASSIFY_STATUSES:
        result["opportunities"] = 1
        if _auto_approval_ready(opportunity):
            if opportunity.status != "approved":
                opportunity.status = "approved"
                result["auto_approved"] = 1
                changed = True
            notes.append(
                "Agent auto-approved catalogue entry because relevance, source traceability and BU/customer assignment thresholds were met."
            )
        elif float(opportunity.relevance_score or 0) >= REVIEW_SCORE:
            if opportunity.status != "review_required":
                opportunity.status = "review_required"
                result["review_required"] = 1
                changed = True
            notes.append("Agent queued catalogue entry for review because confidence or assignment thresholds were incomplete.")

    if changed:
        opportunity.relevance_rationale = _append_note(opportunity.relevance_rationale, " ".join(notes))
        opportunity.updated_at = utc_now()
        session.add(opportunity)
        log_event(
            session,
            entity_type="Opportunity",
            entity_id=opportunity.id,
            action="agent_classify",
            summary=f"Agent classified opportunity {opportunity.title}",
            before=before,
            after=opportunity,
            actor=actor,
        )
    return result


def classify_requirement_record(session: Session, requirement: ExtractedRequirement, actor: str = "classification-agent") -> bool:
    before = compact_snapshot(requirement)
    category = classify_requirement_category(requirement.requirement_text, requirement.requirement_theme)
    changed = False
    if requirement.requirement_category != category:
        requirement.requirement_category = category
        changed = True

    opportunity = session.get(Opportunity, requirement.opportunity_id) if requirement.opportunity_id else None
    if opportunity and not requirement.customer_id and opportunity.customer_id:
        requirement.customer_id = opportunity.customer_id
        changed = True
    if not requirement.customer_id:
        inferred_customer, reason = _infer_customer_from_text(
            session,
            f"{requirement.requirement_theme} {requirement.requirement_text} {requirement.requirement_source}",
        )
        if inferred_customer:
            requirement.customer_id = inferred_customer.id
            changed = True

    confidence, reason = assess_requirement_confidence(
        requirement.requirement_text,
        theme=requirement.requirement_theme,
        category=requirement.requirement_category,
        customer_id=requirement.customer_id,
        opportunity_id=requirement.opportunity_id,
        source_reference=requirement.requirement_source,
    )
    if requirement.confidence != confidence:
        requirement.confidence = confidence
        changed = True
    if requirement.confidence_reason != reason:
        requirement.confidence_reason = reason
        changed = True

    confidence = (requirement.confidence or "").lower()
    if (requirement.human_review_status or "") in {"", "pending", "review_required"}:
        next_status = "approved" if confidence in HIGH_CONFIDENCE else "review_required"
        if requirement.human_review_status != next_status:
            requirement.human_review_status = next_status
            changed = True

    if changed:
        session.add(requirement)
        log_event(
            session,
            entity_type="ExtractedRequirement",
            entity_id=requirement.id,
            action="agent_classify",
            summary=f"Agent categorised requirement {requirement.requirement_theme}",
            before=before,
            after=requirement,
            actor=actor,
        )
    return changed


def classify_quality_question(session: Session, question: ExtractedQualityQuestion, actor: str = "classification-agent") -> bool:
    before = compact_snapshot(question)
    category = classify_requirement_category(question.question_text, question.requirement_theme)
    changed = False
    if question.requirement_category != category:
        question.requirement_category = category
        changed = True

    opportunity = session.get(Opportunity, question.opportunity_id) if question.opportunity_id else None
    if opportunity and not question.customer_id and opportunity.customer_id:
        question.customer_id = opportunity.customer_id
        changed = True
    if not question.customer_id:
        inferred_customer, reason = _infer_customer_from_text(
            session,
            f"{question.requirement_theme} {question.question_text} {question.section_reference}",
        )
        if inferred_customer:
            question.customer_id = inferred_customer.id
            changed = True

    confidence, reason = assess_requirement_confidence(
        question.question_text,
        theme=question.requirement_theme,
        category=question.requirement_category,
        customer_id=question.customer_id,
        opportunity_id=question.opportunity_id,
        source_reference=question.section_reference,
        weighting=question.weighting,
    )
    if question.confidence != confidence:
        question.confidence = confidence
        changed = True
    if question.confidence_reason != reason:
        question.confidence_reason = reason
        changed = True

    confidence = (question.confidence or "").lower()
    if (question.human_review_status or "") in {"", "pending", "review_required"}:
        next_status = "approved" if confidence in HIGH_CONFIDENCE else "review_required"
        if question.human_review_status != next_status:
            question.human_review_status = next_status
            changed = True

    if changed:
        session.add(question)
        log_event(
            session,
            entity_type="ExtractedQualityQuestion",
            entity_id=question.id,
            action="agent_classify",
            summary="Agent categorised quality question",
            before=before,
            after=question,
            actor=actor,
        )
    return changed


def _auto_approval_ready(opportunity: Opportunity) -> bool:
    if (opportunity.status or "") in TERMINAL_STATUSES and opportunity.status != "approved":
        return False
    if _looks_like_award(opportunity):
        return False
    has_assignment = bool(opportunity.customer_id or opportunity.business_unit_id)
    has_source = bool(opportunity.source_id or opportunity.source_url)
    return has_assignment and has_source and float(opportunity.relevance_score or 0) >= AUTO_APPROVE_SCORE


def _infer_customer(session: Session, opportunity: Opportunity) -> tuple[Customer | None, str]:
    if opportunity.customer_id:
        customer = session.get(Customer, opportunity.customer_id)
        return customer, ""
    haystack = _opportunity_text(opportunity)
    best: tuple[int, Customer | None, str] = (0, None, "")
    for customer in session.exec(select(Customer).where(Customer.active == True)):  # noqa: E712
        score, matched_terms = _score_terms(haystack, _customer_terms(customer))
        if score > best[0]:
            best = (score, customer, ", ".join(matched_terms[:5]))
    if best[1] and best[0] >= 2:
        return best[1], f"Agent assigned customer {best[1].customer_name} from buyer/source terms: {best[2]}."
    return None, ""


def _infer_customer_from_text(session: Session, text: str) -> tuple[Customer | None, str]:
    haystack = _normalise(text)
    best: tuple[int, Customer | None, str] = (0, None, "")
    for customer in session.exec(select(Customer).where(Customer.active == True)):  # noqa: E712
        score, matched_terms = _score_terms(haystack, _customer_terms(customer))
        if score > best[0]:
            best = (score, customer, ", ".join(matched_terms[:5]))
    exact_customer_match = bool(best[1] and _normalise(best[1].customer_name) in haystack)
    if best[1] and (best[0] >= 2 or exact_customer_match):
        return best[1], f"Agent mapped customer {best[1].customer_name} from requirement terms: {best[2]}."
    return None, ""


def _infer_business_unit(session: Session, opportunity: Opportunity, customer: Customer | None) -> tuple[BusinessUnit | None, str]:
    if opportunity.business_unit_id:
        unit = session.get(BusinessUnit, opportunity.business_unit_id)
        return unit, ""
    if customer and customer.business_unit_id:
        unit = session.get(BusinessUnit, customer.business_unit_id)
        if unit:
            return unit, f"Agent assigned BU {unit.name} from customer profile."

    haystack = _opportunity_text(opportunity)
    best: tuple[int, BusinessUnit | None, str] = (0, None, "")
    for unit in session.exec(select(BusinessUnit).where(BusinessUnit.active == True)):  # noqa: E712
        terms = _split_terms(f"{unit.name}; {unit.description}")
        score, matched_terms = _score_terms(haystack, terms)
        if score > best[0]:
            best = (score, unit, ", ".join(matched_terms[:5]))
    if best[1] and best[0] >= 1:
        return best[1], f"Agent assigned BU {best[1].name} from opportunity terms: {best[2]}."
    return None, ""


def _customer_terms(customer: Customer) -> list[str]:
    return _split_terms(
        "; ".join(
            [
                customer.customer_name,
                customer.buying_entities,
                customer.aliases,
                customer.domain,
            ]
        )
    )


def _score_terms(haystack: str, terms: list[str]) -> tuple[int, list[str]]:
    matched: list[str] = []
    for term in terms:
        if _term_matches(haystack, term):
            matched.append(term)
    return len(matched), matched


def _term_matches(haystack: str, term: str) -> bool:
    term = term.strip().lower()
    if not term:
        return False
    if len(term) <= 3:
        return re.search(rf"\b{re.escape(term)}\b", haystack) is not None
    return term in haystack


def _opportunity_text(opportunity: Opportunity) -> str:
    return _normalise(
        " ".join(
            [
                opportunity.title,
                opportunity.buyer_name,
                opportunity.summary,
                opportunity.cpv_codes,
                opportunity.location,
                opportunity.notice_type,
                opportunity.procurement_stage,
            ]
        )
    )


def _split_terms(value: str) -> list[str]:
    terms: list[str] = []
    for item in re.split(r"[,;\n|]+", value or ""):
        cleaned = _normalise(item)
        if cleaned and cleaned not in terms and cleaned not in {"uk", "public sector", "transport", "services"}:
            terms.append(cleaned)
    return terms


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _looks_like_award(opportunity: Opportunity) -> bool:
    text = _opportunity_text(opportunity)
    return "award" in text or "awarded" in text or "call-off contract" in text


def _append_note(existing: str, note: str) -> str:
    note = re.sub(r"\s+", " ", note or "").strip()
    if not note:
        return existing or ""
    if note in (existing or ""):
        return existing or ""
    return f"{existing.strip()}\n{note}".strip() if existing else note
