from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import csv
import io
import json

from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.models import (
    ClientInterestSignal,
    DocumentRetrievalTask,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    KRAFinding,
    KRAResearchRun,
    Opportunity,
    OpportunityDocument,
    OpportunityFeedback,
    OpportunityMatchEvidence,
    PortalInformationConnector,
    PortalRetrievalRun,
)


TERMINAL_STATUSES = {
    "cancelled",
    "canceled",
    "closed",
    "complete",
    "completed",
    "duplicate",
    "expired",
    "not_relevant",
    "rejected",
    "stale",
    "withdrawn",
}
TERMINAL_STAGE_TERMS = {"closed", "complete", "completed", "cancelled", "canceled", "withdrawn", "unsuccessful"}
PROTECTED_WORK_STATUSES = {"interested", "document_retrieval_required", "questions_extracted"}


@dataclass(frozen=True)
class ArchiveCandidate:
    opportunity: Opportunity
    reason: str
    detail: str


def normalise(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "_").replace("-", "_")


def archive_reason_for_opportunity(
    opportunity: Opportunity,
    *,
    as_of: date | None = None,
    stale_days: int = 90,
    past_deadline_grace_days: int = 1,
    award_retention_days: int = 90,
) -> tuple[str, str] | None:
    if opportunity.archived:
        return None
    today = as_of or datetime.now(UTC).date()
    status = normalise(opportunity.status)
    stage_text = " ".join([opportunity.procurement_stage or "", opportunity.notice_type or ""]).lower()
    if status in TERMINAL_STATUSES or any(term in stage_text for term in TERMINAL_STAGE_TERMS):
        return "terminal_status", f"Status/stage indicates closed or no longer live: {opportunity.status or opportunity.procurement_stage or opportunity.notice_type}."
    if opportunity.deadline_date and opportunity.deadline_date < today - timedelta(days=max(0, past_deadline_grace_days)):
        return "past_deadline", f"Deadline {opportunity.deadline_date.isoformat()} is past the configured grace window."
    if status in PROTECTED_WORK_STATUSES:
        return None
    if status in {"awarded", "award_notice"} or "award" in stage_text:
        reference_date = opportunity.published_date or opportunity.deadline_date or _as_utc(opportunity.updated_at).date()
        if reference_date < today - timedelta(days=max(0, award_retention_days)):
            return "old_award_evidence", f"Award/market-evidence record is older than {award_retention_days} days."
        return None
    if _as_utc(opportunity.updated_at) < datetime.now(UTC) - timedelta(days=max(1, stale_days)):
        return "stale_record", f"Record has not updated for more than {stale_days} days."
    return None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def archive_candidates(
    session: Session,
    *,
    stale_days: int = 90,
    past_deadline_grace_days: int = 1,
    award_retention_days: int = 90,
    limit: int = 500,
) -> list[ArchiveCandidate]:
    candidates: list[ArchiveCandidate] = []
    statement = select(Opportunity).where(Opportunity.archived == False).order_by(col(Opportunity.updated_at).asc())  # noqa: E712
    for opportunity in session.exec(statement.limit(limit)):
        reason = archive_reason_for_opportunity(
            opportunity,
            stale_days=stale_days,
            past_deadline_grace_days=past_deadline_grace_days,
            award_retention_days=award_retention_days,
        )
        if reason:
            candidates.append(ArchiveCandidate(opportunity=opportunity, reason=reason[0], detail=reason[1]))
    return candidates


def archive_opportunity(session: Session, opportunity: Opportunity, reason: str, detail: str = "", actor: str = "system") -> Opportunity:
    before = compact_snapshot(opportunity)
    opportunity.archive_previous_status = opportunity.status
    opportunity.status = "archived"
    opportunity.archived = True
    opportunity.archived_at = datetime.now(UTC)
    opportunity.archive_reason = reason
    opportunity.archive_note = detail
    opportunity.updated_at = datetime.now(UTC)
    session.add(opportunity)
    session.flush()
    log_event(
        session,
        entity_type="Opportunity",
        entity_id=opportunity.id,
        action="archive",
        summary=f"Archived opportunity {opportunity.title}: {reason}",
        before=before,
        after=opportunity,
    )
    log_event(
        session,
        entity_type="OpportunityArchive",
        entity_id=opportunity.id,
        action="create",
        summary=f"{actor} archived opportunity {opportunity.title}: {detail or reason}",
        after=opportunity,
    )
    return opportunity


def archive_opportunities(
    session: Session,
    *,
    actor: str = "system",
    stale_days: int = 90,
    past_deadline_grace_days: int = 1,
    award_retention_days: int = 90,
    limit: int = 500,
) -> dict:
    archived: list[dict] = []
    candidates = archive_candidates(
        session,
        stale_days=stale_days,
        past_deadline_grace_days=past_deadline_grace_days,
        award_retention_days=award_retention_days,
        limit=limit,
    )
    for candidate in candidates:
        opportunity = archive_opportunity(session, candidate.opportunity, candidate.reason, candidate.detail, actor=actor)
        archived.append(
            {
                "id": opportunity.id,
                "title": opportunity.title,
                "reason": candidate.reason,
                "detail": candidate.detail,
            }
        )
    session.commit()
    return {"archived": len(archived), "items": archived}


