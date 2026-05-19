import json

from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.intelligence import FetchResult
from app.main import app
from app.models import (
    AuditEvent,
    AutomationRun,
    BusinessUnit,
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    DocumentRetrievalTask,
    DigestProfile,
    EmailDeliveryLog,
    EmailConfiguration,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    IntelligenceReport,
    KRAFinding,
    Opportunity,
    OpportunityDocument,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementPlatform,
    ProcurementSource,
    OpportunityFeedback,
)
from app.automation import live_kra_source_ids, run_admin_full_cycle
from app.portal_connectors import run_portal_connector
from app.reports import create_report
from app.export_service import REPORT_CAVEAT


def client_for(session):
    def override_session():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_route_smoke_pages(seeded_session):
    opportunity = seeded_session.exec(select(Opportunity)).first()
    client = client_for(seeded_session)
    try:
        paths = [
            "/",
            "/workflow",
            "/intelligence-packs",
            "/business-units",
            "/customers",
            "/sources",
            "/opportunities",
            f"/opportunities/{opportunity.id}/documents",
            "/review",
            "/client-portal",
            "/portals",
            "/requirements",
            "/kra",
            "/reports",
            "/admin",
            "/audit",
            "/healthz",
        ]
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
    finally:
        app.dependency_overrides.clear()


def test_portal_workbench_guidance_and_task_creation(seeded_session):
    portal = seeded_session.exec(select(BuyerPortalInstance)).first()
    opportunity = seeded_session.exec(select(Opportunity)).first()
    client = client_for(seeded_session)
    try:
        page = client.get("/portals")
        response = client.post(
            f"/portals/{portal.id}/tasks",
            data={
                "task_name": "Retrieve ITT pack",
                "opportunity_id": str(opportunity.id),
                "status": "requested",
                "owner": "bid-team",
                "notes": "Download permitted portal documents and paste quality text.",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == 200
    assert "Portal activation workflow" in page.text
    assert "Turn buyer portals into a managed retrieval service." in page.text
    assert response.status_code == 303
    task = seeded_session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.task_name == "Retrieve ITT pack")).first()
    assert task is not None
    assert task.portal_instance_id == portal.id
    assert task.opportunity_id == opportunity.id


