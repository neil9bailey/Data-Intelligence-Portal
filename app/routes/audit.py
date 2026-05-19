from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session, col, select
import csv
from datetime import datetime, time
import io
import json

from app.auth import require_auditor_or_admin
from app.database import get_session
from app.models import AuditEvent
from app.route_utils import context, paged, templates


router = APIRouter()


def _parse_datetime_filter(value: str | None, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            parsed_date = datetime.fromisoformat(value).date()
            return datetime.combine(parsed_date, time.max if end_of_day else time.min)
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/audit", response_class=HTMLResponse)
def audit(
    request: Request,
    format: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    actor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    session: Session = Depends(get_session),
    _user=Depends(require_auditor_or_admin),
):
    statement = select(AuditEvent).order_by(col(AuditEvent.created_at).desc())
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(AuditEvent.entity_id == entity_id)
    if action:
        statement = statement.where(AuditEvent.action == action)
    if actor:
        statement = statement.where(AuditEvent.actor == actor)
    parsed_from = _parse_datetime_filter(date_from)
    parsed_to = _parse_datetime_filter(date_to, end_of_day=True)
    if parsed_from:
        statement = statement.where(AuditEvent.created_at >= parsed_from)
    if parsed_to:
        statement = statement.where(AuditEvent.created_at <= parsed_to)
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
    return templates.TemplateResponse(
        request,
        "audit.html",
        context(
            request,
            events=events,
            audit_pagination=pagination,
            audit_filters={
                "entity_type": entity_type or "",
                "entity_id": entity_id or "",
                "action": action or "",
                "actor": actor or "",
                "date_from": date_from or "",
                "date_to": date_to or "",
            },
        ),
    )
