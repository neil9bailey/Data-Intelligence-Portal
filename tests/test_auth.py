import base64
import json

from fastapi.testclient import TestClient

from app.database import get_session
from app.main import app
from app.settings import get_settings


def principal_header(groups):
    payload = {
        "auth_typ": "aad",
        "name_typ": "name",
        "role_typ": "roles",
        "claims": [
            {"typ": "name", "val": "Test User"},
            {"typ": "preferred_username", "val": "test.user@vendorlogic.io"},
            *[{"typ": "groups", "val": group_id} for group_id in groups],
        ],
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def client_for(session):
    def override_session():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_admin_route_requires_admin_group_when_entra_enabled(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    get_settings.cache_clear()
    client = client_for(reference_session)
    try:
        standard_response = client.get("/admin", headers={"x-ms-client-principal": principal_header(["standard-group"])})
        admin_response = client.get("/admin", headers={"x-ms-client-principal": principal_header(["admin-group"])})
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert standard_response.status_code == 403
    assert admin_response.status_code == 200


def test_local_auth_disabled_allows_admin(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    client = client_for(reference_session)
    try:
        response = client.get("/admin")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200
