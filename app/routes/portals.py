from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.audit import compact_snapshot
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_bool, parse_optional_date, parse_optional_int, validation_error_response
from app.models import BuyerPortalInstance, DocumentRetrievalTask, PortalInformationConnector, PortalRetrievalRun
from app.portal_connectors import run_enabled_portal_connectors, run_portal_connector
from app.route_utils import (
    clear_links,
    context,
    delete_with_audit,
    portal_workbench_context,
    redirect,
    reference_context,
    save_with_audit,
    templates,
    update_with_audit,
)


router = APIRouter()


@router.get("/portals", response_class=HTMLResponse)
def portals(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "portals.html",
        context(request, **reference_context(session), **portal_workbench_context(session)),
    )


@router.post("/portals")
async def create_portal(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    platform_id = parse_optional_int(form.get("platform_id"), "Platform", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    name = str(form.get("portal_name") or "").strip()
    if not name:
        errors.append("Portal name is required.")
    if errors:
        return validation_error_response(errors, "/portals")
    portal = BuyerPortalInstance(
        portal_name=name,
        platform_id=platform_id,
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        portal_url=str(form.get("portal_url") or ""),
        account_reference=str(form.get("account_reference") or ""),
        access_status=str(form.get("access_status") or "unknown"),
        document_retrieval_mode=str(form.get("document_retrieval_mode") or "account_required_manual"),
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, portal, "create", f"Created portal {portal.portal_name}")
    return redirect("/portals")


@router.post("/portals/{portal_id}")
async def update_portal(portal_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    portal = session.get(BuyerPortalInstance, portal_id)
    if not portal:
        return redirect("/portals")
    form = await request.form()
    errors: list[str] = []
    platform_id = parse_optional_int(form.get("platform_id"), "Platform", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    name = str(form.get("portal_name") or "").strip()
    if not name:
        errors.append("Portal name is required.")
    if errors:
        return validation_error_response(errors, "/portals")
    before = compact_snapshot(portal)
    portal.portal_name = name
    portal.platform_id = platform_id
    portal.customer_id = customer_id
    portal.business_unit_id = business_unit_id
    portal.portal_url = str(form.get("portal_url") or "")
    portal.account_reference = str(form.get("account_reference") or "")
    portal.access_status = str(form.get("access_status") or "unknown")
    portal.document_retrieval_mode = str(form.get("document_retrieval_mode") or "account_required_manual")
    portal.notes = str(form.get("notes") or "")
    update_with_audit(session, portal, f"Updated portal {portal.portal_name}", before)
    return redirect("/portals")


@router.post("/portals/{portal_id}/delete")
def delete_portal(portal_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    portal = session.get(BuyerPortalInstance, portal_id)
    if not portal:
        return redirect("/portals")
    clear_links(session, DocumentRetrievalTask, "portal_instance_id", portal.id)
    clear_links(session, PortalInformationConnector, "portal_instance_id", portal.id)
    clear_links(session, PortalRetrievalRun, "portal_instance_id", portal.id)
    delete_with_audit(session, portal, f"Deleted portal {portal.portal_name}")
    return redirect("/portals")


@router.post("/portal-connectors")
async def create_portal_connector(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("connector_name") or "").strip()
    portal_id = parse_optional_int(form.get("portal_instance_id"), "Portal instance", errors)
    opportunity_id = parse_optional_int(form.get("default_opportunity_id"), "Default opportunity", errors)
    integration_method = str(form.get("integration_method") or "manual_assisted")
    auth_type = str(form.get("auth_type") or "none")
    endpoint_url = str(form.get("endpoint_url") or "").strip()
    if not name:
        errors.append("Connector name is required.")
    if integration_method != "manual_assisted" and not endpoint_url:
        errors.append("Endpoint URL is required for automated retrieval connectors.")
    if errors:
        return validation_error_response(errors, "/portals")
    connector = PortalInformationConnector(
        connector_name=name,
        portal_instance_id=portal_id,
        integration_method=integration_method,
        endpoint_url=endpoint_url,
        auth_type=auth_type,
        api_key_secret_name=str(form.get("api_key_secret_name") or ""),
        api_key_header_name=str(form.get("api_key_header_name") or "X-API-Key"),
        api_key_query_name=str(form.get("api_key_query_name") or "api_key"),
        default_opportunity_id=opportunity_id,
        enabled=parse_bool(form.get("enabled")),
        read_only=True,
        allowed_operations=str(form.get("allowed_operations") or "retrieve_metadata; retrieve_documents; detect_changes"),
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, connector, "create", f"Created portal retrieval connector {connector.connector_name}")
    return redirect("/portals")


@router.post("/portal-connectors/run-all")
def run_all_portal_connectors(session: Session = Depends(get_session), _user=Depends(require_admin)):
    run_enabled_portal_connectors(session)
    return redirect("/portals")


@router.post("/portal-connectors/{connector_id}")
async def update_portal_connector(connector_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    connector = session.get(PortalInformationConnector, connector_id)
    if not connector:
        return redirect("/portals")
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("connector_name") or "").strip()
    portal_id = parse_optional_int(form.get("portal_instance_id"), "Portal instance", errors)
    opportunity_id = parse_optional_int(form.get("default_opportunity_id"), "Default opportunity", errors)
    integration_method = str(form.get("integration_method") or "manual_assisted")
    auth_type = str(form.get("auth_type") or "none")
    endpoint_url = str(form.get("endpoint_url") or "").strip()
    if not name:
        errors.append("Connector name is required.")
    if integration_method != "manual_assisted" and not endpoint_url:
        errors.append("Endpoint URL is required for automated retrieval connectors.")
    if errors:
        return validation_error_response(errors, "/portals")
    before = compact_snapshot(connector)
    connector.connector_name = name
    connector.portal_instance_id = portal_id
    connector.integration_method = integration_method
    connector.endpoint_url = endpoint_url
    connector.auth_type = auth_type
    connector.api_key_secret_name = str(form.get("api_key_secret_name") or "")
    connector.api_key_header_name = str(form.get("api_key_header_name") or "X-API-Key")
    connector.api_key_query_name = str(form.get("api_key_query_name") or "api_key")
    connector.default_opportunity_id = opportunity_id
    connector.enabled = parse_bool(form.get("enabled"))
    connector.read_only = True
    connector.allowed_operations = str(form.get("allowed_operations") or "retrieve_metadata; retrieve_documents; detect_changes")
    connector.notes = str(form.get("notes") or "")
    update_with_audit(session, connector, f"Updated portal retrieval connector {connector.connector_name}", before)
    return redirect("/portals")


@router.post("/portal-connectors/{connector_id}/delete")
def delete_portal_connector(connector_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    connector = session.get(PortalInformationConnector, connector_id)
    if not connector:
        return redirect("/portals")
    clear_links(session, PortalRetrievalRun, "connector_id", connector.id)
    delete_with_audit(session, connector, f"Deleted portal retrieval connector {connector.connector_name}")
    return redirect("/portals")


@router.post("/portal-connectors/{connector_id}/run")
def run_single_portal_connector(connector_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    try:
        run_portal_connector(session, connector_id)
    except ValueError as exc:
        return validation_error_response([str(exc)], "/portals")
    return redirect("/portals")


@router.post("/portals/{portal_id}/tasks")
async def create_portal_task(portal_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    portal = session.get(BuyerPortalInstance, portal_id)
    if not portal:
        return redirect("/portals")
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    due_date = parse_optional_date(form.get("due_date"), "Due date", errors)
    task_name = str(form.get("task_name") or "Manual portal document retrieval").strip()
    if not task_name:
        errors.append("Task name is required.")
    if errors:
        return validation_error_response(errors, "/portals")
    task = DocumentRetrievalTask(
        opportunity_id=opportunity_id,
        portal_instance_id=portal.id,
        task_name=task_name,
        status=str(form.get("status") or "requested"),
        owner=str(form.get("owner") or "local-user"),
        due_date=due_date,
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, task, "create", f"Created portal task {task.task_name}")
    return redirect("/portals")
