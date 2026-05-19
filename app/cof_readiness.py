from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlmodel import Session, col, select

from app.models import (
    BusinessUnit,
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    DigestProfile,
    DocumentRetrievalTask,
    EmailDeliveryLog,
    ExtractedQualityQuestion,
    IntelligenceReport,
    KRAAgentProfile,
    KRAFinding,
    KRAResearchRun,
    Opportunity,
    OpportunityDocument,
    ProcurementPlatform,
    ProcurementSource,
)
from app.settings import get_settings


COF_BUSINESS_UNIT_NAME = "Contracted Opportunity Finder"
COF_CLIENT_PREFIX = "COF Client "
COF_PORTFOLIO_CUSTOMER_NAME = "Procter Street COF Portfolio"
COF_DIGEST_NAME = "COF Monday report send"
REQUIRED_SOURCE_KEYS = {
    "find_a_tender": "Find a Tender",
    "contracts_finder": "Contracts Finder",
    "public_contracts_scotland": "Public Contracts Scotland",
    "sell2wales": "Sell2Wales",
    "ted_eforms": "TED",
}
BACKUP_SOURCE_KEYS = {"tenders_direct_backup": "Tenders Direct"}
REQUIRED_PORTAL_FAMILIES = {"ProContract", "In-Tend", "Jaggaer", "Delta eSourcing"}
APPROVED_REVIEW_STATUSES = {"approved", "accepted", "review_ready", "complete", "completed"}
FINAL_FORBIDDEN_WORDS = {
    "mvp",
    "demo",
    "concept",
    "seeded",
    "live-pilot",
    "walkthrough",
    "prototype",
    "test output",
    "fake",
    "placeholder",
}


@dataclass
class SourceStatus:
    label: str
    reference: str
    valid: bool
    placeholder: bool
    missing: bool


@dataclass
class COFReadinessResult:
    ready_for_final_pack: bool
    customers_configured_count: int = 0
    customers_with_visible_items_count: int = 0
    sources_configured_count: int = 0
    sources_active_count: int = 0
    source_families_present: list[str] = field(default_factory=list)
    portals_configured_count: int = 0
    portal_families_present: list[str] = field(default_factory=list)
    kra_enabled: bool = False
    kra_recent_run_present: bool = False
    kra_pending_findings_count: int = 0
    pending_human_review_count: int = 0
    pending_document_review_count: int = 0
    pending_quality_question_review_count: int = 0
    missing_source_url_count: int = 0
    placeholder_source_url_count: int = 0
    invalid_source_url_count: int = 0
    interested_without_retrieval_task_count: int = 0
    digest_profile_exists: bool = False
    digest_profile_enabled: bool = False
    recipients_count: int = 0
    delivery_mode: str = "file_outbox"
    export_format: str = "pdf"
    latest_report_generated_at: datetime | None = None
    latest_email_delivery_status: str = "not sent"
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "ready_for_final_pack": self.ready_for_final_pack,
            "customers_configured_count": self.customers_configured_count,
            "customers_with_visible_items_count": self.customers_with_visible_items_count,
            "sources_configured_count": self.sources_configured_count,
            "sources_active_count": self.sources_active_count,
            "source_families_present": self.source_families_present,
            "portals_configured_count": self.portals_configured_count,
            "portal_families_present": self.portal_families_present,
            "kra_enabled": self.kra_enabled,
            "kra_recent_run_present": self.kra_recent_run_present,
            "kra_pending_findings_count": self.kra_pending_findings_count,
            "pending_human_review_count": self.pending_human_review_count,
            "pending_document_review_count": self.pending_document_review_count,
            "pending_quality_question_review_count": self.pending_quality_question_review_count,
            "missing_source_url_count": self.missing_source_url_count,
            "placeholder_source_url_count": self.placeholder_source_url_count,
            "invalid_source_url_count": self.invalid_source_url_count,
            "interested_without_retrieval_task_count": self.interested_without_retrieval_task_count,
            "digest_profile_exists": self.digest_profile_exists,
            "digest_profile_enabled": self.digest_profile_enabled,
            "recipients_count": self.recipients_count,
            "delivery_mode": self.delivery_mode,
            "export_format": self.export_format,
            "latest_report_generated_at": self.latest_report_generated_at.isoformat(timespec="seconds")
            if self.latest_report_generated_at
            else None,
            "latest_email_delivery_status": self.latest_email_delivery_status,
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


