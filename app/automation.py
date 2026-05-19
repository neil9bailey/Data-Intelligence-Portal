from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import json
import logging

from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.classification import agent_classify_catalogue
from app.database import backup_sqlite_persistent_copy, engine
from app.email_service import get_email_configuration, send_or_store_email, split_recipients
from app.export_service import report_export, report_filename
from app.intelligence import (
    FetchResult,
    fetch_source_url,
    refresh_news_feeds,
    repair_low_quality_market_opportunities,
    repair_mismatched_customer_assignments,
    run_kra_research,
    run_public_market_keyword_sweep,
    run_source_check,
)
from app.intelligence_packs import apply_intelligence_pack, get_preconfigured_customer_pack, list_preconfigured_customer_packs
from app.models import (
    AuditEvent,
    AutomationRun,
    BuyerPortalInstance,
    Customer,
    DocumentRetrievalTask,
    IntelligenceReport,
    KRAResearchRun,
    PortalRetrievalRun,
    ProcurementSource,
)
from app.portal_connectors import run_enabled_portal_connectors
from app.reports import create_report
from app.settings import get_settings


OPEN_TASK_STATUSES = {"requested", "in_progress", "blocked", "review_required"}
AUTO_PORTAL_MODES = {"approved_api", "public_api_no_key", "api_key_header", "api_key_query", "oauth_client_credentials"}
logger = logging.getLogger(__name__)
LIVE_KRA_SOURCE_KEYS = {"find_a_tender", "contracts_finder"}


def apply_all_preconfigured_packs(session: Session, actor: str = "system") -> list[dict]:
    results: list[dict] = []
    for pack_ref in list_preconfigured_customer_packs():
        pack = get_preconfigured_customer_pack(pack_ref["key"])
        results.append(apply_intelligence_pack(session, pack, actor=actor))
    return results


def mark_interrupted_automation_runs(session: Session) -> int:
    interrupted = list(
        session.exec(
            select(AutomationRun).where(
                col(AutomationRun.status).in_(["queued", "running"]),
                AutomationRun.finished_at == None,  # noqa: E711
            )
        )
    )
    for run in interrupted:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.summary = "Automation was interrupted by an application restart before completion."
        session.add(run)
        log_event(
            session,
            entity_type="AutomationRun",
            entity_id=run.id,
            action="failed",
            summary=run.summary,
            after=run,
        )
    if interrupted:
        session.commit()
    return len(interrupted)


