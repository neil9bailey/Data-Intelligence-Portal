from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.auth import get_current_user, require_admin
from app.database import (
    backup_sqlite_persistent_copy,
    engine,
    get_session,
    init_db,
    restore_sqlite_persistent_copy,
    retry_sqlite_locked,
    sqlite_db_path,
    sqlite_persistent_copy_path,
    sqlite_startup_lock,
)
from app.email_service import get_email_configuration, send_or_store_email, split_recipients
from app.export_service import report_export
from app.form_utils import parse_bool, parse_float, parse_optional_date, parse_optional_int, validation_error_response
from app.intelligence import (
    extract_document_intelligence,
    kra_runtime_status,
    refresh_news_feeds,
    run_kra_research,
    run_source_check,
    source_allowed,
)
from app.models import (
    AuditEvent,
    BusinessUnit,
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    CustomerWatchProfile,
    DocumentRetrievalTask,
    EmailConfiguration,
    EmailDeliveryLog,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    IntelligenceReport,
    KRAAgentProfile,
    KRAFinding,
    KRAResearchRun,
    NewsFeedItem,
    NewsFeedSource,
    Opportunity,
    OpportunityDocument,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementPlatform,
    ProcurementSource,
    SourceCheckSnapshot,
    utc_now,
)
from app.portal_connectors import run_enabled_portal_connectors, run_portal_connector
from app.reports import create_report
from app.rule_loader import load_rule_file, rules_version_summary
from app.seed import seed_demo_data, seed_reference_data
from app.settings import BASE_DIR, get_settings


def run_seed(seed_fn):
    with Session(engine) as session:
        seed_fn(session)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with sqlite_startup_lock():
        restore_sqlite_persistent_copy()
        init_db()
        settings = get_settings()
        if settings.seed_reference_data:
            retry_sqlite_locked(lambda: run_seed(seed_reference_data))
        if settings.seed_demo_data:
            retry_sqlite_locked(lambda: run_seed(seed_demo_data))
        backup_sqlite_persistent_copy()
    try:
        yield
    finally:
        backup_sqlite_persistent_copy()


