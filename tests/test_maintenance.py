from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.main import app
from app.models import (
    AuditEvent,
    AutomationRun,
    Customer,
    EmailDeliveryLog,
    IntelligenceReport,
    KRAFinding,
    KRAResearchRun,
    NewsFeedItem,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementSource,
    SourceCheckSnapshot,
)


def client_for(session):
    def override_session():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_admin_clean_generated_outputs_preserves_configured_data(reference_session):
    source = ProcurementSource(
        name="Clean test source",
        source_key="clean_test",
        base_url="https://www.find-tender.service.gov.uk",
        query_url="https://www.find-tender.service.gov.uk/Search",
        connector_status="find_a_tender_failed",
        last_status="failed",
    )
    connector = PortalInformationConnector(
        connector_name="Clean test connector",
        last_status="failed",
        last_http_status=500,
    )
    customer = Customer(customer_name="Configured customer to keep")
    reference_session.add(source)
    reference_session.add(connector)
    reference_session.add(customer)
    reference_session.commit()
    reference_session.refresh(source)
    reference_session.refresh(connector)

    report = IntelligenceReport(report_name="Old generated report", markdown="old")
    reference_session.add(report)
    reference_session.commit()
    reference_session.refresh(report)
    artefacts = [
        EmailDeliveryLog(report_id=report.id, subject="Old email"),
        AutomationRun(report_id=report.id, summary="Old run"),
        SourceCheckSnapshot(source_id=source.id, change_type="failed"),
        PortalRetrievalRun(connector_id=connector.id, status="failed"),
        KRAResearchRun(source_id=source.id, status="completed"),
        KRAFinding(title="Old finding", source_id=source.id),
        NewsFeedItem(title="Old news item"),
    ]
    for artefact in artefacts:
        reference_session.add(artefact)
    reference_session.commit()

    client = client_for(reference_session)
    try:
        response = client.post(
            "/admin/maintenance/clean-output",
            data={"confirm_clean": "true"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert reference_session.get(Customer, customer.id) is not None
    assert list(reference_session.exec(select(IntelligenceReport))) == []
    assert list(reference_session.exec(select(EmailDeliveryLog))) == []
    assert list(reference_session.exec(select(AutomationRun))) == []
    assert list(reference_session.exec(select(SourceCheckSnapshot))) == []
    assert list(reference_session.exec(select(PortalRetrievalRun))) == []
    assert list(reference_session.exec(select(KRAResearchRun))) == []
    assert list(reference_session.exec(select(KRAFinding))) == []
    assert list(reference_session.exec(select(NewsFeedItem))) == []
    reference_session.refresh(source)
    reference_session.refresh(connector)
    assert source.last_status == ""
    assert source.connector_status == "configured"
    assert connector.last_status == "not_checked"
    assert connector.last_http_status == 0
    assert reference_session.exec(select(AuditEvent).where(AuditEvent.action == "clean_generated_outputs")).first() is not None
