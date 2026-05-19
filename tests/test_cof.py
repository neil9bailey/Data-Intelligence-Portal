from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.export_service import REPORT_CAVEAT, _pdf_text_lines, report_export
from app.intelligence_packs import apply_intelligence_pack, get_preconfigured_customer_pack
from app.main import app
from app.models import (
    BusinessUnit,
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    DocumentRetrievalTask,
    DigestProfile,
    ExtractedQualityQuestion,
    Opportunity,
    OpportunityDocument,
    ProcurementPlatform,
    ProcurementSource,
    IntelligenceReport,
)
from app.reports import cof_monday_send_readiness, cof_stage_for_opportunity, concise_opportunity_title, create_report
from app.settings import get_settings


def client_for(session):
    def override_session():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def apply_cof_pack(session):
    pack = get_preconfigured_customer_pack("procter_street_cof")
    return apply_intelligence_pack(session, pack, actor="test-user")


def cof_clients(session):
    return [item for item in session.exec(select(Customer)) if item.customer_name.startswith("COF Client ")]


def test_procter_street_cof_pack_applies_idempotently(reference_session):
    result = apply_cof_pack(reference_session)
    first_client_count = len(cof_clients(reference_session))
    first_portal_count = len(list(reference_session.exec(select(BuyerPortalInstance))))

    second = apply_cof_pack(reference_session)
    platforms = {item.name for item in reference_session.exec(select(ProcurementPlatform))}
    source_keys = {item.source_key for item in reference_session.exec(select(ProcurementSource))}

    assert first_client_count == 11
    assert len(cof_clients(reference_session)) == 11
    assert len(list(reference_session.exec(select(BuyerPortalInstance)))) == first_portal_count
    assert {"ProContract", "In-Tend", "Jaggaer", "Delta eSourcing"}.issubset(platforms)
    assert {"find_a_tender", "contracts_finder", "public_contracts_scotland", "sell2wales", "ted_eforms", "tenders_direct_backup"}.issubset(source_keys)
    assert any("Customer: COF Client 01" in item for item in result["created"])
    assert second["created"] == []


def test_cof_pack_seeds_client_portal_metrics_and_actions(reference_session):
    apply_cof_pack(reference_session)
    client = client_for(reference_session)
    try:
        page = client.get("/client-portal")
        interested_opportunity = reference_session.exec(select(Opportunity).where(Opportunity.title == "School estate decarbonisation programme")).first()
        watch_opportunity = reference_session.exec(select(Opportunity).where(Opportunity.title == "Highways maintenance framework PIN")).first()
        interested_response = client.post(
            "/client-portal/interests",
            data={
                "opportunity_id": str(interested_opportunity.id),
                "customer_id": str(interested_opportunity.customer_id),
                "signal": "interested",
                "notes": "Client wants Donna follow-up.",
            },
            follow_redirects=False,
        )
        watch_response = client.post(
            "/client-portal/interests",
            data={
                "opportunity_id": str(watch_opportunity.id),
                "customer_id": str(watch_opportunity.customer_id),
                "signal": "watch",
                "notes": "Keep watching.",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == 200
    assert "PINs" in page.text
    assert "Live tenders" in page.text
    assert "Interested" in page.text
    assert "Awarded" in page.text
    assert "View questions" in page.text
    assert interested_response.status_code == 303
    assert watch_response.status_code == 303
    reference_session.refresh(interested_opportunity)
    reference_session.refresh(watch_opportunity)
    assert interested_opportunity.status == "interested"
    assert watch_opportunity.status == "watch"
    assert reference_session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.opportunity_id == interested_opportunity.id)).first()
    assert not reference_session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.opportunity_id == watch_opportunity.id)).first()


