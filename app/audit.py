import json
from typing import Any

from sqlmodel import Session

from app.models import AuditEvent


def compact_snapshot(item: Any) -> str:
    if not item:
        return ""
    if isinstance(item, str):
        return item
    if hasattr(item, "model_dump"):
        data = item.model_dump()
    else:
        data = dict(item)
    for key in list(data):
        if any(term in key.lower() for term in ("password", "secret", "token", "api_key")):
            data[key] = "***redacted***" if data[key] else ""
    return json.dumps(data, default=str, separators=(",", ":"))[:8000]


def log_event(
    session: Session,
    *,
    entity_type: str,
    entity_id: int | None,
    action: str,
    summary: str,
    before: Any = "",
    after: Any = "",
    actor: str = "local-user",
) -> AuditEvent:
    event = AuditEvent(
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        summary=summary,
        before_json=compact_snapshot(before),
        after_json=compact_snapshot(after),
    )
    session.add(event)
    return event