def cof_business_unit(session: Session) -> BusinessUnit | None:
    return session.exec(select(BusinessUnit).where(BusinessUnit.name == COF_BUSINESS_UNIT_NAME)).first()


def cof_customers(session: Session, customer_id: int | None = None) -> list[Customer]:
    statement = select(Customer).order_by(col(Customer.customer_name))
    customers = [
        customer
        for customer in session.exec(statement)
        if customer.customer_name.startswith(COF_CLIENT_PREFIX) or customer.customer_name == COF_PORTFOLIO_CUSTOMER_NAME
    ]
    if customer_id:
        customers = [customer for customer in customers if customer.id == customer_id]
    return [customer for customer in customers if customer.customer_name.startswith(COF_CLIENT_PREFIX)]


def cof_customer_ids(session: Session) -> set[int]:
    return {customer.id for customer in cof_customers(session) if customer.id}


def cof_opportunities(session: Session, customer_id: int | None = None, business_unit_id: int | None = None) -> list[Opportunity]:
    unit = cof_business_unit(session)
    unit_id = unit.id if unit and unit.id else None
    customer_ids = cof_customer_ids(session)
    candidates = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(500)))
    opportunities = [
        item
        for item in candidates
        if item.status != "rejected"
        and (
            bool(item.customer_id and item.customer_id in customer_ids)
            or bool(unit_id and item.business_unit_id == unit_id and item.customer_id)
        )
    ]
    if customer_id:
        opportunities = [item for item in opportunities if item.customer_id == customer_id]
    if business_unit_id and business_unit_id != unit_id:
        opportunities = [item for item in opportunities if item.business_unit_id == business_unit_id]
    return opportunities


def is_placeholder_source_url(url: str | None) -> bool:
    text = (url or "").strip()
    lowered = text.lower()
    return any(pattern in lowered for pattern in ("/notice/cof-", "cof-000", "cof-live-pilot"))


def is_valid_official_source_url(url: str | None) -> bool:
    if not url or is_placeholder_source_url(url):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    official_hosts = {
        "www.find-tender.service.gov.uk",
        "find-tender.service.gov.uk",
        "www.contractsfinder.service.gov.uk",
        "contractsfinder.service.gov.uk",
        "www.publiccontractsscotland.gov.uk",
        "publiccontractsscotland.gov.uk",
        "www.sell2wales.gov.wales",
        "sell2wales.gov.wales",
        "ted.europa.eu",
        "tendersdirect.co.uk",
        "www.tendersdirect.co.uk",
    }
    return host in official_hosts


def source_status_for_opportunity(opportunity: Opportunity) -> SourceStatus:
    url = opportunity.source_url or ""
    if not url:
        return SourceStatus("Source URL missing", "source URL missing", False, False, True)
    if is_placeholder_source_url(url):
        return SourceStatus("Source reference pending validation", "source reference pending validation", False, True, False)
    if not is_valid_official_source_url(url):
        return SourceStatus("Source URL needs validation", "source URL needs validation", False, False, False)
    return SourceStatus("Verified source", url, True, False, False)


def source_reference_for_report(opportunity: Opportunity, report_mode: str) -> str:
    status = source_status_for_opportunity(opportunity)
    if report_mode == "final":
        return status.reference if status.valid else "source withheld pending validation"
    return status.reference


