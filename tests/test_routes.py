from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.main import app
from app.models import Opportunity


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
            "/customers",
            "/sources",
            "/opportunities",
            f"/opportunities/{opportunity.id}/documents",
            "/portals",
            "/requirements",
            "/kra",
            "/reports",
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
