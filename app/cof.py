from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote_plus

from sqlmodel import Session, col, select

from app.audit import log_event
from app.models import (
    BusinessUnit,
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    CustomerWatchProfile,
    DigestProfile,
    DocumentRetrievalTask,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    IntelligenceReport,
    Opportunity,
    OpportunityDocument,
    OpportunityMatchEvidence,
    PortalInformationConnector,
    ProcurementSource,
)


COF_CLIENT_PREFIX = "COF Client "
COF_BUSINESS_UNIT = "Contracted Opportunity Finder"
COF_DIGEST_NAME = "COF Monday report send"
CLIENT_VISIBLE_STATUSES = {
    "pin",
    "live",
    "closing_soon",
    "interested",
    "awarded",
    "watch",
    "document_retrieval_required",
    "questions_extracted",
    "approved",
}
COF_REVIEW_PENDING_STATUSES = {"new", "needs_review", "review_required", "pending_review"}


def reset_cof_workspace_records(session: Session, actor: str = "local-user") -> dict[str, int]:
    """Remove COF-owned workspace data before reapplying the design-brief pack.

    The cleanup is deliberately scoped to the COF business unit, COF client
    records and COF-generated outputs. It leaves unrelated app data alone.
    """
    summary = {
        "opportunities": 0,
        "documents": 0,
        "requirements": 0,
        "questions": 0,
        "signals": 0,
        "tasks": 0,
        "portals": 0,
        "connectors": 0,
        "reports": 0,
        "customers": 0,
        "watch_profiles": 0,
        "digests": 0,
    }
    unit = session.exec(select(BusinessUnit).where(BusinessUnit.name == COF_BUSINESS_UNIT)).first()
    portfolio = session.exec(select(Customer).where(Customer.customer_name == "Procter Street COF Portfolio")).first()
    clients = list(session.exec(select(Customer).where(col(Customer.customer_name).startswith(COF_CLIENT_PREFIX))))
    customer_ids = {item.id for item in [portfolio, *clients] if item and item.id}
    unit_id = unit.id if unit and unit.id else None
    opportunities = [
        item
        for item in session.exec(select(Opportunity))
        if (item.customer_id and item.customer_id in customer_ids)
        or (unit_id and item.business_unit_id == unit_id)
        or (item.notice_identifier or "").startswith(("cof-pipeline-", "cof-live-pilot-"))
    ]
    opportunity_ids = {item.id for item in opportunities if item.id}
    if opportunity_ids:
        for model, key in [
            (ClientInterestSignal, "signals"),
            (DocumentRetrievalTask, "tasks"),
            (ExtractedQualityQuestion, "questions"),
            (ExtractedRequirement, "requirements"),
            (OpportunityDocument, "documents"),
            (OpportunityMatchEvidence, "requirements"),
        ]:
            rows = list(session.exec(select(model).where(model.opportunity_id.in_(opportunity_ids))))
            for row in rows:
                session.delete(row)
            summary[key] += len(rows)
        for opportunity in opportunities:
            session.delete(opportunity)
        summary["opportunities"] = len(opportunities)
    if customer_ids:
        rows = list(session.exec(select(CustomerWatchProfile).where(CustomerWatchProfile.customer_id.in_(customer_ids))))
        for row in rows:
            session.delete(row)
        summary["watch_profiles"] += len(rows)
    portals = [
        item
        for item in session.exec(select(BuyerPortalInstance))
        if (item.customer_id and item.customer_id in customer_ids)
        or (unit_id and item.business_unit_id == unit_id)
        or item.portal_name.startswith("COF ")
    ]
    portal_ids = {item.id for item in portals if item.id}
    if portal_ids:
        connectors = list(session.exec(select(PortalInformationConnector).where(PortalInformationConnector.portal_instance_id.in_(portal_ids))))
        for connector in connectors:
            session.delete(connector)
        summary["connectors"] = len(connectors)
    for portal in portals:
        session.delete(portal)
    summary["portals"] = len(portals)
    reports = [
        item
        for item in session.exec(select(IntelligenceReport))
        if (item.report_type or "").startswith("cof_") or (unit_id and item.business_unit_id == unit_id)
    ]
    for report in reports:
        session.delete(report)
    summary["reports"] = len(reports)
    digests = list(session.exec(select(DigestProfile).where(DigestProfile.name == COF_DIGEST_NAME)))
    for digest in digests:
        session.delete(digest)
    summary["digests"] = len(digests)
    for customer in clients:
        session.delete(customer)
    if portfolio:
        session.delete(portfolio)
    summary["customers"] = len(clients) + (1 if portfolio else 0)
    if unit:
        session.delete(unit)
    session.flush()
    log_event(
        session,
        entity_type="COFWorkspace",
        entity_id=unit_id,
        action="reset",
        summary="Reset COF workspace to the design-brief baseline.",
        after=summary,
        actor=actor,
    )
    return summary