def test_create_customer_route(seeded_session):
    client = client_for(seeded_session)
    try:
        response = client.post(
            "/customers",
            data={"customer_name": "Example Council", "sector": "Local government", "domain": "highways"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


def test_healthz():
    response = TestClient(app).get("/healthz", headers={"x-request-id": "test-request-id"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request-id"
    assert response.json()["status"] == "ok"


def test_readyz():
    response = TestClient(app).get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["database"] == "ok"


def test_opportunities_page_is_paginated(session):
    for index in range(12):
        session.add(
            Opportunity(
                title=f"Paged opportunity {index:02d}",
                buyer_name="Test Buyer",
                status="approved",
                relevance_score=75,
                source_url=f"https://example.com/{index}",
            )
        )
    session.commit()
    client = client_for(session)
    try:
        page_one = client.get("/opportunities")
        page_two = client.get("/opportunities?page=2")
    finally:
        app.dependency_overrides.clear()

    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert "Paged opportunity 11" in page_one.text
    assert "Paged opportunity 01" not in page_one.text
    assert "Paged opportunity 01" in page_two.text
    assert "Next" in page_one.text


def test_dashboard_uses_clean_setup_homepage(reference_session):
    client = client_for(reference_session)
    try:
        response = client.get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert '<base target="_top">' in response.text
    assert "Opportunity intelligence, classified and ready." in response.text
    assert "One customer memory for every source, portal and requirement." not in response.text
    assert "Official Intelligence Feed" in response.text


def test_report_download_formats_and_local_email(reference_session):
    report = create_report(reference_session, "Export test")
    client = client_for(reference_session)
    try:
        html_response = client.get(f"/reports/{report.id}?format=html")
        pdf_response = client.get(f"/reports/{report.id}?format=pdf")
        json_response = client.get(f"/reports/{report.id}?format=json")
        email_response = client.post(
            f"/reports/{report.id}/send-email",
            data={"recipients": "buyer@example.com", "subject": "Export test", "export_format": "md"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert html_response.status_code == 200
    assert "text/html" in html_response.headers["content-type"]
    assert pdf_response.status_code == 200
    assert "application/pdf" in pdf_response.headers["content-type"]
    assert pdf_response.content.startswith(b"%PDF-")
    assert json_response.status_code == 200
    assert json_response.json()["report_name"] == "Export test"
    assert json_response.json()["caveat"] == REPORT_CAVEAT
    assert REPORT_CAVEAT in html_response.text
    assert email_response.status_code == 303
    assert reference_session.exec(select(EmailDeliveryLog)).first().status == "stored"


def test_audit_export_json_and_csv(reference_session):
    client = client_for(reference_session)
    try:
        client.post(
            "/admin/email",
            data={
                "profile_name": "SMTP profile",
                "smtp_port": "587",
                "smtp_password": "do-not-export",
                "smtp_password_secret_name": "DIP_SMTP_PASSWORD",
            },
            follow_redirects=False,
        )
        json_response = client.get("/audit?format=json")
        csv_response = client.get("/audit?format=csv")
    finally:
        app.dependency_overrides.clear()

    assert json_response.status_code == 200
    assert csv_response.status_code == 200
    assert "application/json" in json_response.headers["content-type"]
    assert "text/csv" in csv_response.headers["content-type"]
    exported = json_response.text + csv_response.text
    assert "do-not-export" not in exported
    assert "DIP_SMTP_PASSWORD" not in exported
    assert "***redacted***" in exported


def test_admin_email_test_route(reference_session):
    client = client_for(reference_session)
    try:
        page = client.get("/admin")
        response = client.post(
            "/admin/email/test",
            data={"recipients": "ops@example.com", "subject": "Test", "message": "Hello"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == 200
    assert 'name="smtp_password_secret_name"' in page.text
    assert 'name="smtp_password"' not in page.text
    assert response.status_code == 303
    assert reference_session.exec(select(EmailDeliveryLog)).first() is not None


def test_admin_email_config_stores_secret_reference_not_password(reference_session):
    client = client_for(reference_session)
    try:
        response = client.post(
            "/admin/email",
            data={
                "profile_name": "SMTP profile",
                "delivery_mode": "smtp",
                "smtp_host": "smtp.example.com",
                "smtp_port": "587",
                "smtp_username": "smtp-user",
                "smtp_password": "should-not-store",
                "smtp_password_secret_name": "DIP_SMTP_PASSWORD",
                "sender_name": "DIP",
                "sender_email": "no-reply@example.com",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    config = reference_session.exec(select(EmailConfiguration)).first()
    assert response.status_code == 303
    assert config.smtp_password_secret_name == "DIP_SMTP_PASSWORD"
    assert config.smtp_password == ""


def test_digest_profile_sends_report_via_file_outbox(reference_session):
    client = client_for(reference_session)
    try:
        response = client.post(
            "/admin/digests",
            data={
                "name": "Weekly demo digest",
                "recipients": "digest@example.com",
                "report_type": "executive_summary",
                "export_format": "html",
                "frequency_label": "weekly",
                "enabled": "true",
            },
            follow_redirects=False,
        )
        profile = reference_session.exec(select(DigestProfile).where(DigestProfile.name == "Weekly demo digest")).first()
        assert profile is not None
        send_response = client.post(f"/admin/digests/{profile.id}/send", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    log = reference_session.exec(select(EmailDeliveryLog).order_by(EmailDeliveryLog.id.desc())).first()
    assert response.status_code == 303
    assert send_response.status_code == 303
    assert log is not None
    assert log.status == "stored"
    assert log.recipients == "digest@example.com"
    assert log.attachment_format == "html"


def test_kra_finding_review_route_records_reviewer(reference_session):
    finding = KRAFinding(
        title="AI assisted finding",
        finding_type="ai_research_summary",
        summary="Generated summary requiring review.",
        prompt_version="kra-summary-v1",
        provider="openai_direct",
        model="gpt-5.4",
        output_hash="abc123",
    )
    reference_session.add(finding)
    reference_session.commit()
    reference_session.refresh(finding)
    client = client_for(reference_session)
    try:
        response = client.post(
            f"/kra/findings/{finding.id}/review",
            data={"human_review_status": "approved"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    reference_session.refresh(finding)
    assert response.status_code == 303
    assert finding.human_review_status == "approved"
    assert finding.reviewed_by == "local-user"
    assert finding.reviewed_at is not None


def test_admin_full_cycle_automation_preconfigures_and_exports(reference_session, monkeypatch):
    monkeypatch.setattr("app.automation.refresh_news_feeds", lambda session: 0)
    monkeypatch.setattr(
        "app.automation.run_public_market_keyword_sweep",
        lambda session: {"keywords": 1, "created": 0, "updated": 0, "skipped": 0, "errors": []},
    )

    def fake_source_fetcher(url):
        payload = {
            "releases": [
                {
                    "id": "auto-nh-1",
                    "ocid": "ocds-auto-nh-1",
                    "date": "2026-05-18T09:00:00Z",
                    "tag": ["tender"],
                    "buyer": {"name": "National Highways"},
                    "tender": {
                        "title": "National Highways roadside operational technology services",
                        "description": "Cyber resilience, traffic operations and roadside technology support.",
                        "status": "active",
                    },
                    "links": {"self": "https://www.find-tender.service.gov.uk/Notice/auto-nh-1"},
                }
            ]
        }
        return FetchResult(True, 200, url, json.dumps(payload), "application/json")

    def fake_connector_fetcher(connector):
        return FetchResult(True, 200, connector.endpoint_url, "Automated public connector payload for human review.", "text/plain")

    run = run_admin_full_cycle(
        reference_session,
        actor="test-admin",
        email_recipients="review@example.com",
        source_fetcher=fake_source_fetcher,
        connector_fetcher=fake_connector_fetcher,
    )

    assert run.status == "completed"
    assert run.report_id is not None
    assert run.stored_report_path.endswith(".pdf")
    assert "Apply or update customer packs" in run.steps_json
    assert "Generate branded report export" in run.steps_json
    assert reference_session.exec(select(AutomationRun)).first() is not None
    report = reference_session.exec(select(IntelligenceReport)).first()
    assert report is not None
    assert report.report_type == "executive_pack"
    assert "KRA Runtime" not in report.markdown
    assert reference_session.exec(select(EmailDeliveryLog)).first().status == "stored"
    assert reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender_national_highways")).first().active is False


def test_live_kra_sources_prefer_broad_official_ocds_apis(reference_session):
    source_ids = live_kra_source_ids(reference_session)
    source_keys = {
        reference_session.get(ProcurementSource, source_id).source_key
        for source_id in source_ids
    }

    assert source_keys == {"find_a_tender", "contracts_finder"}


def test_admin_automation_route_queues_background_run(reference_session, monkeypatch):
    calls = []

    def fake_background(run_id, actor, email_recipients="", export_format="md"):
        calls.append(
            {
                "run_id": run_id,
                "actor": actor,
                "email_recipients": email_recipients,
                "export_format": export_format,
            }
        )

    monkeypatch.setattr("app.routes.admin.run_admin_full_cycle_background", fake_background)
    client = client_for(reference_session)
    try:
        response = client.post(
            "/admin/automation/run",
            data={"email_recipients": "ops@example.com", "export_format": "md"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    run = reference_session.exec(select(AutomationRun).order_by(AutomationRun.id.desc())).first()
    assert response.status_code == 303
    assert response.headers["location"] == f"/admin?automation=queued&run_id={run.id}"
    assert run.status == "queued"
    assert calls == [
        {
            "run_id": run.id,
            "actor": "local-user",
            "email_recipients": "ops@example.com",
            "export_format": "md",
        }
    ]


def test_portal_connector_run_all_route_is_not_parsed_as_connector_id(reference_session):
    client = client_for(reference_session)
    try:
        response = client.post("/portal-connectors/run-all", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/portals"


def test_read_only_portal_connector_retrieves_document_for_reports(seeded_session):
    portal = seeded_session.exec(select(BuyerPortalInstance)).first()
    opportunity = seeded_session.exec(select(Opportunity)).first()
    client = client_for(seeded_session)
    try:
        response = client.post(
            "/portal-connectors",
            data={
                "connector_name": "Route connector",
                "portal_instance_id": str(portal.id),
                "default_opportunity_id": str(opportunity.id),
                "integration_method": "public_api_no_key",
                "auth_type": "none",
                "endpoint_url": "https://procontract.due-north.com/api/notices",
                "enabled": "true",
                "notes": "Read-only test connector.",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    connector = seeded_session.exec(select(PortalInformationConnector).where(PortalInformationConnector.connector_name == "Route connector")).first()
    assert connector is not None

    def fake_fetcher(item):
        assert item.id == connector.id
        return FetchResult(
            True,
            200,
            item.endpoint_url,
            "Question 1: Describe your resilient operational technology service. Weighting 20%",
            "text/plain",
        )

    run = run_portal_connector(seeded_session, connector.id, fetcher=fake_fetcher)
    assert run.status == "completed"
    assert run.documents_created == 1
    assert seeded_session.exec(select(PortalRetrievalRun)).first() is not None
    assert seeded_session.exec(select(OpportunityDocument).where(OpportunityDocument.document_type == "automated_retrieval")).first() is not None
    assert seeded_session.exec(select(KRAFinding).where(KRAFinding.finding_type == "portal_retrieval")).first() is None

    report = create_report(seeded_session, "Connector report", report_type="admin_run_log")
    assert "Automated Portal Retrieval" in report.markdown
    assert "Route connector" in report.markdown


def test_user_managed_records_can_be_updated_and_deleted(seeded_session):
    client = client_for(seeded_session)
    platform = seeded_session.exec(select(ProcurementPlatform)).first()
    existing_customer = seeded_session.exec(select(Customer)).first()
    try:
        bu_response = client.post(
            "/business-units",
            data={"name": "Test Unit", "description": "Created by route test", "active": "true"},
            follow_redirects=False,
        )
        unit = seeded_session.exec(select(BusinessUnit).where(BusinessUnit.name == "Test Unit")).first()
        assert bu_response.status_code == 303
        assert unit is not None

        response = client.post(
            f"/business-units/{unit.id}",
            data={"name": "Test Unit Updated", "description": "Updated", "active": "false"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(unit)
        assert unit.name == "Test Unit Updated"
        assert unit.active is False

        response = client.post(
            "/customers",
            data={"customer_name": "CRUD Council", "business_unit_id": str(unit.id), "sector": "Public sector", "domain": "highways"},
            follow_redirects=False,
        )
        customer = seeded_session.exec(select(Customer).where(Customer.customer_name == "CRUD Council")).first()
        assert response.status_code == 303
        assert customer is not None

        response = client.post(
            f"/customers/{customer.id}",
            data={"customer_name": "CRUD Council Updated", "business_unit_id": str(unit.id), "sector": "Local government", "domain": "transport"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(customer)
        assert customer.customer_name == "CRUD Council Updated"

        response = client.post(
            "/sources",
            data={
                "name": "CRUD Source",
                "query_url": "https://www.gov.uk/government/organisations/cabinet-office",
                "base_url": "https://www.gov.uk",
                "source_type": "web_page",
                "coverage": "test coverage",
            },
            follow_redirects=False,
        )
        source = seeded_session.exec(select(ProcurementSource).where(ProcurementSource.name == "CRUD Source")).first()
        assert response.status_code == 303
        assert source is not None

        response = client.post(
            f"/sources/{source.id}",
            data={
                "name": "CRUD Source Updated",
                "query_url": "https://www.gov.uk/search/all",
                "base_url": "https://www.gov.uk",
                "source_type": "web_page",
                "official": "true",
                "active": "false",
                "coverage": "updated",
                "connector_status": "manual_review",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(source)
        assert source.name == "CRUD Source Updated"
        assert source.active is False

        response = client.post(
            "/opportunities",
            data={
                "title": "CRUD Opportunity",
                "source_id": str(source.id),
                "customer_id": str(customer.id),
                "business_unit_id": str(unit.id),
                "buyer_name": "CRUD Buyer",
                "deadline_date": "2026-06-30",
                "value_high": "1000",
                "relevance_score": "55",
                "status": "new",
            },
            follow_redirects=False,
        )
        opportunity = seeded_session.exec(select(Opportunity).where(Opportunity.title == "CRUD Opportunity")).first()
        assert response.status_code == 303
        assert opportunity is not None

        response = client.post(
            f"/opportunities/{opportunity.id}",
            data={
                "title": "CRUD Opportunity Updated",
                "source_id": str(source.id),
                "customer_id": str(customer.id),
                "business_unit_id": str(unit.id),
                "buyer_name": "CRUD Buyer",
                "deadline_date": "2026-07-01",
                "value_high": "2500",
                "relevance_score": "70",
                "status": "watching",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(opportunity)
        assert opportunity.title == "CRUD Opportunity Updated"
        assert opportunity.value_high == 2500

        response = client.post(
            f"/opportunities/{opportunity.id}/feedback",
            data={"feedback_type": "wrong_customer", "notes": "Route test feedback"},
            follow_redirects=False,
        )
        feedback = seeded_session.exec(select(OpportunityFeedback).where(OpportunityFeedback.opportunity_id == opportunity.id)).first()
        assert response.status_code == 303
        assert feedback is not None

        response = client.post(
            "/portals",
            data={
                "portal_name": "CRUD Portal",
                "platform_id": str(platform.id),
                "customer_id": str(customer.id),
                "business_unit_id": str(unit.id),
                "portal_url": "https://procontract.due-north.com/",
                "access_status": "registered",
            },
            follow_redirects=False,
        )
        portal = seeded_session.exec(select(BuyerPortalInstance).where(BuyerPortalInstance.portal_name == "CRUD Portal")).first()
        assert response.status_code == 303
        assert portal is not None

        response = client.post(
            f"/portals/{portal.id}",
            data={
                "portal_name": "CRUD Portal Updated",
                "platform_id": str(platform.id),
                "customer_id": str(customer.id),
                "business_unit_id": str(unit.id),
                "portal_url": "https://procontract.due-north.com/",
                "account_reference": "ops-team",
                "access_status": "active",
                "document_retrieval_mode": "manual",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(portal)
        assert portal.portal_name == "CRUD Portal Updated"

        response = client.post(
            f"/opportunities/{opportunity.id}/documents",
            data={
                "title": "CRUD Document",
                "document_type": "itt_extract",
                "retrieval_status": "linked",
                "storage_provider": "sharepoint",
                "document_storage_ref": "https://sharepoint.example/docs/itt",
                "classification_label": "Commercial",
                "retention_status": "bid_record",
                "source_access_notes": "Permitted extract only.",
            },
            follow_redirects=False,
        )
        document = seeded_session.exec(select(OpportunityDocument).where(OpportunityDocument.title == "CRUD Document")).first()
        assert response.status_code == 303
        assert document is not None
        assert document.storage_provider == "sharepoint"
        assert document.classification_label == "Commercial"

        response = client.post(
            f"/opportunities/{opportunity.id}/documents/{document.id}",
            data={
                "title": "CRUD Document Updated",
                "document_type": "notice",
                "retrieval_status": "reviewed",
                "human_review_status": "approved",
                "storage_provider": "azure_blob",
                "document_storage_ref": "blob://container/itt.pdf",
                "classification_label": "Internal",
                "retention_status": "retained",
                "source_access_notes": "Reference only; extraction still uses permitted text.",
                "reviewed_by": "reviewer@example.com",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(document)
        assert document.title == "CRUD Document Updated"
        assert document.storage_provider == "azure_blob"
        assert document.reviewed_by == "reviewer@example.com"

        response = client.post(
            f"/opportunities/{opportunity.id}/tasks",
            data={"task_name": "CRUD Retrieval", "portal_instance_id": str(portal.id), "due_date": "2026-06-01"},
            follow_redirects=False,
        )
        task = seeded_session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.task_name == "CRUD Retrieval")).first()
        assert response.status_code == 303
        assert task is not None

        response = client.post(
            f"/tasks/{task.id}",
            data={
                "return_to": f"/opportunities/{opportunity.id}/documents",
                "task_name": "CRUD Retrieval Updated",
                "portal_instance_id": str(portal.id),
                "opportunity_id": str(opportunity.id),
                "status": "completed",
                "owner": "test-user",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(task)
        assert task.task_name == "CRUD Retrieval Updated"

        response = client.post(
            "/requirements",
            data={
                "customer_id": str(customer.id),
                "opportunity_id": str(opportunity.id),
                "requirement_theme": "CRUD theme",
                "requirement_text": "Evidence of secure operational delivery.",
            },
            follow_redirects=False,
        )
        requirement = seeded_session.exec(select(ExtractedRequirement).where(ExtractedRequirement.requirement_theme == "CRUD theme")).first()
        assert response.status_code == 303
        assert requirement is not None

        response = client.post(
            f"/requirements/{requirement.id}",
            data={
                "customer_id": str(customer.id),
                "opportunity_id": str(opportunity.id),
                "requirement_theme": "CRUD theme updated",
                "requirement_text": "Updated requirement text.",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(requirement)
        assert requirement.requirement_theme == "CRUD theme updated"

        response = client.post(
            "/quality-questions",
            data={
                "opportunity_id": str(opportunity.id),
                "document_id": str(document.id),
                "question_text": "Describe the mobilisation approach.",
                "requirement_theme": "mobilisation",
            },
            follow_redirects=False,
        )
        question = seeded_session.exec(select(ExtractedQualityQuestion).where(ExtractedQualityQuestion.requirement_theme == "mobilisation")).first()
        assert response.status_code == 303
        assert question is not None

        response = client.post(
            f"/quality-questions/{question.id}",
            data={
                "opportunity_id": str(opportunity.id),
                "document_id": str(document.id),
                "question_text": "Describe the updated mobilisation approach.",
                "requirement_theme": "mobilisation updated",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(question)
        assert question.requirement_theme == "mobilisation updated"

        response = client.post(
            "/client-portal/interests",
            data={"opportunity_id": str(opportunity.id), "customer_id": str(customer.id), "contact_name": "Bid Lead", "signal": "watch"},
            follow_redirects=False,
        )
        signal = seeded_session.exec(select(ClientInterestSignal).where(ClientInterestSignal.contact_name == "Bid Lead")).first()
        assert response.status_code == 303
        assert signal is not None

        response = client.post(
            f"/client-portal/interests/{signal.id}",
            data={"opportunity_id": str(opportunity.id), "customer_id": str(customer.id), "contact_name": "Bid Lead Updated", "signal": "interested", "status": "open"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(signal)
        assert signal.contact_name == "Bid Lead Updated"

        report = create_report(seeded_session, "CRUD Report", customer_id=customer.id, business_unit_id=unit.id)
        response = client.post(
            f"/reports/{report.id}/update",
            data={"report_name": "CRUD Report Updated", "report_type": "executive_summary", "customer_id": str(customer.id), "business_unit_id": str(unit.id)},
            follow_redirects=False,
        )
        assert response.status_code == 303
        seeded_session.refresh(report)
        assert report.report_name == "CRUD Report Updated"

        for url, model, obj in [
            (f"/client-portal/interests/{signal.id}/delete", ClientInterestSignal, signal),
            (f"/quality-questions/{question.id}/delete", ExtractedQualityQuestion, question),
            (f"/requirements/{requirement.id}/delete", ExtractedRequirement, requirement),
            (f"/tasks/{task.id}/delete", DocumentRetrievalTask, task),
            (f"/opportunities/{opportunity.id}/documents/{document.id}/delete", OpportunityDocument, document),
            (f"/portals/{portal.id}/delete", BuyerPortalInstance, portal),
            (f"/opportunities/{opportunity.id}/delete", Opportunity, opportunity),
            (f"/sources/{source.id}/delete", ProcurementSource, source),
            (f"/reports/{report.id}/delete", IntelligenceReport, report),
            (f"/customers/{customer.id}/delete", Customer, customer),
            (f"/business-units/{unit.id}/delete", BusinessUnit, unit),
        ]:
            response = client.post(url, data={"return_to": "/requirements"}, follow_redirects=False)
            assert response.status_code == 303
            assert seeded_session.get(model, obj.id) is None
    finally:
        app.dependency_overrides.clear()

    assert seeded_session.exec(select(AuditEvent).where(AuditEvent.action == "delete")).first() is not None
    assert existing_customer is not None
