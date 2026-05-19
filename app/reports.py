from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
import re

from sqlmodel import Session, col, select

from app.audit import log_event
from app.intelligence import kra_runtime_status, requirement_themes_for_text
from app.llm import LLMError, generate_llm_text, kra_system_prompt, llm_enabled
from app.models import (
    BusinessUnit,
    ClientInterestSignal,
    Customer,
    DocumentRetrievalTask,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    IntelligenceReport,
    KRAFinding,
    Opportunity,
    OpportunityDocument,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.requirement_taxonomy import category_trend_counts
from app.rule_loader import rules_version_summary


ADMIN_REPORT_TYPES = {"admin_run_log", "automation_run_log", "technical_run_log"}
EXECUTIVE_REPORT_TYPES = {"executive_summary", "executive_pack", "executive_intelligence_pack"}
COF_REPORT_TYPES = {"cof_weekly_client_report", "cof_weekly_portfolio_report"}
REVIEW_READY_STATUSES = {"review_required", "review_ready", "accepted", "approved", "complete", "completed"}
COF_BUSINESS_UNIT_NAME = "Contracted Opportunity Finder"
COF_CLIENT_PREFIX = "COF Client "
COF_PORTFOLIO_CUSTOMER_NAME = "Procter Street COF Portfolio"
COF_CLOSING_SOON_DAYS = 14
COF_RETRIEVED_DOCUMENT_TYPES = {"itt_extract", "automated_retrieval", "retrieved", "permitted_extract"}
COF_PUBLIC_NOTICE_DOCUMENT_TYPES = {"public_notice"}
AI_ARTIFACT_PHRASES = (
    "if helpful",
    "if you want",
    "i can also",
    "i can create",
    "i can help",
    "let me know",
    "as an ai",
    "language model",
    "provided in the prompt",
    "based on the prompt",
    "not enough information in the prompt",
    "source text provided",
    "the prompt does not",
)


def clean_ai_text(value: str, max_chars: int = 2200) -> str:
    """Remove assistant-style scaffolding that weakens exported report credibility."""
    text = (value or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        lowered = line.lower()
        if any(phrase in lowered for phrase in AI_ARTIFACT_PHRASES):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    if len(cleaned) > max_chars:
        clipped = cleaned[:max_chars].rsplit(" ", 1)[0].rstrip(".,;: ")
        cleaned = f"{clipped}..."
    return cleaned


def generate_intelligence_report_markdown(
    session: Session,
    report_name: str,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
    include_ai_brief: bool = True,
) -> str:
    return generate_executive_intelligence_pack_markdown(
        session,
        report_name,
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        include_ai_brief=include_ai_brief,
    )


def generate_executive_intelligence_pack_markdown(
    session: Session,
    report_name: str,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
    include_ai_brief: bool = True,
) -> str:
    context = _report_context(session, customer_id, business_unit_id)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    customer = context["customer"]
    unit = context["unit"]
    scope = _scope_label(customer, unit)
    opportunities, excluded = _executive_opportunities(context["opportunities"], customer)
    current_opportunities = [item for item in opportunities if _signal_type(item) != "Award / market evidence"]
    requirements = _requirements_for_opportunities(context["requirements"], opportunities)
    questions = _questions_for_opportunities(context["questions"], opportunities)
    documents = _documents_for_opportunities(context["documents"], opportunities)
    findings = _findings_for_scope(context["findings"], customer, opportunities)
    confidence, readiness_rows, gaps = _readiness_assessment(context, opportunities, requirements, documents, questions, excluded)
    executive_brief = _executive_brief(
        report_name,
        scope,
        opportunities,
        requirements,
        documents,
        findings,
        gaps,
        include_ai_brief,
    )
    opportunity_blocks = [_opportunity_block(index, item, context["sources_by_id"]) for index, item in enumerate(current_opportunities[:25], start=1)]
    requirement_lines = [_requirement_line(item) for item in requirements[:12]]
    question_lines = [_question_line(item) for item in questions[:8]]
    category_lines = _category_trend_lines(requirements + questions)
    exclusion_note = _exclusion_summary(excluded)

    return f"""# {report_name}

**Report type:** Opportunity Intelligence Digest  
**Generated at:** {generated_at}  
**Scope:** {scope}  
**Credibility status:** {confidence}  
**Decision caveat:** Agent-classified records should be checked before bid, customer, legal or compliance action.

## Purpose

This digest summarises current public-sector opportunity signals for leadership, sales, bid, strategy and delivery review. It is not a bid/no-bid, legal, procurement, compliance or customer-contact decision.

## Executive Summary

{executive_brief}

## Opportunity Coverage

{chr(10).join(readiness_rows)}

## Priority Opportunities

{chr(10).join(opportunity_blocks) if opportunity_blocks else "- No live or early-stage opportunity signals passed the credibility gate for this scope. Run the Admin full cycle after source configuration has been checked."}

## Requirement And Capability Themes

{chr(10).join(requirement_lines) if requirement_lines else "- No categorised requirement themes are available yet. Capture permitted tender text or run approved source checks before using the pack externally."}

## Requirement Category Trends

{chr(10).join(category_lines) if category_lines else "- No category trends are available yet."}

## Quality Questions And Weightings

{chr(10).join(question_lines) if question_lines else "- No quality questions or weighting signals have been extracted yet."}

## Data Quality Notes

{exclusion_note}

## Report Gaps

{chr(10).join(f"- {item}" for item in gaps) if gaps else "- No material report-readiness gaps detected for this scope."}

## Recommended Next Actions

- Review all opportunity, requirement and KRA findings before onward circulation.
- Confirm buyer, deadline, source URL and portal evidence before treating any signal as live.
- Capture permitted tender extracts and quality questions where buyer portals require manual login.
- Use the Admin Run Log report type only when diagnosing source, connector or KRA runtime issues.
"""


def generate_admin_run_log_markdown(
    session: Session,
    report_name: str,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
    include_ai_brief: bool = True,
) -> str:
    context = _report_context(session, customer_id, business_unit_id)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    runtime = kra_runtime_status()
    customer = context["customer"]
    unit = context["unit"]
    scope = _scope_label(customer, unit)
    opportunities = context["opportunities"]
    sources = context["sources"]
    connectors = context["connectors"]
    retrieval_runs = context["retrieval_runs"]
    snapshots = context["snapshots"]
    findings = context["findings"]
    requirements = context["requirements"]
    documents = context["documents"]
    questions = context["questions"]
    sources_by_id = context["sources_by_id"]
    connectors_by_id = context["connectors_by_id"]

    source_lines = [
        f"- {source.name}: active {source.active}; {source.connector_status}; {source.coverage or 'no coverage note'}; last status {source.last_status or 'not checked'}"
        for source in sources
    ] or ["- No sources configured."]
    opportunity_lines = [
        f"- {item.title} | buyer {item.buyer_name or 'not detected'} | stage {item.procurement_stage or 'n/a'} | status {item.status} | relevance {item.relevance_score:g}"
        for item in opportunities
    ] or ["- No opportunities captured."]
    requirement_lines = [_requirement_line(item) for item in requirements] or ["- No requirements extracted."]
    document_lines = [_document_line(item) for item in documents] or ["- No documents captured."]
    connector_lines = [
        (
            f"- {item.connector_name}: {item.integration_method}; auth {item.auth_type}; "
            f"{'enabled' if item.enabled else 'disabled'}; last status {item.last_status}"
        )
        for item in connectors
    ] or ["- No portal retrieval connectors configured."]
    retrieval_lines = [
        (
            f"- {item.started_at.date()} {connectors_by_id.get(item.connector_id, 'connector not found')}: {item.status}; "
            f"HTTP {item.http_status or 'n/a'}; documents {item.documents_created}; findings {item.findings_created}; "
            f"{clean_ai_text(item.error_summary, 240) or 'read-only retrieval'}"
        )
        for item in retrieval_runs
    ] or ["- No automated retrieval runs recorded."]
    question_lines = [_question_line(item) for item in questions] or ["- No quality questions extracted."]
    snapshot_lines = [
        (
            f"- {item.checked_at.date()} {sources_by_id.get(item.source_id, 'source not found')}: "
            f"{item.change_type}; schema {item.detected_schema or 'unknown'}; status {item.status_code or item.notes or 'unknown'}"
        )
        for item in snapshots
    ] or ["- No source snapshots recorded."]
    finding_lines = [_finding_line(item, sources_by_id) for item in findings] or ["- No KRA findings recorded."]
    deterministic_brief = _report_brief(
        report_name,
        scope,
        opportunity_lines,
        requirement_lines,
        finding_lines,
        include_ai_brief,
    )

    return f"""# {report_name}

**Report type:** Admin Automation Run Log  
**Generated at:** {generated_at}  
**Scope:** {scope}  
**Rules:** {rules_version_summary()}

## Purpose

This technical run log gives administrators source, connector, KRA and report traceability. It is not intended as the buyer-facing or leadership-facing pack.

## KRA Runtime

- Provider: {runtime['provider']}
- MCP mode: {runtime['mcp_mode']}
- Model: {runtime['model']}
- AI enabled: {runtime['ai_enabled']}

## Run Summary

{deterministic_brief}

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

## Automated Portal Retrieval

Read-only retrieval connectors are used only where an approved public/API route exists. API keys are referenced by secret name or environment variable and are not written into reports.

{chr(10).join(connector_lines)}

### Latest Retrieval Runs
{chr(10).join(retrieval_lines)}

## Requirement Themes
{chr(10).join(requirement_lines)}

## Quality Questions And Weightings
{chr(10).join(question_lines)}

## Recommended Admin Actions

- Review source-check failures and connector warnings.
- Confirm customer matching before publishing executive packs.
- Keep portal retrieval tasks manual unless an approved read-only API is configured.
- Re-run the executive pack after data quality exclusions are resolved.
"""


def create_report(
    session: Session,
    report_name: str,
    report_type: str = "executive_summary",
    customer_id: int | None = None,
    business_unit_id: int | None = None,
    include_ai_brief: bool = True,
    force_all_scope: bool = False,
) -> IntelligenceReport:
    report_type = (report_type or "executive_summary").strip() or "executive_summary"
    if report_type not in ADMIN_REPORT_TYPES | EXECUTIVE_REPORT_TYPES | COF_REPORT_TYPES:
        report_type = "executive_summary"
    customer_id, business_unit_id = _resolve_cof_report_scope(
        session,
        report_type,
        customer_id,
        business_unit_id,
        force_all_scope=force_all_scope,
    )
    report = IntelligenceReport(
        report_name=report_name,
        report_type=report_type,
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        markdown=generate_report_markdown(
            session,
            report_name,
            report_type,
            customer_id,
            business_unit_id,
            include_ai_brief,
            force_all_scope=force_all_scope,
        ),
    )
    session.add(report)
    session.flush()
    log_event(session, entity_type="IntelligenceReport", entity_id=report.id, action="create", summary=f"Created report {report.report_name}", after=report)
    session.commit()
    session.refresh(report)
    return report


def generate_report_markdown(
    session: Session,
    report_name: str,
    report_type: str,
    customer_id: int | None,
    business_unit_id: int | None,
    include_ai_brief: bool,
    force_all_scope: bool = False,
) -> str:
    if (report_type or "").strip() in ADMIN_REPORT_TYPES:
        return generate_admin_run_log_markdown(session, report_name, customer_id, business_unit_id, include_ai_brief)
    if (report_type or "").strip() in COF_REPORT_TYPES:
        return generate_cof_weekly_report_markdown(
            session,
            report_name,
            report_type,
            customer_id,
            business_unit_id,
            force_all_scope=force_all_scope,
        )
    return generate_executive_intelligence_pack_markdown(session, report_name, customer_id, business_unit_id, include_ai_brief)


def _resolve_cof_report_scope(
    session: Session,
    report_type: str,
    customer_id: int | None,
    business_unit_id: int | None,
    force_all_scope: bool = False,
) -> tuple[int | None, int | None]:
    if report_type != "cof_weekly_portfolio_report" or customer_id or business_unit_id or force_all_scope:
        return customer_id, business_unit_id
    unit = _cof_business_unit(session)
    return customer_id, unit.id if unit and unit.id else business_unit_id


def generate_cof_weekly_report_markdown(
    session: Session,
    report_name: str,
    report_type: str,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
    force_all_scope: bool = False,
) -> str:
    customer_id, business_unit_id = _resolve_cof_report_scope(
        session,
        report_type,
        customer_id,
        business_unit_id,
        force_all_scope=force_all_scope,
    )
    context = _report_context(session, customer_id, business_unit_id)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    customer = context["customer"]
    unit = context["unit"]
    scope = _scope_label(customer, unit)
    opportunities = _cof_report_opportunities(session, customer_id, business_unit_id)
    opportunity_ids = {item.id for item in opportunities if item.id}
    documents = _documents_for_opportunities(_records_for_opportunities(session, OpportunityDocument, opportunity_ids), opportunities)
    questions = _questions_for_opportunities(_records_for_opportunities(session, ExtractedQualityQuestion, opportunity_ids), opportunities)
    requirements = _requirements_for_opportunities(_records_for_opportunities(session, ExtractedRequirement, opportunity_ids), opportunities)
    interests = list(session.exec(select(ClientInterestSignal).order_by(col(ClientInterestSignal.created_at).desc()).limit(250)))
    interests = [item for item in interests if item.opportunity_id in opportunity_ids]
    interested_signals = [item for item in interests if (item.signal or "").lower() == "interested"]
    tasks = list(session.exec(select(DocumentRetrievalTask).order_by(col(DocumentRetrievalTask.created_at).desc()).limit(250)))
    tasks = [item for item in tasks if item.opportunity_id in opportunity_ids]
    interests_by_opportunity = _group_by_opportunity(interests)
    tasks_by_opportunity = _group_by_opportunity(tasks)
    documents_by_opportunity = _group_by_opportunity(documents)
    questions_by_opportunity = _group_by_opportunity(questions)
    stages = {
        item.id: cof_stage_for_opportunity(
            item,
            interests_by_opportunity.get(item.id or 0, []),
            tasks_by_opportunity.get(item.id or 0, []),
            documents_by_opportunity.get(item.id or 0, []),
            questions_by_opportunity.get(item.id or 0, []),
        )
        for item in opportunities
        if item.id
    }
    pins = [item for item in opportunities if stages.get(item.id) in {"pin", "watch"}]
    live = [item for item in opportunities if stages.get(item.id) in {"live", "closing_soon", "document_retrieval_required", "questions_extracted"}]
    closing = [item for item in opportunities if stages.get(item.id) == "closing_soon"]
    awards = [item for item in opportunities if stages.get(item.id) == "awarded"]
    retrieved_documents = [item for item in documents if _is_cof_retrieved_document(item)]
    public_notice_documents = [item for item in documents if _is_public_notice_document(item)]
    missing_source = sum(1 for item in opportunities if not item.source_url)
    missing_deadline = sum(1 for item in opportunities if not item.deadline_date and stages.get(item.id) != "awarded")
    task_opportunity_ids = {task.opportunity_id for task in tasks if task.opportunity_id}
    missing_task = sum(1 for signal in interested_signals if signal.opportunity_id not in task_opportunity_ids)
    report_label = "Client Weekly COF Report" if report_type == "cof_weekly_client_report" else "Portfolio Weekly COF Report"
    return f"""# {report_name}

**Report type:** {report_label}  
**Generated at:** {generated_at}  
**Scope:** {scope}  
**Human review caveat:** Human review required before bid, customer-contact, procurement, legal or compliance decisions.

## Client / Portfolio Summary

- {len(opportunities)} opportunity signal(s) are included for this COF scope.
- {len(pins)} PIN / early-market signal(s), {len(live)} live tender signal(s), {len(interested_signals)} interested item(s) and {len(awards)} award / market evidence record(s).
- {len(requirements)} requirement theme(s), {len(questions)} quality question(s), {len(retrieved_documents)} retrieved/permitted document extract(s) and {len(public_notice_documents)} public notice evidence record(s) are available for review.

## PINs

{_cof_opportunity_lines(pins, stages) if pins else "- No PINs are currently visible for this scope."}

## Live Tenders

{_cof_opportunity_lines(live, stages) if live else "- No live tenders are currently visible for this scope."}

## Closing Soon

{_cof_opportunity_lines(closing, stages) if closing else "- No closing-soon tenders are currently visible for this scope."}

## Awards / Market Evidence

{_cof_opportunity_lines(awards, stages) if awards else "- No awards or market evidence are currently visible for this scope."}

## Interested / Donna Actions

{_cof_interest_lines(interested_signals, opportunities) if interested_signals else "- No client interest signals are waiting for Donna action."}

## Documents Retrieved

{chr(10).join(_document_line(item) for item in retrieved_documents) if retrieved_documents else "- No permitted document extracts have been captured yet."}

## Public Notice Evidence

{chr(10).join(_document_line(item) for item in public_notice_documents) if public_notice_documents else "- No public notice evidence records are linked to this COF scope yet."}

## Quality Questions And Weightings

{chr(10).join(_question_line(item) for item in questions) if questions else "- No quality questions or weightings have been extracted yet."}

## Requirement Themes

{chr(10).join(_requirement_line(item) for item in requirements[:20]) if requirements else "- No requirement themes have been extracted yet."}

## Review Gaps

- {missing_source} opportunity record(s) are missing a source URL.
- {missing_deadline} live or early-stage opportunity record(s) are missing a deadline.
- {missing_task} interested opportunity record(s) do not yet have a document retrieval task.

## Monday Send Readiness

- Report export formats available: PDF, HTML, Markdown, JSON and text.
- Default COF digest profile can store or send the Monday report using the configured email mode.
- Human review remains required before onward circulation or customer action.
"""


def _cof_business_unit(session: Session) -> BusinessUnit | None:
    return session.exec(select(BusinessUnit).where(BusinessUnit.name == COF_BUSINESS_UNIT_NAME)).first()


def _cof_customer_ids(session: Session) -> set[int]:
    customers = list(session.exec(select(Customer)))
    return {
        customer.id
        for customer in customers
        if customer.id
        and (
            customer.customer_name.startswith(COF_CLIENT_PREFIX)
            or customer.customer_name == COF_PORTFOLIO_CUSTOMER_NAME
        )
    }


def _cof_report_opportunities(session: Session, customer_id: int | None, business_unit_id: int | None) -> list[Opportunity]:
    unit = _cof_business_unit(session)
    cof_unit_id = unit.id if unit and unit.id else None
    cof_customer_ids = _cof_customer_ids(session)
    candidates = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(300)))
    opportunities = [
        item
        for item in candidates
        if item.status != "rejected"
        and _is_cof_report_opportunity(item, cof_unit_id, cof_customer_ids)
    ]
    if customer_id:
        opportunities = [item for item in opportunities if item.customer_id == customer_id]
    if business_unit_id:
        opportunities = [
            item
            for item in opportunities
            if item.business_unit_id == business_unit_id
            or bool(cof_unit_id and business_unit_id == cof_unit_id and item.customer_id in cof_customer_ids)
        ]
    return opportunities


