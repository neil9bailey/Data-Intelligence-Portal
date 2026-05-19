from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, col, select

from app.auth import require_auditor_or_admin
from app.database import get_session
from app.models import AuditEvent
from app.route_utils import context, paged, templates


router = APIRouter()


@router.get("/audit", response_class=HTMLResponse)
def audit(request: Request, session: Session = Depends(get_session), _user=Depends(require_auditor_or_admin)):
    events, pagination = paged(session, select(AuditEvent).order_by(col(AuditEvent.created_at).desc()), request)
    return templates.TemplateResponse(request, "audit.html", context(request, events=events, audit_pagination=pagination))
