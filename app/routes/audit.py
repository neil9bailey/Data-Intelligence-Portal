from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session, col, select
import csv
import io
import json

from app.auth import require_auditor_or_admin
from app.database import get_session
from app.models import AuditEvent
from app.route_utils import context, paged, templates


router = APIRouter()


@router.get("/audit", response_class=HTMLResponse)
def audit(request: Request, format: str | None = None, entity_type: str | None = None, action: str | None = None, session: Session = Depends(get_session), _user=Depends(require_auditor_or_admin)):
    statement = select(AuditEvent).order_by(col(AuditEvent.created_at).desc())
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if action:
        statement = statement.where(AuditEvent.action == action)
    if format in {"json", "csv"}:
        events = list(session.exec(statement.limit(1000)))
        rows = [
            {
                "created_at": event.created_at.isoformat(),
                "actor": event.actor,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "action": event.action,
                "summary": event.summary,
                "before_json": event.before_json,
                "after_json": event.after_json,
            }
            for event in events
        ]
        if format == "json":
            return Response(json.dumps(rows, indent=2), media_type="application/json")
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()) if rows else ["created_at", "actor", "entity_type", "entity_id", "action", "summary", "before_json", "after_json"])
        writer.writeheader()
        writer.writerows(rows)
        return Response(output.getvalue(), media_type="text/csv")
    events, pagination = paged(session, statement, request)
    return templates.TemplateResponse(request, "audit.html", context(request, events=events, audit_pagination=pagination))
