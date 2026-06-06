from datetime import date, timedelta

from app.intelligence_value import opportunity_value_signal, portfolio_insights, source_traceability
from app.models import Opportunity


def test_opportunity_value_signal_prioritises_source_validation():
    opportunity = Opportunity(
        title="Unverified source",
        status="approved",
        source_url="https://www.find-tender.service.gov.uk/Notice/COF-0001",
        relevance_score=86,
        deadline_date=date.today() + timedelta(days=12),
        value_high=1_250_000,
    )

    signal = opportunity_value_signal(opportunity, interest_count=1, retrieval_task_count=0)

    assert signal.confidence_label == "strong match"
    assert signal.source_label == "source reference pending"
    assert signal.next_action == "Validate source reference"
    assert signal.value_label == "GBP 1.2m"


def test_opportunity_value_signal_handles_interest_document_path():
    opportunity = Opportunity(
        title="Interested live tender",
        status="interested",
        source_url="https://www.find-tender.service.gov.uk/Notice/123456-2026",
        relevance_score=67,
        deadline_date=date.today() + timedelta(days=5),
    )

    signal = opportunity_value_signal(opportunity, interest_count=1, retrieval_task_count=1, document_count=0)

    assert signal.source_label == "official source traced"
    assert signal.urgency_class == "red"
    assert signal.next_action == "Retrieve permitted tender extract"


def test_source_traceability_flags_external_and_missing_sources():
    missing = Opportunity(title="Missing source")
    external = Opportunity(title="External source", source_url="https://buyer.example.org/notice")

    assert source_traceability(missing) == ("source missing", "red")
    assert source_traceability(external) == ("external source traced", "amber")


def test_portfolio_insights_summarise_operating_attention():
    opportunities = [
        Opportunity(
            title="Strong live",
            status="live",
            procurement_stage="tender",
            source_url="https://www.contractsfinder.service.gov.uk/notice/1",
            relevance_score=90,
            deadline_date=date.today() + timedelta(days=20),
        ),
        Opportunity(title="Needs review", status="review_required", relevance_score=45, source_url=""),
    ]

    insights = {item.headline: item for item in portfolio_insights(opportunities)}

    assert "Live opportunity volume" in insights
    assert "1 live/open tender" in insights["Live opportunity volume"].detail
    assert "1 item(s) need source validation" in insights["Source traceability"].detail
    assert insights["Review workload"].status == "amber"
