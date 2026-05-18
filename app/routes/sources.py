from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_bool, validation_error_response
from app.intelligence import run_source_check, source_allowed
from app.models import KRAFinding, KRAResearchRun, Opportunity, ProcurementSource, SourceCheckSnapshot
from app.route_utils import clear_links, context, delete_with_audit, paged, redirect, reference_context, save_with_audit, templates, update_with_audit


router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
def sources(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    snapshots, pagination = paged(
        session,
        select(SourceCheckSnapshot).order_by(col(SourceCheckSnapshot.checked_at).desc()),
        request,
        param="snapshots_page",
    )
    return templates.TemplateResponse(request, "sources.html", context(request, snapshots=snapshots, snapshots_pagination=pagination, **reference_context(session)))


@router.post("/sources/{source_id}/check")
def check_source(source_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    try:
        run_source_check(session, source_id)
    except ValueError as exc:
        return validation_error_response([str(exc)], "/sources")
    return redirect("/sources")


@router.post("/sources")
async def create_source(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
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


@router.post("/sources/{source_id}")
async def update_source(source_id: int, request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
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


@router.post("/sources/{source_id}/delete")
def delete_source(source_id: int, session: Session = Depends(get_session), _user=Depends(require_admin)):
    source = session.get(ProcurementSource, source_id)
    if not source:
        return redirect("/sources")
    clear_links(session, SourceCheckSnapshot, "source_id", source.id)
    clear_links(session, Opportunity, "source_id", source.id)
    clear_links(session, KRAResearchRun, "source_id", source.id)
    clear_links(session, KRAFinding, "source_id", source.id)
    delete_with_audit(session, source, f"Deleted source {source.name}")
    return redirect("/sources")
