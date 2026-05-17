import json

from sqlmodel import select

from app.audit import compact_snapshot
from app.intelligence import FetchResult, extract_document_intelligence, parse_feed_items, run_kra_research, run_source_check, source_allowed
from app.models import (
    Customer,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    EmailConfiguration,
    KRAFinding,
    NewsFeedSource,
    Opportunity,
    OpportunityDocument,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.reports import create_report


def test_source_allowlist():
    assert source_allowed("https://www.gov.uk/contracts-finder")
    assert source_allowed("https://www.find-tender.service.gov.uk/Developer/Documentation")
    assert not source_allowed("http://www.gov.uk/contracts-finder")
    assert not source_allowed("https://example.com/not-approved")


def test_source_check_tracks_first_seen_unchanged_changed(session):
    source = ProcurementSource(
        name="Test source",
        base_url="https://www.find-tender.service.gov.uk",
        query_url="https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?limit=1",
        active=True,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    payloads = iter(["{\"releases\":[]}", "{\"releases\":[]}", "{\"releases\":[{\"id\":\"changed\"}]}"])

    def fake_fetcher(url):
        return FetchResult(True, 200, url, next(payloads), "application/json")

    first = run_source_check(session, source.id, fetcher=fake_fetcher)
    second = run_source_check(session, source.id, fetcher=fake_fetcher)
    third = run_source_check(session, source.id, fetcher=fake_fetcher)

    assert [first.change_type, second.change_type, third.change_type] == ["first_seen", "unchanged", "changed"]
    assert len(list(session.exec(select(SourceCheckSnapshot)))) == 3


def test_kra_run_creates_findings_opportunity_and_requirements(seeded_session):
    source = seeded_session.exec(select(ProcurementSource).where(ProcurementSource.active == True)).first()  # noqa: E712
    payload = {
        "releases": [
            {
                "id": "notice-1",
                "ocid": "ocds-test-1",
                "date": "2026-05-17T12:00:00Z",
                "tag": ["tender"],
                "buyer": {"name": "National Highways"},
                "tender": {
                    "title": "National Highways cyber resilience data platform",
                    "description": "Operational resilience, cyber security, real-time data and service management.",
                    "status": "active",
                    "value": {"amount": 1000000, "currency": "GBP"},
                    "tenderPeriod": {"endDate": "2026-07-01T12:00:00Z"},
                },
                "links": {"self": "https://www.find-tender.service.gov.uk/Notice/1"},
            }
        ]
    }

    def fake_fetcher(url):
        return FetchResult(True, 200, url, json.dumps(payload), "application/json")

    run = run_kra_research(seeded_session, source_id=source.id, query="National Highways cyber resilience", fetcher=fake_fetcher)

    assert run.status == "completed"
    assert seeded_session.exec(select(KRAFinding)).first() is not None
    assert seeded_session.exec(select(Opportunity).where(Opportunity.notice_identifier == "notice-1")).first() is not None
    assert seeded_session.exec(select(ExtractedRequirement)).first() is not None


def test_document_extraction_creates_quality_question(seeded_session):
    opportunity = seeded_session.exec(select(Opportunity)).first()
    document = OpportunityDocument(
        opportunity_id=opportunity.id,
        title="Quality questions",
        document_type="itt_extract",
        content_summary="Operational resilience quality response.",
    )
    seeded_session.add(document)
    seeded_session.commit()
    seeded_session.refresh(document)

    _, question_count = extract_document_intelligence(
        seeded_session,
        opportunity,
        document,
        "Quality question 1: Describe your resilient real-time service management approach. Weighting 25%",
    )
    seeded_session.commit()

    question = seeded_session.exec(select(ExtractedQualityQuestion)).first()
    assert question_count == 1
    assert question.weighting == "25%"


def test_report_generation_contains_kra_runtime(seeded_session):
    report = create_report(seeded_session, "Test report")

    assert report.id is not None
    assert "KRA runtime" in report.markdown
    assert "not a bid/no-bid" in report.markdown


def test_reference_seed_keeps_customer_and_content_tables_clean(reference_session):
    assert list(reference_session.exec(select(Customer))) == []
    assert list(reference_session.exec(select(Opportunity))) == []
    assert list(reference_session.exec(select(KRAFinding))) == []
    assert len(list(reference_session.exec(select(ProcurementSource)))) >= 1
    assert len(list(reference_session.exec(select(NewsFeedSource)))) >= 1


def test_atom_feed_parser_extracts_items():
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Procurement update</title>
        <link href="https://www.gov.uk/example-update"/>
        <updated>2026-05-17T10:30:00Z</updated>
        <summary>Commercial policy signal for review.</summary>
      </entry>
    </feed>"""

    items = parse_feed_items(feed, "https://www.gov.uk/example.atom")

    assert items[0]["title"] == "Procurement update"
    assert items[0]["link"] == "https://www.gov.uk/example-update"
    assert items[0]["content_hash"]


def test_audit_snapshot_redacts_email_password():
    snapshot = compact_snapshot(EmailConfiguration(smtp_password="super-secret"))

    assert "super-secret" not in snapshot
    assert "***redacted***" in snapshot
