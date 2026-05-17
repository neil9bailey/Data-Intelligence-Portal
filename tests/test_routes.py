from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.main import app
from app.models import EmailDeliveryLog, Opportunity
from app.reports import create_report


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
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_uses_clean_setup_homepage(reference_session):
    client = client_for(reference_session)
    try:
        response = client.get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Public sector opportunity intelligence, ready to configure." in response.text
    assert "One customer memory for every source, portal and requirement." not in response.text
    assert "Official Intelligence Feed" in response.text


def test_report_download_formats_and_local_email(reference_session):
    report = create_report(reference_session, "Export test")
    client = client_for(reference_session)
    try:
        html_response = client.get(f"/reports/{report.id}?format=html")
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
    assert json_response.status_code == 200
    assert json_response.json()["report_name"] == "Export test"
    assert email_response.status_code == 303
    assert reference_session.exec(select(EmailDeliveryLog)).first().status == "stored"


def test_admin_email_test_route(reference_session):
    client = client_for(reference_session)
    try:
        response = client.post(
            "/admin/email/test",
            data={"recipients": "ops@example.com", "subject": "Test", "message": "Hello"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert reference_session.exec(select(EmailDeliveryLog)).first() is not None