def _is_cof_report_opportunity(item: Opportunity, cof_unit_id: int | None, cof_customer_ids: set[int]) -> bool:
    if item.customer_id and item.customer_id in cof_customer_ids:
        return True
    if not cof_unit_id or item.business_unit_id != cof_unit_id:
        return False
    if (item.notice_identifier or "").startswith("cof-live-pilot-"):
        return True
    return bool(item.customer_id)


def _records_for_opportunities(session: Session, model, opportunity_ids: set[int]):
    if not opportunity_ids:
        return []
    return list(session.exec(select(model).where(model.opportunity_id.in_(opportunity_ids))))


def _group_by_opportunity(items) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for item in items:
        opportunity_id = getattr(item, "opportunity_id", None)
        if opportunity_id:
            grouped.setdefault(opportunity_id, []).append(item)
    return grouped


def cof_stage_for_opportunity(
    opportunity: Opportunity,
    interest_signals: list[ClientInterestSignal],
    retrieval_tasks: list[DocumentRetrievalTask],
    documents: list[OpportunityDocument],
    questions: list[ExtractedQualityQuestion],
) -> str:
    raw = " ".join(
        [
            opportunity.status or "",
            opportunity.notice_type or "",
            opportunity.procurement_stage or "",
        ]
    ).lower()
    today = date.today()
    deadline = opportunity.deadline_date
    signals = {(signal.signal or "").lower() for signal in interest_signals}
    if "award" in raw:
        return "awarded"
    if "interested" in signals or (opportunity.status or "").lower() == "interested":
        return "interested"
    if questions or "questions_extracted" in raw:
        return "questions_extracted"
    if retrieval_tasks or "document_retrieval_required" in raw:
        return "document_retrieval_required"
    if "watch" in signals or (opportunity.status or "").lower() == "watch":
        return "watch"
    if any(token in raw for token in ("pin", "planning", "early", "pipeline", "future")):
        return "pin"
    live_hint = any(token in raw for token in ("tender", "active", "open", "approved", "review_required", "needs_review"))
    if deadline and today <= deadline <= today + timedelta(days=COF_CLOSING_SOON_DAYS) and live_hint:
        return "closing_soon"
    if live_hint or (deadline and deadline >= today):
        return "live"
    return "pin"


