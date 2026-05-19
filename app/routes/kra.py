from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.audit import compact_snapshot
from app.auth import require_admin
from app.database import get_session
from app.form_utils import parse_optional_int, validation_error_response
from app.intelligence import run_kra_research
from app.models import KRAFinding, KRAResearchRun, utc_now
from app.route_utils import context, paged, redirect, reference_context, templates, update_with_audit


router = APIRouter()


@router.get("/kra", response_class=HTMLResponse)
def kra(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    runs, runs_pagination = paged(
        session,
        select(KRAResearchRun).order_by(col(KRAResearchRun.started_at).desc()),
        request,
        param="runs_page",
    )
    findings, findings_pagination = paged(
        session,
        select(KRAFinding).order_by(col(KRAFinding.created_at).desc()),
        request,
        param="findings_page",
    )
    return templates.TemplateResponse(
        request,
        "kra.html",
        context(
            request,
            runs=runs,
            findings=findings,
            runs_pagination=runs_pagination,
            findings_pagination=findings_pagination,
            **reference_context(session),
        ),
    )


@router.post("/kra/run")
async def run_kra(request: Request, session: Session = Depends(get_session), _user=Depends(require_admin)):
    form = await request.form()
    errors: list[str] = []
    agent_id = parse_optional_int(form.get("agent_profile_id"), "Agent", errors)
    source_id = parse_optional_int(form.get("source_id"), "Source", errors)
    customer_id = parse_optional_int(form.get("customer_id"), "Customer", errors)
    if errors:
        return validation_error_response(errors, "/kra")
    run_kra_research(session, agent_profile_id=agent_id, source_id=source_id, customer_id=customer_id, query=str(form.get("query") or ""))
    return redirect("/kra")


@router.post("/kra/findings/{finding_id}/review")
async def review_kra_finding(finding_id: int, request: Request, session: Session = Depends(get_session), user=Depends(require_admin)):
    finding = session.get(KRAFinding, finding_id)
    if not finding:
        return redirect("/kra")
    form = await request.form()
    review_status = str(form.get("human_review_status") or "pending")
    if review_status not in {"pending", "approved", "rejected"}:
        return validation_error_response(["Review status must be pending, approved or rejected."], "/kra")
    before = compact_snapshot(finding)
    finding.human_review_status = review_status
    finding.reviewed_by = user.username
    finding.reviewed_at = utc_now()
    update_with_audit(session, finding, f"Reviewed KRA finding {finding.title}", before)
    return redirect("/kra")
