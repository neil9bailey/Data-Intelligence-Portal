from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import select

from app.archive import archive_candidates, archive_opportunities, restore_opportunity
from app.database import get_session
from app.main import app
from app.models import AutomationRun, Opportunity
from app.reports import create_report


def client_for(session):
    def override_session():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_archive_candidates_and_restore(reference_session):
    old_deadline = Opportunity(
        title="Past deadline tender",
        status="live",
        deadline_date=date.today() - timedelta(days=5),
        updated_at=datetime.now(UTC),
    )
    terminal = Opportunity(title="Withdrawn tender", status="withdrawn")
    live = Opportunity(title="Live future tender", status="live", deadline_date=date.today() + timedelta(days=20))
    reference_session.add_all([old_deadline, terminal, live])
    reference_session.commit()

    candidates = archive_candidates(reference_session)

    reasons_by_title = {candidate.opportunity.title: candidate.reason for candidate in candidates}
    assert reasons_by_title["Past deadline tender"] == "past_deadline"
    assert reasons_by_title["Withdrawn tender"] == "terminal_status"
    assert "Live future tender" not in reasons_by_title

    result = archive_opportunities(reference_session, actor="test")
    reference_session.refresh(old_deadline)
    reference_session.refresh(terminal)

    assert result["archived"] == 2
    assert old_deadline.archived is True
    assert old_deadline.status == "archived"
    assert old_deadline.archive_previous_status == "live"

    restore_opportunity(reference_session, old_deadline, actor="test")
    reference_session.refresh(old_deadline)

    assert old_deadline.archived is False
    assert old_deadline.status == "live"


def test_archived_opportunities_are_excluded_from_reports(reference_session):
    archived = Opportunity(
        title="Closed tender should not report",
        status="closed",
        deadline_date=date.today() - timedelta(days=3),
        relevance_score=99,
    )
    live = Opportunity(
        title="Live tender should report",
        status="live",
        deadline_date=date.today() + timedelta(days=30),
        relevance_score=99,
        source_url="https://www.find-tender.service.gov.uk/Notice/123456-2026",
    )
    reference_session.add_all([archived, live])
    reference_session.commit()

    archive_opportunities(reference_session, actor="test")
    report = create_report(reference_session, "Archive exclusion report", report_type="executive_summary")

    assert "Closed tender should not report" not in report.markdown
    assert "Live tender should report" in report.markdown


def test_archive_route_export_restore_and_delete(reference_session):
    opportunity = Opportunity(title="Route archive tender", status="closed", deadline_date=date.today() - timedelta(days=2))
    reference_session.add(opportunity)
    reference_session.commit()
    client = client_for(reference_session)
    try:
        page = client.get("/archive")
        run_response = client.post("/archive/run", data={"stale_days": "90", "past_deadline_grace_days": "1"}, follow_redirects=False)
        reference_session.refresh(opportunity)
        csv_response = client.get("/archive/export?format=csv")
        json_response = client.get("/archive/export?format=json")
        restore_response = client.post(f"/archive/{opportunity.id}/restore", follow_redirects=False)
        reference_session.refresh(opportunity)
        restored_archived_flag = opportunity.archived
        opportunity.status = "closed"
        reference_session.add(opportunity)
        reference_session.commit()
        archive_opportunities(reference_session, actor="test")
        delete_response = client.post(f"/archive/{opportunity.id}/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == 200
    assert run_response.status_code == 303
    assert csv_response.status_code == 200
    assert "Route archive tender" in csv_response.text
    assert json_response.status_code == 200
    assert "Route archive tender" in json_response.text
    assert restore_response.status_code == 303
    assert restored_archived_flag is False
    assert delete_response.status_code == 303
    assert reference_session.get(Opportunity, opportunity.id) is None


def test_archive_job_records_automation_run(reference_session):
    reference_session.add(Opportunity(title="Job archive tender", status="closed"))
    reference_session.commit()

    from app.jobs import run_job

    run = run_job("archive-opportunities", reference_session)

    assert run.run_type == "archive_opportunities"
    assert "Archived 1" in run.summary
    assert reference_session.exec(select(AutomationRun).where(AutomationRun.run_type == "archive_opportunities")).first() is not None