app = FastAPI(title="Data Intelligence Portal", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.middleware("http")
async def persist_sqlite_copy_after_writes(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 500:
        backup_sqlite_persistent_copy()
    return response


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def context(request: Request, **extra):
    settings = get_settings()
    base = {
        "request": request,
        "app_name": settings.app_name,
        "rules_versions": rules_version_summary(),
        "kra_runtime": kra_runtime_status(),
        "current_user": get_current_user(request),
        "entra_auth_enabled": settings.entra_auth_enabled,
    }
    base.update(extra)
    return base


def save_with_audit(session: Session, item, action: str, summary: str, before_snapshot: str = ""):
    session.add(item)
    session.flush()
    log_event(
        session,
        entity_type=item.__class__.__name__,
        entity_id=item.id,
        action=action,
        summary=summary,
        before=before_snapshot,
        after=item,
    )
    session.commit()
    return item


def update_with_audit(session: Session, item, summary: str, before_snapshot: str):
    session.add(item)
    session.flush()
    log_event(
        session,
        entity_type=item.__class__.__name__,
        entity_id=item.id,
        action="update",
        summary=summary,
        before=before_snapshot,
        after=item,
    )
    session.commit()
    return item


def delete_with_audit(session: Session, item, summary: str):
    entity_type = item.__class__.__name__
    entity_id = item.id
    before = compact_snapshot(item)
    log_event(session, entity_type=entity_type, entity_id=entity_id, action="delete", summary=summary, before=before)
    session.delete(item)
    session.commit()


def clear_links(session: Session, model, field_name: str, target_id: int | None) -> None:
    if target_id is None:
        return
    field = getattr(model, field_name)
    for item in session.exec(select(model).where(field == target_id)):
        setattr(item, field_name, None)
        session.add(item)


def delete_children(session: Session, model, field_name: str, target_id: int | None) -> None:
    if target_id is None:
        return
    field = getattr(model, field_name)
    for item in session.exec(select(model).where(field == target_id)):
        session.delete(item)


def reference_context(session: Session) -> dict:
    customers = list(session.exec(select(Customer).order_by(col(Customer.customer_name))))
    units = list(session.exec(select(BusinessUnit).order_by(col(BusinessUnit.name))))
    sources = list(session.exec(select(ProcurementSource).order_by(col(ProcurementSource.name))))
    platforms = list(session.exec(select(ProcurementPlatform).order_by(col(ProcurementPlatform.name))))
    portals = list(session.exec(select(BuyerPortalInstance).order_by(col(BuyerPortalInstance.portal_name))))
    connectors = list(session.exec(select(PortalInformationConnector).order_by(col(PortalInformationConnector.connector_name))))
    agents = list(session.exec(select(KRAAgentProfile).order_by(col(KRAAgentProfile.name))))
    news_feeds = list(session.exec(select(NewsFeedSource).order_by(col(NewsFeedSource.name))))
    return {
        "customers": customers,
        "business_units": units,
        "sources": sources,
        "platforms": platforms,
        "portal_instances": portals,
        "portal_connectors": connectors,
        "agents": agents,
        "news_feeds": news_feeds,
        "customer_map": {item.id: item for item in customers},
        "business_unit_map": {item.id: item for item in units},
        "source_map": {item.id: item for item in sources},
        "platform_map": {item.id: item for item in platforms},
        "portal_map": {item.id: item for item in portals},
        "portal_connector_map": {item.id: item for item in connectors},
        "agent_map": {item.id: item for item in agents},
        "news_feed_map": {item.id: item for item in news_feeds},
    }


@app.get("/business-units", response_class=HTMLResponse)
def business_units(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "business_units.html", context(request, **reference_context(session)))


@app.post("/business-units")
async def create_business_unit(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("name") or "").strip()
    parent_id = parse_optional_int(form.get("parent_id"), "Parent business unit", errors)
    if not name:
        errors.append("Business unit name is required.")
    if errors:
        return validation_error_response(errors, "/business-units")
    unit = BusinessUnit(
        name=name,
        parent_id=parent_id,
        description=str(form.get("description") or ""),
        active=parse_bool(form.get("active")) if form.get("active") is not None else True,
    )
    save_with_audit(session, unit, "create", f"Created business unit {unit.name}")
    return redirect("/business-units")


@app.post("/business-units/{unit_id}")
async def update_business_unit(unit_id: int, request: Request, session: Session = Depends(get_session)):
    unit = session.get(BusinessUnit, unit_id)
    if not unit:
        return redirect("/business-units")
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("name") or "").strip()
    parent_id = parse_optional_int(form.get("parent_id"), "Parent business unit", errors)
    if parent_id == unit.id:
        errors.append("A business unit cannot be its own parent.")
    if not name:
        errors.append("Business unit name is required.")
    if errors:
        return validation_error_response(errors, "/business-units")
    before = compact_snapshot(unit)
    unit.name = name
    unit.parent_id = parent_id
    unit.description = str(form.get("description") or "")
    unit.active = parse_bool(form.get("active"))
    update_with_audit(session, unit, f"Updated business unit {unit.name}", before)
    return redirect("/business-units")


@app.post("/business-units/{unit_id}/delete")
def delete_business_unit(unit_id: int, session: Session = Depends(get_session)):
    unit = session.get(BusinessUnit, unit_id)
    if not unit:
        return redirect("/business-units")
    clear_links(session, BusinessUnit, "parent_id", unit.id)
    clear_links(session, Customer, "business_unit_id", unit.id)
    clear_links(session, CustomerWatchProfile, "business_unit_id", unit.id)
    clear_links(session, BuyerPortalInstance, "business_unit_id", unit.id)
    clear_links(session, Opportunity, "business_unit_id", unit.id)
    clear_links(session, IntelligenceReport, "business_unit_id", unit.id)
    delete_with_audit(session, unit, f"Deleted business unit {unit.name}")
    return redirect("/business-units")


PORTAL_READY_STATUSES = {"active", "registered", "live"}
PORTAL_ACTION_STATUSES = {
    "unknown",
    "registration_required",
    "access_requested",
    "blocked",
    "expired",
    "pending_mfa_owner",
    "not_registered",
}
TASK_OPEN_STATUSES = {"requested", "in_progress", "blocked", "review_required"}


def normalise_status(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "_").replace("-", "_")


def status_badge_class(status: str) -> str:
    value = normalise_status(status)
    if value in PORTAL_READY_STATUSES or value in {"completed", "done", "approved"}:
        return "green"
    if value in {"blocked", "expired", "rejected", "failed"}:
        return "red"
    if value in {"manual_assisted", "requested", "in_progress", "review_required"}:
        return "amber"
    return "weak"


def portal_next_action(portal: BuyerPortalInstance, platform: ProcurementPlatform | None, open_task_count: int) -> str:
    status = normalise_status(portal.access_status)
    mode = normalise_status(portal.document_retrieval_mode)
    if not portal.customer_id:
        return "Link the portal instance to the buyer/customer so captured intelligence can be reused."
    if not portal.platform_id or platform is None:
        return "Select the platform family so teams know the registration and retrieval pattern."
    if not portal.portal_url:
        return "Add the buyer portal URL used by the team."
    if status in {"", "unknown"}:
        return "Confirm whether the supplier account is registered, blocked or needs access requested."
    if status in {"registration_required", "not_registered"}:
        return "Assign a central supplier account owner to complete registration outside the app; store only the account reference here."
    if status == "access_requested":
        return "Track the access request and add due-date notes until the portal is usable."
    if status == "pending_mfa_owner":
        return "Record the internal MFA/account owner and keep credentials outside the MVP."
    if status in {"blocked", "expired"}:
        return "Escalate portal access before relying on it for bid document retrieval."
    if open_task_count:
        return "Complete the open manual document retrieval task, then paste permitted text into the opportunity documents screen."
    if mode in {"approved_api", "api_key_header", "api_key_query"}:
        return "Run the approved read-only connector before generating reports."
    return "Ready for manual-assisted document retrieval when a matching opportunity appears."


def portal_workbench_context(session: Session) -> dict:
    platforms = list(session.exec(select(ProcurementPlatform).order_by(col(ProcurementPlatform.name))))
    portals = list(session.exec(select(BuyerPortalInstance).order_by(col(BuyerPortalInstance.portal_name))))
    connectors = list(session.exec(select(PortalInformationConnector).order_by(col(PortalInformationConnector.connector_name))))
    retrieval_runs = list(session.exec(select(PortalRetrievalRun).order_by(col(PortalRetrievalRun.started_at).desc()).limit(80)))
    tasks = list(session.exec(select(DocumentRetrievalTask).order_by(col(DocumentRetrievalTask.created_at).desc())))
    opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.created_at).desc()).limit(100)))

    platform_map = {item.id: item for item in platforms}
    portal_task_map: dict[int, list[DocumentRetrievalTask]] = {}
    for task in tasks:
        if task.portal_instance_id:
            portal_task_map.setdefault(task.portal_instance_id, []).append(task)
    portal_connector_map: dict[int, list[PortalInformationConnector]] = {}
    for connector in connectors:
        if connector.portal_instance_id:
            portal_connector_map.setdefault(connector.portal_instance_id, []).append(connector)

    readiness_items = []
    for portal in portals:
        platform = platform_map.get(portal.platform_id)
        portal_tasks = portal_task_map.get(portal.id or 0, [])
        open_tasks = [task for task in portal_tasks if normalise_status(task.status) in TASK_OPEN_STATUSES]
        portal_connectors = portal_connector_map.get(portal.id or 0, [])
        status = normalise_status(portal.access_status)
        missing_items = []
        if not portal.customer_id:
            missing_items.append("customer link")
        if not portal.platform_id:
            missing_items.append("platform family")
        if not portal.portal_url:
            missing_items.append("portal URL")
        if status in {"", "unknown"}:
            missing_items.append("confirmed access status")
        readiness_items.append(
            {
                "portal": portal,
                "platform": platform,
                "tasks": portal_tasks,
                "open_tasks": open_tasks,
                "connectors": portal_connectors,
                "missing_items": missing_items,
                "next_action": portal_next_action(portal, platform, len(open_tasks)),
                "badge_class": status_badge_class(portal.access_status),
                "ready": status in PORTAL_READY_STATUSES and not missing_items,
                "needs_action": bool(missing_items) or status in PORTAL_ACTION_STATUSES or bool(open_tasks),
            }
        )

    platform_rows = []
    for platform in platforms:
        platform_portals = [portal for portal in portals if portal.platform_id == platform.id]
        ready_count = sum(1 for portal in platform_portals if normalise_status(portal.access_status) in PORTAL_READY_STATUSES)
        action_count = sum(1 for portal in platform_portals if normalise_status(portal.access_status) in PORTAL_ACTION_STATUSES)
        platform_rows.append(
            {
                "platform": platform,
                "instance_count": len(platform_portals),
                "ready_count": ready_count,
                "action_count": action_count,
            }
        )

    open_tasks = [task for task in tasks if normalise_status(task.status) in TASK_OPEN_STATUSES]
    metrics = {
        "platforms": len(platforms),
        "portal_instances": len(portals),
        "automated_connectors": sum(1 for connector in connectors if connector.enabled),
        "ready_portals": sum(1 for item in readiness_items if item["ready"]),
        "needs_action": sum(1 for item in readiness_items if item["needs_action"]),
        "open_tasks": len(open_tasks),
        "missing_urls": sum(1 for portal in portals if not portal.portal_url),
        "retrieval_runs": len(retrieval_runs),
    }
    return {
        "portal_metrics": metrics,
        "platform_rows": platform_rows,
        "portal_readiness_items": readiness_items,
        "portal_tasks": tasks[:80],
        "open_portal_tasks": open_tasks[:80],
        "retrieval_runs": retrieval_runs,
        "opportunities": opportunities,
        "portal_status_options": [
            "unknown",
            "registration_required",
            "access_requested",
            "pending_mfa_owner",
            "registered",
            "active",
            "blocked",
            "expired",
        ],
        "retrieval_mode_options": [
            "account_required_manual",
            "approved_api",
            "public_api_no_key",
            "api_key_header",
            "api_key_query",
            "not_available",
        ],
        "connector_method_options": ["manual_assisted", "public_api_no_key", "api_key_header", "api_key_query", "oauth_client_credentials"],
        "connector_auth_options": ["none", "api_key_header", "api_key_query"],
        "task_status_options": ["requested", "in_progress", "blocked", "review_required", "completed"],
    }


