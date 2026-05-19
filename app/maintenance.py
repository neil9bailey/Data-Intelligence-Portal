from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session, select

from app.audit import log_event
from app.database import backup_sqlite_persistent_copy, engine
from app.models import (
    AutomationRun,
    EmailDeliveryLog,
    IntelligenceReport,
    KRAFinding,
    KRAResearchRun,
    NewsFeedItem,
    PortalInformationConnector,
    PortalRetrievalRun,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.settings import get_settings


OUTPUT_MODELS = [
    KRAFinding,
    KRAResearchRun,
    PortalRetrievalRun,
    SourceCheckSnapshot,
    AutomationRun,
    EmailDeliveryLog,
    IntelligenceReport,
    NewsFeedItem,
]


def clean_generated_outputs(session: Session, actor: str = "local-user", clean_outbox: bool = True) -> dict[str, int]:
    """Remove generated output artefacts while preserving configured COF data."""
    summary: dict[str, int] = {}
    for model in OUTPUT_MODELS:
        items = list(session.exec(select(model)))
        summary[model.__name__] = len(items)
        for item in items:
            session.delete(item)

    source_count = 0
    for source in session.exec(select(ProcurementSource)):
        source.last_checked_at = None
        source.last_status = ""
        source.connector_status = "configured"
        session.add(source)
        source_count += 1
    summary["ProcurementSourceStatusReset"] = source_count

    connector_count = 0
    for connector in session.exec(select(PortalInformationConnector)):
        connector.last_checked_at = None
        connector.last_status = "not_checked"
        connector.last_http_status = 0
        session.add(connector)
        connector_count += 1
    summary["PortalConnectorStatusReset"] = connector_count

    if clean_outbox:
        summary["OutboxFilesDeleted"] = _clean_outbox_files()

    log_event(
        session,
        entity_type="Maintenance",
        entity_id=None,
        action="clean_generated_outputs",
        summary="Cleaned generated reports, run history, source snapshots, email logs and outbox files.",
        after=summary,
        actor=actor,
    )
    session.commit()
    backup_sqlite_persistent_copy()
    return summary


def _clean_outbox_files() -> int:
    outbox = Path(get_settings().outbox_dir).resolve()
    if not outbox.exists() or not outbox.is_dir():
        return 0
    deleted = 0
    for path in sorted(outbox.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if outbox not in resolved.parents and resolved != outbox:
            continue
        if resolved.is_file():
            resolved.unlink(missing_ok=True)
            deleted += 1
        elif resolved.is_dir() and resolved != outbox:
            try:
                resolved.rmdir()
            except OSError:
                pass
    return deleted


def main() -> None:
    with Session(engine) as session:
        print(json.dumps(clean_generated_outputs(session, actor="maintenance-cli"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
