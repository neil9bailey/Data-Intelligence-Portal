from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.auth import require_admin, require_standard_or_admin
from app.database import get_session
from app.intelligence import refresh_news_feeds
from app.models import DocumentRetrievalTask, IntelligenceReport, KRAFinding, NewsFeedItem, Opportunity, PortalRetrievalRun, SourceCheckSnapshot
from app.route_utils import context, portal_workbench_context, redirect, scoped_dashboard_metrics, scoped_reference_context, templates
from app.rule_loader import load_rule_file
from app.automation import automation_steps
from app.access_scope import scope_for_user, scoped_kra_finding_statement, scoped_opportunity_statement, scoped_report_statement


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session), user=Depends(require_standard_or_admin)):
    scope = scope_for_user(user)
    reference = scoped_reference_context(session, user)
    opportunities = list(session.exec(scoped_opportunity_statement(user).order_by(col(Opportunity.updated_at).desc()).limit(8)))
    findings = list(session.exec(scoped_kra_finding_statement(user).order_by(col(KRAFinding.created_at).desc()).limit(6)))
    source_ids = [source.id for source in reference["sources"] if source.id]
    snapshots_statement = select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc())
    snapshots = list(session.exec(snapshots_statement.where(col(SourceCheckSnapshot.source_id).in_(source_ids)).limit(5))) if source_ids else []
    news_items = [] if scope.restricted else list(session.exec(select(NewsFeedItem).order_by(col(NewsFeedItem.published_at).desc()).limit(6)))
    reports = list(session.exec(scoped_report_statement(user).order_by(col(IntelligenceReport.generated_at).desc()).limit(4)))
    opportunity_ids = [item.id for item in list(session.exec(scoped_opportunity_statement(user))) if item.id]
    tasks_statement = select(DocumentRetrievalTask).order_by(col(DocumentRetrievalTask.created_at).desc())
    tasks = list(session.exec(tasks_statement.where(col(DocumentRetrievalTask.opportunity_id).in_(opportunity_ids)).limit(5))) if scope.restricted else list(session.exec(tasks_statement.limit(5)))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context(
            request,
            metrics=scoped_dashboard_metrics(session, user),
            opportunities=opportunities,
            findings=findings,
            snapshots=snapshots,
            news_items=news_items,
            reports=reports,
            tasks=tasks,
            workflow=load_rule_file("workflow.yml"),
            automation_steps=automation_steps,
            **reference,
        ),
    )


@router.post("/news/refresh")
def refresh_news(session: Session = Depends(get_session), _user=Depends(require_admin)):
    refresh_news_feeds(session)
    return redirect("/")


@router.get("/workflow", response_class=HTMLResponse)
def workflow(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    workflow_rules = load_rule_file("workflow.yml")
    opportunities = list(
        session.exec(
            select(Opportunity)
            .where(Opportunity.archived == False)  # noqa: E712
            .order_by(col(Opportunity.updated_at).desc())
            .limit(5)
        )
    )
    recent_runs = list(session.exec(select(PortalRetrievalRun).order_by(col(PortalRetrievalRun.started_at).desc()).limit(5)))
    return templates.TemplateResponse(
        request,
        "workflow.html",
        context(
            request,
            workflow=workflow_rules,
            metrics=scoped_dashboard_metrics(session, _user),
            portal_metrics=portal_workbench_context(session)["portal_metrics"],
            recent_opportunities=opportunities,
            recent_retrieval_runs=recent_runs,
            **scoped_reference_context(session, _user),
        ),
    )
