from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session

from app.archive import (
    archive_candidates,
    archive_opportunities,
    archive_summary,
    archived_opportunity_statement,
    delete_opportunity_graph,
    export_archived_opportunities,
    restore_opportunity,
)
from app.auth import get_current_user, require_admin
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.models import Opportunity
from app.route_utils import context, paged, redirect, reference_context, templates


router = APIRouter()


@router.get("/archive", response_class=HTMLResponse)
def archive_page(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    q = str(request.query_params.get("q") or "").strip()
    reason = str(request.query_params.get("reason") or "").strip()
    errors: list[str] = []
    customer_id = parse_optional_int(request.query_params.get("customer_id"), "Customer", errors)
    source_id = parse_optional_int(request.query_params.get("source_id"), "Source", errors)
    if errors:
        return validation_error_response(errors, "/archive")
    statement = archived_opportunity_statement(q=q, reason=reason, customer_id=customer_id, source_id=source_id)
    items, pagination = paged(session, statement, request)
    preview = archive_candidates(session, limit=25)
    return templates.TemplateResponse(
        request,
        "archive.html",
        context(
            request,
            archived_opportunities=items,
            archive_pagination=pagination,
            archive_preview=preview,
            archive_summary=archive_summary(session),
            filters={"q": q, "reason": reason, "customer_id": customer_id, "source_id": source_id},
            archive_reasons=["past_deadline", "terminal_status", "stale_record", "old_award_evidence"],
            **reference_context(session),
        ),
    )


@router.post("/archive/run")
async def run_archive_cleanup(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    stale_days = parse_optional_int(form.get("stale_days"), "Stale days", errors) or 90
    grace_days = parse_optional_int(form.get("past_deadline_grace_days"), "Past-deadline grace days", errors) or 1
    award_days = parse_optional_int(form.get("award_retention_days"), "Award retention days", errors) or 90
    limit = parse_optional_int(form.get("limit"), "Limit", errors) or 500
    if errors:
        return validation_error_response(errors, "/archive")
    archive_opportunities(
        session,
        actor=get_current_user(request).username,
        stale_days=stale_days,
        past_deadline_grace_days=grace_days,
        award_retention_days=award_days,
        limit=limit,
    )
    return redirect("/archive")


@router.post("/archive/{opportunity_id}/restore")
def restore_archived_opportunity(opportunity_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity and opportunity.archived:
        restore_opportunity(session, opportunity, actor=get_current_user(request).username)
    return redirect("/archive")


@router.post("/archive/{opportunity_id}/delete")
def delete_archived_opportunity(opportunity_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity and opportunity.archived:
        delete_opportunity_graph(session, opportunity, f"Permanently deleted archived opportunity {opportunity.title}")
    return redirect("/archive")


@router.post("/archive/purge")
async def purge_archived_opportunities(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    confirm = str(form.get("confirm") or "").strip()
    if confirm != "DELETE ARCHIVE":
        return validation_error_response(["Type DELETE ARCHIVE to permanently delete archived opportunities."], "/archive")
    q = str(form.get("q") or "").strip()
    reason = str(form.get("reason") or "").strip()
    statement = archived_opportunity_statement(q=q, reason=reason)
    opportunities = list(session.exec(statement.limit(1000)))
    for opportunity in opportunities:
        delete_opportunity_graph(session, opportunity, f"Purged archived opportunity {opportunity.title}")
    return redirect("/archive")


@router.get("/archive/export")
def export_archive(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    q = str(request.query_params.get("q") or "").strip()
    reason = str(request.query_params.get("reason") or "").strip()
    export_format = str(request.query_params.get("format") or "csv").lower()
    errors: list[str] = []
    customer_id = parse_optional_int(request.query_params.get("customer_id"), "Customer", errors)
    source_id = parse_optional_int(request.query_params.get("source_id"), "Source", errors)
    if errors:
        return validation_error_response(errors, "/archive")
    if export_format not in {"csv", "json"}:
        export_format = "csv"
    opportunities = list(session.exec(archived_opportunity_statement(q=q, reason=reason, customer_id=customer_id, source_id=source_id).limit(5000)))
    media_type, filename, body = export_archived_opportunities(opportunities, export_format)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
