from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.auth import require_admin, require_standard_or_admin
from app.database import get_session
from app.intelligence import refresh_news_feeds
from app.models import DocumentRetrievalTask, IntelligenceReport, KRAFinding, NewsFeedItem, Opportunity, PortalRetrievalRun, SourceCheckSnapshot
from app.route_utils import context, dashboard_metrics, portal_workbench_context, redirect, reference_context, templates
from app.rule_loader import load_rule_file
from app.automation import automation_steps


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session), _user=Depends(require_standard_or_admin)):
    opportunities = list(session.exec(select(Opportunity).order_by(col(Opportunity.updated_at).desc()).limit(8)))
    findings = list(session.exec(select(KRAFinding).order_by(col(KRAFinding.created_at).desc()).limit(6)))
    snapshots = list(session.exec(select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()).limit(5)))
    news_items = list(session.exec(select(NewsFeedItem).order_by(col(NewsFeedItem.published_at).desc()).limit(6)))
    reports = list(session.exec(select(IntelligenceReport).order_by(col(IntelligenceReport.generated_at).desc()).limit(4)))
    tasks = list(session.exec(select(DocumentRetrievalTask).order_by(col(DocumentRetrievalTask.created_at).desc()).limit(5)))
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
            reports=reports,
            tasks=tasks,
            workflow=load_rule_file("workflow.yml"),
            automation_steps=automation_steps,
            **reference_context(session),
        ),
    )


@router.post("/news/refresh")
def refresh_news(session: Session = Depends(get_session), _user=Depends(require_admin)):
    refresh_news_feeds(session)
    return redirect("/")


@router.get("/workflow", response_class=HTMLResponse)
def workflow(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
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
