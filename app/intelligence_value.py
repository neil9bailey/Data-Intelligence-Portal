from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from typing import Iterable

from app.models import ClientInterestSignal, DocumentRetrievalTask, ExtractedQualityQuestion, Opportunity, OpportunityDocument, ProcurementSource


OFFICIAL_SOURCE_HOSTS = {
    "www.find-tender.service.gov.uk",
    "find-tender.service.gov.uk",
    "www.contractsfinder.service.gov.uk",
    "contractsfinder.service.gov.uk",
    "www.publiccontractsscotland.gov.uk",
    "publiccontractsscotland.gov.uk",
    "www.sell2wales.gov.wales",
    "sell2wales.gov.wales",
    "ted.europa.eu",
    "docs.ted.europa.eu",
}
PLACEHOLDER_SOURCE_MARKERS = ("/notice/cof-", "cof-000", "cof-live-pilot", "example.com")
LIVE_STAGE_TERMS = {"live", "tender", "open", "active", "closing_soon", "questions_extracted", "document_retrieval_required"}
REVIEW_TERMS = {"new", "needs_review", "review_required", "pending_review", "matched"}
APPROVED_TERMS = {"approved", "accepted", "review_ready", "complete", "completed", "live", "pin", "watch", "interested", "awarded"}


@dataclass(frozen=True)
class OpportunityValueSignal:
    confidence_label: str
    confidence_class: str
    source_label: str
    source_class: str
    urgency_label: str
    urgency_class: str
    stage_label: str
    next_action: str
    evidence_summary: str
    value_label: str


@dataclass(frozen=True)
class PortfolioInsight:
    headline: str
    detail: str
    status: str = "info"


def concise_money(value: float | int | None, currency: str = "GBP") -> str:
    amount = float(value or 0)
    if amount <= 0:
        return "value not detected"
    if amount >= 1_000_000:
        return f"{currency} {amount / 1_000_000:.1f}m"
    if amount >= 1_000:
        return f"{currency} {amount / 1_000:.0f}k"
    return f"{currency} {amount:.0f}"


def confidence_band(score: float | int | None) -> tuple[str, str]:
    value = float(score or 0)
    if value >= 80:
        return "strong match", "green"
    if value >= 60:
        return "good match", "green"
    if value >= 40:
        return "review match", "amber"
    if value > 0:
        return "weak match", "red"
    return "unscored", "weak"


def source_traceability(opportunity: Opportunity, source: ProcurementSource | None = None) -> tuple[str, str]:
    url = (opportunity.source_url or "").strip()
    if not url:
        return "source missing", "red"
    lowered = url.lower()
    if any(marker in lowered for marker in PLACEHOLDER_SOURCE_MARKERS):
        return "source reference pending", "amber"
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc.lower() in OFFICIAL_SOURCE_HOSTS:
        if source and not source.active:
            return "official source inactive", "amber"
        return "official source traced", "green"
    if parsed.scheme == "https":
        return "external source traced", "amber"
    return "source needs validation", "red"


def deadline_urgency(opportunity: Opportunity, today: date | None = None) -> tuple[str, str]:
    current = today or date.today()
    deadline = opportunity.deadline_date
    if not deadline:
        if (opportunity.notice_type or "").lower() == "award" or (opportunity.status or "").lower() == "awarded":
            return "award evidence", "weak"
        return "deadline not detected", "amber"
    days = (deadline - current).days
    if days < 0:
        return "deadline passed", "red"
    if days <= 7:
        return f"closing in {days} day(s)", "red"
    if days <= 21:
        return f"closing in {days} day(s)", "amber"
    return f"{days} day(s) to deadline", "green"


def stage_label(opportunity: Opportunity) -> str:
    status = (opportunity.status or "").replace("_", " ").strip()
    stage = (opportunity.procurement_stage or opportunity.notice_type or "").replace("_", " ").strip()
    if status and stage and status.lower() != stage.lower():
        return f"{status} / {stage}"
    return status or stage or "stage to confirm"


def next_best_action(
    opportunity: Opportunity,
    *,
    interest_count: int = 0,
    retrieval_task_count: int = 0,
    question_count: int = 0,
    document_count: int = 0,
) -> str:
    status = (opportunity.status or "").lower()
    source_label, _ = source_traceability(opportunity)
    urgency, urgency_class = deadline_urgency(opportunity)
    if "missing" in source_label or "validation" in source_label or "pending" in source_label:
        return "Validate source reference"
    if status in REVIEW_TERMS:
        return "Review Lead to approve or reject"
    if interest_count and not retrieval_task_count:
        return "Create document retrieval task"
    if interest_count and retrieval_task_count and not document_count:
        return "Retrieve permitted tender extract"
    if document_count and not question_count:
        return "Extract quality questions"
    if question_count:
        return "Review extracted questions"
    if urgency_class == "red" and "passed" not in urgency:
        return "Prioritise review before deadline"
    if status in {"awarded", "award_notice"}:
        return "Use as market evidence"
    return "Monitor and include in next pack"


