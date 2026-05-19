import json

from sqlmodel import select

from app.cof_readiness import cof_source_health
from app.intelligence import FetchResult, run_kra_research, run_source_check
from app.models import KRAResearchRun, Opportunity, OpportunityMatchEvidence, ProcurementSource
from app.source_connectors import connector_for_source


def ocds_payload(title="National Highways roadside technology services"):
    return json.dumps(
        {
            "releases": [
                {
                    "id": "ocds-test-1",
                    "ocid": "ocds-test-1",
                    "date": "2026-05-19T10:00:00Z",
                    "tag": ["tender"],
                    "buyer": {"name": "National Highways"},
                    "tender": {
                        "title": title,
                        "description": "Traffic operations, cyber resilience, SCADA and network communications.",
                        "status": "active",
                    },
                    "links": {"self": "https://www.find-tender.service.gov.uk/Notice/000001-2026"},
                }
            ]
        }
    )


def test_contracts_finder_connector_builds_official_query():
    source = ProcurementSource(
        name="Contracts Finder",
        source_key="contracts_finder",
        base_url="https://www.contractsfinder.service.gov.uk",
        query_url="https://www.contractsfinder.service.gov.uk/Search",
    )

    url = connector_for_source(source).build_query(["National Highways", "SCADA"])

    assert "Published/Notices/OCDS/Search" in url
    assert "National+Highways" in url


def test_contracts_finder_connector_renders_configured_date_placeholders(reference_session):
    source = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "contracts_finder")).first()

    url = connector_for_source(source).build_query(["National Highways", "SCADA"])

    assert "{published_from}" not in url
    assert "{published_to}" not in url
    assert "publishedFrom=" in url
    assert "publishedTo=" in url
    assert "limit=100" in url


def test_find_a_tender_connector_renders_configured_date_placeholders(reference_session):
    source = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender")).first()

    url = connector_for_source(source).build_query(["National Highways", "SCADA"])

    assert "{updated_from}" not in url
    assert "{updated_to}" not in url
    assert "updatedFrom=" in url
    assert "updatedTo=" in url
    assert "limit=100" in url


def test_find_a_tender_connector_creates_opportunity_and_match_evidence(reference_session):
    source = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender")).first()

    def fake_fetcher(url):
        return FetchResult(True, 200, url, ocds_payload(), "application/json")

    run = run_kra_research(reference_session, source_ids=[source.id], query="roadside technology cyber", fetcher=fake_fetcher)

    assert reference_session.get(KRAResearchRun, run.id) is not None
    opportunity = reference_session.exec(select(Opportunity).where(Opportunity.ocid == "ocds-test-1")).first()
    assert opportunity is not None
    assert reference_session.exec(select(OpportunityMatchEvidence).where(OpportunityMatchEvidence.opportunity_id == opportunity.id)).first() is not None


def test_source_check_classifies_rate_limit(reference_session):
    source = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "contracts_finder")).first()

    def fake_fetcher(url):
        return FetchResult(False, 429, url, "", "application/json", error="Rate limited by provider")

    snapshot = run_source_check(reference_session, source.id, fetcher=fake_fetcher)

    assert snapshot.ok is False
    assert snapshot.detected_schema == "rate_limited"
    assert snapshot.connector_status == "contracts_finder_rate_limited"


def test_contracts_finder_connector_retries_rate_limit_then_success():
    source = ProcurementSource(
        name="Contracts Finder",
        source_key="contracts_finder",
        base_url="https://www.contractsfinder.service.gov.uk",
        query_url="https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search?limit=50",
    )
    connector = connector_for_source(source)
    calls = []

    def fake_fetcher(url):
        calls.append(url)
        if len(calls) == 1:
            return FetchResult(False, 429, url, "", "application/json", error="Rate limited", retry_after_seconds=0)
        return FetchResult(True, 200, url, ocds_payload(), "application/json")

    result = connector.fetch_page(connector.build_query(["National Highways"]), fake_fetcher)

    assert result.ok is True
    assert result.status_code == 200
    assert len(calls) == 2
    assert connector.detect_schema(result) == "ocds_json"


def test_find_a_tender_connector_stops_after_retryable_failure():
    source = ProcurementSource(
        name="Find a Tender",
        source_key="find_a_tender",
        base_url="https://www.find-tender.service.gov.uk",
        query_url="https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages",
    )
    connector = connector_for_source(source)
    calls = []

    def fake_fetcher(url):
        calls.append(url)
        return FetchResult(False, 503, url, "", "application/json", error="Service unavailable", retry_after_seconds=0)

    result = connector.fetch_page(connector.build_query(["SCADA"]), fake_fetcher)

    assert result.ok is False
    assert result.status_code == 503
    assert len(calls) == 3
    assert "Retried 2 time(s)" in result.error


def test_provider_next_page_keeps_to_approved_domains():
    source = ProcurementSource(
        name="Find a Tender",
        source_key="find_a_tender",
        base_url="https://www.find-tender.service.gov.uk",
        query_url="https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages",
    )
    connector = connector_for_source(source)
    payload = json.dumps({"links": {"next": "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?page=2"}})

    assert connector.next_page(FetchResult(True, 200, source.query_url, payload, "application/json")).endswith("page=2")
    blocked = json.dumps({"links": {"next": "https://example.com/not-approved"}})
    assert connector.next_page(FetchResult(True, 200, source.query_url, blocked, "application/json")) == ""


def test_kra_query_failure_does_not_downgrade_source_catalogue_health(reference_session):
    source = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender")).first()

    def source_check_fetcher(url):
        return FetchResult(True, 200, url, ocds_payload(), "application/json")

    def kra_fetcher(url):
        return FetchResult(False, 429, url, "", "application/json", error="Rate limited by provider")

    run_source_check(reference_session, source.id, fetcher=source_check_fetcher)
    run_kra_research(reference_session, source_ids=[source.id], query="highways maintenance", fetcher=kra_fetcher)

    health = {item.key: item for item in cof_source_health(reference_session)}

    assert health["find_a_tender"].status == "active"
