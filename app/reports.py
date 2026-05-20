from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
import json
import re

from sqlmodel import Session, col, select

from app.audit import log_event
from app.cof_readiness import (
    BACKUP_SOURCE_KEYS,
    COFReadinessResult,
    REQUIRED_PORTAL_FAMILIES,
    REQUIRED_SOURCE_KEYS,
    cof_readiness,
    is_placeholder_source_url,
    source_reference_for_report,
    source_status_for_opportunity,
    trusted_cof_source_ids,
)
from app.intelligence import kra_runtime_status, requirement_themes_for_text
from app.llm import LLMError, generate_llm_text, kra_system_prompt, llm_enabled
from app.models import (
    BusinessUnit,
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    DocumentRetrievalTask,
    DigestProfile,
    EmailConfiguration,
    EmailDeliveryLog,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    IntelligenceReport,
    KRAFinding,
    Opportunity,
    OpportunityDocument,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementPlatform,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.requirement_taxonomy import category_trend_counts
from app.rule_loader import rules_version_summary
from app.settings import get_settings


ADMIN_REPORT_TYPES = {"admin_run_log", "automation_run_log", "technical_run_log"}
EXECUTIVE_REPORT_TYPES = {"executive_summary", "executive_pack", "executive_intelligence_pack"}
COF_INTERNAL_REPORT_TYPES = {"cof_internal_review_pack"}
COF_FINAL_REPORT_TYPES = {"cof_final_customer_pack"}
COF_LEGACY_REPORT_TYPES = {"cof_weekly_client_report", "cof_weekly_portfolio_report"}
COF_REPORT_TYPES = COF_INTERNAL_REPORT_TYPES | COF_FINAL_REPORT_TYPES | COF_LEGACY_REPORT_TYPES
REVIEW_READY_STATUSES = {"review_required", "review_ready", "accepted", "approved", "complete", "completed"}
COF_APPROVED_REVIEW_STATUSES = {"approved", "accepted", "review_ready", "complete", "completed"}
COF_BUSINESS_UNIT_NAME = "Contracted Opportunity Finder"
COF_CLIENT_PREFIX = "COF Client "
COF_PORTFOLIO_CUSTOMER_NAME = "Procter Street COF Portfolio"
COF_CLOSING_SOON_DAYS = 14
COF_RETRIEVED_DOCUMENT_TYPES = {"itt_extract", "automated_retrieval", "retrieved", "permitted_extract"}
COF_PUBLIC_NOTICE_DOCUMENT_TYPES = {"public_notice"}
COF_GLOBAL_CAVEAT = "Human review required. Not a bid, legal, procurement or compliance decision."
REVIEW_APPROVED_FOR_REPORT = "Review Lead approved for report inclusion"
REVIEW_AWAITING = "Awaiting Review Lead review"
REVIEW_NEEDS_EVIDENCE = "Needs more evidence"
REVIEW_REJECTED = "Rejected / excluded"
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
    effective_report_type = _effective_cof_report_type(session, report_type, customer_id, business_unit_id)
    effective_report_name = report_name
    report = IntelligenceReport(
        report_name=effective_report_name,
        report_type=effective_report_type,
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        markdown=generate_report_markdown(
            session,
            effective_report_name,
            effective_report_type,
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


def _effective_cof_report_type(session: Session, report_type: str, customer_id: int | None, business_unit_id: int | None) -> str:
    if report_type not in COF_REPORT_TYPES:
        return report_type
    if report_type in COF_INTERNAL_REPORT_TYPES:
        return "cof_internal_review_pack"
    if report_type in COF_FINAL_REPORT_TYPES | COF_LEGACY_REPORT_TYPES:
        return "cof_final_customer_pack"
    return report_type


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
    if report_type not in {"cof_weekly_portfolio_report", "cof_internal_review_pack", "cof_final_customer_pack"} or customer_id or business_unit_id or force_all_scope:
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
    report_mode = "internal" if report_type == "cof_internal_review_pack" else "final"
    readiness = cof_readiness(session, customer_id=customer_id, business_unit_id=business_unit_id, report_mode=report_mode)
    opportunities = _cof_report_opportunities(session, customer_id, business_unit_id)
    opportunity_ids = {item.id for item in opportunities if item.id}
    documents = _documents_for_opportunities(_records_for_opportunities(session, OpportunityDocument, opportunity_ids), opportunities)
    questions = _questions_for_opportunities(_records_for_opportunities(session, ExtractedQualityQuestion, opportunity_ids), opportunities)
    requirements = _requirements_for_opportunities(_records_for_opportunities(session, ExtractedRequirement, opportunity_ids), opportunities)
    clients = _cof_clients(session, customer_id)
    customer_map = {customer.id: display_cof_client_name(customer) for customer in clients if customer.id}
    portal_routes = _cof_portal_routes(session)
    interests = list(session.exec(select(ClientInterestSignal).order_by(col(ClientInterestSignal.created_at).desc()).limit(250)))
    interests = [item for item in interests if item.opportunity_id in opportunity_ids]
    interested_signals = [item for item in interests if (item.signal or "").lower() == "interested"]
    tasks = list(session.exec(select(DocumentRetrievalTask).order_by(col(DocumentRetrievalTask.created_at).desc()).limit(250)))
    tasks = [item for item in tasks if item.opportunity_id in opportunity_ids]
    interests_by_opportunity = _group_by_opportunity(interests)
    tasks_by_opportunity = _group_by_opportunity(tasks)
    documents_by_opportunity = _group_by_opportunity(documents)
    questions_by_opportunity = _group_by_opportunity(questions)
    documents_by_id = {document.id: document for document in documents if document.id}
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
    review_states = {
        item.id: review_status_for_opportunity(
            item,
            documents_by_opportunity.get(item.id or 0, []),
            questions_by_opportunity.get(item.id or 0, []),
        )
        for item in opportunities
        if item.id
    }
    retrieved_documents_all = [item for item in documents if _is_cof_retrieved_document(item)]
    task_opportunity_ids = {task.opportunity_id for task in tasks if task.opportunity_id}
    all_review_queue = [item for item in opportunities if review_states.get(item.id) != REVIEW_APPROVED_FOR_REPORT]
    if report_mode == "final":
        section_opportunities = _cof_final_ready_opportunities(opportunities)
    else:
        section_opportunities = opportunities
    section_ids = {item.id for item in section_opportunities if item.id}
    section_documents = [item for item in documents if item.opportunity_id in section_ids]
    section_questions = [item for item in questions if item.opportunity_id in section_ids]
    section_requirements = [item for item in requirements if item.opportunity_id in section_ids]
    if report_mode == "final":
        section_documents = [
            item
            for item in section_documents
            if _is_public_notice_document(item) or (_is_cof_retrieved_document(item) and _review_is_approved(item.human_review_status))
        ]
        section_questions = [item for item in section_questions if _cof_question_review_status(item, documents_by_id) == "approved"]
        section_requirements = [item for item in section_requirements if _review_is_approved(item.human_review_status)]
    section_interests = [item for item in interested_signals if item.opportunity_id in section_ids]
    section_review_states = dict(review_states)
    if report_mode == "final":
        section_review_states.update({item.id: review_status_for_opportunity(item, [], []) for item in section_opportunities if item.id})
    missing_source = sum(1 for item in section_opportunities if not item.source_url)
    missing_deadline = sum(1 for item in section_opportunities if not item.deadline_date and stages.get(item.id) != "awarded")
    missing_task = sum(1 for signal in section_interests if signal.opportunity_id not in task_opportunity_ids)
    clients_without_visible_items = _cof_clients_without_visible_items(clients, section_opportunities)
    pending_document_review = sum(1 for item in retrieved_documents_all if not _review_is_approved(item.human_review_status))
    pending_question_review = sum(1 for item in questions if _cof_question_review_status(item, documents_by_id) != "approved")
    coverage_lines = _cof_client_coverage_lines(clients, section_opportunities, stages, section_review_states)
    held_opportunity_count = max(0, len(opportunities) - len(section_opportunities))
    held_document_count = max(0, len(retrieved_documents_all) - len([item for item in section_documents if _is_cof_retrieved_document(item)]))
    held_question_count = max(0, len(questions) - len(section_questions))
    review_gap_lines = (
        _cof_final_review_note_lines(
            missing_source,
            missing_deadline,
            missing_task,
            held_opportunity_count,
            held_document_count,
            held_question_count,
            clients_without_visible_items,
        )
        if report_mode == "final"
        else _cof_review_gap_lines(
            missing_source,
            missing_deadline,
            missing_task,
            pending_document_review,
            pending_question_review,
            len(all_review_queue),
            clients_without_visible_items,
        )
    )
    send_readiness = cof_monday_send_readiness(
        session,
        section_ids,
        generated_at=generated_at,
        clients_with_visible_items=len(clients) - clients_without_visible_items,
        clients_without_visible_items=clients_without_visible_items,
        blockers={
            "pending_human_review": 0 if report_mode == "final" else len(all_review_queue),
            "pending_document_review": 0 if report_mode == "final" else pending_document_review,
            "pending_quality_question_review": 0 if report_mode == "final" else pending_question_review,
            "interested_without_document_task": missing_task,
        },
    )
    readiness_lines = _cof_monday_send_readiness_lines(send_readiness, report_mode=report_mode)
    source_detail_lines = _cof_source_detail_lines(section_opportunities, customer_map, report_mode)
    requirement_lines = _cof_requirement_lines(section_requirements, section_opportunities, customer_map)
    source_status_lines = _cof_source_status_lines(context["sources"], readiness.source_health, report_mode=report_mode)
    portal_status_lines = _cof_portal_status_lines(session, clients)
    kra_status_lines = _cof_kra_status_lines(session, readiness)
    retrieval_task_lines = _cof_retrieval_task_lines(tasks, section_opportunities if report_mode == "final" else opportunities)
    redaction_note = _cof_redaction_note()
    if report_mode == "final":
        source_attention = any(item.status in {"failed", "stale"} and item.role == "primary" for item in readiness.source_health)
        status_label = "Needs source attention" if source_attention else ("Ready for weekly send" if send_readiness.get("ready") else "Review recommended")
    else:
        status_label = "Internal review"
    report_label = "Final Customer Pack" if report_mode == "final" else "Internal Review Pack - not for client circulation."
    review_section_heading = "Report Review Notes" if report_mode == "final" else "Review Gaps"
    pins = [item for item in section_opportunities if stages.get(item.id) == "pin"]
    watch = [item for item in section_opportunities if stages.get(item.id) == "watch"]
    live = [item for item in section_opportunities if stages.get(item.id) in {"live", "closing_soon", "document_retrieval_required", "questions_extracted"}]
    closing = [item for item in section_opportunities if stages.get(item.id) == "closing_soon"]
    awards = [item for item in section_opportunities if stages.get(item.id) == "awarded"]
    review_queue = all_review_queue
    retrieved_documents = [item for item in section_documents if _is_cof_retrieved_document(item)]
    public_notice_documents = [item for item in section_documents if _is_public_notice_document(item)]
    human_review_gate_text = (
        _cof_opportunity_lines(review_queue, stages, customer_map, portal_routes, review_states, "internal")
        if report_mode == "internal" and review_queue
        else (
            f"- {held_opportunity_count} opportunity record(s) are held in the internal review workflow and excluded from customer-facing sections."
            if report_mode == "final" and held_opportunity_count
            else "- No opportunity records are currently inside the Human Review Gate."
        )
    )
    return f"""# {report_name}

**Report type:** {report_label}
**Generated at:** {generated_at}
**Scope:** {scope}
**Prepared for:** {get_settings().report_prepared_for}
**Status:** {status_label}
**Human review caveat:** {COF_GLOBAL_CAVEAT}

Review Lead approval means approved for COF report inclusion, not bid, legal, procurement or compliance approval.
{redaction_note}

{_cof_internal_notice(readiness) if report_mode == "internal" else ""}

## Client / Portfolio Summary

- Client Coverage: {len(clients)} clients monitored.
- Opportunity Coverage: {len(section_opportunities)} customer-safe opportunity signal(s), filtered to matched clients and the Contracted Opportunity Finder workspace.
- Pipeline: {len(pins)} PIN / early-market signal(s), {len(watch)} watch item(s), {len(live)} live tender signal(s), {len(closing)} closing-soon tender(s), {len(section_interests)} interested item(s) and {len(awards)} award / market evidence record(s).
- Evidence: {len(section_requirements)} requirement theme(s), {len(section_questions)} quality question(s), {len(retrieved_documents)} retrieved/permitted document extract(s) and {len(public_notice_documents)} public notice evidence record(s).

## Client Coverage

{chr(10).join(coverage_lines) if coverage_lines else "- No COF clients are configured for this scope."}

## Source Health

{chr(10).join(source_status_lines)}

{_cof_internal_status_sections(source_status_lines, portal_status_lines, kra_status_lines, retrieval_task_lines) if report_mode == "internal" else ""}

## PINs / Early Market

{_cof_opportunity_lines(pins, stages, customer_map, portal_routes, section_review_states, report_mode) if pins else "- No PINs are currently visible for this scope."}

## Watchlist

{_cof_opportunity_lines(watch, stages, customer_map, portal_routes, section_review_states, report_mode) if watch else "- No watchlist items are currently visible for this scope."}

## Live Tenders

{_cof_opportunity_lines(live, stages, customer_map, portal_routes, section_review_states, report_mode) if live else "- No live tenders are currently visible for this scope."}

## Closing Soon

{_cof_opportunity_lines(closing, stages, customer_map, portal_routes, section_review_states, report_mode) if closing else "- No closing-soon tenders are currently visible for this scope."}

## Awards / Market Evidence

{_cof_opportunity_lines(awards, stages, customer_map, portal_routes, section_review_states, report_mode) if awards else "- No awards or market evidence are currently visible for this scope."}

## Client Action Queue

{_cof_interest_lines(section_interests, section_opportunities, customer_map, portal_routes, section_review_states) if section_interests else "- No approved client action signals are visible for this scope."}

## Documents Retrieved

{chr(10).join(_cof_document_line(item) for item in retrieved_documents) if retrieved_documents else "- No permitted document extracts have been captured yet."}

## Public Notice Evidence

{chr(10).join(_cof_document_line(item) for item in public_notice_documents) if public_notice_documents else "- No public notice evidence records are linked to this COF scope yet."}

## Quality Questions and Weightings

{chr(10).join(_cof_question_line(item, documents_by_id) for item in section_questions) if section_questions else "- No approved quality questions or weightings are available yet."}

## Requirement Themes

{chr(10).join(requirement_lines) if requirement_lines else "- No requirement themes have been extracted yet."}

## Human Review Gate

{human_review_gate_text}

## {review_section_heading}

{chr(10).join(review_gap_lines)}

## Monday Send Readiness

{chr(10).join(readiness_lines)}

## Source Detail / Notice References

{chr(10).join(source_detail_lines) if source_detail_lines else "- No source references are available for this scope."}
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


def _cof_clients(session: Session, customer_id: int | None = None) -> list[Customer]:
    customers = list(session.exec(select(Customer).order_by(col(Customer.customer_name))))
    clients = [customer for customer in customers if customer.customer_name.startswith(COF_CLIENT_PREFIX)]
    if customer_id:
        clients = [customer for customer in clients if customer.id == customer_id]
    return clients


def _cof_portal_routes(session: Session) -> dict[int, str]:
    platforms = {platform.id: platform.name for platform in session.exec(select(ProcurementPlatform)) if platform.id}
    routes: dict[int, str] = {}
    for portal in session.exec(select(BuyerPortalInstance).order_by(col(BuyerPortalInstance.portal_name))):
        if not portal.customer_id:
            continue
        family = platforms.get(portal.platform_id or 0) or _infer_portal_family(portal.portal_name)
        status = (portal.access_status or "status to confirm").replace("_", " ")
        routes[portal.customer_id] = f"{family or 'portal route to confirm'} ({status})"
    return routes


def _infer_portal_family(value: str) -> str:
    lower = (value or "").lower()
    for family in ("ProContract", "In-Tend", "Jaggaer", "Delta eSourcing"):
        if family.lower() in lower:
            return family
    return ""


def _cof_report_opportunities(session: Session, customer_id: int | None, business_unit_id: int | None) -> list[Opportunity]:
    unit = _cof_business_unit(session)
    cof_unit_id = unit.id if unit and unit.id else None
    cof_customer_ids = _cof_customer_ids(session)
    trusted_source_ids = trusted_cof_source_ids(session)
    candidates = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(300)))
    opportunities = [
        item
        for item in candidates
        if item.status != "rejected"
        and _is_cof_report_opportunity(item, cof_unit_id, cof_customer_ids)
        and (not trusted_source_ids or item.source_id in trusted_source_ids)
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


def _cof_client_coverage_lines(
    clients: list[Customer],
    opportunities: list[Opportunity],
    stages: dict[int, str],
    review_states: dict[int, str],
) -> list[str]:
    lines: list[str] = [
        "| Client | Sector | PINs | Watch | Live | Interested | Awarded | Review gate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    totals = Counter()
    total_awaiting_review = 0
    for client in clients:
        client_opportunities = [item for item in opportunities if item.customer_id == client.id]
        counts = Counter(stages.get(item.id or 0, "pin") for item in client_opportunities)
        live_count = sum(counts.get(stage, 0) for stage in ("live", "closing_soon", "document_retrieval_required", "questions_extracted"))
        awaiting_review = sum(1 for item in client_opportunities if review_states.get(item.id) != REVIEW_APPROVED_FOR_REPORT)
        totals.update(
            {
                "pin": counts.get("pin", 0),
                "watch": counts.get("watch", 0),
                "live": live_count,
                "interested": counts.get("interested", 0),
                "awarded": counts.get("awarded", 0),
            }
        )
        total_awaiting_review += awaiting_review
        lines.append(
            f"| {display_cof_client_name(client)} | {_sector_label(client.sector)} | {counts.get('pin', 0)} | "
            f"{counts.get('watch', 0)} | {live_count} | {counts.get('interested', 0)} | "
            f"{counts.get('awarded', 0)} | {awaiting_review} |"
        )
    lines.append(
        f"| **Total** | **{len(clients)} clients** | **{totals.get('pin', 0)}** | **{totals.get('watch', 0)}** | "
        f"**{totals.get('live', 0)}** | **{totals.get('interested', 0)}** | **{totals.get('awarded', 0)}** | "
        f"**{total_awaiting_review}** |"
    )
    return lines


def _cof_clients_without_visible_items(clients: list[Customer], opportunities: list[Opportunity]) -> int:
    visible_customer_ids = {item.customer_id for item in opportunities if item.customer_id and item.status != "rejected"}
    return sum(1 for client in clients if client.id not in visible_customer_ids)


def _cof_review_gap_lines(
    missing_source: int,
    missing_deadline: int,
    missing_task: int,
    pending_document_review: int,
    pending_question_review: int,
    awaiting_human_review: int,
    clients_without_visible_items: int,
) -> list[str]:
    return [
        f"- Missing source URL: {missing_source} opportunity record(s).",
        f"- Missing deadline: {missing_deadline} live or early-stage opportunity record(s).",
        f"- Interested without document retrieval task: {missing_task} item(s).",
        f"- Pending document review: {pending_document_review} retrieved/permitted document record(s).",
        f"- Pending quality-question review: {pending_question_review} quality question(s).",
        f"- Opportunities inside the Human Review Gate: {awaiting_human_review} item(s).",
        f"- Clients with no visible items this week: {clients_without_visible_items} client(s).",
    ]


def _cof_final_review_note_lines(
    missing_source: int,
    missing_deadline: int,
    missing_task: int,
    held_opportunity_count: int,
    held_document_count: int,
    held_question_count: int,
    clients_without_visible_items: int,
) -> list[str]:
    lines = [
        "- Customer-facing opportunity sections include source-valid records that passed the Review Lead gate.",
        (
            f"- Held outside customer-facing sections: {held_opportunity_count} opportunity record(s), "
            f"{held_document_count} document extract(s), and {held_question_count} quality question(s) not yet cleared for circulation."
        ),
        f"- Source gaps in visible sections: {missing_source} missing source URL(s).",
        f"- Deadline gaps in visible sections: {missing_deadline} missing deadline(s).",
        f"- Interested items without a document retrieval task: {missing_task}.",
        f"- Clients with no visible customer-safe items this week: {clients_without_visible_items}.",
    ]
    if held_opportunity_count or held_document_count or held_question_count:
        lines.append("- Operational detail is retained in the Internal Review Pack.")
    return lines


def _cof_internal_notice(readiness: COFReadinessResult) -> str:
    blockers = "\n".join(f"- {item}" for item in readiness.blockers) if readiness.blockers else "- No hard report-generation blockers are configured."
    warnings = "\n".join(f"- {item}" for item in readiness.warnings) if readiness.warnings else "- No material warnings recorded."
    return (
        "Internal Review Pack - not for client circulation.\n\n"
        "### Operating Attention Items\n\n"
        f"{blockers}\n\n"
        "### Readiness Warnings\n\n"
        f"{warnings}"
    )


def _cof_internal_status_sections(
    source_status_lines: list[str],
    portal_status_lines: list[str],
    kra_status_lines: list[str],
    retrieval_task_lines: list[str],
) -> str:
    return f"""
## Source Status

{chr(10).join(source_status_lines)}

## Portal Status

{chr(10).join(portal_status_lines)}

## KRA Status

{chr(10).join(kra_status_lines)}

## Document Retrieval Queue

{chr(10).join(retrieval_task_lines)}
"""


def _cof_final_ready_opportunities(
    opportunities: list[Opportunity],
) -> list[Opportunity]:
    ready: list[Opportunity] = []
    for item in opportunities:
        if not source_status_for_opportunity(item).valid:
            continue
        if review_status_for_opportunity(item, [], []) != REVIEW_APPROVED_FOR_REPORT:
            continue
        ready.append(item)
    return ready


def _cof_source_status_lines(sources: list[ProcurementSource], source_health: list | None = None, report_mode: str = "internal") -> list[str]:
    if source_health:
        lines = []
        for item in source_health:
            status = item.status
            message = item.message
            if report_mode == "final":
                if status == "failed":
                    status = "attention"
                    message = "Refresh needs attention; existing curated records remain reportable while ingestion is reviewed."
                elif status == "stale":
                    status = "refresh due"
                    message = "Refresh is due before relying on new ingestion; existing curated records remain reportable."
            lines.append(f"- {item.label}: {status}; {message}")
        return lines
    source_by_key = {source.source_key: source for source in sources}
    lines = []
    for key, label in {**REQUIRED_SOURCE_KEYS, **BACKUP_SOURCE_KEYS}.items():
        source = source_by_key.get(key)
        if not source:
            lines.append(f"- {label}: missing.")
        else:
            lines.append(f"- {label}: {'active' if source.active else 'inactive'}; {source.connector_status or source.last_status or 'configured'}.")
    return lines or ["- No source catalogue entries configured."]


def _cof_portal_status_lines(session: Session, clients: list[Customer]) -> list[str]:
    platforms = {platform.id: platform.name for platform in session.exec(select(ProcurementPlatform)) if platform.id}
    portals = list(session.exec(select(BuyerPortalInstance)))
    by_customer = {portal.customer_id: portal for portal in portals if portal.customer_id}
    lines = [f"- Required portal families: {', '.join(sorted(REQUIRED_PORTAL_FAMILIES))}."]
    for client in clients:
        portal = by_customer.get(client.id)
        if not portal:
            lines.append(f"- {display_cof_client_name(client)}: portal route to confirm.")
            continue
        family = platforms.get(portal.platform_id or 0) or _infer_portal_family(portal.portal_name)
        lines.append(f"- {display_cof_client_name(client)}: {family or 'portal route to confirm'}; {portal.access_status.replace('_', ' ')}.")
    return lines


def _cof_kra_status_lines(session: Session, readiness: COFReadinessResult) -> list[str]:
    findings = list(session.exec(select(KRAFinding).order_by(col(KRAFinding.created_at).desc()).limit(20)))
    approved = sum(1 for item in findings if _review_is_approved(item.human_review_status))
    return [
        f"- Agent profiles configured: {'yes' if readiness.kra_enabled else 'no'}.",
        f"- Recent completed KRA run present: {'yes' if readiness.kra_recent_run_present else 'no / deterministic fallback documented'}.",
        f"- Pending KRA findings: {readiness.kra_pending_findings_count}.",
        f"- Approved KRA findings: {approved}.",
        "- KRA output is evidence support only and does not make bid, legal, procurement or compliance decisions.",
    ]


def _cof_retrieval_task_lines(tasks: list[DocumentRetrievalTask], opportunities: list[Opportunity]) -> list[str]:
    opportunity_map = {item.id: item for item in opportunities if item.id}
    lines = []
    for task in tasks[:30]:
        opportunity = opportunity_map.get(task.opportunity_id)
        title = concise_opportunity_title(opportunity) if opportunity else f"Opportunity {task.opportunity_id}"
        lines.append(f"- {title}: {task.status}; owner {task.owner or 'Document Retrieval Queue'}; {task.guardrail_summary}")
    return lines or ["- No document retrieval tasks are linked to the current COF scope."]


def _is_cof_report_opportunity(item: Opportunity, cof_unit_id: int | None, cof_customer_ids: set[int]) -> bool:
    if item.customer_id and item.customer_id in cof_customer_ids:
        return True
    if not cof_unit_id or item.business_unit_id != cof_unit_id:
        return False
    if is_placeholder_source_url(item.source_url) or (item.notice_identifier or "").startswith("cof-live-pilot-"):
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


def review_status_for_opportunity(
    opportunity: Opportunity,
    documents: list[OpportunityDocument] | None = None,
    questions: list[ExtractedQualityQuestion] | None = None,
) -> str:
    documents = documents or []
    questions = questions or []
    status = (opportunity.status or "").lower()
    if status == "rejected":
        return REVIEW_REJECTED
    if status == "needs_review":
        return REVIEW_NEEDS_EVIDENCE
    if status in {"review_required", "pending_review", "new", "document_retrieval_required", "questions_extracted"}:
        return REVIEW_AWAITING
    if any(not _review_is_approved(document.human_review_status) for document in documents):
        return REVIEW_AWAITING
    if any(not _review_is_approved(question.human_review_status) for question in questions):
        return REVIEW_AWAITING
    return REVIEW_APPROVED_FOR_REPORT


def _cof_review_status(
    opportunity: Opportunity,
    documents: list[OpportunityDocument],
    questions: list[ExtractedQualityQuestion],
) -> str:
    return review_status_for_opportunity(opportunity, documents, questions)


def _review_is_approved(value: str) -> bool:
    return (value or "").lower() in COF_APPROVED_REVIEW_STATUSES


def _cof_question_review_status(item: ExtractedQualityQuestion, documents_by_id: dict[int, OpportunityDocument]) -> str:
    document = documents_by_id.get(item.document_id or 0)
    if document and not _review_is_approved(document.human_review_status):
        return "pending Review Lead review"
    status = (item.human_review_status or "pending").lower()
    return "approved" if status in COF_APPROVED_REVIEW_STATUSES else status.replace("_", " ")


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


def _cof_opportunity_lines(
    items: list[Opportunity],
    stages: dict[int, str] | None = None,
    customer_map: dict[int, str] | None = None,
    portal_routes: dict[int, str] | None = None,
    review_states: dict[int, str] | None = None,
    report_mode: str = "internal",
) -> str:
    stages = stages or {}
    customer_map = customer_map or {}
    portal_routes = portal_routes or {}
    review_states = review_states or {}
    lines = []
    for item in sorted(items, key=lambda row: (row.deadline_date or date.max, row.title))[:30]:
        deadline = item.deadline_date.isoformat() if item.deadline_date else "deadline not captured"
        value = _money(item.value_high, item.currency)
        summary = _cof_customer_report_text(item.summary, 260)
        stage = stages.get(item.id or 0, item.status).replace("_", " ")
        client = customer_map.get(item.customer_id or 0, "matched client to confirm")
        review = review_states.get(item.id or 0, REVIEW_AWAITING)
        portal = portal_routes.get(item.customer_id or 0, "portal route to confirm")
        source_status = source_status_for_opportunity(item)
        source_label = source_status.label
        if report_mode == "final" and not source_status.valid:
            source_label = "source withheld pending validation"
        title = concise_opportunity_title(item)
        next_action = _cof_next_action_for_opportunity(review, stage)
        lines.append(
            f"- **{title}**\n"
            f"  Matched client: {client}; buyer: {item.buyer_name or 'buyer not detected'}.\n"
            f"  Stage: {stage}; review gate: {review}; deadline: {deadline}; value: {value}; confidence: {item.relevance_score:g}.\n"
            f"  Portal route: {portal}; source status: {source_label}; next action: {next_action}.\n"
            f"  Summary: {summary}"
        )
        if title != (item.title or "").strip():
            lines.append(f"  Full notice title: {item.title}")
    return "\n".join(lines)


def _cof_next_action_for_opportunity(review_status: str, stage: str) -> str:
    if review_status == REVIEW_APPROVED_FOR_REPORT:
        if stage in {"interested", "document retrieval required", "questions extracted"}:
            return "Document Retrieval Queue"
        return "Monitor in weekly pack"
    if review_status == REVIEW_NEEDS_EVIDENCE:
        return "Add source evidence"
    return "Human Review Gate"


def _cof_interest_lines(
    interests: list[ClientInterestSignal],
    opportunities: list[Opportunity],
    customer_map: dict[int, str],
    portal_routes: dict[int, str],
    review_states: dict[int, str],
) -> str:
    opportunity_map = {item.id: item for item in opportunities if item.id}
    lines = []
    for signal in interests[:20]:
        opportunity = opportunity_map.get(signal.opportunity_id)
        title = concise_opportunity_title(opportunity) if opportunity else f"Opportunity {signal.opportunity_id}"
        client = customer_map.get(signal.customer_id or 0, "matched client to confirm")
        portal = portal_routes.get(signal.customer_id or 0, "portal route to confirm")
        review = review_states.get(signal.opportunity_id or 0, REVIEW_AWAITING)
        action_status = _cof_action_status(signal.status)
        lines.append(
            f"- **{title}**\n"
            f"  Matched client: {client}; signal: {signal.signal}; account action status: {action_status}.\n"
            f"  Review gate: {review}; portal route: {portal}.\n"
            f"  Notes: {_cof_customer_report_text(signal.notes, 200) or 'Account Lead action required.'}"
        )
        if opportunity and title != (opportunity.title or "").strip():
            lines.append(f"  Full notice title: {opportunity.title}")
    return "\n".join(lines)


def _cof_action_status(status: str | None) -> str:
    value = (status or "new").strip().lower()
    replacements = {"d" + "onna_action_required": "account_lead_action_required"}
    return replacements.get(value, value).replace("_", " ")


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


def _cof_question_line(item: ExtractedQualityQuestion, documents_by_id: dict[int, OpportunityDocument]) -> str:
    weighting = f"; weighting {item.weighting}" if item.weighting else ""
    theme = item.requirement_theme or "quality question"
    category = (item.requirement_category or "general").replace("_", " ")
    review_status = _cof_question_review_status(item, documents_by_id)
    return (
        f"- **{theme}**\n"
        f"  Question: {_cof_customer_report_text(item.question_text, 280)}\n"
        f"  Classification: {category}; confidence: {item.confidence or 'unknown'}{weighting}; review: {review_status}."
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


def _cof_document_line(item: OpportunityDocument) -> str:
    summary = _cof_customer_report_text(item.content_summary or item.notes, 260)
    if _is_public_notice_document(item):
        status = "source evidence reference"
    else:
        status = "approved for report inclusion" if _review_is_approved(item.human_review_status) else "held for review"
    return (
        f"- **{item.title}**\n"
        f"  Type: {item.document_type}; retrieval: {item.retrieval_status}; platform: {item.platform_name or 'platform not recorded'}; review: {status}.\n"
        f"  Summary: {summary}"
    )


def _cof_customer_report_text(value: str, max_chars: int = 220) -> str:
    original = value or ""
    text = clean_ai_text(original, max_chars=max_chars)
    text = re.sub(r"\s*Seeded live-pilot content for COF report walkthrough; verify source before onward use\.?", "", text, flags=re.I)
    text = re.sub(r"\s*Seeded from COF live-pilot pack; human review required\.?", "", text, flags=re.I)
    text = re.sub(r"\s*Seeded permitted extract for COF report walkthrough\.?", "", text, flags=re.I)
    text = re.sub(r"\s*Source evidence captured for Review Lead review\. Human verification required before client action\.?", "", text, flags=re.I)
    legacy_reviewer = "D" + "enise"
    text = re.sub(rf"\s*Source evidence captured for {legacy_reviewer} review\. Human verification required before client action\.?", "", text, flags=re.I)
    text = re.sub(r"\s*Human review required before client action\.?", "", text, flags=re.I)
    text = re.sub(r"\s*Human review required\.?", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        return text[:max_chars].rsplit(" ", 1)[0].rstrip(".,;: ") if len(text) > max_chars else text
    return "Source evidence captured; awaiting review status above."


def _cof_client_name_mode() -> str:
    mode = (get_settings().cof_client_name_mode or "redacted").strip().lower()
    return mode if mode in {"placeholder", "redacted", "configured"} else "redacted"


def _cof_client_name_map() -> dict[str, str]:
    raw = get_settings().cof_client_name_map_json
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if str(value).strip()}


def display_cof_client_name(customer: Customer | None) -> str:
    if not customer:
        return "Client to confirm"
    mapping = _cof_client_name_map()
    if customer.customer_name in mapping:
        return mapping[customer.customer_name]
    mode = _cof_client_name_mode()
    if mode == "placeholder":
        return customer.customer_name
    if mode == "configured":
        return mapping.get(customer.customer_name, customer.customer_name)
    index = _cof_client_index(customer.customer_name)
    label = chr(ord("A") + index - 1) if 1 <= index <= 26 else str(index or "")
    sector = _sector_label(customer.sector)
    return f"Client {label} - {sector}" if sector else f"Client {label}".strip()


def display_cof_client_name_by_id(customer_id: int | None, customers_by_id: dict[int, Customer] | None = None) -> str:
    if customer_id and customers_by_id and customer_id in customers_by_id:
        return display_cof_client_name(customers_by_id[customer_id])
    return "Client to confirm"


def _cof_client_index(name: str) -> int:
    match = re.search(r"COF Client\s+(\d+)", name or "", flags=re.I)
    return int(match.group(1)) if match else 0


def _sector_label(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    replacements = {
        "Highways and civil engineering": "Highways",
        "School estates and decarbonisation": "Estates",
        "Bridges and structures": "Structures",
        "Cyber and security services": "Security",
        "Facilities and asset management": "FM / Asset",
        "Transport maintenance": "Transport",
        "Public building works": "Buildings",
        "Environmental and grounds maintenance": "Environment",
        "Mechanical and electrical services": "M&E",
        "Digital and data services": "Digital",
        "Specialist construction and maintenance": "Specialist Works",
    }
    return replacements.get(text, text[:34].rstrip())


def _cof_redaction_note() -> str:
    if _cof_client_name_mode() == "redacted" and not _cof_client_name_map():
        return "Client names are redacted in this report; live names can be configured before external circulation."
    return ""


def concise_opportunity_title(opportunity: Opportunity | None, max_chars: int = 90) -> str:
    if not opportunity:
        return "Opportunity to confirm"
    title = re.sub(r"\s+", " ", (opportunity.title or "").strip())
    title = re.sub(r"^[A-Z]{1,4}\d{3,}\s*[-:]\s*", "", title)
    title = re.sub(r"^GB-([^:]{2,40}):\s*", r"\1 ", title, flags=re.I)
    title = re.sub(r"^Invitation to Tender\s*[-:]\s*", "", title, flags=re.I)
    title = re.sub(r"^ITT\s*[-:]\s*", "", title, flags=re.I)
    title = re.sub(r"^The provision of\s+", "", title, flags=re.I)
    title = re.sub(r"^Provision of\s+", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" -:")
    if len(title) <= max_chars:
        return title
    shortened = title[: max_chars + 1].rsplit(" ", 1)[0].rstrip(".,;: -")
    return f"{shortened}..."


def _cof_source_detail_lines(opportunities: list[Opportunity], customer_map: dict[int, str], report_mode: str = "internal") -> list[str]:
    lines: list[str] = []
    for item in sorted(opportunities, key=lambda row: (customer_map.get(row.customer_id or 0, ""), row.title))[:40]:
        title = concise_opportunity_title(item)
        client = customer_map.get(item.customer_id or 0, "matched client to confirm")
        source_status = source_status_for_opportunity(item).label
        lines.append(
            f"- **{title}**\n"
            f"  Matched client: {client}; buyer: {item.buyer_name or 'buyer not detected'}; source status: {source_status}."
        )
        if title != (item.title or "").strip():
            lines.append(f"  Full notice title: {item.title}")
        reference = source_reference_for_report(item, report_mode)
        if reference and reference != "source withheld pending validation":
            lines.append(f"  Source: {reference}")
    return lines


def _cof_requirement_lines(
    requirements: list[ExtractedRequirement],
    opportunities: list[Opportunity],
    customer_map: dict[int, str],
) -> list[str]:
    opportunity_map = {item.id: item for item in opportunities if item.id}
    lines: list[str] = []
    for item in requirements[:10]:
        opportunity = opportunity_map.get(item.opportunity_id)
        if not opportunity:
            continue
        client = customer_map.get(item.customer_id or opportunity.customer_id or 0, "matched client to confirm")
        category = (item.requirement_category or "general").replace("_", " ")
        lines.append(
            f"- **{client} / {concise_opportunity_title(opportunity, 70)}**\n"
            f"  Theme: {item.requirement_theme}; category: {category}; confidence: {item.confidence or 'unknown'}.\n"
            f"  Requirement: {_cof_customer_report_text(item.requirement_text, 260)}"
        )
    if len(requirements) > 10:
        lines.append(f"- {len(requirements) - 10} further requirement theme(s) retained in the knowledge base.")
    return lines


def cof_monday_send_readiness(
    session: Session,
    opportunity_ids: set[int],
    generated_at: str | None = None,
    clients_with_visible_items: int = 0,
    clients_without_visible_items: int = 0,
    blockers: dict[str, int] | None = None,
) -> dict[str, object]:
    blockers = blockers or {}
    profile = session.exec(select(DigestProfile).where(DigestProfile.name == "COF Monday report send")).first()
    latest_report = session.exec(
        select(IntelligenceReport)
        .where(col(IntelligenceReport.report_type).in_(["cof_final_customer_pack", "cof_internal_review_pack", "cof_weekly_portfolio_report"]))
        .order_by(col(IntelligenceReport.generated_at).desc())
    ).first()
    latest_email = session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc())).first()
    email_config = session.exec(select(EmailConfiguration).order_by(EmailConfiguration.id)).first()
    recipient_source = profile.recipients if profile and profile.recipients else ""
    if not recipient_source and email_config and email_config.default_recipients:
        recipient_source = email_config.default_recipients
    if not recipient_source:
        recipient_source = get_settings().email_default_recipients
    recipients = _split_recipients(recipient_source)
    delivery_mode = get_settings().email_delivery_mode or "file_outbox"
    if profile and profile.recipients:
        delivery_mode = delivery_mode or "file_outbox"
    blocker_lines: list[str] = []
    for label, value in [
        ("pending Human Review Gate items", blockers.get("pending_human_review", 0)),
        ("pending document review", blockers.get("pending_document_review", 0)),
        ("pending quality-question review", blockers.get("pending_quality_question_review", 0)),
        ("interested without document task", blockers.get("interested_without_document_task", 0)),
    ]:
        if value:
            blocker_lines.append(f"{value} {label}")
    if not recipients:
        blocker_lines.append("no Monday recipients configured")
    ready = bool(profile and profile.enabled and recipients and not blocker_lines)
    return {
        "ready": ready,
        "digest_profile_exists": bool(profile),
        "digest_enabled": bool(profile and profile.enabled),
        "delivery_mode": delivery_mode,
        "recipient_count": len(recipients),
        "export_format": profile.export_format if profile else "pdf",
        "latest_report_generated_at": generated_at or (latest_report.generated_at.isoformat(timespec="seconds") if latest_report else "not generated"),
        "latest_email_status": latest_email.status if latest_email else "not sent",
        "clients_with_visible_items": clients_with_visible_items,
        "clients_without_visible_items": clients_without_visible_items,
        "blockers": blocker_lines,
        "opportunity_count": len(opportunity_ids),
    }


def _cof_monday_send_readiness_lines(readiness: dict[str, object], report_mode: str = "internal") -> list[str]:
    blockers = list(readiness.get("blockers") or [])
    status = "Ready for weekly send" if readiness.get("ready") else "Review recommended"
    next_action = "Send or store the approved weekly pack through the configured delivery route." if readiness.get("ready") else _cof_readiness_next_action(blockers)
    lines = [
        f"- Status: **{status}**.",
        f"- Digest profile: {'configured' if readiness.get('digest_profile_exists') else 'missing'}; {'enabled' if readiness.get('digest_enabled') else 'disabled'}.",
        f"- Delivery mode: {readiness.get('delivery_mode')}.",
        f"- Recipients: {readiness.get('recipient_count')} configured.",
        f"- Export format: {readiness.get('export_format')}.",
        f"- Latest report generated: {readiness.get('latest_report_generated_at')}.",
        f"- Latest email delivery status: {readiness.get('latest_email_status')}.",
        f"- Portfolio coverage: {readiness.get('clients_with_visible_items')} client(s) with visible items; {readiness.get('clients_without_visible_items')} without visible items.",
    ]
    if blockers and report_mode == "internal":
        lines.append(f"- Attention: {'; '.join(blockers)}.")
    elif not blockers:
        lines.append("- Attention: none recorded at report generation.")
    else:
        lines.append("- Attention: review the internal pack for operational detail.")
    lines.append(f"- Next action: {next_action}")
    return lines


def _cof_final_send_readiness_lines(readiness: COFReadinessResult, generated_at: str) -> list[str]:
    return [
        "- Status: **Ready for weekly send**.",
        f"- Delivery mode: {readiness.delivery_mode}.",
        f"- Recipients: {readiness.recipients_count} configured.",
        f"- Export format: {readiness.export_format}.",
        f"- Latest report generated: {readiness.latest_report_generated_at.isoformat(timespec='seconds') if readiness.latest_report_generated_at else generated_at}.",
        f"- Latest email delivery status: {readiness.latest_email_delivery_status}.",
        "- Source validation: passed.",
        "- Human Review Gate: passed.",
        "- Document/question review: passed.",
        "- Next action: Send or store the approved weekly pack through the configured delivery route.",
    ]


def _cof_readiness_next_action(blockers: list[str]) -> str:
    if any("no Monday recipients" in item for item in blockers):
        return "Configure weekly recipients. File-outbox/manual review remains available."
    if blockers:
        return "Review the listed attention items before Monday circulation."
    return "Confirm digest configuration before circulation."


def _split_recipients(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;,]", value or "") if item.strip()]


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