def dashboard_metrics(session: Session) -> dict:
    return {
        "customers": len(list(session.exec(select(Customer)))),
        "sources": len(list(session.exec(select(ProcurementSource)))),
        "active_sources": len(list(session.exec(select(ProcurementSource).where(ProcurementSource.active == True)))),  # noqa: E712
        "platforms": len(list(session.exec(select(ProcurementPlatform)))),
        "portal_connectors": len(list(session.exec(select(PortalInformationConnector)))),
        "enabled_portal_connectors": len(list(session.exec(select(PortalInformationConnector).where(PortalInformationConnector.enabled == True)))),  # noqa: E712
        "opportunities": len(list(session.exec(select(Opportunity)))),
        "documents": len(list(session.exec(select(OpportunityDocument)))),
        "requirements": len(list(session.exec(select(ExtractedRequirement)))),
        "questions": len(list(session.exec(select(ExtractedQualityQuestion)))),
        "pending_findings": len(list(session.exec(select(KRAFinding).where(KRAFinding.human_review_status == "pending")))),
        "source_changes": len(list(session.exec(select(SourceCheckSnapshot).where(SourceCheckSnapshot.change_type == "changed")))),
        "news_items": len(list(session.exec(select(NewsFeedItem)))),
        "review_queue": len(list(session.exec(select(Opportunity).where(col(Opportunity.status).in_(["new", "pending_review", "matched"]))))),
        "client_interests": len(list(session.exec(select(ClientInterestSignal)))),
    }


def file_status(path: Path | None) -> dict:
    if path is None:
        return {"path": "not configured", "exists": False, "size": ""}
    exists = path.exists()
    size = f"{path.stat().st_size / 1024:.1f} KB" if exists and path.is_file() else ""
    return {"path": str(path), "exists": exists, "size": size}


def remote_health_check(url: str) -> dict:
    if not url:
        return {"status": "not configured", "ok": False, "detail": ""}
    try:
        with httpx.Client(timeout=2.5, follow_redirects=False) as client:
            response = client.get(url)
        return {
            "status": str(response.status_code),
            "ok": response.status_code == 200,
            "detail": response.text[:160],
        }
    except httpx.HTTPError as exc:
        return {"status": "unreachable", "ok": False, "detail": str(exc)[:160]}


def health_dashboard_context(session: Session, request: Request) -> dict:
    settings = get_settings()
    db_count = len(list(session.exec(select(BusinessUnit)))) + len(list(session.exec(select(Customer))))
    sources = list(session.exec(select(ProcurementSource)))
    source_snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(20)))
    connectors = list(session.exec(select(PortalInformationConnector)))
    retrieval_runs = list(session.exec(select(PortalRetrievalRun).order_by(col(PortalRetrievalRun.started_at).desc()).limit(20)))
    portals = list(session.exec(select(BuyerPortalInstance)))
    tasks = list(session.exec(select(DocumentRetrievalTask)))
    email_config = get_email_configuration(session)
    email_logs = list(session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc()).limit(10)))
    current_user = get_current_user(request)
    source_failures = [item for item in source_snapshots if item.change_type == "failed" or not item.ok]
    connector_failures = [item for item in retrieval_runs if item.status in {"failed", "blocked"}]
    account_required = sum(
        1
        for portal in portals
        if normalise_status(portal.document_retrieval_mode)
        in {"", "manual", "manual_assisted", "account_required_manual", "not_available"}
    )
    return {
        "deployment": {
            "label": settings.deployment_label,
            "public_domain": settings.public_domain,
            "remote_url": settings.remote_health_url,
            "remote": remote_health_check(settings.remote_health_url),
        },
        "database": {
            "status": "ok" if db_count >= 0 else "warning",
            "url": settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
            "sqlite": file_status(sqlite_db_path()),
            "persistent_copy": file_status(sqlite_persistent_copy_path()),
        },
        "email": {
            "mode": email_config.delivery_mode,
            "enabled": email_config.enabled,
            "sender": email_config.sender_email,
            "outbox": file_status(Path(settings.outbox_dir)),
            "last_status": email_logs[0].status if email_logs else "not used",
        },
        "auth": {
            "entra_enabled": settings.entra_auth_enabled,
            "role": current_user.role,
            "user": current_user.username,
            "admin_group_configured": bool(settings.entra_admin_group_id),
            "standard_group_configured": bool(settings.entra_standard_group_id),
        },
        "sources_health": {
            "total": len(sources),
            "active": sum(1 for item in sources if item.active),
            "failures": len(source_failures),
            "last_checked": source_snapshots[0].checked_at if source_snapshots else None,
        },
        "portal_health": {
            "portals": len(portals),
            "account_required": account_required,
            "enabled_connectors": sum(1 for item in connectors if item.enabled),
            "connector_failures": len(connector_failures),
            "open_tasks": sum(1 for item in tasks if normalise_status(item.status) in TASK_OPEN_STATUSES),
        },
        "kra": kra_runtime_status(),
        "recent_retrieval_runs": retrieval_runs[:8],
        "recent_source_snapshots": source_snapshots[:8],
        "recent_email_logs": email_logs,
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": get_settings().app_name}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(8)))
    findings = list(session.exec(select(KRAFinding).order_by(col(KRAFinding.created_at).desc()).limit(6)))
    snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(5)))
    news_items = list(session.exec(select(NewsFeedItem).order_by(col(NewsFeedItem.published_at).desc()).limit(6)))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context(
            request,
            metrics=dashboard_metrics(session),
            opportunities=opportunities,
            findings=findings,
            snapshots=snapshots,
            news_items=news_items,
            **reference_context(session),
        ),
    )


@app.post("/news/refresh")
def refresh_news(session: Session = Depends(get_session)):
    refresh_news_feeds(session)
    return redirect("/")


@app.get("/workflow", response_class=HTMLResponse)
def workflow(request: Request, session: Session = Depends(get_session)):
    workflow_rules = load_rule_file("workflow.yml")
    opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(5)))
    recent_runs = list(session.exec(select(PortalRetrievalRun).order_by(col(PortalRetrievalRun.started_at).desc()).limit(5)))
    return templates.TemplateResponse(
        request,
        "workflow.html",
        context(
            request,
            workflow=workflow_rules,
            metrics=dashboard_metrics(session),
            portal_metrics=portal_workbench_context(session)["portal_metrics"],
            recent_opportunities=opportunities,
            recent_retrieval_runs=recent_runs,
            **reference_context(session),
        ),
    )


