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
    EmailConfiguration,
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
    SourceCheckSnapshot,
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
PRIMARY_SOURCE_STATUSES = {"active", "stale", "failed", "ignored"}
SOURCE_FRESHNESS_DAYS = 7


@dataclass
class SourceHealthItem:
    key: str
    label: str
    status: str
    role: str = "primary"
    active: bool = False
    connector_status: str = ""
    last_checked_at: datetime | None = None
    last_status: str = ""
    message: str = ""

    @property
    def trusted_for_output(self) -> bool:
        return self.role == "primary" and self.status in {"active", "stale", "failed"}

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "role": self.role,
            "active": self.active,
            "connector_status": self.connector_status,
            "last_checked_at": self.last_checked_at.isoformat(timespec="seconds") if self.last_checked_at else None,
            "last_status": self.last_status,
            "message": self.message,
        }


@dataclass
class COFOperatingStatus:
    status: str
    source_health: list[SourceHealthItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    delivery_warnings: list[str] = field(default_factory=list)
    ignored_opportunity_count: int = 0
    customers_configured_count: int = 0
    recipients_count: int = 0
    delivery_mode: str = "file_outbox"

    @property
    def ready_for_weekly_send(self) -> bool:
        return self.status == "Ready for weekly send"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ready_for_weekly_send": self.ready_for_weekly_send,
            "source_health": [item.as_dict() for item in self.source_health],
            "warnings": self.warnings,
            "delivery_warnings": self.delivery_warnings,
            "ignored_opportunity_count": self.ignored_opportunity_count,
            "customers_configured_count": self.customers_configured_count,
            "recipients_count": self.recipients_count,
            "delivery_mode": self.delivery_mode,
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
    report_status: str = "Review recommended"
    source_health: list[SourceHealthItem] = field(default_factory=list)
    ignored_source_count: int = 0
    stale_source_count: int = 0
    failed_source_count: int = 0

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
            "report_status": self.report_status,
            "source_health": [item.as_dict() for item in self.source_health],
            "ignored_source_count": self.ignored_source_count,
            "stale_source_count": self.stale_source_count,
            "failed_source_count": self.failed_source_count,
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


def cof_source_health(session: Session, freshness_days: int = SOURCE_FRESHNESS_DAYS) -> list[SourceHealthItem]:
    sources = list(session.exec(select(ProcurementSource)))
    snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(200)))
    latest_by_source: dict[int, SourceCheckSnapshot] = {}
    for snapshot in snapshots:
        if _is_kra_query_snapshot(snapshot):
            continue
        if snapshot.source_id and snapshot.source_id not in latest_by_source:
            latest_by_source[snapshot.source_id] = snapshot
    by_key = {source.source_key: source for source in sources if source.source_key}
    health: list[SourceHealthItem] = []
    for key, label in {**REQUIRED_SOURCE_KEYS, **BACKUP_SOURCE_KEYS}.items():
        source = by_key.get(key)
        role = "backup" if key in BACKUP_SOURCE_KEYS else "primary"
        if not source:
            health.append(SourceHealthItem(key=key, label=label, status="failed", role=role, message="Source catalogue entry is missing."))
            continue
        if role == "backup":
            health.append(
                SourceHealthItem(
                    key=key,
                    label=label,
                    status="backup",
                    role=role,
                    active=source.active,
                    connector_status=source.connector_status,
                    last_checked_at=source.last_checked_at,
                    last_status=source.last_status,
                    message="Backup source configured for future approved use.",
                )
            )
            continue
        latest = latest_by_source.get(source.id or 0)
        last_checked = latest.checked_at if latest else source.last_checked_at
        status_text = " ".join(
            [
                source.connector_status or "",
                source.last_status or "",
                latest.connector_status if latest else "",
                latest.notes if latest else "",
            ]
        ).lower()
        if not source.active:
            status = "ignored"
            message = "Source is configured but inactive, so its opportunities are ignored from output."
        elif any(token in status_text for token in ("failed", "error", "unreachable", "blocked", "rate_limited", "rate limited")):
            status = "failed"
            message = "Latest connector/source check needs attention; existing curated records remain reportable while new ingestion is reviewed."
        elif latest and not latest.ok:
            status = "failed"
            message = "Latest source check failed; existing curated records remain reportable while new ingestion is reviewed."
        elif last_checked and _as_utc(last_checked) < datetime.now(UTC) - timedelta(days=freshness_days):
            status = "stale"
            message = f"Source has not refreshed within {freshness_days} days; run a refresh before relying on new ingestion."
        elif not last_checked and not any(token in status_text for token in ("live_public_source", "live_mvp", "active")):
            status = "stale"
            message = "Source is configured but has no proven recent check; run a check before relying on new ingestion."
        else:
            status = "active"
            message = "Source is available for opportunity output."
        health.append(
            SourceHealthItem(
                key=key,
                label=label,
                status=status,
                role=role,
                active=source.active,
                connector_status=source.connector_status,
                last_checked_at=last_checked,
                last_status=source.last_status or (str(latest.status_code) if latest else ""),
                message=message,
            )
        )
    return health


