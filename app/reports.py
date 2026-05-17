from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.audit import log_event
from app.intelligence import kra_runtime_status
from app.models import (
    BusinessUnit,
    Customer,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    IntelligenceReport,
    KRAFinding,
    Opportunity,
    OpportunityDocument,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.rule_loader import rules_version_summary


def generate_intelligence_report_markdown(
    session: Session,
    report_name: str,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
) -> str:
    opportunity_query = select(Opportunity).order_by(col(Opportunity.updated_at).desc())
    if customer_id:
        opportunity_query = opportunity_query.where(Opportunity.customer_id == customer_id)
    if business_unit_id:
        opportunity_query = opportunity_query.where(Opportunity.business_unit_id == business_unit_id)
    opportunities = list(session.exec(opportunity_query.limit(50)))
    opportunity_ids = [item.id for item in opportunities if item.id]
    requirements = []
    documents = []
    questions = []
    if opportunity_ids:
        requirements = list(session.exec(select(ExtractedRequirement).where(ExtractedRequirement.opportunity_id.in_(opportunity_ids))))
        documents = list(session.exec(select(OpportunityDocument).where(OpportunityDocument.opportunity_id.in_(opportunity_ids))))
        questions = list(session.exec(select(ExtractedQualityQuestion).where(ExtractedQualityQuestion.opportunity_id.in_(opportunity_ids))))
    sources = list(session.exec(select(ProcurementSource).order_by(col(ProcurementSource.name))))
    snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(10)))
    findings = list(session.exec(select(KRAFinding).order_by(col(KRAFinding.created_at).desc()).limit(20)))
    customer = session.get(Customer, customer_id) if customer_id else None
    unit = session.get(BusinessUnit, business_unit_id) if business_unit_id else None
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    runtime = kra_runtime_status()
    source_lines = [
        f"- {source.name}: {source.connector_status}; {source.coverage}; last status {source.last_status or 'not checked'}"
        for source in sources
    ] or ["- No sources configured."]
    opportunity_lines = [
        f"- {item.title} | buyer {item.buyer_name or 'not detected'} | stage {item.procurement_stage or 'n/a'} | status {item.status} | relevance {item.relevance_score:g}"
        for item in opportunities
    ] or ["- No opportunities captured."]
    requirement_lines = [
        f"- {item.requirement_theme}: {item.requirement_text[:220]} ({item.human_review_status})"
        for item in requirements
    ] or ["- No requirements extracted."]
    document_lines = [
        f"- {item.title}: {item.document_type}; {item.retrieval_status}; {item.platform_name or 'no platform'}"
        for item in documents
    ] or ["- No documents captured."]
    question_lines = [
        f"- {item.requirement_theme}: {item.question_text[:220]} weighting {item.weighting or 'not detected'} ({item.human_review_status})"
        for item in questions
    ] or ["- No quality questions extracted."]
    snapshot_lines = [
        f"- {item.checked_at.date()} source {item.source_id}: {item.change_type}; schema {item.detected_schema}; status {item.status_code or item.notes}"
        for item in snapshots
    ] or ["- No source snapshots recorded."]
    finding_lines = [
        f"- {item.title}: {item.summary} ({item.human_review_status})"
        for item in findings
    ] or ["- No KRA findings recorded."]
    return f"""# {report_name}

**Generated at:** {generated_at}  
**Customer:** {customer.customer_name if customer else 'All customers'}  
**Business unit:** {unit.name if unit else 'All business units'}  
**Rules:** {rules_version_summary()}  
**KRA runtime:** provider {runtime['provider']}; mode {runtime['mcp_mode']}; API key configured {runtime['api_key_configured']}

## Purpose

This report consolidates customer, source, portal, opportunity, document and requirement intelligence for human review. It is not a bid/no-bid, legal, procurement, compliance or customer-commitment decision.

## KRA Findings
{chr(10).join(finding_lines)}

## Source Health And Changes
{chr(10).join(source_lines)}

## Recent Source Snapshots
{chr(10).join(snapshot_lines)}

## Opportunity Catalogue
{chr(10).join(opportunity_lines)}

## Documents And Retrieval
{chr(10).join(document_lines)}

## Requirement Themes
{chr(10).join(requirement_lines)}

## Quality Questions And Weightings
{chr(10).join(question_lines)}

## Recommended Human Actions

- Review pending KRA findings and extracted requirements.
- Confirm customer/account ownership and source relevance.
- Prioritise portal document retrieval tasks before bid deadlines.
- Use requirement themes to shape bid, service design and delivery preparation.
"""


def create_report(
    session: Session,
    report_name: str,
    report_type: str = "executive_summary",
    customer_id: int | None = None,
    business_unit_id: int | None = None,
) -> IntelligenceReport:
    report = IntelligenceReport(
        report_name=report_name,
        report_type=report_type,
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        markdown=generate_intelligence_report_markdown(session, report_name, customer_id, business_unit_id),
    )
    session.add(report)
    session.flush()
    log_event(session, entity_type="IntelligenceReport", entity_id=report.id, action="create", summary=f"Created report {report.report_name}", after=report)
    session.commit()
    session.refresh(report)
    return report
