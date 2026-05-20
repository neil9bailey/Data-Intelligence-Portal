from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.automation import (
    mark_interrupted_automation_runs,
    next_customers_for_kra,
    run_customer_kra_checks,
)
from app.evaluation import evaluate_cases, load_evaluation_cases
from app.intelligence_packs import apply_intelligence_pack, get_preconfigured_customer_pack
from app.jobs import record_job_run, run_job
from app.models import (
    AuditEvent,
    AutomationRun,
    Customer,
    DigestProfile,
    EmailDeliveryLog,
    IntelligenceReport,
    KRAResearchRun,
)


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


def test_kra_customer_rotation_prioritises_never_or_oldest_run_customers(reference_session):
    customers = [
        Customer(customer_name="Client A", domain="estates"),
        Customer(customer_name="Client B", domain="highways"),
        Customer(customer_name="Client C", domain="housing"),
        Customer(customer_name="Client D", domain="transport"),
        Customer(customer_name="Client E", domain="security"),
    ]
    reference_session.add_all(customers)
    reference_session.commit()
    for customer in customers:
        reference_session.refresh(customer)

    now = datetime.now(UTC)
    reference_session.add(
        KRAResearchRun(
            customer_id=customers[0].id,
            status="completed",
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1),
        )
    )
    reference_session.add(
        KRAResearchRun(
            customer_id=customers[1].id,
            status="completed",
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=2),
        )
    )
    reference_session.commit()

    selected = next_customers_for_kra(reference_session, 3)

    assert [customer.customer_name for customer in selected] == ["Client C", "Client D", "Client E"]


def test_run_customer_kra_checks_respects_rotation_limit(reference_session, monkeypatch):
    customers = [
        Customer(customer_name=f"Client {letter}", domain="transport")
        for letter in ["A", "B", "C", "D"]
    ]
    reference_session.add_all(customers)
    reference_session.commit()
    for customer in customers:
        reference_session.refresh(customer)
    reference_session.add(KRAResearchRun(customer_id=customers[0].id, status="completed"))
    reference_session.commit()
    called_customer_ids: list[int] = []

    def fake_kra_run(session, customer_id=None, **_kwargs):
        called_customer_ids.append(customer_id)
        run = KRAResearchRun(customer_id=customer_id, status="completed", finished_at=datetime.now(UTC))
        session.add(run)
        session.flush()
        return run

    monkeypatch.setattr("app.automation.run_kra_research", fake_kra_run)

    run_ids = run_customer_kra_checks(reference_session, customer_limit=2)

    assert len(run_ids) == 2
    assert called_customer_ids == [customers[1].id, customers[2].id]


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