@app.get("/review", response_class=HTMLResponse)
def review_queue(request: Request, session: Session = Depends(get_session)):
    opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(200)))
    return templates.TemplateResponse(
        request,
        "review.html",
        context(request, opportunities=opportunities, **reference_context(session)),
    )


@app.post("/opportunities/{opportunity_id}/review")
async def update_opportunity_review(opportunity_id: int, request: Request, session: Session = Depends(get_session)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/review")
    form = await request.form()
    errors: list[str] = []
    action = str(form.get("action") or "").strip()
    allowed = {"approve": "approved", "reject": "rejected", "reassign": "pending_review", "hold": "pending_review"}
    if action not in allowed:
        errors.append("Review action must be approve, reject, reassign or hold.")
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    if errors:
        return validation_error_response(errors, "/review")
    before = compact_snapshot(opportunity)
    opportunity.status = allowed[action]
    if action == "reassign":
        opportunity.customer_id = customer_id
        opportunity.business_unit_id = business_unit_id
    opportunity.relevance_rationale = str(form.get("review_notes") or opportunity.relevance_rationale or "")
    session.add(opportunity)
    log_event(
        session,
        entity_type="Opportunity",
        entity_id=opportunity.id,
        action=f"review_{action}",
        summary=f"Review action {action} for {opportunity.title}",
        before=before,
        after=opportunity,
    )
    session.commit()
    return redirect("/review")


@app.get("/client-portal", response_class=HTMLResponse)
def client_portal(request: Request, session: Session = Depends(get_session)):
    opportunities = list(session.exec(select(Opportunity).where(Opportunity.status == "approved").order_by(col(Opportunity.updated_at).desc()).limit(100)))
    all_opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(300)))
    interests = list(session.exec(select(ClientInterestSignal).order_by(col(ClientInterestSignal.created_at).desc()).limit(100)))
    return templates.TemplateResponse(
        request,
        "client_portal.html",
        context(request, opportunities=opportunities, all_opportunities=all_opportunities, interests=interests, **reference_context(session)),
    )


@app.post("/client-portal/interests")
async def create_interest_signal(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/client-portal")
    signal = ClientInterestSignal(
        opportunity_id=opportunity_id,
        customer_id=customer_id,
        contact_name=str(form.get("contact_name") or ""),
        contact_email=str(form.get("contact_email") or ""),
        signal=str(form.get("signal") or "interested"),
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, signal, "create", "Created client interest signal")
    return redirect("/client-portal")


@app.post("/client-portal/interests/{signal_id}")
async def update_interest_signal(signal_id: int, request: Request, session: Session = Depends(get_session)):
    signal = session.get(ClientInterestSignal, signal_id)
    if not signal:
        return redirect("/client-portal")
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/client-portal")
    before = compact_snapshot(signal)
    signal.opportunity_id = opportunity_id
    signal.customer_id = customer_id
    signal.contact_name = str(form.get("contact_name") or "")
    signal.contact_email = str(form.get("contact_email") or "")
    signal.signal = str(form.get("signal") or "interested")
    signal.status = str(form.get("status") or "new")
    signal.notes = str(form.get("notes") or "")
    update_with_audit(session, signal, "Updated client interest signal", before)
    return redirect("/client-portal")


@app.post("/client-portal/interests/{signal_id}/delete")
def delete_interest_signal(signal_id: int, session: Session = Depends(get_session)):
    signal = session.get(ClientInterestSignal, signal_id)
    if not signal:
        return redirect("/client-portal")
    delete_with_audit(session, signal, "Deleted client interest signal")
    return redirect("/client-portal")


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    email_config = get_email_configuration(session)
    email_logs = list(session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc()).limit(50)))
    return templates.TemplateResponse(
        request,
        "admin.html",
        context(
            request,
            email_config=email_config,
            email_logs=email_logs,
            health=health_dashboard_context(session, request),
            **reference_context(session),
        ),
    )


@app.post("/admin/email")
async def update_email_configuration(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    config = get_email_configuration(session)
    smtp_port = parse_optional_int(form.get("smtp_port"), "SMTP port", errors) or 587
    if errors:
        return validation_error_response(errors, "/admin")
    before = compact_snapshot(config)
    config.profile_name = str(form.get("profile_name") or "Default local profile")
    config.delivery_mode = str(form.get("delivery_mode") or "file_outbox")
    config.smtp_host = str(form.get("smtp_host") or "")
    config.smtp_port = smtp_port
    config.smtp_username = str(form.get("smtp_username") or "")
    password = str(form.get("smtp_password") or "")
    if password:
        config.smtp_password = password
    config.use_tls = parse_bool(form.get("use_tls"))
    config.enabled = parse_bool(form.get("enabled"))
    config.sender_name = str(form.get("sender_name") or "Data Intelligence Portal")
    config.sender_email = str(form.get("sender_email") or "no-reply@local.test")
    config.default_recipients = str(form.get("default_recipients") or "")
    config.notes = str(form.get("notes") or "")
    session.add(config)
    log_event(session, entity_type="EmailConfiguration", entity_id=config.id, action="update", summary="Updated email configuration", before=before, after=config)
    session.commit()
    return redirect("/admin")


@app.post("/admin/email/test")
async def send_test_email(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    config = get_email_configuration(session)
    recipients = split_recipients(str(form.get("recipients") or config.default_recipients))
    if not recipients:
        return validation_error_response(["At least one recipient is required for a test email."], "/admin")
    send_or_store_email(
        session,
        config,
        recipients=recipients,
        subject=str(form.get("subject") or "Data Intelligence Portal test email"),
        body=str(form.get("message") or "This is a local MVP email configuration test."),
        sender_name=str(form.get("sender_name") or config.sender_name),
        sender_email=str(form.get("sender_email") or config.sender_email),
    )
    return redirect("/admin")


@app.get("/customers", response_class=HTMLResponse)
def customers(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "customers.html", context(request, **reference_context(session)))


@app.post("/customers")
async def create_customer(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("customer_name") or "").strip()
    if not name:
        errors.append("Customer name is required.")
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    if errors:
        return validation_error_response(errors, "/customers")
    customer = Customer(
        customer_name=name,
        business_unit_id=business_unit_id,
        sector=str(form.get("sector") or "Public sector"),
        domain=str(form.get("domain") or ""),
        customer_type=str(form.get("customer_type") or ""),
        region=str(form.get("region") or "UK"),
        buying_entities=str(form.get("buying_entities") or ""),
        aliases=str(form.get("aliases") or ""),
        strategic_notes=str(form.get("strategic_notes") or ""),
        portal_notes=str(form.get("portal_notes") or ""),
    )
    save_with_audit(session, customer, "create", f"Created customer {customer.customer_name}")
    return redirect("/customers")


@app.post("/customers/{customer_id}")
async def update_customer(customer_id: int, request: Request, session: Session = Depends(get_session)):
    customer = session.get(Customer, customer_id)
    if not customer:
        return redirect("/customers")
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("customer_name") or "").strip()
    if not name:
        errors.append("Customer name is required.")
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    if errors:
        return validation_error_response(errors, "/customers")
    before = compact_snapshot(customer)
    customer.customer_name = name
    customer.business_unit_id = business_unit_id
    customer.sector = str(form.get("sector") or "Public sector")
    customer.domain = str(form.get("domain") or "")
    customer.customer_type = str(form.get("customer_type") or "")
    customer.region = str(form.get("region") or "UK")
    customer.buying_entities = str(form.get("buying_entities") or "")
    customer.aliases = str(form.get("aliases") or "")
    customer.strategic_notes = str(form.get("strategic_notes") or "")
    customer.portal_notes = str(form.get("portal_notes") or "")
    update_with_audit(session, customer, f"Updated customer {customer.customer_name}", before)
    return redirect("/customers")


@app.post("/customers/{customer_id}/delete")
def delete_customer(customer_id: int, session: Session = Depends(get_session)):
    customer = session.get(Customer, customer_id)
    if not customer:
        return redirect("/customers")
    clear_links(session, CustomerWatchProfile, "customer_id", customer.id)
    clear_links(session, BuyerPortalInstance, "customer_id", customer.id)
    clear_links(session, Opportunity, "customer_id", customer.id)
    clear_links(session, ClientInterestSignal, "customer_id", customer.id)
    clear_links(session, ExtractedRequirement, "customer_id", customer.id)
    clear_links(session, KRAResearchRun, "customer_id", customer.id)
    clear_links(session, KRAFinding, "customer_id", customer.id)
    delete_with_audit(session, customer, f"Deleted customer {customer.customer_name}")
    return redirect("/customers")


@app.get("/sources", response_class=HTMLResponse)
def sources(request: Request, session: Session = Depends(get_session)):
    snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(100)))
    return templates.TemplateResponse(request, "sources.html", context(request, snapshots=snapshots, **reference_context(session)))