def test_human_review_gate_and_donna_queue(reference_session):
    apply_cof_pack(reference_session)
    opportunity = reference_session.exec(select(Opportunity).where(Opportunity.status == "needs_review")).first()
    client = client_for(reference_session)
    try:
        page = client.get("/review")
        response = client.post(
            f"/opportunities/{opportunity.id}/review",
            data={"action": "needs_more_evidence", "review_notes": "Need stronger source evidence."},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == 200
    assert "Human Review Gate" in page.text
    assert "Donna Relationship / Action Queue" in page.text
    assert response.status_code == 303
    reference_session.refresh(opportunity)
    assert opportunity.status == "review_required"


def test_cof_weekly_report_content_and_exports(reference_session):
    get_settings.cache_clear()
    apply_cof_pack(reference_session)
    cof_unit = reference_session.exec(select(BusinessUnit).where(BusinessUnit.name == "Contracted Opportunity Finder")).first()
    public_notice_opportunity = reference_session.exec(select(Opportunity).where(Opportunity.title == "Highways maintenance framework PIN")).first()
    reference_session.add(
        OpportunityDocument(
            opportunity_id=public_notice_opportunity.id,
            title="COF public notice evidence record",
            document_type="public_notice",
            url_or_path=public_notice_opportunity.source_url,
            retrieval_status="retrieved",
            platform_name="Find a Tender",
            content_summary="Public notice metadata retained as source evidence, not a retrieved tender pack.",
        )
    )
    rejected = Opportunity(title="Rejected noise record", status="rejected", summary="Should not appear in COF report.")
    reference_session.add(rejected)
    for title in [
        "South Devon College boiler maintenance notice",
        "Home Office DSA Cyber Security framework",
        "Telecommunications market sweep record",
        "Waltham Forest minor works contract",
        "Basildon CCTV maintenance opportunity",
    ]:
        reference_session.add(
            Opportunity(
                title=title,
                buyer_name=title.split(" ", 2)[0],
                status="live",
                notice_type="tender",
                procurement_stage="tender",
                deadline_date=date.today() + timedelta(days=20),
                source_url="https://www.find-tender.service.gov.uk/Notice/NOISE",
                summary="Generic public-market sweep record that is not assigned to the COF workspace.",
                relevance_score=80,
            )
        )
    reference_session.add(
        Opportunity(
            title="Generic Telecommunications COF business-unit sweep record",
            buyer_name="Generic Authority",
            business_unit_id=cof_unit.id,
            status="live",
            notice_type="tender",
            procurement_stage="tender",
            deadline_date=date.today() + timedelta(days=20),
            source_url="https://www.find-tender.service.gov.uk/Notice/BU-NOISE",
            summary="BU-only public-market sweep record with no matched COF client.",
            relevance_score=80,
        )
    )
    reference_session.commit()
    pending_document = reference_session.exec(select(OpportunityDocument).where(OpportunityDocument.document_type == "itt_extract")).first()
    linked_question = reference_session.exec(select(ExtractedQualityQuestion).where(ExtractedQualityQuestion.document_id == pending_document.id)).first()
    linked_question.human_review_status = "approved"
    reference_session.add(linked_question)
    reference_session.commit()

    report = create_report(reference_session, "COF Weekly Portfolio Report", "cof_weekly_portfolio_report")
    markdown = report.markdown
    interested_count = len([item for item in reference_session.exec(select(ClientInterestSignal)) if item.signal == "interested"])
    lower_markdown = markdown.lower()

    assert report.business_unit_id == cof_unit.id
    assert "**Scope:** Contracted Opportunity Finder" in markdown
    assert "All customers and business units" not in markdown
    assert "Client Coverage: 11 clients monitored" in markdown
    assert "| Client | Sector | PINs | Watch | Live | Interested | Awarded | Denise review |" in markdown
    assert markdown.count("| Client ") >= 11
    assert "COF Client 01" not in markdown
    assert "Client A - Highways" in markdown
    assert "Client B - Estates" in markdown
    assert "PINs" in markdown
    assert "PINs / Early Market" in markdown
    assert "Watchlist" in markdown
    pins_section = markdown.split("## PINs / Early Market", 1)[1].split("## Watchlist", 1)[0]
    watch_section = markdown.split("## Watchlist", 1)[1].split("## Live Tenders", 1)[0]
    assert "Facilities and asset management services" not in pins_section
    assert "Facilities and asset management services" in watch_section
    assert "Live Tenders" in markdown
    assert "0 live tender signal" not in markdown
    assert "School estate decarbonisation programme" in markdown
    assert "matched client Client B - Estates" in markdown
    assert "portal/source: In-Tend" in markdown
    assert "Denise approved for report inclusion" in markdown
    assert "Awards / Market Evidence" in markdown
    assert "Interested / Donna Actions" in markdown
    assert "Donna action status donna_action_required" in markdown
    assert f"{interested_count} interested item(s)" in markdown
    assert "Quality Questions and Weightings" in markdown
    questions_section = markdown.split("## Quality Questions and Weightings", 1)[1].split("## Requirement Themes", 1)[0]
    assert "pending Denise review" in questions_section
    assert "approved status" not in questions_section
    assert "Public Notice Evidence" in markdown
    documents_section = markdown.split("## Documents Retrieved", 1)[1].split("## Public Notice Evidence", 1)[0]
    public_notice_section = markdown.split("## Public Notice Evidence", 1)[1].split("## Quality Questions and Weightings", 1)[0]
    review_gaps_section = markdown.split("## Review Gaps", 1)[1].split("## Monday Send Readiness", 1)[0]
    assert "Human review required" in markdown
    assert "Rejected noise record" not in markdown
    for forbidden in ["mvp", "demo", "concept", "seeded", "live-pilot", "test output", "walkthrough", "prototype"]:
        assert forbidden not in lower_markdown
    assert markdown.count("Human review required") <= 2
    assert "Source evidence captured for Denise review. Human verification required before client action." not in markdown
    assert "Pending document review: " in review_gaps_section
    assert "Pending document review: 0" not in review_gaps_section
    assert "COF public notice evidence record" not in documents_section
    assert "COF public notice evidence record" in public_notice_section
    for title in [
        "South Devon College",
        "Home Office",
        "Telecommunications",
        "Waltham Forest",
        "Basildon",
        "Generic Telecommunications",
    ]:
        assert title not in markdown
    for export_format in ("pdf", "html", "json", "md", "txt"):
        payload, media_type, filename = report_export(report, export_format)
        assert payload
        assert filename.endswith("." + ("md" if export_format == "md" else export_format))
        assert media_type
    pdf_payload, _, _ = report_export(report, "pdf")
    assert REPORT_CAVEAT.encode("cp1252") in pdf_payload
    html_payload, _, _ = report_export(report, "html")
    assert b"Contracted Opportunity Finder" in html_payload
    json_payload, _, _ = report_export(report, "json")
    assert b'"prepared_for": "Procter Street"' in json_payload


def test_cof_stage_classification_uses_lifecycle_not_review_status():
    live_approved = Opportunity(
        title="Approved live tender",
        status="approved",
        notice_type="tender",
        procurement_stage="tender",
        deadline_date=date.today() + timedelta(days=30),
    )
    closing = Opportunity(
        title="Closing tender",
        status="review_required",
        notice_type="tender",
        procurement_stage="tender",
        deadline_date=date.today() + timedelta(days=5),
    )
    interested = ClientInterestSignal(signal="interested")
    question = ExtractedQualityQuestion(question_text="Quality question", opportunity_id=1)

    assert cof_stage_for_opportunity(live_approved, [], [], [], []) == "live"
    assert cof_stage_for_opportunity(closing, [], [], [], []) == "closing_soon"
    assert cof_stage_for_opportunity(live_approved, [interested], [], [], []) == "interested"
    assert cof_stage_for_opportunity(live_approved, [], [], [], [question]) == "questions_extracted"


def test_concise_opportunity_title_shortens_without_inventing():
    opportunity = Opportunity(
        title=(
            "CA17827 - Invitation to Tender - The provision of integrated highways maintenance, "
            "winter resilience, drainage, traffic management and associated civil engineering works"
        )
    )
    basildon = Opportunity(title="GB-Basildon: CCTV supply, design and installation with support and maintenance")

    assert concise_opportunity_title(opportunity, max_chars=70).startswith("integrated highways maintenance")
    assert concise_opportunity_title(opportunity, max_chars=70).endswith("...")
    assert concise_opportunity_title(basildon) == "Basildon CCTV supply, design and installation with support and maintenance"


def test_cof_client_name_modes(reference_session, monkeypatch):
    apply_cof_pack(reference_session)
    report = create_report(reference_session, "COF redacted", "cof_weekly_portfolio_report")
    assert "Client A - Highways" in report.markdown
    assert "COF Client 01" not in report.markdown

    monkeypatch.setenv("DIP_COF_CLIENT_NAME_MODE", "placeholder")
    get_settings.cache_clear()
    placeholder_report = create_report(reference_session, "COF placeholder", "cof_weekly_portfolio_report")
    assert "COF Client 01" in placeholder_report.markdown

    monkeypatch.setenv("DIP_COF_CLIENT_NAME_MODE", "configured")
    monkeypatch.setenv("DIP_COF_CLIENT_NAME_MAP_JSON", '{"COF Client 01": "Acme Highways", "COF Client 02": "Beacon Estates"}')
    get_settings.cache_clear()
    configured_report = create_report(reference_session, "COF configured", "cof_weekly_portfolio_report")
    assert "Acme Highways" in configured_report.markdown
    assert "Beacon Estates" in configured_report.markdown
    get_settings.cache_clear()


def test_pdf_text_generation_sanitises_non_printable_characters():
    lines = _pdf_text_lines("# operational\u2011report\x00\nBad\ufffd control")
    text = "\n".join(lines)

    assert "operational-report" in text.lower()
    assert "\ufffd" not in text
    assert all(ch in {"\n", "\t"} or ord(ch) >= 32 for ch in text)


def test_customer_visible_pages_do_not_use_mvp_demo_or_concept_language(reference_session):
    apply_cof_pack(reference_session)
    client = client_for(reference_session)
    try:
        for path in ["/", "/client-portal", "/reports"]:
            response = client.get(path)
            text = response.text.lower()
            assert response.status_code == 200
            for forbidden in ["mvp", "demo", "concept", "test output", "seeded", "live-pilot", "walkthrough", "prototype"]:
                assert forbidden not in text
    finally:
        app.dependency_overrides.clear()


def test_cof_monday_digest_profile_is_created(reference_session):
    apply_cof_pack(reference_session)
    profile = reference_session.exec(select(DigestProfile).where(DigestProfile.name == "COF Monday report send")).first()
    report = reference_session.exec(select(IntelligenceReport).where(IntelligenceReport.report_type == "cof_weekly_portfolio_report")).first()
    signals = list(reference_session.exec(select(ClientInterestSignal)))

    assert profile is not None
    assert profile.report_type == "cof_weekly_portfolio_report"
    assert profile.frequency_label == "Monday"
    assert profile.export_format == "pdf"
    assert report is not None
    assert len([item for item in signals if item.signal == "interested"]) >= 3
    assert len([item for item in signals if item.signal == "watch"]) >= 2


def test_cof_monday_send_readiness_ready_and_not_ready(reference_session):
    apply_cof_pack(reference_session)
    opportunity_ids = {item.id for item in reference_session.exec(select(Opportunity)) if item.id}
    not_ready = cof_monday_send_readiness(reference_session, opportunity_ids, blockers={})
    assert not_ready["ready"] is False
    assert "no Monday recipients configured" in not_ready["blockers"]

    profile = reference_session.exec(select(DigestProfile).where(DigestProfile.name == "COF Monday report send")).first()
    profile.recipients = "ops@example.com; board@example.com"
    reference_session.add(profile)
    reference_session.commit()

    ready = cof_monday_send_readiness(reference_session, opportunity_ids, blockers={})
    assert ready["ready"] is True
    assert ready["recipient_count"] == 2
    assert ready["delivery_mode"] == "file_outbox"
