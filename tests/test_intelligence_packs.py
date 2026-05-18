from fastapi.testclient import TestClient
from sqlmodel import select

from app.database import get_session
from app.intelligence_packs import apply_intelligence_pack, build_discovery_pack, get_preconfigured_customer_pack
from app.main import app
from app.models import (
    AuditEvent,
    BusinessUnit,
    BuyerPortalInstance,
    Customer,
    CustomerWatchProfile,
    PortalInformationConnector,
    ProcurementSource,
)


def client_for(session):
    def override_session():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_national_highways_pack_applies_expected_records(reference_session):
    pack = get_preconfigured_customer_pack("national_highways")

    result = apply_intelligence_pack(reference_session, pack)

    customer = reference_session.exec(select(Customer).where(Customer.customer_name == "National Highways")).first()
    unit = reference_session.exec(select(BusinessUnit).where(BusinessUnit.name == "Highways")).first()
    watch = reference_session.exec(select(CustomerWatchProfile).where(CustomerWatchProfile.profile_name == "National Highways public sector watch")).first()
    portal = reference_session.exec(select(BuyerPortalInstance).where(BuyerPortalInstance.portal_name == "National Highways - Jaggaer eSourcing")).first()
    source = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender_national_highways")).first()
    connector = reference_session.exec(select(PortalInformationConnector).where(PortalInformationConnector.connector_name == "Contracts Finder - National Highways public notices")).first()

    assert customer is not None
    assert unit is not None
    assert watch is not None
    assert "roadside technology" in watch.keywords
    assert portal is not None
    assert portal.customer_id == customer.id
    assert source is not None
    assert connector is not None
    assert connector.enabled is True
    assert connector.integration_method == "public_api_no_key"
    assert any("Customer: National Highways" in item for item in result["created"])
    assert reference_session.exec(select(AuditEvent).where(AuditEvent.entity_type == "IntelligencePack")).first() is not None


def test_intelligence_pack_reapply_is_idempotent(reference_session):
    pack = get_preconfigured_customer_pack("national_highways")
    apply_intelligence_pack(reference_session, pack)
    counts = {
        "customers": len(list(reference_session.exec(select(Customer)))),
        "sources": len(list(reference_session.exec(select(ProcurementSource)))),
        "portals": len(list(reference_session.exec(select(BuyerPortalInstance)))),
        "connectors": len(list(reference_session.exec(select(PortalInformationConnector)))),
    }

    result = apply_intelligence_pack(reference_session, pack)
    after_counts = {
        "customers": len(list(reference_session.exec(select(Customer)))),
        "sources": len(list(reference_session.exec(select(ProcurementSource)))),
        "portals": len(list(reference_session.exec(select(BuyerPortalInstance)))),
        "connectors": len(list(reference_session.exec(select(PortalInformationConnector)))),
    }

    assert after_counts == counts
    assert result["created"] == []
    assert any("Customer already configured" in item for item in result["skipped"])


def test_generic_discovery_pack_creates_public_source_baseline(reference_session):
    pack = build_discovery_pack("Leeds City Council", "local_authority", "Highways")

    result = apply_intelligence_pack(reference_session, pack)

    customer = reference_session.exec(select(Customer).where(Customer.customer_name == "Leeds City Council")).first()
    watch = reference_session.exec(select(CustomerWatchProfile).where(CustomerWatchProfile.profile_name == "Leeds City Council watch")).first()
    fat = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender_leeds_city_council")).first()
    cf = reference_session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "contracts_finder_leeds_city_council")).first()

    assert customer is not None
    assert customer.customer_type == "local authority"
    assert watch is not None
    assert "highways maintenance" in watch.keywords
    assert fat is not None
    assert cf is not None
    assert "Confirm the active buyer portal family" in "; ".join(pack["missing_actions"])
    assert any("Customer: Leeds City Council" in item for item in result["created"])


def test_intelligence_pack_routes_preview_and_apply(reference_session):
    client = client_for(reference_session)
    try:
        page = client.get("/intelligence-packs")
        preview = client.post(
            "/intelligence-packs/preview",
            data={"mode": "built_in", "pack_key": "national_highways"},
        )
        apply_response = client.post(
            "/intelligence-packs/apply",
            data={"mode": "discover", "organisation_name": "Bristol City Council", "template_key": "local_authority"},
        )
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == 200
    assert "Configure a public-sector customer in minutes" in page.text
    assert preview.status_code == 200
    assert "National Highways" in preview.text
    assert apply_response.status_code == 200
    assert "Pack Applied" in apply_response.text
    assert reference_session.exec(select(Customer).where(Customer.customer_name == "Bristol City Council")).first() is not None