def cof_readiness(
    session: Session,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
    report_mode: str = "final",
) -> COFReadinessResult:
    settings = get_settings()
    customers = cof_customers(session, customer_id)
    opportunities = cof_opportunities(session, customer_id, business_unit_id)
    opportunity_ids = {item.id for item in opportunities if item.id}
    documents = _records_for_opportunities(session, OpportunityDocument, opportunity_ids)
    questions = _records_for_opportunities(session, ExtractedQualityQuestion, opportunity_ids)
    sources = list(session.exec(select(ProcurementSource)))
    platforms = list(session.exec(select(ProcurementPlatform)))
    portals = list(session.exec(select(BuyerPortalInstance)))
    findings = list(session.exec(select(KRAFinding)))
    runs = list(session.exec(select(KRAResearchRun).order_by(col(KRAResearchRun.started_at).desc()).limit(20)))
    agents = list(session.exec(select(KRAAgentProfile).where(KRAAgentProfile.active == True)))  # noqa: E712
    tasks = _records_for_opportunities(session, DocumentRetrievalTask, opportunity_ids)
    interests = _records_for_opportunities(session, ClientInterestSignal, opportunity_ids)
    digest = session.exec(select(DigestProfile).where(DigestProfile.name == COF_DIGEST_NAME)).first()
    latest_email = session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc())).first()
    latest_report = session.exec(
        select(IntelligenceReport)
        .where(col(IntelligenceReport.report_type).in_(["cof_final_customer_pack", "cof_internal_review_pack", "cof_weekly_portfolio_report"]))
        .order_by(col(IntelligenceReport.generated_at).desc())
    ).first()

    required_sources = REQUIRED_SOURCE_KEYS | BACKUP_SOURCE_KEYS
    source_keys = {source.source_key for source in sources}
    active_source_keys = {source.source_key for source in sources if source.active}
    platform_names = {platform.name for platform in platforms}
    portal_customer_ids = {portal.customer_id for portal in portals if portal.customer_id}
    source_statuses = [source_status_for_opportunity(item) for item in opportunities]
    task_opportunity_ids = {task.opportunity_id for task in tasks if task.opportunity_id}
    interested_without_task = [
        signal
        for signal in interests
        if (signal.signal or "").lower() == "interested" and signal.opportunity_id not in task_opportunity_ids
    ]
    completed_run = _latest_completed_kra_run(runs)
    deterministic_kra = settings.kra_llm_provider in {"", "disabled", "deterministic-local"} or settings.kra_mcp_mode == "local_registry"
    recipients = _split_recipients(digest.recipients if digest else "")
    delivery_mode = settings.email_delivery_mode or "file_outbox"

    result = COFReadinessResult(
        ready_for_final_pack=False,
        customers_configured_count=len(customers),
        customers_with_visible_items_count=len({item.customer_id for item in opportunities if item.customer_id}),
        sources_configured_count=len(sources),
        sources_active_count=sum(1 for source in sources if source.active),
        source_families_present=sorted(source_keys),
        portals_configured_count=len(portals),
        portal_families_present=sorted(platform_names),
        kra_enabled=bool(agents),
        kra_recent_run_present=bool(completed_run),
        kra_pending_findings_count=sum(1 for item in findings if not _review_is_approved(item.human_review_status)),
        pending_human_review_count=sum(1 for item in opportunities if _opportunity_needs_review(item)),
        pending_document_review_count=sum(1 for item in documents if _is_retrieved_document(item) and not _review_is_approved(item.human_review_status)),
        pending_quality_question_review_count=sum(1 for item in questions if not _review_is_approved(item.human_review_status)),
        missing_source_url_count=sum(1 for status in source_statuses if status.missing),
        placeholder_source_url_count=sum(1 for status in source_statuses if status.placeholder),
        invalid_source_url_count=sum(1 for status in source_statuses if not status.valid and not status.placeholder and not status.missing),
        interested_without_retrieval_task_count=len(interested_without_task),
        digest_profile_exists=bool(digest),
        digest_profile_enabled=bool(digest and digest.enabled),
        recipients_count=len(recipients),
        delivery_mode=delivery_mode,
        export_format=digest.export_format if digest else "pdf",
        latest_report_generated_at=latest_report.generated_at if latest_report else None,
        latest_email_delivery_status=latest_email.status if latest_email else "not sent",
    )

    result.blockers.extend(_coverage_blockers(result, settings.cof_min_customers))
    for source_key, label in required_sources.items():
        if source_key not in source_keys:
            result.blockers.append(f"Required source missing: {label}.")
    for source_key, label in REQUIRED_SOURCE_KEYS.items():
        if source_key in source_keys and source_key not in active_source_keys:
            result.blockers.append(f"Required source inactive: {label}.")
    for family in sorted(REQUIRED_PORTAL_FAMILIES - platform_names):
        result.blockers.append(f"Required portal family missing: {family}.")
    missing_portal_customers = [customer.customer_name for customer in customers if customer.id not in portal_customer_ids]
    if missing_portal_customers:
        result.blockers.append(f"{len(missing_portal_customers)} COF customer(s) have no portal route configured.")
    metadata_warnings = _customer_metadata_warnings(customers)
    result.warnings.extend(metadata_warnings)
    if result.placeholder_source_url_count:
        result.blockers.append(f"{result.placeholder_source_url_count} opportunity source reference(s) are pending validation.")
    if result.invalid_source_url_count:
        result.blockers.append(f"{result.invalid_source_url_count} opportunity source URL(s) need validation.")
    if result.missing_source_url_count:
        result.blockers.append(f"{result.missing_source_url_count} opportunity source URL(s) are missing.")
    if result.pending_human_review_count:
        result.blockers.append(f"{result.pending_human_review_count} opportunity record(s) are still inside the Human Review Gate.")
    if result.pending_document_review_count:
        result.blockers.append(f"{result.pending_document_review_count} retrieved document(s) are pending review.")
    if result.pending_quality_question_review_count:
        result.blockers.append(f"{result.pending_quality_question_review_count} quality question(s) are pending review.")
    if result.interested_without_retrieval_task_count:
        result.blockers.append(f"{result.interested_without_retrieval_task_count} client interest signal(s) have no document retrieval task.")
    if not result.digest_profile_exists:
        result.blockers.append("COF Monday digest profile is missing.")
    elif not result.digest_profile_enabled:
        result.blockers.append("COF Monday digest profile is disabled.")
    if result.recipients_count == 0:
        result.blockers.append("No weekly report recipients are configured.")
    if not result.export_format:
        result.blockers.append("Digest export format is not configured.")
    if report_mode == "final" and settings.cof_client_name_mode == "placeholder":
        result.blockers.append("Final customer pack cannot use raw COF client placeholder names.")
    if not result.kra_enabled:
        result.blockers.append("KRA agent profiles are not configured.")
    if not result.kra_recent_run_present:
        if deterministic_kra:
            result.warnings.append("KRA is operating in deterministic/manual mode; no recent completed KRA run is required for this pilot.")
        else:
            result.blockers.append("No recent completed KRA run is present.")
    if result.kra_pending_findings_count and report_mode == "final":
        result.warnings.append(f"{result.kra_pending_findings_count} KRA finding(s) remain pending review and are excluded from the final pack.")

    result.ready_for_final_pack = not result.blockers
    return result