def seed_cof_live_pilot_content(session: Session, actor: str = "local-user") -> dict[str, int]:
    unit = session.exec(select(BusinessUnit).where(BusinessUnit.name == COF_BUSINESS_UNIT)).first()
    clients = list(session.exec(select(Customer).where(col(Customer.customer_name).startswith(COF_CLIENT_PREFIX))))
    if not unit or len(clients) < 11:
        return {"opportunities": 0, "documents": 0, "requirements": 0, "questions": 0, "signals": 0}

    source = (
        session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender")).first()
        or session.exec(select(ProcurementSource)).first()
    )
    created = {"opportunities": 0, "documents": 0, "requirements": 0, "questions": 0, "signals": 0, "reports": 0}
    clients_by_name = {client.customer_name: client for client in clients}
    today = date.today()
    rows = [
        ("COF Client 01", "Highways maintenance framework PIN", "County Highways Authority", "pin", "planning", today + timedelta(days=45), 2400000, "Highways maintenance, drainage, surfacing and traffic management pipeline notice.", "highways maintenance", "asset_and_field_operations"),
        ("COF Client 02", "School estate decarbonisation programme", "Education Estates Partnership", "live", "tender", today + timedelta(days=28), 1800000, "Retrofit, heat pumps, solar PV, building fabric and energy efficiency works across school estate sites.", "school estate decarbonisation", "sustainability_and_social_value"),
        ("COF Client 03", "Bridge strengthening and refurbishment works", "Metropolitan Borough Council", "closing_soon", "tender", today + timedelta(days=8), 3200000, "Bridge strengthening, concrete repairs, parapets and structural inspection requirements.", "bridge strengthening", "asset_and_field_operations"),
        ("COF Client 04", "Public estate cyber and CCTV services", "City Council", "interested", "tender", today + timedelta(days=21), 950000, "Cyber security, CCTV, access control and managed security service requirements.", "security systems", "cyber_and_information_security"),
        ("COF Client 05", "Facilities and asset management services", "NHS Property Body", "watch", "early engagement", today + timedelta(days=60), 4100000, "Planned and reactive maintenance, estate compliance, asset lifecycle and helpdesk requirements.", "facilities management", "asset_and_field_operations"),
        ("COF Client 06", "Transport depot maintenance contract", "Regional Transport Authority", "live", "tender", today + timedelta(days=31), 1600000, "Depot maintenance, passenger systems, fleet facilities and transport infrastructure service continuity.", "transport maintenance", "service_management_and_operations"),
        ("COF Client 07", "Public building refurbishment lot", "District Council", "awarded", "award", today - timedelta(days=12), 2200000, "Award evidence for civic building refurbishment and M&E upgrades.", "public building works", "commercial_and_procurement"),
        ("COF Client 08", "Public realm drainage and grounds maintenance PIN", "County Council", "pin", "planning", today + timedelta(days=75), 1250000, "Grounds maintenance, drainage, flood resilience and public realm works.", "grounds maintenance", "asset_and_field_operations"),
        ("COF Client 09", "Fire alarm and building controls maintenance", "Further Education College", "document_retrieval_required", "tender", today + timedelta(days=18), 720000, "Fire alarm, intruder alarm, building controls, compliance testing and reactive maintenance.", "building controls", "compliance_and_assurance"),
        ("COF Client 10", "Digital reporting dashboard and integration support", "Unitary Authority", "questions_extracted", "tender", today + timedelta(days=24), 650000, "Data platform integration, reporting dashboards, support services and service desk requirements.", "data platform", "digital_data_and_integration"),
        ("COF Client 11", "Specialist concrete repair and retaining wall works", "Scottish Local Authority", "needs_review", "tender", today + timedelta(days=34), 1450000, "Specialist concrete repairs, waterproofing and retaining wall maintenance. Needs source verification before client release.", "concrete repairs", "asset_and_field_operations"),
        ("COF Client 04", "Legacy CCTV monitoring system replacement", "City Council", "review_required", "tender", today + timedelta(days=15), 820000, "CCTV monitoring, cyber hardening, network connectivity and support model. Human review required.", "CCTV", "cyber_and_information_security"),
        ("COF Client 05", "Minor works asset survey award evidence", "Housing Association", "awarded", "award", today - timedelta(days=20), 330000, "Award evidence for asset survey and minor works packages.", "asset survey", "commercial_and_procurement"),
    ]
    for index, row in enumerate(rows, start=1):
        client_name, title, buyer, status, stage, deadline, value, summary, theme, category = row
        client = clients_by_name[client_name]
        created["opportunities"] += _ensure_cof_opportunity(
            session,
            source,
            unit,
            client,
            index,
            title,
            buyer,
            status,
            stage,
            deadline,
            value,
            summary,
            theme,
            category,
        )

    created["signals"] += _ensure_interest(session, "COF Client 04", "Public estate cyber and CCTV services", "interested", "Account Lead action required: retrieve tender documents and confirm client follow-up.")
    created["signals"] += _ensure_interest(session, "COF Client 09", "Fire alarm and building controls maintenance", "interested", "Account Lead action required: confirm portal document access.")
    created["signals"] += _ensure_interest(session, "COF Client 10", "Digital reporting dashboard and integration support", "interested", "Account Lead action required: share extracted quality questions after human review.")
    created["signals"] += _ensure_interest(session, "COF Client 05", "Facilities and asset management services", "watch", "Client asked to keep this under weekly watch.")
    created["signals"] += _ensure_interest(session, "COF Client 08", "Public realm drainage and grounds maintenance PIN", "watch", "PIN to monitor for tender publication.")

    _ensure_cof_digest(session, unit)
    created["reports"] += _ensure_cof_seed_report(session, unit)
    session.flush()
    log_event(
        session,
        entity_type="COFSeed",
        entity_id=unit.id,
        action="apply",
        summary="Applied Procter Street COF operating content pack.",
        after=created,
        actor=actor,
    )
    return created


