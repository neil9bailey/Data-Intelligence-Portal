from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.database import engine, get_session, init_db
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
    ProcurementPlatform,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.reports import create_report
from app.rule_loader import load_rule_file, rules_version_summary
from app.seed import seed_demo_data, seed_reference_data
from app.settings import BASE_DIR, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    if settings.seed_reference_data:
        with Session(engine) as session:
            seed_reference_data(session)
    if settings.seed_demo_data:
        with Session(engine) as session:
            seed_demo_data(session)
    yield


app = FastAPI(title="Data Intelligence Portal", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def context(request: Request, **extra):
    base = {
        "request": request,
        "app_name": get_settings().app_name,
        "rules_versions": rules_version_summary(),
        "kra_runtime": kra_runtime_status(),
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


def reference_context(session: Session) -> dict:
    customers = list(session.exec(select(Customer).order_by(col(Customer.customer_name))))
    units = list(session.exec(select(BusinessUnit).order_by(col(BusinessUnit.name))))
    sources = list(session.exec(select(ProcurementSource).order_by(col(ProcurementSource.name))))
    platforms = list(session.exec(select(ProcurementPlatform).order_by(col(ProcurementPlatform.name))))
    portals = list(session.exec(select(BuyerPortalInstance).order_by(col(BuyerPortalInstance.portal_name))))
    agents = list(session.exec(select(KRAAgentProfile).order_by(col(KRAAgentProfile.name))))
    news_feeds = list(session.exec(select(NewsFeedSource).order_by(col(NewsFeedSource.name))))
    return {
        "customers": customers,
        "business_units": units,
        "sources": sources,
        "platforms": platforms,
        "portal_instances": portals,
        "agents": agents,
        "news_feeds": news_feeds,
        "customer_map": {item.id: item for item in customers},
        "business_unit_map": {item.id: item for item in units},
        "source_map": {item.id: item for item in sources},
        "platform_map": {item.id: item for item in platforms},
        "portal_map": {item.id: item for item in portals},
        "agent_map": {item.id: item for item in agents},
        "news_feed_map": {item.id: item for item in news_feeds},
    }


def dashboard_metrics(session: Session) -> dict:
    return {
        "customers": len(list(session.exec(select(Customer)))),
        "sources": len(list(session.exec(select(ProcurementSource)))),
        "active_sources": len(list(session.exec(select(ProcurementSource).where(ProcurementSource.active == True)))),  # noqa: E712
        "platforms": len(list(session.exec(select(ProcurementPlatform)))),
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


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": get_settings().app_name}


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
    return templates.TemplateResponse(
        request,
        "workflow.html",
        context(request, workflow=workflow_rules, metrics=dashboard_metrics(session), **reference_context(session)),
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
    interests = list(session.exec(select(ClientInterestSignal).order_by(col(ClientInterestSignal.created_at).desc()).limit(100)))
    return templates.TemplateResponse(
        request,
        "client_portal.html",
        context(request, opportunities=opportunities, interests=interests, **reference_context(session)),
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


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, session: Session = Depends(get_session)):
    email_config = get_email_configuration(session)
    email_logs = list(session.exec(select(EmailDeliveryLog).order_by(col(EmailDeliveryLog.created_at).desc()).limit(50)))
    return templates.TemplateResponse(
        request,
        "admin.html",
        context(request, email_config=email_config, email_logs=email_logs),
    )


@app.post("/admin/email")
async def update_email_configuration(request: Request, session: Session = Depends(get_session)):
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
async def send_test_email(request: Request, session: Session = Depends(get_session)):
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


@app.get("/opportunities", response_class=HTMLResponse)
def opportunities(request: Request, session: Session = Depends(get_session)):
    items = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(200)))
    documents = list(session.exec(select(OpportunityDocument)))
    doc_counts: dict[int, int] = {}
    for doc in documents:
        doc_counts[doc.opportunity_id] = doc_counts.get(doc.opportunity_id, 0) + 1
    return templates.TemplateResponse(request, "opportunities.html", context(request, opportunities=items, doc_counts=doc_counts, **reference_context(session)))


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
        context(request, opportunity=opportunity, documents=documents, questions=questions, tasks=tasks, **reference_context(session)),
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


@app.get("/portals", response_class=HTMLResponse)
def portals(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "portals.html", context(request, **reference_context(session)))


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
        access_status=str(form.get("access_status") or "unknown"),
        notes=str(form.get("notes") or ""),
    )
    save_with_audit(session, portal, "create", f"Created portal {portal.portal_name}")
    return redirect("/portals")


@app.get("/requirements", response_class=HTMLResponse)
def requirements(request: Request, session: Session = Depends(get_session)):
    reqs = list(session.exec(select(ExtractedRequirement).order_by(col(ExtractedRequirement.created_at).desc()).limit(300)))
    questions = list(session.exec(select(ExtractedQualityQuestion).order_by(col(ExtractedQualityQuestion.created_at).desc()).limit(300)))
    return templates.TemplateResponse(request, "requirements.html", context(request, requirements=reqs, questions=questions, **reference_context(session)))


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
    report = create_report(session, name, str(form.get("report_type") or "executive_summary"), customer_id, business_unit_id)
    return redirect(f"/reports/{report.id}")


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
def audit(request: Request, session: Session = Depends(get_session)):
    events = list(session.exec(select(AuditEvent).order_by(col(AuditEvent.created_at).desc()).limit(200)))
    return templates.TemplateResponse(request, "audit.html", context(request, events=events))
