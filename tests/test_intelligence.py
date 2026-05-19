import json

from sqlmodel import select

from app.audit import compact_snapshot
from app.email_service import resolve_smtp_password, send_or_store_email
from app.intelligence import (
    FetchResult,
    CandidateOpportunity,
    extract_document_intelligence,
    parse_feed_items,
    repair_low_quality_market_opportunities,
    repair_mismatched_customer_assignments,
    relevance_for_candidate,
    run_kra_research,
    run_public_market_keyword_sweep,
    run_source_check,
    source_allowed,
    source_query_url,
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
    assert finding.provider
    assert finding.prompt_version == "kra-summary-v1"
    assert finding.system_prompt_hash
    assert finding.user_prompt_hash
    assert finding.output_hash
    assert finding.human_review_status == "pending"


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


def test_market_quality_repair_holds_back_noisy_opportunity(seeded_session):
    opportunity = Opportunity(
        title="Award of a Call-Off Contract under the Prison Education DPS",
        buyer_name="Ministry of Justice",
        status="new",
        relevance_score=80,
        summary="Self-employment training course for prisoners.",
    )
    seeded_session.add(opportunity)
    seeded_session.commit()
    seeded_session.refresh(opportunity)

    repaired = repair_low_quality_market_opportunities(seeded_session)
    seeded_session.refresh(opportunity)
    report = create_report(seeded_session, "Market quality report")

    assert repaired == 1
    assert opportunity.relevance_score == 0
    assert opportunity.status == "needs_review"
    assert "Held back from executive pack" in opportunity.relevance_rationale
    assert "### 1. Award of a Call-Off Contract" not in report.markdown


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


def test_executive_report_generation_hides_admin_runtime(seeded_session):
    report = create_report(seeded_session, "Test report")

    assert report.id is not None
    assert "Opportunity Intelligence Digest" in report.markdown
    assert "KRA Runtime" not in report.markdown
    assert "API key configured" not in report.markdown
    assert "Executive Summary" in report.markdown
    assert "not a bid/no-bid" in report.markdown
    assert "KRA Intelligence Signals" not in report.markdown


def test_admin_report_generation_contains_kra_runtime(seeded_session):
    report = create_report(seeded_session, "Admin report", report_type="admin_run_log")

    assert report.id is not None
    assert "Admin Automation Run Log" in report.markdown
    assert "KRA Runtime" in report.markdown
    assert "API key configured" not in report.markdown


def test_report_generation_uses_ai_brief_when_llm_enabled(seeded_session, monkeypatch):
    monkeypatch.setattr("app.reports.llm_enabled", lambda: True)
    monkeypatch.setattr("app.reports.generate_llm_text", lambda *args, **kwargs: "Executive AI briefing text.")

    report = create_report(seeded_session, "AI report")

    assert "Executive AI briefing text." in report.markdown
    assert "Agent-classified records should be checked before bid, customer, legal or compliance action." in report.markdown


def test_report_generation_can_skip_report_level_ai_brief(seeded_session, monkeypatch):
    monkeypatch.setattr("app.reports.llm_enabled", lambda: True)
    monkeypatch.setattr("app.reports.generate_llm_text", lambda *args, **kwargs: "Should not be called.")

    report = create_report(seeded_session, "Automation report", include_ai_brief=False)

    assert "Report-level AI brief was skipped for the automated cycle" not in report.markdown
    assert "Executive Summary" in report.markdown
    assert "Should not be called." not in report.markdown


def test_report_generation_cleans_ai_artifacts(seeded_session, monkeypatch):
    monkeypatch.setattr("app.reports.llm_enabled", lambda: True)
    monkeypatch.setattr(
        "app.reports.generate_llm_text",
        lambda *args, **kwargs: "Strong National Highways opportunity signal.\nIf helpful, I can create a longer buyer pack.",
    )

    report = create_report(seeded_session, "Clean AI report")

    assert "Strong National Highways opportunity signal." in report.markdown
    assert "If helpful" not in report.markdown
    assert "I can create" not in report.markdown


def test_customer_scoped_executive_report_excludes_buyer_mismatch(seeded_session):
    customer = seeded_session.exec(select(Customer).where(Customer.customer_name == "National Highways")).first()
    source = seeded_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender")).first()
    opportunity = Opportunity(
        source_id=source.id if source else None,
        customer_id=customer.id,
        title="Prison Education DPS call-off training opportunity",
        buyer_name="Ministry of Justice",
        procurement_stage="tender",
        status="new",
        relevance_score=92,
        summary="Prison education training course notice that should not appear as a National Highways live signal.",
    )
    seeded_session.add(opportunity)
    seeded_session.commit()

    report = create_report(seeded_session, "National Highways report", customer_id=customer.id)

    assert "low-confidence, stale or buyer-mismatch record(s) were held back" in report.markdown
    assert "No buyer mismatch or low-confidence opportunity records were excluded" not in report.markdown


def test_relevance_does_not_match_short_alias_inside_words():
    candidate = CandidateOpportunity(
        title="Consultancy Services To Develop An Estates Strategy",
        buyer_name="Gloucestershire Hospitals Subsidiary Company Limited",
        summary="The estates strategy covers general facilities planning.",
    )

    score, rationale = relevance_for_candidate(candidate, ["NH", "HE", "National Highways"])

    assert score == 0
    assert rationale == "No watch terms matched."


def test_public_market_keyword_sweep_creates_reviewable_opportunity(seeded_session):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "noticeList": [
                    {
                        "item": {
                            "id": "cf-open-cyber",
                            "noticeIdentifier": "tender_123",
                            "title": "Cyber security services for public operations",
                            "description": "Specialist cyber security support, network communications and operational resilience.",
                            "organisationName": "Home Office",
                            "noticeType": "Contract",
                            "noticeStatus": "Open",
                            "publishedDate": "2026-05-01T09:00:00Z",
                            "deadlineDate": "2026-07-01T12:00:00Z",
                            "valueHigh": 3000000,
                            "cpvDescription": "IT services",
                        }
                    },
                    {
                        "item": {
                            "id": "cf-noise",
                            "title": "Self-employment training course for prisoners",
                            "description": "Training course under an education DPS.",
                            "organisationName": "Ministry of Justice",
                            "noticeType": "Contract",
                            "noticeStatus": "Open",
                            "deadlineDate": "2026-07-01T12:00:00Z",
                        }
                    },
                ]
            }

    result = run_public_market_keyword_sweep(
        seeded_session,
        keywords=["cyber security"],
        poster=lambda *args, **kwargs: FakeResponse(),
    )

    opportunity = seeded_session.exec(select(Opportunity).where(Opportunity.notice_identifier == "tender_123")).first()

    assert result["created"] == 1
    assert result["skipped"] == 1
    assert opportunity is not None
    assert opportunity.customer_id is None
    assert "Public sector market signal" in opportunity.relevance_rationale
    assert seeded_session.exec(select(OpportunityDocument).where(OpportunityDocument.opportunity_id == opportunity.id)).first() is not None
    assert seeded_session.exec(select(ExtractedRequirement).where(ExtractedRequirement.opportunity_id == opportunity.id)).first() is not None


