from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import false, or_
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.access_scope import (
    interest_in_scope,
    scope_for_user,
    scoped_business_unit_statement,
    scoped_customer_statement,
    scoped_kra_finding_statement,
    scoped_opportunity_statement,
)
from app.auth import CurrentUser, get_current_user
from app.database import database_mode, sqlite_db_path, sqlite_persistent_copy_path
from app.email_service import get_email_configuration
from app.intelligence import kra_runtime_status
from app.models import (
    BusinessUnit,
    BuyerPortalInstance,
    ClientInterestSignal,
    Customer,
    DocumentRetrievalTask,
    EmailDeliveryLog,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    KRAAgentProfile,
    KRAFinding,
    NewsFeedItem,
    NewsFeedSource,
    Opportunity,
    OpportunityDocument,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementPlatform,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.requirement_taxonomy import requirement_categories
from app.rule_loader import rules_version_summary
from app.settings import BASE_DIR, get_settings


templates = Jinja2Templates(directory=BASE_DIR / "templates")
PAGE_SIZE = 10

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


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def page_url(request: Request, param: str, page: int) -> str:
    return str(request.url.include_query_params(**{param: page}))


def context(request: Request, **extra):
    settings = get_settings()
    base = {
        "request": request,
        "app_name": settings.app_name,
        "rules_versions": rules_version_summary(),
        "kra_runtime": kra_runtime_status(),
        "current_user": get_current_user(request),
        "entra_auth_enabled": settings.entra_auth_enabled,
        "page_url": page_url,
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
        "requirement_categories": sorted(requirement_categories().keys()),
    }


def scoped_reference_context(session: Session, user) -> dict:
    scope = scope_for_user(user)
    if not scope.restricted:
        return reference_context(session)

    customers = list(session.exec(scoped_customer_statement(user)))
    customer_unit_ids = {item.business_unit_id for item in customers if item.business_unit_id}
    unit_ids = set(scope.business_unit_ids) | customer_unit_ids
    units = (
        list(session.exec(select(BusinessUnit).where(col(BusinessUnit.id).in_(unit_ids)).order_by(col(BusinessUnit.name))))
        if unit_ids
        else []
    )
    opportunities = list(session.exec(scoped_opportunity_statement(user)))
    source_ids = {item.source_id for item in opportunities if item.source_id}

    sources = (
        list(session.exec(select(ProcurementSource).where(col(ProcurementSource.id).in_(source_ids)).order_by(col(ProcurementSource.name))))
        if source_ids
        else []
    )
    portals = []
    if scope.customer_ids or scope.business_unit_ids:
        portal_conditions = []
        if scope.customer_ids:
            portal_conditions.append(col(BuyerPortalInstance.customer_id).in_(scope.customer_ids))
        if scope.business_unit_ids:
            portal_conditions.append(col(BuyerPortalInstance.business_unit_id).in_(scope.business_unit_ids))
        portals = list(session.exec(select(BuyerPortalInstance).where(or_(*portal_conditions)).order_by(col(BuyerPortalInstance.portal_name))))

    portal_ids = {item.id for item in portals if item.id}
    connectors = (
        list(
            session.exec(
                select(PortalInformationConnector)
                .where(col(PortalInformationConnector.portal_instance_id).in_(portal_ids))
                .order_by(col(PortalInformationConnector.connector_name))
            )
        )
        if portal_ids
        else []
    )
    platforms = []
    platform_ids = {item.platform_id for item in portals if item.platform_id}
    if platform_ids:
        platforms = list(session.exec(select(ProcurementPlatform).where(col(ProcurementPlatform.id).in_(platform_ids)).order_by(col(ProcurementPlatform.name))))

    agents: list[KRAAgentProfile] = []
    news_feeds: list[NewsFeedSource] = []
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
        "agent_map": {},
        "news_feed_map": {},
        "requirement_categories": sorted(requirement_categories().keys()),
    }


def page_number(request: Request, param: str = "page") -> int:
    try:
        return max(1, int(request.query_params.get(param, "1")))
    except ValueError:
        return 1


def paged(session: Session, statement, request: Request, param: str = "page", page_size: int = PAGE_SIZE):
    page = page_number(request, param)
    rows = list(session.exec(statement.offset((page - 1) * page_size).limit(page_size + 1)))
    pagination = {
        "page": page,
        "param": param,
        "has_prev": page > 1,
        "prev_page": page - 1,
        "has_next": len(rows) > page_size,
        "next_page": page + 1,
    }
    return rows[:page_size], pagination


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