@app.post("/sources/{source_id}/check")
def check_source(source_id: int, session: Session = Depends(get_session)):
    try:
        run_source_check(session, source_id)
    except ValueError as exc:
        return validation_error_response([str(exc)], "/sources")
    return redirect("/sources")


@app.post("/sources")
async def create_source(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("name") or "").strip()
    query_url = str(form.get("query_url") or "").strip()
    if not name:
        errors.append("Source name is required.")
    if not query_url:
        errors.append("Query URL is required.")
    elif not source_allowed(query_url):
        errors.append("Query URL must be HTTPS and on the approved source allow-list.")
    if errors:
        return validation_error_response(errors, "/sources")
    source = ProcurementSource(
        name=name,
        source_key=str(form.get("source_key") or ""),
        source_family=str(form.get("source_family") or "official_notice"),
        source_type=str(form.get("source_type") or "web_page"),
        base_url=str(form.get("base_url") or query_url),
        query_url=query_url,
        official=parse_bool(form.get("official")) if form.get("official") is not None else True,
        active=parse_bool(form.get("active")) if form.get("active") is not None else True,
        coverage=str(form.get("coverage") or ""),
        data_format=str(form.get("data_format") or ""),
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, source, "create", f"Created source {source.name}")
    return redirect("/sources")


@app.post("/sources/{source_id}")
async def update_source(source_id: int, request: Request, session: Session = Depends(get_session)):
    source = session.get(ProcurementSource, source_id)
    if not source:
        return redirect("/sources")
    form = await request.form()
    errors: list[str] = []
    name = str(form.get("name") or "").strip()
    query_url = str(form.get("query_url") or "").strip()
    if not name:
        errors.append("Source name is required.")
    if not query_url:
        errors.append("Query URL is required.")
    elif not source_allowed(query_url):
        errors.append("Query URL must be HTTPS and on the approved source allow-list.")
    if errors:
        return validation_error_response(errors, "/sources")
    before = compact_snapshot(source)
    source.name = name
    source.source_key = str(form.get("source_key") or source.source_key or "")
    source.source_family = str(form.get("source_family") or source.source_family or "official_notice")
    source.source_type = str(form.get("source_type") or "web_page")
    source.base_url = str(form.get("base_url") or query_url)
    source.query_url = query_url
    source.official = parse_bool(form.get("official"))
    source.active = parse_bool(form.get("active"))
    source.coverage = str(form.get("coverage") or "")
    source.data_format = str(form.get("data_format") or "")
    source.connector_status = str(form.get("connector_status") or source.connector_status or "configured")
    source.notes = str(form.get("notes") or "")
    update_with_audit(session, source, f"Updated source {source.name}", before)
    return redirect("/sources")


@app.post("/sources/{source_id}/delete")
def delete_source(source_id: int, session: Session = Depends(get_session)):
    source = session.get(ProcurementSource, source_id)
    if not source:
        return redirect("/sources")
    clear_links(session, SourceCheckSnapshot, "source_id", source.id)
    clear_links(session, Opportunity, "source_id", source.id)
    clear_links(session, KRAResearchRun, "source_id", source.id)
    clear_links(session, KRAFinding, "source_id", source.id)
    delete_with_audit(session, source, f"Deleted source {source.name}")
    return redirect("/sources")


@app.get("/opportunities", response_class=HTMLResponse)
def opportunities(request: Request, session: Session = Depends(get_session)):
    items = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(200)))
    documents = list(session.exec(select(OpportunityDocument)))
    doc_counts: dict[int, int] = {}
    for doc in documents:
        doc_counts[doc.opportunity_id] = doc_counts.get(doc.opportunity_id, 0) + 1
    return templates.TemplateResponse(request, "opportunities.html", context(request, opportunities=items, doc_counts=doc_counts, **reference_context(session)))


