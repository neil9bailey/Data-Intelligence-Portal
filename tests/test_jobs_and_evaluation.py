from sqlmodel import select

from app.automation import mark_interrupted_automation_runs
from app.evaluation import evaluate_cases, load_evaluation_cases
from app.intelligence_packs import apply_intelligence_pack, get_preconfigured_customer_pack
from app.jobs import record_job_run, run_job
from app.models import AuditEvent, AutomationRun, DigestProfile, EmailDeliveryLog, IntelligenceReport


def test_record_job_run_creates_audit_event(reference_session):
    run = record_job_run(reference_session, "refresh_sources", "completed", "Refreshed sources", [{"ok": True}])

    assert reference_session.get(AutomationRun, run.id) is not None
    assert reference_session.exec(select(AuditEvent).where(AuditEvent.entity_type == "AutomationRun")).first() is not None


def test_send_digests_job_processes_enabled_profiles(reference_session):
    reference_session.add(DigestProfile(name="Job digest", recipients="ops@example.com", export_format="md"))
    reference_session.commit()

    run = run_job("send-digests", reference_session)

    assert run.run_type == "send_digests"
    assert run.status == "completed"
    assert "Processed 1 digest profile" in run.summary
    log = reference_session.exec(select(EmailDeliveryLog)).first()
    assert log is not None
    assert log.status == "stored"


def test_mark_interrupted_automation_runs_closes_running_runs(reference_session):
    reference_session.add(AutomationRun(status="running", summary="Cycle in progress"))
    reference_session.commit()

    count = mark_interrupted_automation_runs(reference_session)

    run = reference_session.exec(select(AutomationRun).order_by(AutomationRun.id.desc())).first()
    assert count == 1
    assert run.status == "failed"
    assert "interrupted" in run.summary


def test_generate_cof_report_job_creates_report_without_full_admin_cycle(reference_session):
    apply_intelligence_pack(reference_session, get_preconfigured_customer_pack("procter_street_cof"), actor="test")

    run = run_job("generate-cof-report", reference_session)

    assert run.run_type == "generate_cof_report"
    assert run.status == "completed"
    assert "Generated COF report" in run.summary
    report = reference_session.exec(select(IntelligenceReport).where(IntelligenceReport.report_type == "cof_final_customer_pack")).first()
    assert report is not None
    assert "Client Coverage: 11 clients monitored" in report.markdown


def test_matching_evaluation_fixture_passes_baseline():
    cases = load_evaluation_cases("tests/fixtures/evaluation/opportunity_matching.json")
    report = evaluate_cases(cases)

    assert report["precision"] >= 0.9
    assert report["recall"] >= 0.9
    assert report["false_positives"] == []
    assert report["false_negatives"] == []