def opportunity_value_signal(
    opportunity: Opportunity,
    *,
    source: ProcurementSource | None = None,
    interest_count: int = 0,
    retrieval_task_count: int = 0,
    question_count: int = 0,
    document_count: int = 0,
) -> OpportunityValueSignal:
    confidence_label, confidence_class = confidence_band(opportunity.relevance_score)
    source_label, source_class = source_traceability(opportunity, source)
    urgency_label, urgency_class = deadline_urgency(opportunity)
    return OpportunityValueSignal(
        confidence_label=confidence_label,
        confidence_class=confidence_class,
        source_label=source_label,
        source_class=source_class,
        urgency_label=urgency_label,
        urgency_class=urgency_class,
        stage_label=stage_label(opportunity),
        next_action=next_best_action(
            opportunity,
            interest_count=interest_count,
            retrieval_task_count=retrieval_task_count,
            question_count=question_count,
            document_count=document_count,
        ),
        evidence_summary=f"{document_count} document(s), {question_count} question(s), {interest_count} client signal(s)",
        value_label=concise_money(opportunity.value_high, opportunity.currency or "GBP"),
    )


def value_signal_map(
    opportunities: Iterable[Opportunity],
    *,
    sources_by_id: dict[int | None, ProcurementSource] | None = None,
    interests: Iterable[ClientInterestSignal] = (),
    retrieval_tasks: Iterable[DocumentRetrievalTask] = (),
    documents: Iterable[OpportunityDocument] = (),
    questions: Iterable[ExtractedQualityQuestion] = (),
) -> dict[int, OpportunityValueSignal]:
    source_lookup = sources_by_id or {}
    interest_counts = _count_by_opportunity(interests)
    task_counts = _count_by_opportunity(retrieval_tasks)
    document_counts = _count_by_opportunity(documents)
    question_counts = _count_by_opportunity(questions)
    signals: dict[int, OpportunityValueSignal] = {}
    for opportunity in opportunities:
        if not opportunity.id:
            continue
        signals[opportunity.id] = opportunity_value_signal(
            opportunity,
            source=source_lookup.get(opportunity.source_id),
            interest_count=interest_counts.get(opportunity.id, 0),
            retrieval_task_count=task_counts.get(opportunity.id, 0),
            document_count=document_counts.get(opportunity.id, 0),
            question_count=question_counts.get(opportunity.id, 0),
        )
    return signals


def portfolio_insights(opportunities: list[Opportunity]) -> list[PortfolioInsight]:
    live = [item for item in opportunities if _is_live(item)]
    closing = [item for item in opportunities if deadline_urgency(item)[1] in {"red", "amber"} and item.deadline_date]
    source_attention = [item for item in opportunities if source_traceability(item)[1] != "green"]
    review = [item for item in opportunities if (item.status or "").lower() in REVIEW_TERMS]
    strong = [item for item in opportunities if float(item.relevance_score or 0) >= 80]
    insights = [
        PortfolioInsight("Live opportunity volume", f"{len(live)} live/open tender signal(s) in the current visible pipeline.", "green" if live else "amber"),
        PortfolioInsight("Near-term deadlines", f"{len(closing)} item(s) need timing attention inside the next 21 days.", "amber" if closing else "green"),
        PortfolioInsight("Source traceability", f"{len(source_attention)} item(s) need source validation or stronger traceability.", "amber" if source_attention else "green"),
        PortfolioInsight("Review workload", f"{len(review)} item(s) are waiting for Review Lead decisioning.", "amber" if review else "green"),
        PortfolioInsight("High-confidence matches", f"{len(strong)} item(s) currently score as strong customer/capability matches.", "green" if strong else "weak"),
    ]
    return insights


def _is_live(opportunity: Opportunity) -> bool:
    status = (opportunity.status or "").lower()
    stage = (opportunity.procurement_stage or "").lower()
    notice_type = (opportunity.notice_type or "").lower()
    return any(term in {status, stage, notice_type} for term in LIVE_STAGE_TERMS)


def _count_by_opportunity(rows: Iterable[object]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for row in rows:
        opportunity_id = getattr(row, "opportunity_id", None)
        if not opportunity_id:
            continue
        counts[opportunity_id] = counts.get(opportunity_id, 0) + 1
    return counts
