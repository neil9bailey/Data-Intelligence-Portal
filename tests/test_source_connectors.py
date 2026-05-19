import json

from sqlmodel import select

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