def run_admin_full_cycle(
    session: Session,
    actor: str = "local-user",
    email_recipients: str = "",
    export_format: str = "pdf",
    source_fetcher=None,
    connector_fetcher=None,
    run_id: int | None = None,
) -> AutomationRun:
    run = session.get(AutomationRun, run_id) if run_id else None
    if run is None:
        run = AutomationRun(actor=actor)
    run.actor = actor
    run.status = "running"
    run.summary = "Admin automation cycle running."
    session.add(run)
    session.commit()
    session.refresh(run)
    logger.info("DIP automation run %s started by %s", run.id, actor)

    steps: list[dict] = []
    live_source_fetcher = cached_source_fetcher(source_fetcher)

    def step(name: str, status: str, detail: str, **extra) -> None:
        steps.append({"name": name, "status": status, "detail": detail, **extra})

    try:
        pack_results = apply_all_preconfigured_packs(session, actor=actor)
        created = sum(len(item["created"]) for item in pack_results)
        updated = sum(len(item["updated"]) for item in pack_results)
        step("Apply or update customer packs", "completed", f"{len(pack_results)} packs processed; {created} created; {updated} updated.")

        news_created = refresh_news_feeds(session)
        step("Refresh official news feeds", "completed", f"{news_created} feed items created or refreshed.")

        source_results = refresh_public_sources(session, fetcher=live_source_fetcher)
        source_failures = [item for item in source_results if not item.get("ok")]
        step(
            "Refresh public sources",
            "warning" if source_failures else "completed",
            f"{len(source_results)} sources checked; {len(source_failures)} warnings.",
            warnings=source_failures[:5],
        )

        repair_count = repair_mismatched_customer_assignments(session)
        kra_runs = run_customer_kra_checks(session, fetcher=live_source_fetcher)
        kra_run_rows = [item for item in (session.get(KRAResearchRun, run_id) for run_id in kra_runs) if item]
        kra_warnings = [item for item in kra_run_rows if item.error_summary]
        step(
            "Run KRA checks",
            "warning" if kra_warnings else "completed",
            f"{len(kra_runs)} KRA runs completed; {repair_count} mismatched assignments repaired; {len(kra_warnings)} AI/runtime warnings.",
            warnings=[item.error_summary for item in kra_warnings[:5]],
        )

        market_result = run_public_market_keyword_sweep(session)
        market_repair_count = repair_low_quality_market_opportunities(session)
        market_errors = list(market_result.get("errors") or [])
        step(
            "Run public opportunity keyword sweep",
            "warning" if market_errors else "completed",
            (
                f"{market_result.get('keywords', 0)} keyword families searched; "
                f"{market_result.get('created', 0)} opportunities created; "
                f"{market_result.get('updated', 0)} updated; "
                f"{market_result.get('skipped', 0)} filtered out; "
                f"{market_repair_count} existing market record(s) quality-gated."
            ),
            warnings=market_errors,
        )

        review_result = auto_prepare_review_queue(session)
        step(
            "Classify opportunities and requirements",
            "completed",
            (
                f"{review_result.get('auto_approved', 0)} opportunities auto-approved; "
                f"{review_result.get('review_required', 0)} queued for review; "
                f"{review_result.get('assigned_customers', 0)} customer assignments; "
                f"{review_result.get('assigned_business_units', 0)} BU assignments; "
                f"{review_result.get('requirements', 0)} requirements categorised."
            ),
        )

        retrieval_runs = run_enabled_portal_connectors(session, fetcher=connector_fetcher) if connector_fetcher else run_enabled_portal_connectors(session)
        automated_runs = [item for item in retrieval_runs if item.status == "completed"]
        blocked_runs = [item for item in retrieval_runs if item.status != "completed"]
        step(
            "Run approved portal retrieval",
            "warning" if blocked_runs else "completed",
            f"{len(automated_runs)} completed; {len(blocked_runs)} blocked or failed.",
        )

        post_retrieval_review = auto_prepare_review_queue(session)
        if (
            post_retrieval_review.get("opportunities")
            or post_retrieval_review.get("requirements")
            or post_retrieval_review.get("questions")
        ):
            step(
                "Classify retrieved intelligence",
                "completed",
                (
                    f"{post_retrieval_review.get('auto_approved', 0)} opportunities auto-approved; "
                    f"{post_retrieval_review.get('requirements', 0)} requirements and "
                    f"{post_retrieval_review.get('questions', 0)} quality questions categorised after retrieval."
                ),
            )

        task_result = complete_automated_portal_tasks(session)
        step(
            "Confirm portal tasks are complete",
            "warning" if task_result["manual_open"] else "completed",
            f"{task_result['completed']} automated tasks completed; {task_result['manual_open']} manual/account tasks remain open.",
        )

        report = create_report(
            session,
            f"DIP executive intelligence pack {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
            report_type="executive_pack",
            include_ai_brief=False,
        )
        step("Generate a report", "completed", f"Report {report.id} generated.", report_id=report.id)

        stored_path = store_report_export(report, export_format)
        step("Generate branded report export", "completed", f"{export_format.upper()} report export stored at {stored_path}.")

        config = get_email_configuration(session)
        recipients = split_recipients(email_recipients or config.default_recipients)
        email_log_id = None
        if recipients:
            email_log = send_or_store_email(
                session,
                config,
                recipients=recipients,
                subject=report.report_name,
                body="Please find the attached Data Intelligence Portal report for review.",
                report=report,
                export_format=export_format,
            )
            email_log_id = email_log.id
            step("Email the report", email_log.status, f"Email delivery status: {email_log.status}.", email_log_id=email_log.id)
        else:
            step("Email the report", "warning", "No agreed recipients configured; report email was not created.")

        audit_count = len(list(session.exec(select(AuditEvent).order_by(col(AuditEvent.created_at).desc()).limit(25))))
        step("Check the audit log", "completed", f"Latest {audit_count} audit events are available in Admin > Audit.")

        run.status = "completed"
        run.report_id = report.id
        run.stored_report_path = stored_path
        run.email_log_id = email_log_id
        run.summary = f"Automation complete: {len(source_results)} sources, {len(kra_runs)} KRA runs, report {report.id}."
    except Exception as exc:
        run.status = "failed"
        run.summary = f"Automation failed: {str(exc)[:240]}"
        step("Automation failure", "failed", str(exc)[:500])

    run.finished_at = datetime.now(UTC)
    run.steps_json = json.dumps(steps, default=str)
    session.add(run)
    log_event(
        session,
        entity_type="AutomationRun",
        entity_id=run.id,
        action=run.status,
        summary=run.summary,
        after=compact_snapshot({"steps": steps, "stored_report_path": run.stored_report_path}),
    )
    session.commit()
    session.refresh(run)
    logger.info("DIP automation run %s finished with status %s", run.id, run.status)
    return run