def cof_friday_readiness(session: Session) -> dict[str, int | bool]:
    """Return Friday review checks for the Procter Street COF operating rhythm."""
    unit = session.exec(select(BusinessUnit).where(BusinessUnit.name == COF_BUSINESS_UNIT)).first()
    if not unit or not unit.id:
        return {
            "configured": False,
            "unreviewed_opportunities": 0,
            "clients_without_visible_items": 0,
            "missing_source_url": 0,
            "missing_deadline": 0,
            "interested_missing_retrieval_task": 0,
            "reports_ready_to_send": 0,
        }
    opportunities = list(
        session.exec(
            select(Opportunity).where(
                Opportunity.business_unit_id == unit.id,
                Opportunity.archived == False,  # noqa: E712
            )
        )
    )
    clients = list(session.exec(select(Customer).where(Customer.business_unit_id == unit.id)))
    tasks = list(session.exec(select(DocumentRetrievalTask)))
    task_opportunity_ids = {task.opportunity_id for task in tasks if task.opportunity_id}
    visible_by_client: dict[int, int] = {}
    for item in opportunities:
        if item.customer_id and item.status in CLIENT_VISIBLE_STATUSES:
            visible_by_client[item.customer_id] = visible_by_client.get(item.customer_id, 0) + 1
    interested = [item for item in opportunities if item.status == "interested"]
    digest = session.exec(select(DigestProfile).where(DigestProfile.name == COF_DIGEST_NAME)).first()
    return {
        "configured": True,
        "unreviewed_opportunities": sum(1 for item in opportunities if item.status in COF_REVIEW_PENDING_STATUSES),
        "clients_without_visible_items": sum(1 for client in clients if client.customer_name.startswith(COF_CLIENT_PREFIX) and not visible_by_client.get(client.id or 0)),
        "missing_source_url": sum(1 for item in opportunities if not item.source_url),
        "missing_deadline": sum(1 for item in opportunities if not item.deadline_date and item.status not in {"awarded"}),
        "interested_missing_retrieval_task": sum(1 for item in interested if item.id not in task_opportunity_ids),
        "reports_ready_to_send": 1 if digest and digest.enabled else 0,
    }