def trusted_cof_source_ids(session: Session) -> set[int]:
    trusted_keys = {item.key for item in cof_source_health(session) if item.trusted_for_output}
    if not trusted_keys:
        return set()
    return {
        source.id
        for source in session.exec(select(ProcurementSource))
        if source.id and source.source_key in trusted_keys
    }


def cof_operating_status(
    session: Session,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
) -> COFOperatingStatus:
    readiness = cof_readiness(session, customer_id=customer_id, business_unit_id=business_unit_id, report_mode="final")
    source_health = readiness.source_health or cof_source_health(session)
    source_warnings = [
        f"{item.label}: {item.status} - {item.message}"
        for item in source_health
        if item.status in {"stale", "failed", "ignored"}
    ]
    delivery_warnings: list[str] = []
    if not readiness.digest_profile_exists:
        delivery_warnings.append("Weekly report digest profile is not configured.")
    elif not readiness.digest_profile_enabled:
        delivery_warnings.append("Weekly report digest profile is disabled.")
    if readiness.recipients_count == 0:
        delivery_warnings.append("No weekly report recipients are configured; download/file-outbox remains available.")
    if readiness.failed_source_count or readiness.stale_source_count:
        status = "Needs source attention"
    elif readiness.pending_human_review_count or readiness.pending_document_review_count or readiness.pending_quality_question_review_count:
        status = "Review recommended"
    elif delivery_warnings:
        status = "Review recommended"
    else:
        status = "Ready for weekly send"
    return COFOperatingStatus(
        status=status,
        source_health=source_health,
        warnings=[*source_warnings, *readiness.warnings],
        delivery_warnings=delivery_warnings,
        ignored_opportunity_count=readiness.ignored_source_count,
        customers_configured_count=readiness.customers_configured_count,
        recipients_count=readiness.recipients_count,
        delivery_mode=readiness.delivery_mode,
    )


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

    source_health = cof_source_health(session)
    health_by_key = {item.key: item for item in source_health}
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
    email_config = session.exec(select(EmailConfiguration).order_by(EmailConfiguration.id)).first()
    recipient_source = digest.recipients if digest and digest.recipients else ""
    if not recipient_source and email_config and email_config.default_recipients:
        recipient_source = email_config.default_recipients
    if not recipient_source:
        recipient_source = settings.email_default_recipients
    recipients = _split_recipients(recipient_source)
    delivery_mode = settings.email_delivery_mode or "file_outbox"

    result = COFReadinessResult(
        ready_for_final_pack=True,
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
        source_health=source_health,
        ignored_source_count=sum(1 for item in source_health if item.status == "ignored"),
        stale_source_count=sum(1 for item in source_health if item.status == "stale"),
        failed_source_count=sum(1 for item in source_health if item.status == "failed"),
    )

    result.warnings.extend(_coverage_blockers(result, settings.cof_min_customers))
    for source_key, label in {**REQUIRED_SOURCE_KEYS, **BACKUP_SOURCE_KEYS}.items():
        if source_key not in source_keys:
            result.warnings.append(f"Required source missing: {label}.")
    for source_key, label in REQUIRED_SOURCE_KEYS.items():
        health = health_by_key.get(source_key)
        if source_key in source_keys and source_key not in active_source_keys:
            result.warnings.append(f"Required source inactive/ignored: {label}.")
        elif health and health.status in {"stale", "failed", "ignored"}:
            result.warnings.append(f"{label} source health is {health.status}: {health.message}")
    for family in sorted(REQUIRED_PORTAL_FAMILIES - platform_names):
        result.warnings.append(f"Required portal family missing: {family}.")
    missing_portal_customers = [customer.customer_name for customer in customers if customer.id not in portal_customer_ids]
    if missing_portal_customers:
        result.warnings.append(f"{len(missing_portal_customers)} COF customer(s) have no portal route configured.")
    metadata_warnings = _customer_metadata_warnings(customers)
    result.warnings.extend(metadata_warnings)
    if result.placeholder_source_url_count:
        result.warnings.append(f"{result.placeholder_source_url_count} opportunity source reference(s) are pending validation.")
    if result.invalid_source_url_count:
        result.warnings.append(f"{result.invalid_source_url_count} opportunity source URL(s) need validation.")
    if result.missing_source_url_count:
        result.warnings.append(f"{result.missing_source_url_count} opportunity source URL(s) are missing.")
    if result.pending_human_review_count:
        result.warnings.append(f"{result.pending_human_review_count} opportunity record(s) are still inside the Human Review Gate.")
    if result.pending_document_review_count:
        result.warnings.append(f"{result.pending_document_review_count} retrieved document(s) are pending review.")
    if result.pending_quality_question_review_count:
        result.warnings.append(f"{result.pending_quality_question_review_count} quality question(s) are pending review.")
    if result.interested_without_retrieval_task_count:
        result.warnings.append(f"{result.interested_without_retrieval_task_count} client interest signal(s) have no document retrieval task.")
    if not result.digest_profile_exists:
        result.warnings.append("COF Monday digest profile is missing.")
    elif not result.digest_profile_enabled:
        result.warnings.append("COF Monday digest profile is disabled.")
    if result.recipients_count == 0:
        result.warnings.append("No weekly report recipients are configured; report downloads remain available.")
    if not result.export_format:
        result.warnings.append("Digest export format is not configured.")
    if report_mode == "final" and settings.cof_client_name_mode == "placeholder":
        result.warnings.append("Raw COF client placeholder names are visible because placeholder mode is enabled.")
    if not result.kra_enabled:
        result.warnings.append("KRA agent profiles are not configured.")
    if not result.kra_recent_run_present:
        if deterministic_kra:
            result.warnings.append("KRA is operating in deterministic/manual mode; no recent completed KRA run is required for this pilot.")
        else:
            result.warnings.append("No recent completed KRA run is present.")
    if result.kra_pending_findings_count and report_mode == "final":
        result.warnings.append(f"{result.kra_pending_findings_count} KRA finding(s) remain pending review and are excluded from the final pack.")

    if result.failed_source_count or result.stale_source_count:
        result.report_status = "Needs source attention"
    elif result.warnings:
        result.report_status = "Review recommended"
    else:
        result.report_status = "Ready for weekly send"
    result.ready_for_final_pack = True
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


def _is_kra_query_snapshot(snapshot: SourceCheckSnapshot) -> bool:
    return (snapshot.notes or "").lower().startswith("kra query:")


def _split_recipients(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace(",", ";").split(";") if item.strip()]