def _is_public_notice_document(item: OpportunityDocument) -> bool:
    return (item.document_type or "").lower() in COF_PUBLIC_NOTICE_DOCUMENT_TYPES


def _is_cof_retrieved_document(item: OpportunityDocument) -> bool:
    if _is_public_notice_document(item):
        return False
    doc_type = (item.document_type or "").lower()
    status = (item.retrieval_status or "").lower()
    classification = (item.classification_label or "").lower()
    return (
        doc_type in COF_RETRIEVED_DOCUMENT_TYPES
        or status in {"retrieved", "completed", "automated_retrieval"}
        or "permitted" in doc_type
        or "permitted" in classification
    )


def _report_context(session: Session, customer_id: int | None, business_unit_id: int | None) -> dict:
    opportunity_query = select(Opportunity).order_by(col(Opportunity.updated_at).desc())
    if customer_id:
        opportunity_query = opportunity_query.where(Opportunity.customer_id == customer_id)
    if business_unit_id:
        opportunity_query = opportunity_query.where(Opportunity.business_unit_id == business_unit_id)
    opportunities = list(session.exec(opportunity_query.limit(80)))
    opportunity_ids = [item.id for item in opportunities if item.id]
    requirements: list[ExtractedRequirement] = []
    documents: list[OpportunityDocument] = []
    questions: list[ExtractedQualityQuestion] = []
    if opportunity_ids:
        requirements = list(session.exec(select(ExtractedRequirement).where(ExtractedRequirement.opportunity_id.in_(opportunity_ids))))
        documents = list(session.exec(select(OpportunityDocument).where(OpportunityDocument.opportunity_id.in_(opportunity_ids))))
        questions = list(session.exec(select(ExtractedQualityQuestion).where(ExtractedQualityQuestion.opportunity_id.in_(opportunity_ids))))
    sources = list(session.exec(select(ProcurementSource).order_by(col(ProcurementSource.name))))
    connectors = list(session.exec(select(PortalInformationConnector).order_by(col(PortalInformationConnector.connector_name))))
    retrieval_runs = list(session.exec(select(PortalRetrievalRun).order_by(col(PortalRetrievalRun.started_at).desc()).limit(20)))
    snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(30)))
    findings_query = select(KRAFinding).order_by(col(KRAFinding.created_at).desc()).limit(30)
    if customer_id:
        findings_query = findings_query.where(KRAFinding.customer_id == customer_id)
    findings = list(session.exec(findings_query))
    sources_by_id = {source.id: source.name for source in sources if source.id}
    connectors_by_id = {connector.id: connector.connector_name for connector in connectors if connector.id}
    latest_snapshots_by_source: dict[int, SourceCheckSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.source_id and snapshot.source_id not in latest_snapshots_by_source:
            latest_snapshots_by_source[snapshot.source_id] = snapshot
    return {
        "customer": session.get(Customer, customer_id) if customer_id else None,
        "unit": session.get(BusinessUnit, business_unit_id) if business_unit_id else None,
        "opportunities": opportunities,
        "requirements": requirements,
        "documents": documents,
        "questions": questions,
        "sources": sources,
        "connectors": connectors,
        "retrieval_runs": retrieval_runs,
        "snapshots": snapshots,
        "findings": findings,
        "sources_by_id": sources_by_id,
        "connectors_by_id": connectors_by_id,
        "latest_snapshots_by_source": latest_snapshots_by_source,
    }


def _scope_label(customer: Customer | None, unit: BusinessUnit | None) -> str:
    if customer and unit:
        return f"{customer.customer_name} / {unit.name}"
    if customer:
        return customer.customer_name
    if unit:
        return unit.name
    return "All customers and business units"


def _executive_opportunities(opportunities: list[Opportunity], customer: Customer | None) -> tuple[list[Opportunity], list[Opportunity]]:
    included: list[Opportunity] = []
    excluded: list[Opportunity] = []
    for item in opportunities:
        if _signal_type(item) in {"Award / market evidence", "Closed / historical signal"}:
            continue
        if customer and item.buyer_name and not _buyer_matches_customer(item, customer):
            excluded.append(item)
            continue
        if item.relevance_score < 25:
            excluded.append(item)
            continue
        included.append(item)
    included.sort(key=lambda item: (-item.relevance_score, item.deadline_date or date.max, item.title))
    return included, excluded


def _buyer_matches_customer(item: Opportunity, customer: Customer) -> bool:
    aliases = [customer.customer_name, *(customer.aliases or "").replace(",", ";").split(";"), *(customer.buying_entities or "").replace(",", ";").split(";")]
    if item.buyer_name:
        haystack = item.buyer_name.lower()
        return any(alias.strip().lower() in haystack for alias in aliases if len(alias.strip()) >= 3)
    haystack = " ".join([item.title or "", item.summary or ""]).lower()
    return any(alias.strip().lower() in haystack for alias in aliases if len(alias.strip()) >= 3)


def _signal_type(item: Opportunity) -> str:
    raw = " ".join([item.notice_type or "", item.procurement_stage or "", item.status or ""]).lower()
    if "award" in raw:
        return "Award / market evidence"
    if item.deadline_date and item.deadline_date < date.today():
        return "Closed / historical signal"
    if any(word in raw for word in ("tender", "active", "open")):
        return "Live tender signal"
    if any(word in raw for word in ("planning", "early", "pipeline", "future")):
        return "Early market signal"
    return "Watch signal"


def _readiness_assessment(
    context: dict,
    opportunities: list[Opportunity],
    requirements: list[ExtractedRequirement],
    documents: list[OpportunityDocument],
    questions: list[ExtractedQualityQuestion],
    excluded: list[Opportunity],
) -> tuple[str, list[str], list[str]]:
    active_sources = [source for source in context["sources"] if source.active]
    latest = context["latest_snapshots_by_source"]
    ok_sources = [source for source in active_sources if _snapshot_ok(latest.get(source.id or 0)) or str(source.last_status).lower() in {"ok", "200"}]
    high_relevance = [item for item in opportunities if item.relevance_score >= 70]
    gaps: list[str] = []
    if not opportunities:
        gaps.append("No credible opportunity signals passed the current scope gate.")
    if not requirements:
        gaps.append("No extracted requirement themes are available for the current scope.")
    if not documents:
        gaps.append("No permitted source document or tender extract evidence has been linked.")
    if active_sources and not ok_sources:
        gaps.append("Active source checks have not yet produced a clean OK result.")
    if excluded:
        gaps.append(f"{len(excluded)} opportunity record(s) were excluded because buyer matching or relevance was not credible enough for the executive pack.")
    if requirements and not any((item.human_review_status or "") in REVIEW_READY_STATUSES for item in requirements):
        gaps.append("Requirements remain pending agent or manual approval.")
    if questions and not any((item.human_review_status or "") in REVIEW_READY_STATUSES for item in questions):
        gaps.append("Extracted quality questions remain pending agent or manual approval.")

    if opportunities and requirements and documents and ok_sources and not excluded:
        confidence = "Green - credible pack ready for human approval"
    elif opportunities and (requirements or documents or ok_sources):
        confidence = "Amber - credible live showcase pack, review required"
    else:
        confidence = "Red - not enough evidence for onward use"

    rows = [
        f"- {len(opportunities)} current opportunity signal(s) included in this digest.",
        f"- {len(high_relevance)} high-relevance signal(s) scored 70 or above.",
        f"- {len(requirements)} requirement or capability theme(s) captured from notices and permitted extracts.",
        f"- {len(questions)} quality question or weighting signal(s) extracted.",
        f"- {len(excluded)} low-confidence or buyer-mismatch record(s) held back from the opportunity digest.",
    ]
    return confidence, rows, gaps


def _snapshot_ok(snapshot: SourceCheckSnapshot | None) -> bool:
    return bool(snapshot and snapshot.ok and 200 <= int(snapshot.status_code or 0) < 400)


def _requirements_for_opportunities(requirements: list[ExtractedRequirement], opportunities: list[Opportunity]) -> list[ExtractedRequirement]:
    opportunity_ids = {item.id for item in opportunities if item.id}
    return sorted(
        [item for item in requirements if item.opportunity_id in opportunity_ids and _requirement_theme_still_matches(item)],
        key=lambda item: (_review_rank(item.human_review_status), item.requirement_theme),
    )


def _requirement_theme_still_matches(item: ExtractedRequirement) -> bool:
    if item.requirement_theme == "general opportunity fit":
        return True
    current_themes = requirement_themes_for_text(item.requirement_text)
    return item.requirement_theme in current_themes


def _documents_for_opportunities(documents: list[OpportunityDocument], opportunities: list[Opportunity]) -> list[OpportunityDocument]:
    opportunity_ids = {item.id for item in opportunities if item.id}
    return sorted(
        [item for item in documents if item.opportunity_id in opportunity_ids],
        key=lambda item: (_review_rank(item.human_review_status), item.title),
    )


def _questions_for_opportunities(questions: list[ExtractedQualityQuestion], opportunities: list[Opportunity]) -> list[ExtractedQualityQuestion]:
    opportunity_ids = {item.id for item in opportunities if item.id}
    return sorted(
        [item for item in questions if item.opportunity_id in opportunity_ids],
        key=lambda item: (_review_rank(item.human_review_status), item.requirement_theme or item.question_text),
    )


def _findings_for_scope(findings: list[KRAFinding], customer: Customer | None, opportunities: list[Opportunity]) -> list[KRAFinding]:
    opportunity_ids = {item.id for item in opportunities if item.id}
    filtered = [
        item
        for item in findings
        if (not customer or item.customer_id == customer.id)
        and (not item.opportunity_id or item.opportunity_id in opportunity_ids)
    ]
    return sorted(filtered, key=lambda item: (_confidence_rank(item.confidence), _review_rank(item.human_review_status), item.title))


def _review_rank(value: str) -> int:
    value = (value or "").lower()
    if value in {"approved", "accepted", "review_ready", "review_required"}:
        return 0
    if value == "pending":
        return 1
    return 2


def _confidence_rank(value: str) -> int:
    value = (value or "").lower()
    if value in {"high", "strong"}:
        return 0
    if value in {"medium", "moderate"}:
        return 1
    return 2


def _executive_brief(
    report_name: str,
    scope: str,
    opportunities: list[Opportunity],
    requirements: list[ExtractedRequirement],
    documents: list[OpportunityDocument],
    findings: list[KRAFinding],
    gaps: list[str],
    include_ai_brief: bool,
) -> str:
    opportunity_lines = [_executive_opportunity_line(item, {}) for item in opportunities[:8]]
    requirement_lines = [_requirement_line(item) for item in requirements[:8]]
    finding_lines = [f"- {item.title}: {clean_ai_text(item.summary, 240)}" for item in findings[:6]]
    live_count = sum(1 for item in opportunities if _signal_type(item) == "Live tender signal")
    early_count = sum(1 for item in opportunities if _signal_type(item) == "Early market signal")
    deterministic = (
        f"{scope} currently has {len(opportunities)} current opportunity signal(s): "
        f"{live_count} live tender(s) and {early_count} early-market signal(s). "
        f"{len(requirements)} requirement or capability theme(s) have been captured for review. "
        f"There are {len(gaps)} material gap(s) to resolve before onward reliance."
    )
    if not llm_enabled():
        return deterministic
    if not include_ai_brief:
        return deterministic
    try:
        brief = generate_llm_text(
            kra_system_prompt(),
            "\n".join(
                [
                    f"Report: {report_name}",
                    f"Scope: {scope}",
                    "Credible opportunities:",
                    *(opportunity_lines or ["- None"]),
                    "Requirement themes:",
                    *(requirement_lines or ["- None"]),
                    "KRA findings for context only:",
                    *(finding_lines[:3] or ["- None"]),
                    "Known gaps:",
                    *(f"- {item}" for item in gaps),
                    "",
                    "Write a concise executive intelligence brief for a live showcase environment. Do not mention prompts or offer follow-up content. Include public-source caveats, data gaps and next human actions.",
                ]
            ),
            max_output_tokens=800,
        )
        return clean_ai_text(brief) or deterministic
    except LLMError as exc:
        return f"AI-assisted executive brief unavailable: {clean_ai_text(str(exc), 220)}\n\n{deterministic}"


def _report_brief(
    report_name: str,
    scope: str,
    opportunity_lines: list[str],
    requirement_lines: list[str],
    finding_lines: list[str],
    include_ai_brief: bool,
) -> str:
    deterministic = (
        f"Admin log for {scope}: {len(opportunity_lines)} opportunity line(s), "
        f"{len(requirement_lines)} requirement line(s) and {len(finding_lines)} KRA finding line(s) were available when this report was generated."
    )
    if not llm_enabled():
        return deterministic
    if not include_ai_brief:
        return "Report-level AI brief was skipped for the automated cycle. " + deterministic
    try:
        return clean_ai_text(
            generate_llm_text(
                kra_system_prompt(),
                "\n".join(
                    [
                        f"Report: {report_name}",
                        f"Scope: {scope}",
                        "Opportunities:",
                        *opportunity_lines[:15],
                        "Requirements:",
                        *requirement_lines[:12],
                        "KRA findings:",
                        *finding_lines[:10],
                        "Summarise this technical admin run log in five concise bullets.",
                    ]
                ),
                max_output_tokens=700,
            )
        ) or deterministic
    except LLMError as exc:
        return f"AI-assisted run summary unavailable: {clean_ai_text(str(exc), 220)}\n\n{deterministic}"


def _source_evidence_lines(sources: list[ProcurementSource], latest_snapshots_by_source: dict[int, SourceCheckSnapshot]) -> list[str]:
    active_sources = [source for source in sources if source.active]
    if not active_sources:
        return ["- No active public sources are configured."]
    lines = []
    for source in active_sources[:12]:
        snapshot = latest_snapshots_by_source.get(source.id or 0)
        status = "OK" if _snapshot_ok(snapshot) or str(source.last_status).lower() in {"ok", "200"} else (source.last_status or "not checked")
        checked = snapshot.checked_at.date().isoformat() if snapshot else "not checked"
        coverage = clean_ai_text(source.coverage or source.notes, 150) or "source coverage not described"
        lines.append(f"- {source.name}: {status}; checked {checked}; {coverage}.")
    return lines


def _retrieval_guardrail_lines(connectors: list[PortalInformationConnector], retrieval_runs: list[PortalRetrievalRun]) -> list[str]:
    enabled = [item for item in connectors if item.enabled]
    if not enabled:
        return ["- No enabled read-only retrieval connectors are configured for this report scope."]
    run_counts = Counter(item.connector_id for item in retrieval_runs if item.connector_id)
    lines = []
    for connector in enabled[:10]:
        mode = connector.integration_method or "not recorded"
        last_status = connector.last_status or "not checked"
        runs = run_counts.get(connector.id, 0)
        lines.append(f"- {connector.connector_name}: approved read-only mode {mode}; last status {last_status}; {runs} recent run(s) recorded.")
    return lines


def _opportunity_block(index: int, item: Opportunity, sources_by_id: dict[int, str]) -> str:
    signal = _signal_type(item)
    deadline = item.deadline_date.isoformat() if item.deadline_date else "not captured"
    published = item.published_date.isoformat() if item.published_date else "not captured"
    value = _money(item.value_high, item.currency)
    source = sources_by_id.get(item.source_id or 0, "source not recorded")
    summary = clean_ai_text(item.summary, 420) or "No notice summary has been captured yet."
    rationale = _executive_rationale(item)
    link = item.source_url or "source URL not captured"
    return f"""### {index}. {item.title}

Buyer: {item.buyer_name or "not detected"}  
Signal: {signal}  
Stage: {item.procurement_stage or item.notice_type or "not captured"}  
Published: {published}  
Deadline: {deadline}  
Estimated value: {value}  
Source: {source}  
Link: {link}

Why this matters: {rationale}

Notice summary: {summary}
"""


def _executive_rationale(item: Opportunity) -> str:
    rationale = clean_ai_text(item.relevance_rationale, 260) or ""
    rationale = rationale.replace("Automation prepared this opportunity for human review.", "").strip()
    rationale = rationale.replace("Agent auto-approved catalogue entry because relevance, source traceability and BU/customer assignment thresholds were met.", "").strip()
    rationale = rationale.replace("Agent queued catalogue entry for review because confidence or assignment thresholds were incomplete.", "").strip()
    if rationale.startswith("Capability-market match for "):
        marker = ": "
        rationale = rationale.split(marker, 1)[1] if marker in rationale else rationale
    if rationale.startswith("Matched terms:"):
        rationale = f"Public sector market signal. {rationale}"
    return rationale or "Public-source opportunity signal matched configured public-sector capability themes."


def _money(value: float, currency: str) -> str:
    if not value:
        return "not captured"
    prefix = "GBP" if (currency or "GBP").upper() == "GBP" else (currency or "GBP").upper()
    if value >= 1_000_000:
        return f"{prefix} {value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"{prefix} {value / 1_000:.0f}k"
    return f"{prefix} {value:.0f}"


def _executive_opportunity_line(item: Opportunity, sources_by_id: dict[int, str]) -> str:
    signal = _signal_type(item)
    deadline = item.deadline_date.isoformat() if item.deadline_date else "deadline not captured"
    source = sources_by_id.get(item.source_id or 0, "source not recorded") if sources_by_id else "source not recorded"
    summary = clean_ai_text(item.summary or item.relevance_rationale, 260) or "no summary captured"
    return (
        f"- **{item.title}** ({signal}) | buyer {item.buyer_name or 'not detected'} | "
        f"deadline {deadline} | relevance {item.relevance_score:g} | source {source}. {summary}"
    )


def _cof_opportunity_lines(items: list[Opportunity], stages: dict[int, str] | None = None) -> str:
    stages = stages or {}
    lines = []
    for item in sorted(items, key=lambda row: (row.deadline_date or date.max, row.title))[:30]:
        deadline = item.deadline_date.isoformat() if item.deadline_date else "deadline not captured"
        value = _money(item.value_high, item.currency)
        summary = clean_ai_text(item.summary, 220) or "No summary captured."
        stage = stages.get(item.id or 0, item.status).replace("_", " ")
        lines.append(
            f"- **{item.title}** | {item.buyer_name or 'buyer not detected'} | {stage} | "
            f"deadline {deadline} | {value}. {summary}"
        )
    return "\n".join(lines)


def _cof_interest_lines(interests: list[ClientInterestSignal], opportunities: list[Opportunity]) -> str:
    opportunity_map = {item.id: item for item in opportunities if item.id}
    lines = []
    for signal in interests[:20]:
        opportunity = opportunity_map.get(signal.opportunity_id)
        title = opportunity.title if opportunity else f"Opportunity {signal.opportunity_id}"
        lines.append(
            f"- **{title}** | signal {signal.signal} | status {signal.status or 'new'} | "
            f"{clean_ai_text(signal.notes, 180) or 'Donna action required.'}"
        )
    return "\n".join(lines)


def _historical_opportunity_line(item: Opportunity) -> str:
    return f"- **{item.title}** is retained as award / market evidence, not presented as a live opportunity."


def _requirement_line(item: ExtractedRequirement) -> str:
    category = (item.requirement_category or "general").replace("_", " ")
    return (
        f"- **{item.requirement_theme}:** {clean_ai_text(item.requirement_text, 260)} "
        f"({category}; {item.confidence or 'unknown'} confidence; {item.human_review_status or 'pending'} status)."
    )


def _question_line(item: ExtractedQualityQuestion) -> str:
    weighting = f"; weighting {item.weighting}" if item.weighting else ""
    theme = item.requirement_theme or "quality question"
    category = (item.requirement_category or "general").replace("_", " ")
    return (
        f"- **{theme}:** {clean_ai_text(item.question_text, 260)} "
        f"({category}; {item.confidence or 'unknown'} confidence{weighting}; {item.human_review_status or 'pending'} status)."
    )


def _category_trend_lines(items: list[ExtractedRequirement | ExtractedQualityQuestion]) -> list[str]:
    counts = category_trend_counts(items)
    return [f"- **{category.replace('_', ' ').title()}**: {count} signal(s)." for category, count in counts.most_common(10)]


def _document_line(item: OpportunityDocument) -> str:
    summary = clean_ai_text(item.content_summary or item.notes, 220) or "no summary captured"
    governance = []
    if item.classification_label:
        governance.append(f"classification {item.classification_label}")
    if item.storage_provider and item.storage_provider != "none":
        governance.append(f"storage {item.storage_provider}")
    if item.retention_status and item.retention_status != "standard":
        governance.append(f"retention {item.retention_status}")
    governance_note = f" ({'; '.join(governance)})" if governance else ""
    return (
        f"- {item.title}: {item.document_type}; {item.retrieval_status}; "
        f"{item.platform_name or 'platform not recorded'}; {item.human_review_status or 'pending'} review{governance_note}. {summary}"
    )


def _finding_line(item: KRAFinding, sources_by_id: dict[int, str]) -> str:
    source = sources_by_id.get(item.source_id or 0, "source not recorded")
    summary = clean_ai_text(item.summary, 280) or "no summary captured"
    return (
        f"- **{item.title}:** {summary} "
        f"({item.confidence or 'unknown'} confidence; {item.human_review_status or 'pending'} review; source {source})."
    )


def _exclusion_line(item: Opportunity) -> str:
    reason = "buyer mismatch" if item.buyer_name else "low relevance"
    return f"- {item.title}: excluded from executive pack due to {reason}; buyer {item.buyer_name or 'not detected'}; relevance {item.relevance_score:g}."


def _exclusion_summary(excluded: list[Opportunity]) -> str:
    if not excluded:
        return "- No buyer mismatch or low-confidence opportunity records were excluded from this executive view."
    return (
        f"- {len(excluded)} low-confidence, stale or buyer-mismatch record(s) were held back from this executive view. "
        "Use the Admin Run Log and audit view for the diagnostic list."
    )
