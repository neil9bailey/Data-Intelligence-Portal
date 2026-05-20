from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json

from sqlmodel import Session
from sqlmodel import select

from app.archive import archive_opportunities
from app.audit import log_event
from app.automation import refresh_public_sources, run_admin_full_cycle, store_report_export
from app.database import backup_sqlite_persistent_copy, engine, init_db
from app.digests import send_digest
from app.intelligence import refresh_news_feeds
from app.models import AutomationRun, DigestProfile
from app.portal_connectors import run_enabled_portal_connectors
from app.reports import create_report


def record_job_run(session: Session, run_type: str, status: str, summary: str, details: dict | list | None = None) -> AutomationRun:
    run = AutomationRun(
        run_type=run_type,
        status=status,
        summary=summary,
        steps_json=json.dumps(details or [], default=str),
        finished_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    log_event(session, entity_type="AutomationRun", entity_id=run.id, action=status, summary=summary, after=run)
    session.commit()
    session.refresh(run)
    return run


def run_job(job_name: str, session: Session) -> AutomationRun:
    try:
        if job_name == "refresh-sources":
            results = refresh_public_sources(session)
            failed = sum(1 for item in results if not item.get("ok"))
            return record_job_run(session, "refresh_sources", "completed" if failed == 0 else "completed_with_warnings", f"Refreshed {len(results)} public sources; {failed} warnings.", results)
        if job_name == "refresh-feeds":
            count = refresh_news_feeds(session)
            return record_job_run(session, "refresh_feeds", "completed", f"Refreshed news feeds; {count} items created or updated.", [{"items": count}])
        if job_name == "run-connectors":
            runs = run_enabled_portal_connectors(session)
            failed = sum(1 for item in runs if item.status != "completed")
            return record_job_run(session, "run_connectors", "completed" if failed == 0 else "completed_with_warnings", f"Ran {len(runs)} read-only connectors; {failed} warnings.", runs)
        if job_name == "archive-opportunities":
            result = archive_opportunities(session, actor="job:archive-opportunities")
            return record_job_run(
                session,
                "archive_opportunities",
                "completed",
                f"Archived {result['archived']} closed, past-deadline or stale opportunity record(s).",
                result,
            )
        if job_name == "send-digests":
            profiles = list(session.exec(select(DigestProfile).where(DigestProfile.enabled == True)))  # noqa: E712
            results = []
            failures = 0
            for profile in profiles:
                try:
                    log = send_digest(session, profile)
                    results.append({"profile": profile.name, "status": log.status, "email_log_id": log.id})
                    if log.status == "failed":
                        failures += 1
                except Exception as exc:
                    failures += 1
                    results.append({"profile": profile.name, "status": "failed", "error": str(exc)[:220]})
            return record_job_run(
                session,
                "send_digests",
                "completed" if failures == 0 else "completed_with_warnings",
                f"Processed {len(profiles)} digest profile(s); {failures} warning(s).",
                results,
            )
        if job_name == "admin-cycle":
            return run_admin_full_cycle(session)
        if job_name == "generate-cof-report":
            report = create_report(
                session,
                f"COF final customer pack {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
                report_type="cof_final_customer_pack",
                include_ai_brief=False,
            )
            stored_path = store_report_export(report, "pdf")
            return record_job_run(
                session,
                "generate_cof_report",
                "completed",
                f"Generated COF report {report.id} at {stored_path}.",
                {"report_id": report.id, "stored_path": stored_path},
            )
    except Exception as exc:
        return record_job_run(session, job_name.replace("-", "_"), "failed", f"Job {job_name} failed: {str(exc)[:220]}")
    return record_job_run(session, job_name.replace("-", "_"), "failed", f"Unknown job {job_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Data Intelligence Portal job runner")
    parser.add_argument(
        "job",
        choices=[
            "refresh-sources",
            "refresh-feeds",
            "run-connectors",
            "archive-opportunities",
            "send-digests",
            "admin-cycle",
            "generate-cof-report",
        ],
    )
    args = parser.parse_args()
    init_db()
    with Session(engine) as session:
        run = run_job(args.job, session)
        print(f"{run.run_type}: {run.status} - {run.summary}")
    backup_sqlite_persistent_copy()


if __name__ == "__main__":
    main()
