from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.export_service import report_export
from app.intelligence_packs import apply_intelligence_pack, get_preconfigured_customer_pack
from app.main import app
from app.models import (
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    DocumentRetrievalTask,
    DigestProfile,
    Opportunity,
    ProcurementPlatform,
    ProcurementSource,
)
from app.reports import create_report


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


def test_denise_review_gate_and_donna_queue(reference_session):
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
    assert "Denise Review Gate" in page.text
    assert "Donna Relationship / Action Queue" in page.text
    assert response.status_code == 303
    reference_session.refresh(opportunity)
    assert opportunity.status == "review_required"


def test_cof_weekly_report_content_and_exports(reference_session):
    apply_cof_pack(reference_session)
    rejected = Opportunity(title="Rejected noise record", status="rejected", summary="Should not appear in COF report.")
    reference_session.add(rejected)
    reference_session.commit()

    report = create_report(reference_session, "COF Weekly Portfolio Report", "cof_weekly_portfolio_report")
    markdown = report.markdown

    assert "PINs" in markdown
    assert "Live Tenders" in markdown
    assert "Awards / Market Evidence" in markdown
    assert "Interested / Donna Actions" in markdown
    assert "Quality Questions And Weightings" in markdown
    assert "Human review required" in markdown
    assert "Rejected noise record" not in markdown
    for export_format in ("pdf", "html", "json", "md", "txt"):
        payload, media_type, filename = report_export(report, export_format)
        assert payload
        assert filename.endswith("." + ("md" if export_format == "md" else export_format))
        assert media_type


def test_customer_visible_pages_do_not_use_mvp_demo_or_concept_language(reference_session):
    apply_cof_pack(reference_session)
    client = client_for(reference_session)
    try:
        for path in ["/", "/client-portal", "/reports"]:
            response = client.get(path)
            text = response.text.lower()
            assert response.status_code == 200
            assert "mvp" not in text
            assert "demo" not in text
            assert "concept" not in text
    finally:
        app.dependency_overrides.clear()


def test_cof_monday_digest_profile_is_created(reference_session):
    apply_cof_pack(reference_session)
    profile = reference_session.exec(select(DigestProfile).where(DigestProfile.name == "COF Monday report send")).first()
    signals = list(reference_session.exec(select(ClientInterestSignal)))

    assert profile is not None
    assert profile.report_type == "cof_weekly_portfolio_report"
    assert profile.frequency_label == "Monday"
    assert profile.export_format == "pdf"
    assert len([item for item in signals if item.signal == "interested"]) >= 3
    assert len([item for item in signals if item.signal == "watch"]) >= 2
