from __future__ import annotations

from datetime import UTC, datetime
import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from sqlmodel import Session, select

from app.audit import compact_snapshot, log_event
from app.intelligence import FetchResult, content_hash, extract_document_intelligence, source_allowed, textish
from app.models import (
    BuyerPortalInstance,
    KRAFinding,
    Opportunity,
    OpportunityDocument,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementPlatform,
)


AUTOMATED_METHODS = {"public_api_no_key", "api_key_header", "api_key_query", "oauth_client_credentials"}
SUPPORTED_AUTH_TYPES = {"none", "api_key_header", "api_key_query"}


def split_domains(value: str) -> set[str]:
    domains: set[str] = set()
    for item in (value or "").replace(",", ";").split(";"):
        cleaned = item.strip().lower()
        if cleaned:
            domains.add(cleaned.removeprefix("https://").removeprefix("http://").split("/")[0])
    return domains


def host_matches(host: str, allowed_domain: str) -> bool:
    host = host.lower()
    allowed_domain = allowed_domain.lower()
    return host == allowed_domain or host.endswith(f".{allowed_domain}")


def permitted_portal_domains(session: Session, connector: PortalInformationConnector) -> set[str]:
    domains: set[str] = set()
    portal = session.get(BuyerPortalInstance, connector.portal_instance_id) if connector.portal_instance_id else None
    if portal:
        if portal.portal_url:
            parsed = urlparse(portal.portal_url)
            if parsed.netloc:
                domains.add(parsed.netloc.lower())
        platform = session.get(ProcurementPlatform, portal.platform_id) if portal.platform_id else None
        if platform:
            domains.update(split_domains(platform.platform_domains))
    return domains