def _ensure_cof_opportunity(
    session: Session,
    source: ProcurementSource | None,
    unit: BusinessUnit,
    client: Customer,
    index: int,
    title: str,
    buyer: str,
    status: str,
    stage: str,
    deadline: date,
    value: float,
    summary: str,
    theme: str,
    category: str,
) -> int:
    notice_id = f"cof-pipeline-{index:02d}"
    legacy_notice_id = f"cof-live-pilot-{index:02d}"
    opportunity = session.exec(select(Opportunity).where(Opportunity.notice_identifier == notice_id)).first()
    if not opportunity:
        opportunity = session.exec(select(Opportunity).where(Opportunity.notice_identifier == legacy_notice_id)).first()
    created = 0
    if not opportunity:
        opportunity = Opportunity(source_id=source.id if source else None, notice_identifier=notice_id, title=title)
        created = 1
    opportunity.customer_id = client.id
    opportunity.business_unit_id = unit.id
    opportunity.buyer_name = buyer
    opportunity.notice_type = "award" if status == "awarded" else "planning" if status == "pin" else "tender"
    opportunity.procurement_stage = stage
    opportunity.deadline_date = deadline
    opportunity.value_high = value
    opportunity.currency = "GBP"
    opportunity.cpv_codes = client.strategic_notes
    opportunity.source_url = f"https://www.find-tender.service.gov.uk/Search/Results?Keywords={quote_plus(title)}"
    opportunity.summary = summary
    opportunity.status = status
    opportunity.archived = False
    opportunity.archived_at = None
    opportunity.archive_reason = ""
    opportunity.archive_previous_status = ""
    opportunity.archive_note = ""
    opportunity.relevance_score = 86 if status not in {"needs_review", "review_required"} else 58
    opportunity.relevance_rationale = f"Matched COF client keywords: {theme}. Review Lead approval required before client action."
    opportunity.content_hash = notice_id
    session.add(opportunity)
    session.flush()
    _ensure_match_evidence(session, opportunity, client, unit, theme, category)
    _ensure_requirement(session, opportunity, client, theme, category, summary)
    if status in {"document_retrieval_required", "questions_extracted", "interested"}:
        _ensure_document_and_questions(session, opportunity, theme)
    return created


def _ensure_match_evidence(session: Session, opportunity: Opportunity, client: Customer, unit: BusinessUnit, theme: str, category: str) -> None:
    existing = session.exec(
        select(OpportunityMatchEvidence).where(
            OpportunityMatchEvidence.opportunity_id == opportunity.id,
            OpportunityMatchEvidence.matched_term == theme,
        )
    ).first()
    if existing:
        return
    session.add(
        OpportunityMatchEvidence(
            opportunity_id=opportunity.id,
            customer_id=client.id,
            business_unit_id=unit.id,
            evidence_type="cof_seed_match",
            matched_term=theme,
            source_field="title_summary_keywords",
            score_delta=25,
            rationale=f"COF seed matched {client.customer_name} watch terms for {category.replace('_', ' ')}.",
        )
    )


def _ensure_requirement(session: Session, opportunity: Opportunity, client: Customer, theme: str, category: str, text: str) -> None:
    existing = session.exec(
        select(ExtractedRequirement).where(
            ExtractedRequirement.opportunity_id == opportunity.id,
            ExtractedRequirement.requirement_theme == theme,
        )
    ).first()
    if existing:
        return
    session.add(
        ExtractedRequirement(
            opportunity_id=opportunity.id,
            customer_id=client.id,
            requirement_theme=theme,
            requirement_category=category,
            requirement_text=text,
            requirement_source=opportunity.source_url,
            confidence="high" if opportunity.status not in {"needs_review", "review_required"} else "medium",
            confidence_reason="Captured from COF portfolio source evidence; human review required.",
            human_review_status="approved" if opportunity.status not in {"needs_review", "review_required"} else "pending",
        )
    )


def _ensure_document_and_questions(session: Session, opportunity: Opportunity, theme: str) -> None:
    document = session.exec(select(OpportunityDocument).where(OpportunityDocument.opportunity_id == opportunity.id)).first()
    if not document:
        document = OpportunityDocument(
            opportunity_id=opportunity.id or 0,
            title=f"{opportunity.title} permitted ITT extract",
            document_type="itt_extract",
            url_or_path=opportunity.source_url,
            retrieval_status="review_required",
            human_review_status="pending",
            platform_name="COF portal family",
            content_summary=f"Permitted text extract for {theme}; quality questions and weightings require reviewer verification.",
            classification_label="COF permitted extract",
            source_access_notes="On-demand document retrieval triggered by client interest. No portal login is automated.",
            notes="Quality question 1: Describe your delivery approach, mobilisation controls and evidence of similar public-sector work. Weighting 35%. Quality question 2: Explain risk management, social value and reporting governance. Weighting 25%.",
        )
        session.add(document)
        session.flush()
    questions = [
        ("Delivery approach and mobilisation controls", "35%"),
        ("Risk management, social value and reporting governance", "25%"),
    ]
    for section, weighting in questions:
        exists = session.exec(
            select(ExtractedQualityQuestion).where(
                ExtractedQualityQuestion.opportunity_id == opportunity.id,
                ExtractedQualityQuestion.section_reference == section,
            )
        ).first()
        if exists:
            continue
        session.add(
            ExtractedQualityQuestion(
                opportunity_id=opportunity.id or 0,
                customer_id=opportunity.customer_id,
                document_id=document.id,
                section_reference=section,
                question_text=f"{section}: provide a concise, evidenced response for {opportunity.title}.",
                weighting=weighting,
                requirement_theme=theme,
                requirement_category="commercial_and_procurement",
                confidence="high",
                confidence_reason="Captured from permitted COF extract; human review required.",
                human_review_status="pending",
            )
        )