def scoped_dashboard_metrics(session: Session, user) -> dict:
    scope = scope_for_user(user)
    if not scope.restricted:
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
            "review_queue": len(list(session.exec(select(Opportunity).where(col(Opportunity.status).in_(["new", "pending_review", "matched", "needs_review"]))))),
            "client_interests": len(list(session.exec(select(ClientInterestSignal)))),
        }

    opportunities = list(session.exec(scoped_opportunity_statement(user)))
    opportunity_ids = [item.id for item in opportunities if item.id]
    source_ids = {item.source_id for item in opportunities if item.source_id}
    opportunity_map = {item.id: item for item in opportunities if item.id}

    requirements_statement = select(ExtractedRequirement)
    req_conditions = []
    if scope.customer_ids:
        req_conditions.append(col(ExtractedRequirement.customer_id).in_(scope.customer_ids))
    if opportunity_ids:
        req_conditions.append(col(ExtractedRequirement.opportunity_id).in_(opportunity_ids))
    requirements = list(session.exec(requirements_statement.where(or_(*req_conditions)) if req_conditions else requirements_statement.where(false())))

    questions_statement = select(ExtractedQualityQuestion)
    question_conditions = []
    if scope.customer_ids:
        question_conditions.append(col(ExtractedQualityQuestion.customer_id).in_(scope.customer_ids))
    if opportunity_ids:
        question_conditions.append(col(ExtractedQualityQuestion.opportunity_id).in_(opportunity_ids))
    questions = list(session.exec(questions_statement.where(or_(*question_conditions)) if question_conditions else questions_statement.where(false())))

    raw_interests = list(session.exec(select(ClientInterestSignal)))
    return {
        "customers": len(list(session.exec(scoped_customer_statement(user)))),
        "sources": len(source_ids),
        "active_sources": len(list(session.exec(select(ProcurementSource).where(col(ProcurementSource.id).in_(source_ids), ProcurementSource.active == True)))) if source_ids else 0,  # noqa: E712
        "platforms": len(list(session.exec(scoped_business_unit_statement(user)))),
        "portal_connectors": 0,
        "enabled_portal_connectors": 0,
        "opportunities": len(opportunities),
        "documents": len(list(session.exec(select(OpportunityDocument).where(col(OpportunityDocument.opportunity_id).in_(opportunity_ids))))) if opportunity_ids else 0,
        "requirements": len(requirements),
        "questions": len(questions),
        "pending_findings": len(list(session.exec(scoped_kra_finding_statement(user).where(KRAFinding.human_review_status == "pending")))),
        "source_changes": len(list(session.exec(select(SourceCheckSnapshot).where(col(SourceCheckSnapshot.source_id).in_(source_ids), SourceCheckSnapshot.change_type == "changed")))) if source_ids else 0,
        "news_items": 0,
        "review_queue": len([item for item in opportunities if normalise_status(item.status) in {"new", "pending_review", "matched", "needs_review"}]),
        "client_interests": len([item for item in raw_interests if interest_in_scope(item, user, opportunity_map)]),
    }


def dashboard_metrics(session: Session) -> dict:
    return scoped_dashboard_metrics(session, CurrentUser())


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


def latest_active_source_snapshots(sources: list[ProcurementSource], snapshots: list[SourceCheckSnapshot]) -> list[SourceCheckSnapshot]:
    active_ids = {source.id for source in sources if source.active and source.id}
    latest: list[SourceCheckSnapshot] = []
    seen: set[int] = set()
    for snapshot in snapshots:
        if snapshot.source_id not in active_ids or snapshot.source_id in seen:
            continue
        seen.add(snapshot.source_id)
        latest.append(snapshot)
    return latest


def health_dashboard_context(session: Session, request: Request) -> dict:
    settings = get_settings()
    db_count = len(list(session.exec(select(BusinessUnit)))) + len(list(session.exec(select(Customer))))
    sources = list(session.exec(select(ProcurementSource)))
    source_snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(200)))
    active_source_snapshots = latest_active_source_snapshots(sources, source_snapshots)
    connectors = list(session.exec(select(PortalInformationConnector)))
    retrieval_runs = list(session.exec(select(PortalRetrievalRun).order_by(col(PortalRetrievalRun.started_at).desc()).limit(20)))
    portals = list(session.exec(select(BuyerPortalInstance)))
    tasks = list(session.exec(select(DocumentRetrievalTask)))
    email_config = get_email_configuration(session)
    email_logs = list(session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc()).limit(10)))
    current_user = get_current_user(request)
    source_failures = [item for item in active_source_snapshots if item.change_type == "failed" or not item.ok]
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
            "mode": database_mode(),
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
            "last_checked": active_source_snapshots[0].checked_at if active_source_snapshots else None,
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
        "recent_source_snapshots": active_source_snapshots[:8],
        "recent_email_logs": email_logs,
    }