def connector_endpoint_allowed(session: Session, connector: PortalInformationConnector) -> bool:
    parsed = urlparse(connector.endpoint_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    if source_allowed(connector.endpoint_url):
        return True
    return any(host_matches(parsed.netloc, domain) for domain in permitted_portal_domains(session, connector))


def connector_secret(connector: PortalInformationConnector) -> str:
    if not connector.api_key_secret_name:
        return ""
    return os.getenv(connector.api_key_secret_name, "")


def url_with_api_key(url: str, key_name: str, api_key: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key_name or "api_key"] = api_key
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_auth_request(connector: PortalInformationConnector) -> tuple[str, dict[str, str], str]:
    url = connector.endpoint_url
    headers = {"User-Agent": "Data Intelligence Portal read-only retrieval connector", "Accept": "application/json,text/plain,text/html,*/*"}
    if connector.auth_type == "none":
        return url, headers, ""
    api_key = connector_secret(connector)
    if not api_key:
        return url, headers, f"Secret environment variable {connector.api_key_secret_name or '[missing]'} is not configured."
    if connector.auth_type == "api_key_header":
        headers[connector.api_key_header_name or "X-API-Key"] = api_key
    elif connector.auth_type == "api_key_query":
        url = url_with_api_key(url, connector.api_key_query_name or "api_key", api_key)
    else:
        return url, headers, f"Auth type {connector.auth_type} is not supported by the MVP connector runner."
    return url, headers, ""


def fetch_connector(connector: PortalInformationConnector) -> FetchResult:
    url, headers, error = build_auth_request(connector)
    if error:
        return FetchResult(False, 0, connector.endpoint_url, "", error=error)
    try:
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            response = client.get(url, headers=headers)
        return FetchResult(
            response.status_code < 400,
            response.status_code,
            str(response.url),
            response.text or "",
            response.headers.get("content-type", ""),
            "" if response.status_code < 400 else f"HTTP {response.status_code}",
        )
    except httpx.HTTPError as exc:
        return FetchResult(False, 0, connector.endpoint_url, "", error=f"Connector fetch failed: {exc}")


def retrieval_summary(text: str, content_type: str) -> str:
    cleaned = textish(text)
    if "json" in (content_type or "").lower():
        return f"Retrieved JSON payload for review. Preview: {cleaned[:900]}"
    if "<html" in cleaned[:2000].lower():
        return f"Retrieved HTML/web payload for review. Preview: {cleaned[:900]}"
    return cleaned[:1000]


def create_or_update_retrieved_document(
    session: Session,
    connector: PortalInformationConnector,
    opportunity: Opportunity,
    fetch: FetchResult,
    digest: str,
) -> tuple[OpportunityDocument, bool]:
    existing = session.exec(
        select(OpportunityDocument).where(
            OpportunityDocument.opportunity_id == opportunity.id,
            OpportunityDocument.source_hash == digest,
        )
    ).first()
    created = existing is None
    document = existing or OpportunityDocument(opportunity_id=opportunity.id or 0, title=f"Automated retrieval - {connector.connector_name}")
    before = compact_snapshot(document) if existing else ""
    document.title = f"Automated retrieval - {connector.connector_name}"
    document.document_type = "automated_retrieval"
    document.url_or_path = fetch.url
    document.source_hash = digest
    document.retrieval_status = "retrieved"
    document.human_review_status = "pending"
    document.platform_name = connector.connector_name
    document.content_summary = retrieval_summary(fetch.text, fetch.content_type)
    document.notes = (
        "Read-only automated information retrieval. Human review is required before onward use. "
        "No portal login, expression of interest or submission was performed."
    )
    document.extracted_at = datetime.now(UTC)
    session.add(document)
    session.flush()
    log_event(
        session,
        entity_type="OpportunityDocument",
        entity_id=document.id,
        action="create" if created else "update",
        summary=f"{'Created' if created else 'Updated'} automated retrieval document for {opportunity.title}",
        before=before,
        after=document,
    )
    return document, created


def create_retrieval_finding(
    session: Session,
    connector: PortalInformationConnector,
    portal: BuyerPortalInstance | None,
    fetch: FetchResult,
    digest: str,
) -> KRAFinding:
    finding = KRAFinding(
        customer_id=portal.customer_id if portal else None,
        finding_type="portal_retrieval",
        title=f"{connector.connector_name}: automated retrieval completed",
        summary=(
            f"Read-only connector fetched {fetch.url}; HTTP {fetch.status_code}; "
            f"content hash {digest[:12]}; human review required before report use."
        ),
        source_url=fetch.url,
        content_hash=digest,
        confidence="medium" if fetch.ok else "low",
        change_status="retrieved" if fetch.ok else "failed",
        human_review_status="pending",
    )
    session.add(finding)
    session.flush()
    log_event(session, entity_type="KRAFinding", entity_id=finding.id, action="create", summary=f"Created retrieval finding for {connector.connector_name}", after=finding)
    return finding


def run_portal_connector(session: Session, connector_id: int, fetcher=fetch_connector) -> PortalRetrievalRun:
    connector = session.get(PortalInformationConnector, connector_id)
    if not connector:
        raise ValueError(f"Connector {connector_id} not found")
    portal = session.get(BuyerPortalInstance, connector.portal_instance_id) if connector.portal_instance_id else None
    run = PortalRetrievalRun(
        connector_id=connector.id,
        portal_instance_id=connector.portal_instance_id,
        opportunity_id=connector.default_opportunity_id,
        status="started",
        guardrail_summary=(
            "Read-only information retrieval only. No portal login, expression of interest, "
            "message, customer contact or submission is automated."
        ),
    )
    session.add(run)
    session.flush()

    before = compact_snapshot(connector)
    now = datetime.now(UTC)
    connector.last_checked_at = now
    try:
        if not connector.enabled:
            raise ValueError("Connector is disabled.")
        if not connector.read_only:
            raise ValueError("Connector is not marked read-only.")
        if connector.integration_method not in AUTOMATED_METHODS:
            raise ValueError("Connector method is manual-assisted; no automated retrieval was run.")
        if connector.auth_type not in SUPPORTED_AUTH_TYPES:
            raise ValueError(f"Auth type {connector.auth_type} is not supported for automated retrieval.")
        if not connector_endpoint_allowed(session, connector):
            raise ValueError("Endpoint is outside the portal/platform/source allow-list.")
        fetch = fetcher(connector)
        digest = content_hash(fetch.text) if fetch.ok else ""
        run.http_status = fetch.status_code
        run.content_hash = digest
        run.items_found = 1 if fetch.ok and fetch.text else 0
        connector.last_http_status = fetch.status_code
        if not fetch.ok:
            raise ValueError(fetch.error or f"HTTP {fetch.status_code}")
        documents_created = 0
        findings_created = 0
        opportunity = session.get(Opportunity, connector.default_opportunity_id) if connector.default_opportunity_id else None
        if opportunity:
            document, created = create_or_update_retrieved_document(session, connector, opportunity, fetch, digest)
            documents_created = 1 if created else 0
            extract_document_intelligence(session, opportunity, document, fetch.text)
        else:
            create_retrieval_finding(session, connector, portal, fetch, digest)
            findings_created = 1
        run.status = "completed"
        run.documents_created = documents_created
        run.findings_created = findings_created
        connector.last_status = "completed"
    except ValueError as exc:
        run.status = "blocked" if "manual-assisted" in str(exc) or "disabled" in str(exc) else "failed"
        run.error_summary = str(exc)
        connector.last_status = run.error_summary
    run.finished_at = datetime.now(UTC)
    session.add(connector)
    session.add(run)
    log_event(
        session,
        entity_type="PortalRetrievalRun",
        entity_id=run.id,
        action="create",
        summary=f"Portal retrieval run {run.status} for {connector.connector_name}",
        after=run,
    )
    log_event(session, entity_type="PortalInformationConnector", entity_id=connector.id, action="update", summary=f"Updated connector status {connector.connector_name}", before=before, after=connector)
    session.commit()
    session.refresh(run)
    return run


def run_enabled_portal_connectors(
    session: Session,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
    fetcher=fetch_connector,
) -> list[PortalRetrievalRun]:
    connectors = list(session.exec(select(PortalInformationConnector).where(PortalInformationConnector.enabled == True)))  # noqa: E712
    runs: list[PortalRetrievalRun] = []
    for connector in connectors:
        portal = session.get(BuyerPortalInstance, connector.portal_instance_id) if connector.portal_instance_id else None
        if customer_id and portal and portal.customer_id != customer_id:
            continue
        if business_unit_id and portal and portal.business_unit_id != business_unit_id:
            continue
        runs.append(run_portal_connector(session, connector.id or 0, fetcher=fetcher))
    return runs
