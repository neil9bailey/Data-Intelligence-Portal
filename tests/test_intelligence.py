import json

from sqlmodel import select

from app.audit import compact_snapshot
from app.intelligence import (
    FetchResult,
    extract_document_intelligence,
    parse_feed_items,
    repair_mismatched_customer_assignments,
    run_kra_research,
    run_source_check,
    source_allowed,
)
from app.llm import llm_enabled
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
from app.settings import get_settings


def test_source_allowlist():
    assert source_allowed("https://www.gov.uk/contracts-finder")
    assert source_allowed("https://www.find-tender.service.gov.uk/Developer/Documentation")
    assert source_allowed("https://nationalhighways.co.uk/suppliers/")
    assert source_allowed("https://www.nationalhighways.co.uk/suppliers/")
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


def test_source_check_categorises_rate_limit_failures(session):
    source = ProcurementSource(
        name="Rate limited source",
        base_url="https://www.find-tender.service.gov.uk",
        query_url="https://www.find-tender.service.gov.uk/Search/Results?Keywords=National%20Highways",
        active=True,
    )
    session.add(source)
    session.commit()
    session.refresh(source)

    def fake_fetcher(url):
        return FetchResult(False, 429, url, "", "text/plain", "HTTP 429 rate/service limit; retry after 11 seconds")

    snapshot = run_source_check(session, source.id, fetcher=fake_fetcher)

    assert snapshot.change_type == "failed"
    assert snapshot.detected_schema == "rate_limited"
    assert "retry after 11 seconds" in snapshot.notes


def test_source_check_categorises_guardrail_failures(session):
    source = ProcurementSource(
        name="Blocked source",
        base_url="https://example.com",
        query_url="https://example.com/source",
        active=True,
    )
    session.add(source)
    session.commit()
    session.refresh(source)

    def fake_fetcher(url):
        return FetchResult(False, 0, url, "", "", "Blocked by approved-source allow-list.")

    snapshot = run_source_check(session, source.id, fetcher=fake_fetcher)

    assert snapshot.detected_schema == "guardrail_blocked"
    assert snapshot.notes == "Blocked by approved-source allow-list."


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


def test_kra_run_adds_ai_summary_when_llm_enabled(seeded_session, monkeypatch):
    source = seeded_session.exec(select(ProcurementSource).where(ProcurementSource.active == True)).first()  # noqa: E712
    payload = {
        "releases": [
            {
                "id": "notice-ai",
                "ocid": "ocds-test-ai",
                "date": "2026-05-17T12:00:00Z",
                "tag": ["tender"],
                "buyer": {"name": "National Highways"},
                "tender": {
                    "title": "National Highways roadside data service",
                    "description": "Roadside operational technology and real-time data services.",
                    "status": "active",
                },
                "links": {"self": "https://www.find-tender.service.gov.uk/Notice/ai"},
            }
        ]
    }

    def fake_fetcher(url):
        return FetchResult(True, 200, url, json.dumps(payload), "application/json")

    monkeypatch.setattr("app.intelligence.llm_enabled", lambda: True)
    monkeypatch.setattr("app.intelligence.generate_llm_text", lambda *args, **kwargs: "AI summary for review.")

    run = run_kra_research(seeded_session, source_id=source.id, query="National Highways", fetcher=fake_fetcher)

    finding = seeded_session.exec(select(KRAFinding).where(KRAFinding.finding_type == "ai_research_summary")).first()
    assert run.status == "completed"
    assert finding is not None
    assert "Requires human review" in finding.summary