@app.post("/opportunities")
async def create_opportunity(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    title = str(form.get("title") or "").strip()
    if not title:
        errors.append("Opportunity title is required.")
    source_id = parse_optional_int(form.get("source_id"), "Source", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    deadline_date = parse_optional_date(form.get("deadline_date"), "Deadline date", errors)
    value_high = parse_float(form.get("value_high"), "Value high", errors, default=0)
    relevance_score = parse_float(form.get("relevance_score"), "Relevance score", errors, default=0)
    if errors:
        return validation_error_response(errors, "/opportunities")
    opportunity = Opportunity(
        title=title,
        source_id=source_id,
        customer_id=customer_id,
        business_unit_id=business_unit_id,
        buyer_name=str(form.get("buyer_name") or ""),
        notice_identifier=str(form.get("notice_identifier") or ""),
        notice_type=str(form.get("notice_type") or ""),
        procurement_stage=str(form.get("procurement_stage") or ""),
        deadline_date=deadline_date,
        value_high=value_high,
        cpv_codes=str(form.get("cpv_codes") or ""),
        location=str(form.get("location") or ""),
        source_url=str(form.get("source_url") or ""),
        summary=str(form.get("summary") or ""),
        status=str(form.get("status") or "new"),
        relevance_score=relevance_score,
        relevance_rationale=str(form.get("relevance_rationale") or ""),
    )
    save_with_audit(session, opportunity, "create", f"Created opportunity {opportunity.title}")
    return redirect("/opportunities")


@app.post("/opportunities/{opportunity_id}")
async def update_opportunity(opportunity_id: int, request: Request, session: Session = Depends(get_session)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    form = await request.form()
    errors: list[str] = []
    title = str(form.get("title") or "").strip()
    if not title:
        errors.append("Opportunity title is required.")
    source_id = parse_optional_int(form.get("source_id"), "Source", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    deadline_date = parse_optional_date(form.get("deadline_date"), "Deadline date", errors)
    value_high = parse_float(form.get("value_high"), "Value high", errors, default=0)
    relevance_score = parse_float(form.get("relevance_score"), "Relevance score", errors, default=0)
    if errors:
        return validation_error_response(errors, "/opportunities")
    before = compact_snapshot(opportunity)
    opportunity.title = title
    opportunity.source_id = source_id
    opportunity.customer_id = customer_id
    opportunity.business_unit_id = business_unit_id
    opportunity.buyer_name = str(form.get("buyer_name") or "")
    opportunity.notice_identifier = str(form.get("notice_identifier") or "")
    opportunity.notice_type = str(form.get("notice_type") or "")
    opportunity.procurement_stage = str(form.get("procurement_stage") or "")
    opportunity.deadline_date = deadline_date
    opportunity.value_high = value_high
    opportunity.cpv_codes = str(form.get("cpv_codes") or "")
    opportunity.location = str(form.get("location") or "")
    opportunity.source_url = str(form.get("source_url") or "")
    opportunity.summary = str(form.get("summary") or "")
    opportunity.status = str(form.get("status") or "new")
    opportunity.relevance_score = relevance_score
    opportunity.relevance_rationale = str(form.get("relevance_rationale") or "")
    opportunity.updated_at = utc_now()
    update_with_audit(session, opportunity, f"Updated opportunity {opportunity.title}", before)
    return redirect("/opportunities")


@app.post("/opportunities/{opportunity_id}/delete")
def delete_opportunity(opportunity_id: int, session: Session = Depends(get_session)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    delete_children(session, ExtractedQualityQuestion, "opportunity_id", opportunity.id)
    delete_children(session, OpportunityDocument, "opportunity_id", opportunity.id)
    delete_children(session, DocumentRetrievalTask, "opportunity_id", opportunity.id)
    clear_links(session, PortalInformationConnector, "default_opportunity_id", opportunity.id)
    clear_links(session, PortalRetrievalRun, "opportunity_id", opportunity.id)
    clear_links(session, ClientInterestSignal, "opportunity_id", opportunity.id)
    clear_links(session, ExtractedRequirement, "opportunity_id", opportunity.id)
    clear_links(session, KRAFinding, "opportunity_id", opportunity.id)
    clear_links(session, KRAResearchRun, "opportunity_id", opportunity.id)
    delete_with_audit(session, opportunity, f"Deleted opportunity {opportunity.title}")
    return redirect("/opportunities")


@app.get("/opportunities/{opportunity_id}/documents", response_class=HTMLResponse)
def opportunity_documents(opportunity_id: int, request: Request, session: Session = Depends(get_session)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    documents = list(session.exec(select(OpportunityDocument).where(OpportunityDocument.opportunity_id == opportunity_id)))
    questions = list(session.exec(select(ExtractedQualityQuestion).where(ExtractedQualityQuestion.opportunity_id == opportunity_id)))
    tasks = list(session.exec(select(DocumentRetrievalTask).where(DocumentRetrievalTask.opportunity_id == opportunity_id)))
    return templates.TemplateResponse(
        request,
        "documents.html",
        context(
            request,
            opportunity=opportunity,
            documents=documents,
            questions=questions,
            tasks=tasks,
            task_status_options=["requested", "in_progress", "blocked", "review_required", "completed"],
            **reference_context(session),
        ),
    )


@app.post("/opportunities/{opportunity_id}/documents")
async def create_document(opportunity_id: int, request: Request, session: Session = Depends(get_session)):
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity:
        return redirect("/opportunities")
    form = await request.form()
    title = str(form.get("title") or "").strip()
    if not title:
        return validation_error_response(["Document title is required."], f"/opportunities/{opportunity_id}/documents")
    document = OpportunityDocument(
        opportunity_id=opportunity_id,
        title=title,
        document_type=str(form.get("document_type") or "itt_extract"),
        url_or_path=str(form.get("url_or_path") or ""),
        retrieval_status=str(form.get("retrieval_status") or "linked"),
        platform_name=str(form.get("platform_name") or ""),
        content_summary=str(form.get("content_summary") or ""),
        notes=str(form.get("notes") or ""),
    )
    session.add(document)
    session.flush()
    log_event(session, entity_type="OpportunityDocument", entity_id=document.id, action="create", summary=f"Created document {document.title}", after=document)
    extract_document_intelligence(session, opportunity, document, str(form.get("document_text") or ""))
    session.commit()
    return redirect(f"/opportunities/{opportunity_id}/documents")


@app.post("/opportunities/{opportunity_id}/documents/{document_id}")
async def update_document(opportunity_id: int, document_id: int, request: Request, session: Session = Depends(get_session)):
    document = session.get(OpportunityDocument, document_id)
    if not document or document.opportunity_id != opportunity_id:
        return redirect(f"/opportunities/{opportunity_id}/documents")
    form = await request.form()
    title = str(form.get("title") or "").strip()
    if not title:
        return validation_error_response(["Document title is required."], f"/opportunities/{opportunity_id}/documents")
    before = compact_snapshot(document)
    document.title = title
    document.document_type = str(form.get("document_type") or "itt_extract")
    document.url_or_path = str(form.get("url_or_path") or "")
    document.retrieval_status = str(form.get("retrieval_status") or "linked")
    document.human_review_status = str(form.get("human_review_status") or document.human_review_status or "pending")
    document.platform_name = str(form.get("platform_name") or "")
    document.content_summary = str(form.get("content_summary") or "")
    document.notes = str(form.get("notes") or "")
    update_with_audit(session, document, f"Updated document {document.title}", before)
    return redirect(f"/opportunities/{opportunity_id}/documents")


@app.post("/opportunities/{opportunity_id}/documents/{document_id}/delete")
def delete_document(opportunity_id: int, document_id: int, session: Session = Depends(get_session)):
    document = session.get(OpportunityDocument, document_id)
    if not document or document.opportunity_id != opportunity_id:
        return redirect(f"/opportunities/{opportunity_id}/documents")
    delete_children(session, ExtractedQualityQuestion, "document_id", document.id)
    delete_with_audit(session, document, f"Deleted document {document.title}")
    return redirect(f"/opportunities/{opportunity_id}/documents")


@app.post("/opportunities/{opportunity_id}/tasks")
async def create_document_task(opportunity_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    portal_id = parse_optional_int(form.get("portal_instance_id"), "Portal instance", errors)
    due_date = parse_optional_date(form.get("due_date"), "Due date", errors)
    if errors:
        return validation_error_response(errors, f"/opportunities/{opportunity_id}/documents")
    task = DocumentRetrievalTask(
        opportunity_id=opportunity_id,
        portal_instance_id=portal_id,
        task_name=str(form.get("task_name") or "Manual portal document retrieval"),
        status=str(form.get("status") or "requested"),
        due_date=due_date,
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, task, "create", f"Created document retrieval task {task.task_name}")
    return redirect(f"/opportunities/{opportunity_id}/documents")


@app.post("/tasks/{task_id}")
async def update_task(task_id: int, request: Request, session: Session = Depends(get_session)):
    task = session.get(DocumentRetrievalTask, task_id)
    if not task:
        return redirect("/portals")
    form = await request.form()
    errors: list[str] = []
    portal_id = parse_optional_int(form.get("portal_instance_id"), "Portal instance", errors)
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    due_date = parse_optional_date(form.get("due_date"), "Due date", errors)
    return_to = str(form.get("return_to") or "/portals")
    task_name = str(form.get("task_name") or "").strip()
    if not task_name:
        errors.append("Task name is required.")
    if errors:
        return validation_error_response(errors, return_to)
    before = compact_snapshot(task)
    task.task_name = task_name
    task.opportunity_id = opportunity_id
    task.portal_instance_id = portal_id
    task.status = str(form.get("status") or "requested")
    task.owner = str(form.get("owner") or "local-user")
    task.due_date = due_date
    task.notes = str(form.get("notes") or "")
    update_with_audit(session, task, f"Updated retrieval task {task.task_name}", before)
    return redirect(return_to)


@app.post("/tasks/{task_id}/delete")
async def delete_task(task_id: int, request: Request, session: Session = Depends(get_session)):
    task = session.get(DocumentRetrievalTask, task_id)
    form = await request.form()
    return_to = str(form.get("return_to") or "/portals")
    if not task:
        return redirect(return_to)
    delete_with_audit(session, task, f"Deleted retrieval task {task.task_name}")
    return redirect(return_to)


@app.get("/portals", response_class=HTMLResponse)
def portals(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request,
        "portals.html",
        context(request, **reference_context(session), **portal_workbench_context(session)),
    )


@app.post("/portals")
async def create_portal(request: Request, session: Session = Depends(get_session)):
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


@app.post("/portals/{portal_id}")
async def update_portal(portal_id: int, request: Request, session: Session = Depends(get_session)):
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


@app.post("/portals/{portal_id}/delete")
def delete_portal(portal_id: int, session: Session = Depends(get_session)):
    portal = session.get(BuyerPortalInstance, portal_id)
    if not portal:
        return redirect("/portals")
    clear_links(session, DocumentRetrievalTask, "portal_instance_id", portal.id)
    clear_links(session, PortalInformationConnector, "portal_instance_id", portal.id)
    clear_links(session, PortalRetrievalRun, "portal_instance_id", portal.id)
    delete_with_audit(session, portal, f"Deleted portal {portal.portal_name}")
    return redirect("/portals")


@app.post("/portal-connectors")
async def create_portal_connector(request: Request, session: Session = Depends(get_session)):
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


@app.post("/portal-connectors/{connector_id}")
async def update_portal_connector(connector_id: int, request: Request, session: Session = Depends(get_session)):
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


@app.post("/portal-connectors/{connector_id}/delete")
def delete_portal_connector(connector_id: int, session: Session = Depends(get_session)):
    connector = session.get(PortalInformationConnector, connector_id)
    if not connector:
        return redirect("/portals")
    clear_links(session, PortalRetrievalRun, "connector_id", connector.id)
    delete_with_audit(session, connector, f"Deleted portal retrieval connector {connector.connector_name}")
    return redirect("/portals")


@app.post("/portal-connectors/{connector_id}/run")
def run_single_portal_connector(connector_id: int, session: Session = Depends(get_session)):
    try:
        run_portal_connector(session, connector_id)
    except ValueError as exc:
        return validation_error_response([str(exc)], "/portals")
    return redirect("/portals")


@app.post("/portal-connectors/run-all")
def run_all_portal_connectors(session: Session = Depends(get_session)):
    run_enabled_portal_connectors(session)
    return redirect("/portals")


@app.post("/portals/{portal_id}/tasks")
async def create_portal_task(portal_id: int, request: Request, session: Session = Depends(get_session)):
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


@app.get("/requirements", response_class=HTMLResponse)
def requirements(request: Request, session: Session = Depends(get_session)):
    reqs = list(session.exec(select(ExtractedRequirement).order_by(col(ExtractedRequirement.created_at).desc()).limit(300)))
    questions = list(session.exec(select(ExtractedQualityQuestion).order_by(col(ExtractedQualityQuestion.created_at).desc()).limit(300)))
    opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(300)))
    documents = list(session.exec(select(OpportunityDocument).order_by(col(OpportunityDocument.extracted_at).desc()).limit(300)))
    return templates.TemplateResponse(
        request,
        "requirements.html",
        context(request, requirements=reqs, questions=questions, opportunities=opportunities, documents=documents, **reference_context(session)),
    )


@app.post("/requirements")
async def create_requirement(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    theme = str(form.get("requirement_theme") or "").strip()
    text = str(form.get("requirement_text") or "").strip()
    if not theme or not text:
        errors.append("Requirement theme and text are required.")
    if errors:
        return validation_error_response(errors, "/requirements")
    requirement = ExtractedRequirement(
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        requirement_theme=theme,
        requirement_text=text,
        requirement_source=str(form.get("requirement_source") or ""),
        confidence=str(form.get("confidence") or "medium"),
        human_review_status=str(form.get("human_review_status") or "pending"),
    )
    save_with_audit(session, requirement, "create", f"Created requirement {requirement.requirement_theme}")
    return redirect("/requirements")


@app.post("/requirements/{requirement_id}")
async def update_requirement(requirement_id: int, request: Request, session: Session = Depends(get_session)):
    requirement = session.get(ExtractedRequirement, requirement_id)
    if not requirement:
        return redirect("/requirements")
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    theme = str(form.get("requirement_theme") or "").strip()
    text = str(form.get("requirement_text") or "").strip()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    if not theme or not text:
        errors.append("Requirement theme and text are required.")
    if errors:
        return validation_error_response(errors, return_to)
    before = compact_snapshot(requirement)
    requirement.customer_id = customer_id
    requirement.opportunity_id = opportunity_id
    requirement.requirement_theme = theme
    requirement.requirement_text = text
    requirement.requirement_source = str(form.get("requirement_source") or "")
    requirement.confidence = str(form.get("confidence") or "medium")
    requirement.human_review_status = str(form.get("human_review_status") or "pending")
    update_with_audit(session, requirement, f"Updated requirement {requirement.requirement_theme}", before)
    return redirect(return_to)


@app.post("/requirements/{requirement_id}/delete")
async def delete_requirement(requirement_id: int, request: Request, session: Session = Depends(get_session)):
    requirement = session.get(ExtractedRequirement, requirement_id)
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    if not requirement:
        return redirect(return_to)
    delete_with_audit(session, requirement, f"Deleted requirement {requirement.requirement_theme}")
    return redirect(return_to)


@app.post("/quality-questions")
async def create_quality_question(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors)
    document_id = parse_optional_int(form.get("document_id"), "Document", errors)
    text = str(form.get("question_text") or "").strip()
    if opportunity_id is None:
        errors.append("Opportunity is required for a quality question.")
    if not text:
        errors.append("Question text is required.")
    if errors:
        return validation_error_response(errors, "/requirements")
    question = ExtractedQualityQuestion(
        opportunity_id=opportunity_id,
        document_id=document_id,
        section_reference=str(form.get("section_reference") or ""),
        question_text=text,
        weighting=str(form.get("weighting") or ""),
        requirement_theme=str(form.get("requirement_theme") or ""),
        confidence=str(form.get("confidence") or "medium"),
        human_review_status=str(form.get("human_review_status") or "pending"),
    )
    save_with_audit(session, question, "create", "Created quality question")
    return redirect("/requirements")


@app.post("/quality-questions/{question_id}")
async def update_quality_question(question_id: int, request: Request, session: Session = Depends(get_session)):
    question = session.get(ExtractedQualityQuestion, question_id)
    if not question:
        return redirect("/requirements")
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    text = str(form.get("question_text") or "").strip()
    if not text:
        return validation_error_response(["Question text is required."], return_to)
    errors: list[str] = []
    opportunity_id = parse_optional_int(form.get("opportunity_id"), "Opportunity", errors) or question.opportunity_id
    document_id = parse_optional_int(form.get("document_id"), "Document", errors)
    if errors:
        return validation_error_response(errors, return_to)
    before = compact_snapshot(question)
    question.opportunity_id = opportunity_id
    question.document_id = document_id
    question.section_reference = str(form.get("section_reference") or "")
    question.question_text = text
    question.weighting = str(form.get("weighting") or "")
    question.requirement_theme = str(form.get("requirement_theme") or "")
    question.confidence = str(form.get("confidence") or "medium")
    question.human_review_status = str(form.get("human_review_status") or "pending")
    update_with_audit(session, question, "Updated quality question", before)
    return redirect(return_to)


@app.post("/quality-questions/{question_id}/delete")
async def delete_quality_question(question_id: int, request: Request, session: Session = Depends(get_session)):
    question = session.get(ExtractedQualityQuestion, question_id)
    form = await request.form()
    return_to = str(form.get("return_to") or "/requirements")
    if not question:
        return redirect(return_to)
    delete_with_audit(session, question, "Deleted quality question")
    return redirect(return_to)


@app.get("/kra", response_class=HTMLResponse)
def kra(request: Request, session: Session = Depends(get_session)):
    runs = list(session.exec(select(KRAResearchRun).order_by(col(KRAResearchRun.started_at).desc()).limit(100)))
    findings = list(session.exec(select(KRAFinding).order_by(col(KRAFinding.created_at).desc()).limit(200)))
    return templates.TemplateResponse(request, "kra.html", context(request, runs=runs, findings=findings, **reference_context(session)))


@app.post("/kra/run")
async def run_kra(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    agent_id = parse_optional_int(form.get("agent_profile_id"), "Agent", errors)
    source_id = parse_optional_int(form.get("source_id"), "Source", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/kra")
    run_kra_research(session, agent_profile_id=agent_id, source_id=source_id, customer_id=customer_id, query=str(form.get("query") or ""))
    return redirect("/kra")


@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request, session: Session = Depends(get_session)):
    items = list(session.exec(select(IntelligenceReport).order_by(col(IntelligenceReport.generated_at).desc())))
    return templates.TemplateResponse(request, "reports.html", context(request, reports=items, **reference_context(session)))


@app.post("/reports")
async def create_intelligence_report(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    name = str(form.get("report_name") or "Data intelligence summary").strip()
    if errors:
        return validation_error_response(errors, "/reports")
    if parse_bool(form.get("auto_retrieve")):
        run_enabled_portal_connectors(session, customer_id=customer_id, business_unit_id=business_unit_id)
    report = create_report(session, name, str(form.get("report_type") or "executive_summary"), customer_id, business_unit_id)
    return redirect(f"/reports/{report.id}")


@app.post("/reports/{report_id}/update")
async def update_report(report_id: int, request: Request, session: Session = Depends(get_session)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    form = await request.form()
    errors: list[str] = []
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    business_unit_id = parse_optional_int(form.get("business_unit_id"), "Business unit", errors)
    name = str(form.get("report_name") or "").strip()
    if not name:
        errors.append("Report name is required.")
    if errors:
        return validation_error_response(errors, f"/reports/{report_id}")
    before = compact_snapshot(report)
    report.report_name = name
    report.report_type = str(form.get("report_type") or "executive_summary")
    report.customer_id = customer_id
    report.business_unit_id = business_unit_id
    report.markdown = str(form.get("markdown") or report.markdown or "")
    update_with_audit(session, report, f"Updated report {report.report_name}", before)
    return redirect(f"/reports/{report.id}")


@app.post("/reports/{report_id}/delete")
def delete_report(report_id: int, session: Session = Depends(get_session)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    clear_links(session, EmailDeliveryLog, "report_id", report.id)
    delete_with_audit(session, report, f"Deleted report {report.report_name}")
    return redirect("/reports")


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(report_id: int, request: Request, format: str | None = None, session: Session = Depends(get_session)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    if format in {"md", "html", "json", "txt"}:
        payload, media_type, filename = report_export(report, format)
        return Response(payload, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    email_config = get_email_configuration(session)
    return templates.TemplateResponse(request, "report_detail.html", context(request, report=report, email_config=email_config, **reference_context(session)))


@app.post("/reports/{report_id}/send-email")
async def send_report_email(report_id: int, request: Request, session: Session = Depends(get_session)):
    report = session.get(IntelligenceReport, report_id)
    if not report:
        return redirect("/reports")
    form = await request.form()
    config = get_email_configuration(session)
    recipients = split_recipients(str(form.get("recipients") or config.default_recipients))
    if not recipients:
        return validation_error_response(["Add at least one recipient before sending the report."], f"/reports/{report_id}")
    send_or_store_email(
        session,
        config,
        recipients=recipients,
        subject=str(form.get("subject") or report.report_name),
        body=str(form.get("message") or "Please find the attached Data Intelligence Portal report for review."),
        report=report,
        sender_name=str(form.get("sender_name") or config.sender_name),
        sender_email=str(form.get("sender_email") or config.sender_email),
        export_format=str(form.get("export_format") or "md"),
    )
    return redirect(f"/reports/{report_id}")


@app.get("/audit", response_class=HTMLResponse)
def audit(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    events = list(session.exec(select(AuditEvent).order_by(col(AuditEvent.created_at).desc()).limit(200)))
    return templates.TemplateResponse(request, "audit.html", context(request, events=events))