def test_source_query_url_uses_date_scoped_live_notice_filters(seeded_session):
    contracts = seeded_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "contracts_finder")).first()
    find_tender = seeded_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender")).first()

    contracts_url = source_query_url(contracts, ["highways"])
    find_tender_url = source_query_url(find_tender, ["highways"])

    assert "publishedFrom=" in contracts_url
    assert "stages=planning%2Ctender" in contracts_url or "stages=planning,tender" in contracts_url
    assert "updatedFrom=" in find_tender_url
    assert "stages=planning%2Ctender" in find_tender_url or "stages=planning,tender" in find_tender_url


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
    snapshot = compact_snapshot(EmailConfiguration(smtp_password="super-secret", smtp_password_secret_name="DIP_SMTP_PASSWORD"))

    assert "super-secret" not in snapshot
    assert "DIP_SMTP_PASSWORD" not in snapshot
    assert "***redacted***" in snapshot


def test_smtp_password_resolves_from_secret_reference(monkeypatch, session):
    captures = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            captures["host"] = host
            captures["port"] = port
            captures["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            captures["tls"] = True

        def login(self, username, password):
            captures["username"] = username
            captures["password"] = password

        def send_message(self, msg):
            captures["subject"] = msg["Subject"]

    monkeypatch.setenv("DIP_SMTP_TEST_PASSWORD", "smtp-secret")
    monkeypatch.setattr("app.email_service.smtplib.SMTP", FakeSMTP)
    config = EmailConfiguration(
        delivery_mode="smtp",
        enabled=True,
        smtp_host="smtp.test.local",
        smtp_port=2525,
        smtp_username="smtp-user",
        smtp_password_secret_name="DIP_SMTP_TEST_PASSWORD",
        sender_email="no-reply@example.com",
    )

    assert resolve_smtp_password(config) == "smtp-secret"
    log = send_or_store_email(session, config, ["ops@example.com"], "Secret ref test", "Body")

    assert log.status == "sent"
    assert captures["password"] == "smtp-secret"
    assert captures["subject"] == "Secret ref test"