def create_queued_automation_run(session: Session, actor: str = "local-user") -> AutomationRun:
    run = AutomationRun(actor=actor, status="queued", summary="Automation queued. The run will continue in the live Azure app background worker.")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def run_admin_full_cycle_background(run_id: int, actor: str, email_recipients: str = "", export_format: str = "pdf") -> None:
    try:
        with Session(engine) as session:
            run_admin_full_cycle(
                session,
                actor=actor,
                email_recipients=email_recipients,
                export_format=export_format,
                run_id=run_id,
            )
    except Exception as exc:
        logger.exception("DIP automation run %s failed outside the managed cycle", run_id)
        with Session(engine) as session:
            run = session.get(AutomationRun, run_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.now(UTC)
                run.summary = f"Automation failed before completion: {str(exc)[:220]}"
                session.add(run)
                session.commit()
    finally:
        backup_sqlite_persistent_copy()


def refresh_public_sources(session: Session, fetcher=None) -> list[dict]:
    sources = list(session.exec(select(ProcurementSource).where(ProcurementSource.active == True)))  # noqa: E712
    results: list[dict] = []
    for source in sources:
        try:
            snapshot = run_source_check(session, source.id or 0, fetcher=fetcher) if fetcher else run_source_check(session, source.id or 0)
            results.append(
                {
                    "source": source.name,
                    "ok": snapshot.ok,
                    "change_type": snapshot.change_type,
                    "status": snapshot.status_code,
                    "schema": snapshot.detected_schema,
                    "notes": snapshot.notes,
                }
            )
        except Exception as exc:
            results.append({"source": source.name, "ok": False, "error": str(exc)[:220]})
    return results


def run_customer_kra_checks(session: Session, fetcher=None) -> list[int]:
    customers = list(session.exec(select(Customer).where(Customer.active == True).order_by(col(Customer.customer_name))))  # noqa: E712
    source_ids = live_kra_source_ids(session)
    run_ids: list[int] = []
    for customer in customers:
        query = f"{customer.customer_name} {customer.domain} {customer.strategic_notes[:160]}"
        kra_run = (
            run_kra_research(session, customer_id=customer.id, source_ids=source_ids, query=query, fetcher=fetcher)
            if fetcher
            else run_kra_research(session, customer_id=customer.id, source_ids=source_ids, query=query)
        )
        if kra_run.id:
            run_ids.append(kra_run.id)
    return run_ids


def live_kra_source_ids(session: Session) -> list[int]:
    sources = list(session.exec(select(ProcurementSource).where(ProcurementSource.active == True)))  # noqa: E712
    preferred = [source.id for source in sources if source.id and source.source_key in LIVE_KRA_SOURCE_KEYS]
    if preferred:
        return preferred
    return [source.id for source in sources if source.id and source.source_type == "ocds_api"]


def cached_source_fetcher(fetcher=None):
    base_fetcher = fetcher or fetch_source_url
    cache: dict[str, FetchResult] = {}

    def fetch(url: str) -> FetchResult:
        if url not in cache:
            cache[url] = base_fetcher(url)
        return cache[url]

    return fetch


def auto_prepare_review_queue(session: Session) -> dict[str, int]:
    result = agent_classify_catalogue(session, actor="automation-agent")
    session.commit()
    return result


def complete_automated_portal_tasks(session: Session) -> dict[str, int]:
    completed = 0
    manual_open = 0
    for task in session.exec(select(DocumentRetrievalTask)):
        if task.status not in OPEN_TASK_STATUSES:
            continue
        portal = session.get(BuyerPortalInstance, task.portal_instance_id) if task.portal_instance_id else None
        mode = (portal.document_retrieval_mode if portal else "").strip()
        has_completed_run = False
        if portal and mode in AUTO_PORTAL_MODES:
            has_completed_run = (
                session.exec(
                    select(PortalRetrievalRun).where(
                        PortalRetrievalRun.portal_instance_id == portal.id,
                        PortalRetrievalRun.status == "completed",
                    )
                ).first()
                is not None
            )
        if has_completed_run:
            before = compact_snapshot(task)
            task.status = "completed"
            task.notes = _append_note(task.notes, "Automation confirmed an approved read-only retrieval completed.")
            session.add(task)
            log_event(session, entity_type="DocumentRetrievalTask", entity_id=task.id, action="auto_complete", summary=f"Completed portal task {task.task_name}", before=before, after=task)
            completed += 1
        else:
            manual_open += 1
    session.commit()
    return {"completed": completed, "manual_open": manual_open}


def store_report_export(report: IntelligenceReport, export_format: str = "md") -> str:
    payload, _media_type, _filename = report_export(report, export_format)
    out_dir = Path(get_settings().outbox_dir) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / report_filename(report, export_format)
    path.write_bytes(payload)
    return str(path)


def automation_steps(run: AutomationRun) -> list[dict]:
    try:
        return list(json.loads(run.steps_json or "[]"))
    except json.JSONDecodeError:
        return []


def automation_summary(session: Session) -> dict:
    runs = list(session.exec(select(AutomationRun).order_by(col(AutomationRun.created_at).desc()).limit(8)))
    return {
        "runs": runs,
        "latest": runs[0] if runs else None,
        "latest_steps": automation_steps(runs[0]) if runs else [],
    }


def _append_note(existing: str, note: str) -> str:
    return existing if note in (existing or "") else f"{existing}\n{note}".strip()