def test_customer_scoped_kra_filters_irrelevant_buyer_and_marks_award(seeded_session):
    customer = seeded_session.exec(select(Customer).where(Customer.customer_name == "National Highways")).first()
    source = seeded_session.exec(select(ProcurementSource).where(ProcurementSource.active == True)).first()  # noqa: E712
    payload = {
        "releases": [
            {
                "id": "moj-prison-education",
                "ocid": "ocds-test-moj",
                "date": "2026-05-18T09:00:00Z",
                "tag": ["award"],
                "buyer": {"name": "Ministry of Justice"},
                "tender": {
                    "title": "Award of a Call-Off Contract under the Prison Education Dynamic Purchasing System for a Self-Employment training course for Prisoners at HMP Lewes",
                    "description": "Self-employment training course for prisoners.",
                    "status": "complete",
                },
                "links": {"self": "https://www.contractsfinder.service.gov.uk/Notice/moj-prison-education"},
            },
            {
                "id": "nh-award-1",
                "ocid": "ocds-test-nh-award",
                "date": "2026-05-18T09:00:00Z",
                "tag": ["award"],
                "buyer": {"name": "National Highways Limited"},
                "tender": {
                    "title": "National Highways roadside technology support award",
                    "description": "Operational technology support for the strategic road network.",
                    "status": "complete",
                },
                "links": {"self": "https://www.contractsfinder.service.gov.uk/Notice/nh-award-1"},
            },
        ]
    }

    def fake_fetcher(url):
        return FetchResult(True, 200, url, json.dumps(payload), "application/json")

    run = run_kra_research(
        seeded_session,
        source_id=source.id,
        customer_id=customer.id,
        query="National Highways",
        fetcher=fake_fetcher,
    )

    assert run.status == "completed"
    assert seeded_session.exec(select(Opportunity).where(Opportunity.notice_identifier == "moj-prison-education")).first() is None
    opportunity = seeded_session.exec(select(Opportunity).where(Opportunity.notice_identifier == "nh-award-1")).first()
    assert opportunity is not None
    assert opportunity.customer_id == customer.id
    assert opportunity.status == "award_notice"


def test_data_quality_repair_unassigns_mismatched_customer_opportunity(seeded_session):
    customer = seeded_session.exec(select(Customer).where(Customer.customer_name == "National Highways")).first()
    opportunity = Opportunity(
        customer_id=customer.id,
        business_unit_id=customer.business_unit_id,
        title="Award of a Call-Off Contract under the Prison Education Dynamic Purchasing System",
        buyer_name="Ministry of Justice",
        status="new",
        relevance_score=50,
    )
    seeded_session.add(opportunity)
    seeded_session.commit()
    seeded_session.refresh(opportunity)

    repaired = repair_mismatched_customer_assignments(seeded_session)

    seeded_session.refresh(opportunity)
    assert repaired >= 1
    assert opportunity.customer_id is None
    assert opportunity.business_unit_id is None
    assert opportunity.status == "needs_review"
    assert "did not match National Highways aliases" in opportunity.relevance_rationale


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
    assert "AI-Assisted Executive Brief" in report.markdown
    assert "not a bid/no-bid" in report.markdown


def test_report_generation_uses_ai_brief_when_llm_enabled(seeded_session, monkeypatch):
    monkeypatch.setattr("app.reports.llm_enabled", lambda: True)
    monkeypatch.setattr("app.reports.generate_llm_text", lambda *args, **kwargs: "Executive AI briefing text.")

    report = create_report(seeded_session, "AI report")

    assert "Executive AI briefing text." in report.markdown
    assert "Requires human review before onward use." in report.markdown


def test_report_generation_can_skip_report_level_ai_brief(seeded_session, monkeypatch):
    monkeypatch.setattr("app.reports.llm_enabled", lambda: True)
    monkeypatch.setattr("app.reports.generate_llm_text", lambda *args, **kwargs: "Should not be called.")

    report = create_report(seeded_session, "Automation report", include_ai_brief=False)

    assert "Report-level AI brief was skipped for the automated cycle" in report.markdown
    assert "Should not be called." not in report.markdown


def test_llm_enabled_requires_provider_model_and_key(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("KRA_LLM_PROVIDER", "openai_direct")
    monkeypatch.setenv("KRA_API_KEY", "test-key")
    monkeypatch.setenv("KRA_MODEL", "gpt-5.4")

    assert llm_enabled()

    monkeypatch.setenv("KRA_API_KEY", "")
    get_settings.cache_clear()
    assert not llm_enabled()
    get_settings.cache_clear()


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