def _ensure_interest(session: Session, client_name: str, opportunity_title: str, signal: str, notes: str) -> int:
    client = session.exec(select(Customer).where(Customer.customer_name == client_name)).first()
    opportunity = session.exec(select(Opportunity).where(Opportunity.title == opportunity_title)).first()
    if not client or not opportunity:
        return 0
    existing = session.exec(
        select(ClientInterestSignal).where(
            ClientInterestSignal.customer_id == client.id,
            ClientInterestSignal.opportunity_id == opportunity.id,
            ClientInterestSignal.signal == signal,
        )
    ).first()
    if existing:
        existing.notes = existing.notes or notes
        existing.status = "account_lead_action_required" if signal == "interested" else "watching"
        session.add(existing)
        _reconcile_interest_workflow(session, client, opportunity, signal)
        return 0
    session.add(
        ClientInterestSignal(
            opportunity_id=opportunity.id,
            customer_id=client.id,
            contact_name="COF client contact",
            contact_email="relationship-owner@example.com",
            signal=signal,
            notes=notes,
            status="account_lead_action_required" if signal == "interested" else "watching",
        )
    )
    _reconcile_interest_workflow(session, client, opportunity, signal)
    return 1


def _reconcile_interest_workflow(session: Session, client: Customer, opportunity: Opportunity, signal: str) -> None:
    if signal == "interested":
        opportunity.status = "interested"
        session.add(opportunity)
        task = session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.opportunity_id == opportunity.id)).first()
        if not task:
            session.add(
                DocumentRetrievalTask(
                    opportunity_id=opportunity.id,
                    task_name=f"Account Lead action: retrieve documents for {client.customer_name}",
                    status="requested",
                    owner="Client Action Queue",
                    notes="Client interest triggered on-demand portal/document retrieval. No portal login is automated by COF.",
                )
            )
    elif signal == "watch" and opportunity.status not in {"interested", "awarded"}:
        opportunity.status = "watch"
        session.add(opportunity)


def _ensure_cof_digest(session: Session, unit: BusinessUnit) -> None:
    existing = session.exec(select(DigestProfile).where(DigestProfile.name == COF_DIGEST_NAME)).first()
    if existing:
        return
    session.add(
        DigestProfile(
            name=COF_DIGEST_NAME,
            report_type="cof_final_customer_pack",
            business_unit_id=unit.id,
            recipients="",
            frequency_label="Monday",
            enabled=True,
            export_format="pdf",
        )
    )


def _ensure_cof_seed_report(session: Session, unit: BusinessUnit) -> int:
    report_name = "COF internal review pack - portfolio baseline"
    existing = None
    for candidate_name in [report_name, "COF weekly portfolio report - live pilot baseline"]:
        existing = session.exec(select(IntelligenceReport).where(IntelligenceReport.report_name == candidate_name)).first()
        if existing:
            break
    from app.reports import generate_cof_weekly_report_markdown

    if existing:
        existing.report_name = report_name
        existing.report_type = "cof_internal_review_pack"
        existing.customer_id = None
        existing.business_unit_id = unit.id
        existing.markdown = generate_cof_weekly_report_markdown(
            session,
            report_name,
            "cof_internal_review_pack",
            business_unit_id=unit.id,
        )
        session.add(existing)
        return 0

    report = IntelligenceReport(
        report_name=report_name,
        report_type="cof_internal_review_pack",
        business_unit_id=unit.id,
        markdown=generate_cof_weekly_report_markdown(
            session,
            report_name,
            "cof_internal_review_pack",
            business_unit_id=unit.id,
        ),
    )
    session.add(report)
    return 1
