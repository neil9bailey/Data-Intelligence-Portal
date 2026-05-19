from sqlmodel import select

from app.evaluation import evaluate_cases, load_evaluation_cases
from app.jobs import record_job_run
from app.models import AuditEvent, AutomationRun


def test_record_job_run_creates_audit_event(reference_session):
    run = record_job_run(reference_session, "refresh_sources", "completed", "Refreshed sources", [{"ok": True}])

    assert reference_session.get(AutomationRun, run.id) is not None
    assert reference_session.exec(select(AuditEvent).where(AuditEvent.entity_type == "AutomationRun")).first() is not None


def test_matching_evaluation_fixture_passes_baseline():
    cases = load_evaluation_cases("tests/fixtures/evaluation/opportunity_matching.json")
    report = evaluate_cases(cases)

    assert report["precision"] >= 0.9
    assert report["recall"] >= 0.9
    assert report["false_positives"] == []
    assert report["false_negatives"] == []