def _coverage_blockers(result: COFReadinessResult, minimum_customers: int) -> list[str]:
    blockers = []
    if result.customers_configured_count < minimum_customers:
        blockers.append(f"At least {minimum_customers} COF customers are required; {result.customers_configured_count} configured.")
    if result.customers_with_visible_items_count < result.customers_configured_count:
        blockers.append(
            f"{result.customers_configured_count - result.customers_with_visible_items_count} COF customer(s) have no visible pipeline items."
        )
    return blockers


def _customer_metadata_warnings(customers: list[Customer]) -> list[str]:
    warnings = []
    for customer in customers:
        missing = []
        if not customer.sector:
            missing.append("sector")
        if not customer.region:
            missing.append("region")
        if not customer.aliases:
            missing.append("aliases")
        if not customer.strategic_notes:
            missing.append("CPV/watch metadata")
        if missing:
            warnings.append(f"{customer.customer_name} missing {', '.join(missing)}.")
    return warnings


def _latest_completed_kra_run(runs: list[KRAResearchRun]) -> KRAResearchRun | None:
    cutoff = datetime.now(UTC) - timedelta(days=14)
    for run in runs:
        started_at = _as_utc(run.started_at)
        if run.status in {"completed", "succeeded", "success"} and started_at >= cutoff:
            return run
    return None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _records_for_opportunities(session: Session, model, opportunity_ids: set[int]):
    if not opportunity_ids:
        return []
    return list(session.exec(select(model).where(model.opportunity_id.in_(opportunity_ids))))


def _review_is_approved(value: str) -> bool:
    return (value or "").lower() in APPROVED_REVIEW_STATUSES


def _opportunity_needs_review(item: Opportunity) -> bool:
    return (item.status or "").lower() in {"new", "needs_review", "review_required", "pending_review", "document_retrieval_required", "questions_extracted"}


def _is_retrieved_document(item: OpportunityDocument) -> bool:
    doc_type = (item.document_type or "").lower()
    status = (item.retrieval_status or "").lower()
    return doc_type in {"itt_extract", "automated_retrieval", "retrieved", "permitted_extract"} or status in {
        "retrieved",
        "completed",
        "automated_retrieval",
    }


def _split_recipients(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace(",", ";").split(";") if item.strip()]
