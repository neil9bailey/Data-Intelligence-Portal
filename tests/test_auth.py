import base64
import json

from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.main import app
from app.models import AuditEvent, BusinessUnit, ClientInterestSignal, Customer, IntelligenceReport, KRAFinding, Opportunity, OpportunityFeedback
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
    monkeypatch.setenv("ENTRA_AUDITOR_GROUP_ID", "auditor-group")
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


def test_standard_user_sees_simple_pages_not_admin_setup(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    get_settings.cache_clear()
    client = client_for(reference_session)
    headers = {"x-ms-client-principal": principal_header(["standard-group"])}
    try:
        home_response = client.get("/", headers=headers)
        reports_response = client.get("/reports", headers=headers)
        customers_response = client.get("/customers", headers=headers)
        admin_post_response = client.post("/admin/email", headers=headers, data={"smtp_port": "587"})
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert home_response.status_code == 200
    assert reports_response.status_code == 200
    assert customers_response.status_code == 403
    assert admin_post_response.status_code == 403
    assert 'href="/admin"' not in home_response.text
    assert "Opportunity intelligence, classified and ready." in home_response.text


def test_admin_user_gets_dedicated_admin_workspace(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    get_settings.cache_clear()
    client = client_for(reference_session)
    headers = {"x-ms-client-principal": principal_header(["admin-group"])}
    try:
        home_response = client.get("/", headers=headers)
        admin_response = client.get("/admin", headers=headers)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert home_response.status_code == 200
    assert admin_response.status_code == 200
    assert 'href="/admin"' in home_response.text
    assert "Admin Configuration Workspace" in admin_response.text
    assert "Customer packs" in admin_response.text
    assert "Portals / connectors" in admin_response.text
    assert "Admin Control" not in home_response.text


def test_local_auth_disabled_allows_admin(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "false")
    monkeypatch.setenv("LOCAL_ADMIN_MODE", "true")
    get_settings.cache_clear()
    client = client_for(reference_session)
    try:
        response = client.get("/admin")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200


def test_local_admin_mode_can_be_disabled_for_production_style_auth(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "false")
    monkeypatch.setenv("LOCAL_ADMIN_MODE", "false")
    get_settings.cache_clear()
    client = client_for(reference_session)
    try:
        admin_response = client.get("/admin")
        health_response = client.get("/healthz")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert admin_response.status_code == 401
    assert health_response.status_code == 200


def test_anonymous_entra_request_cannot_access_standard_pages(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    get_settings.cache_clear()
    client = client_for(reference_session)
    try:
        home_response = client.get("/")
        reports_response = client.get("/reports")
        health_response = client.get("/healthz")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert home_response.status_code == 401
    assert reports_response.status_code == 401
    assert health_response.status_code == 200


def test_auditor_can_view_reports_and_audit_but_not_admin(monkeypatch, reference_session):
    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    monkeypatch.setenv("ENTRA_AUDITOR_GROUP_ID", "auditor-group")
    get_settings.cache_clear()
    client = client_for(reference_session)
    headers = {"x-ms-client-principal": principal_header(["auditor-group"])}
    try:
        reports_response = client.get("/reports", headers=headers)
        audit_response = client.get("/audit", headers=headers)
        admin_response = client.get("/admin", headers=headers)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert reports_response.status_code == 200
    assert audit_response.status_code == 200
    assert admin_response.status_code == 403


def test_audit_export_filters_and_redacts_for_auditor(monkeypatch, reference_session):
    reference_session.add(
        AuditEvent(
            actor="ops@example.com",
            entity_type="EmailConfiguration",
            entity_id=99,
            action="update",
            summary="Updated email config",
            before_json='{"smtp_password":"***redacted***"}',
            after_json='{"smtp_password":"***redacted***"}',
        )
    )
    reference_session.add(
        AuditEvent(
            actor="other@example.com",
            entity_type="Opportunity",
            entity_id=100,
            action="create",
            summary="Created opportunity",
        )
    )
    reference_session.commit()

    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    monkeypatch.setenv("ENTRA_AUDITOR_GROUP_ID", "auditor-group")
    get_settings.cache_clear()
    client = client_for(reference_session)
    headers = {"x-ms-client-principal": principal_header(["auditor-group"])}
    try:
        response = client.get(
            "/audit?format=json&entity_type=EmailConfiguration&actor=ops@example.com&action=update",
            headers=headers,
        )
        denied = client.get("/audit?format=csv", headers={"x-ms-client-principal": principal_header(["standard-group"])})
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["entity_type"] == "EmailConfiguration"
    assert payload[0]["actor"] == "ops@example.com"
    assert "secret-value" not in response.text
    assert "***redacted***" in response.text
    assert denied.status_code == 403


def test_standard_user_scope_filters_reports_and_client_feed(monkeypatch, reference_session):
    in_scope = Customer(customer_name="Scoped Council", sector="Local government")
    out_scope = Customer(customer_name="Other Council", sector="Local government")
    reference_session.add(in_scope)
    reference_session.add(out_scope)
    reference_session.commit()
    reference_session.refresh(in_scope)
    reference_session.refresh(out_scope)
    visible_report = IntelligenceReport(report_name="Scoped report", customer_id=in_scope.id, markdown="Visible")
    hidden_report = IntelligenceReport(report_name="Hidden report", customer_id=out_scope.id, markdown="Hidden")
    visible_opportunity = Opportunity(title="Scoped opportunity", customer_id=in_scope.id, status="approved", relevance_score=80)
    hidden_opportunity = Opportunity(title="Hidden opportunity", customer_id=out_scope.id, status="approved", relevance_score=80)
    reference_session.add(visible_report)
    reference_session.add(hidden_report)
    reference_session.add(visible_opportunity)
    reference_session.add(hidden_opportunity)
    reference_session.commit()
    reference_session.refresh(visible_report)
    reference_session.refresh(hidden_report)
    reference_session.refresh(visible_opportunity)
    reference_session.refresh(hidden_opportunity)
    reference_session.add(ClientInterestSignal(customer_id=in_scope.id, opportunity_id=visible_opportunity.id, contact_name="Scoped lead"))
    reference_session.add(ClientInterestSignal(customer_id=out_scope.id, opportunity_id=hidden_opportunity.id, contact_name="Hidden lead"))
    reference_session.commit()

    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    monkeypatch.setenv(
        "DIP_ACCESS_SCOPES_JSON",
        json.dumps({"test.user@vendorlogic.io": {"customer_ids": [in_scope.id]}}),
    )
    get_settings.cache_clear()
    client = client_for(reference_session)
    headers = {"x-ms-client-principal": principal_header(["standard-group"])}
    try:
        reports_response = client.get("/reports", headers=headers)
        hidden_detail = client.get(f"/reports/{hidden_report.id}", headers=headers)
        feed_response = client.get("/client-portal", headers=headers)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert reports_response.status_code == 200
    assert "Scoped report" in reports_response.text
    assert "Hidden report" not in reports_response.text
    assert hidden_detail.status_code == 403
    assert feed_response.status_code == 200
    assert "Scoped opportunity" in feed_response.text
    assert "Hidden opportunity" not in feed_response.text
    assert "Scoped lead" in feed_response.text
    assert "Hidden lead" not in feed_response.text


def test_standard_user_scope_filters_dashboard_and_reference_context(monkeypatch, reference_session):
    in_unit = BusinessUnit(name="Scoped Unit")
    out_unit = BusinessUnit(name="Hidden Unit")
    reference_session.add(in_unit)
    reference_session.add(out_unit)
    reference_session.commit()
    reference_session.refresh(in_unit)
    reference_session.refresh(out_unit)
    in_scope = Customer(customer_name="Scoped Authority", business_unit_id=in_unit.id, sector="Transport")
    out_scope = Customer(customer_name="Hidden Authority", business_unit_id=out_unit.id, sector="Transport")
    reference_session.add(in_scope)
    reference_session.add(out_scope)
    reference_session.commit()
    reference_session.refresh(in_scope)
    reference_session.refresh(out_scope)
    visible_opportunity = Opportunity(
        title="Scoped dashboard opportunity",
        customer_id=in_scope.id,
        business_unit_id=in_unit.id,
        status="approved",
        relevance_score=90,
        summary="Visible source-backed opportunity",
    )
    hidden_opportunity = Opportunity(
        title="Hidden dashboard opportunity",
        customer_id=out_scope.id,
        business_unit_id=out_unit.id,
        status="approved",
        relevance_score=90,
        summary="Should not appear",
    )
    visible_report = IntelligenceReport(report_name="Scoped dashboard report", customer_id=in_scope.id, markdown="Visible")
    hidden_report = IntelligenceReport(report_name="Hidden dashboard report", customer_id=out_scope.id, markdown="Hidden")
    visible_finding = KRAFinding(title="Scoped KRA signal", customer_id=in_scope.id, summary="Visible finding")
    hidden_finding = KRAFinding(title="Hidden KRA signal", customer_id=out_scope.id, summary="Hidden finding")
    reference_session.add(visible_opportunity)
    reference_session.add(hidden_opportunity)
    reference_session.add(visible_report)
    reference_session.add(hidden_report)
    reference_session.add(visible_finding)
    reference_session.add(hidden_finding)
    reference_session.commit()

    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    monkeypatch.setenv("ENTRA_STANDARD_GROUP_ID", "standard-group")
    monkeypatch.setenv(
        "DIP_ACCESS_SCOPES_JSON",
        json.dumps({"test.user@vendorlogic.io": {"customer_ids": [in_scope.id]}}),
    )
    get_settings.cache_clear()
    client = client_for(reference_session)
    headers = {"x-ms-client-principal": principal_header(["standard-group"])}
    try:
        response = client.get("/", headers=headers)
        reports_response = client.get("/reports", headers=headers)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200
    assert "Scoped dashboard opportunity" in response.text
    assert "Hidden dashboard opportunity" not in response.text
    assert "Scoped dashboard report" in response.text
    assert "Hidden dashboard report" not in response.text
    assert "Scoped KRA signal" in response.text
    assert "Hidden KRA signal" not in response.text
    assert "Hidden Authority" not in response.text
    assert "Hidden Unit" not in response.text
    assert reports_response.status_code == 200
    assert "Scoped dashboard report" in reports_response.text
    assert "Hidden Authority" not in reports_response.text


def test_admin_feedback_updates_opportunity_status_and_audit(monkeypatch, reference_session):
    opportunity = Opportunity(title="Feedback candidate", status="new", relevance_score=62)
    reference_session.add(opportunity)
    reference_session.commit()
    reference_session.refresh(opportunity)

    monkeypatch.setenv("ENTRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_ADMIN_GROUP_ID", "admin-group")
    get_settings.cache_clear()
    client = client_for(reference_session)
    headers = {"x-ms-client-principal": principal_header(["admin-group"])}
    try:
        approve_response = client.post(
            f"/opportunities/{opportunity.id}/feedback",
            headers=headers,
            data={"feedback_type": "approve", "notes": "Reviewed and suitable for the client feed."},
            follow_redirects=False,
        )
        reference_session.refresh(opportunity)
        review_response = client.post(
            f"/opportunities/{opportunity.id}/feedback",
            headers=headers,
            data={"feedback_type": "needs_more_evidence", "notes": "Need tender document text."},
            follow_redirects=False,
        )
        reference_session.refresh(opportunity)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert approve_response.status_code == 303
    assert review_response.status_code == 303
    assert opportunity.status == "review_required"
    assert reference_session.exec(select(OpportunityFeedback).where(OpportunityFeedback.opportunity_id == opportunity.id)).first() is not None
    assert (
        reference_session.exec(select(AuditEvent).where(AuditEvent.entity_type == "Opportunity", AuditEvent.action == "update")).first()
        is not None
    )