def restore_opportunity(session: Session, opportunity: Opportunity, actor: str = "system") -> Opportunity:
    before = compact_snapshot(opportunity)
    restored_status = opportunity.archive_previous_status or "needs_review"
    opportunity.status = restored_status
    opportunity.archived = False
    opportunity.archive_note = f"Restored by {actor}; previous archive reason was {opportunity.archive_reason}."
    opportunity.archive_reason = ""
    opportunity.archived_at = None
    opportunity.archive_previous_status = ""
    opportunity.updated_at = datetime.now(UTC)
    session.add(opportunity)
    session.flush()
    log_event(
        session,
        entity_type="Opportunity",
        entity_id=opportunity.id,
        action="restore",
        summary=f"Restored opportunity {opportunity.title}",
        before=before,
        after=opportunity,
    )
    session.commit()
    return opportunity


def archived_opportunity_statement(q: str = "", reason: str = "", customer_id: int | None = None, source_id: int | None = None):
    statement = select(Opportunity).where(Opportunity.archived == True)  # noqa: E712
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                col(Opportunity.title).ilike(pattern),
                col(Opportunity.buyer_name).ilike(pattern),
                col(Opportunity.notice_identifier).ilike(pattern),
                col(Opportunity.summary).ilike(pattern),
            )
        )
    if reason:
        statement = statement.where(Opportunity.archive_reason == reason)
    if customer_id:
        statement = statement.where(Opportunity.customer_id == customer_id)
    if source_id:
        statement = statement.where(Opportunity.source_id == source_id)
    return statement.order_by(col(Opportunity.archived_at).desc())


def archive_summary(session: Session) -> dict:
    archived = list(session.exec(select(Opportunity).where(Opportunity.archived == True)))  # noqa: E712
    live = list(session.exec(select(Opportunity).where(Opportunity.archived == False)))  # noqa: E712
    reason_counts: dict[str, int] = {}
    for opportunity in archived:
        reason = opportunity.archive_reason or "unspecified"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "archived_count": len(archived),
        "live_count": len(live),
        "reason_counts": reason_counts,
        "latest_archived_at": max((item.archived_at for item in archived if item.archived_at), default=None),
    }


def export_archived_opportunities(opportunities: list[Opportunity], export_format: str = "csv") -> tuple[str, str, str]:
    rows = [_archive_export_row(item) for item in opportunities]
    if export_format == "json":
        return "application/json", "cof-opportunity-archive.json", json.dumps(rows, default=str, indent=2)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()) if rows else list(_archive_export_row(Opportunity(title="")).keys()))
    writer.writeheader()
    writer.writerows(rows)
    return "text/csv", "cof-opportunity-archive.csv", output.getvalue()


def _archive_export_row(opportunity: Opportunity) -> dict:
    return {
        "id": opportunity.id,
        "title": opportunity.title,
        "buyer_name": opportunity.buyer_name,
        "customer_id": opportunity.customer_id,
        "source_id": opportunity.source_id,
        "notice_identifier": opportunity.notice_identifier,
        "notice_type": opportunity.notice_type,
        "procurement_stage": opportunity.procurement_stage,
        "deadline_date": opportunity.deadline_date,
        "published_date": opportunity.published_date,
        "status": opportunity.status,
        "archive_previous_status": opportunity.archive_previous_status,
        "archive_reason": opportunity.archive_reason,
        "archive_note": opportunity.archive_note,
        "archived_at": opportunity.archived_at,
        "source_url": opportunity.source_url,
    }


def delete_opportunity_graph(session: Session, opportunity: Opportunity, summary: str = "") -> None:
    opportunity_id = opportunity.id
    if opportunity_id is None:
        return
    for model, field_name in [
        (ExtractedQualityQuestion, "opportunity_id"),
        (OpportunityDocument, "opportunity_id"),
        (DocumentRetrievalTask, "opportunity_id"),
        (OpportunityMatchEvidence, "opportunity_id"),
        (OpportunityFeedback, "opportunity_id"),
    ]:
        field = getattr(model, field_name)
        for child in session.exec(select(model).where(field == opportunity_id)):
            session.delete(child)
    for model, field_name in [
        (PortalInformationConnector, "default_opportunity_id"),
        (PortalRetrievalRun, "opportunity_id"),
        (ClientInterestSignal, "opportunity_id"),
        (ExtractedRequirement, "opportunity_id"),
        (KRAFinding, "opportunity_id"),
        (KRAResearchRun, "opportunity_id"),
    ]:
        field = getattr(model, field_name)
        for item in session.exec(select(model).where(field == opportunity_id)):
            setattr(item, field_name, None)
            session.add(item)
    before = compact_snapshot(opportunity)
    log_event(
        session,
        entity_type="Opportunity",
        entity_id=opportunity_id,
        action="delete",
        summary=summary or f"Deleted opportunity {opportunity.title}",
        before=before,
    )
    session.delete(opportunity)
    session.commit()


def archive_filter_or_false(include_archived: bool = False):
    return None if include_archived else Opportunity.archived == False  # noqa: E712
