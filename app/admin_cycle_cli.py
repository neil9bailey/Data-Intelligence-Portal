from __future__ import annotations

import json
import os

from sqlmodel import Session

from app.automation import automation_steps, run_admin_full_cycle
from app.database import backup_sqlite_persistent_copy, engine, init_db


def main() -> int:
    init_db()
    with Session(engine) as session:
        run = run_admin_full_cycle(
            session,
            actor=os.getenv("DIP_CLI_ACTOR", "azure-cli-admin"),
            email_recipients=os.getenv("DIP_CLI_EMAIL_RECIPIENTS", ""),
            export_format=os.getenv("DIP_CLI_EXPORT_FORMAT", "pdf"),
        )
        payload = {
            "run_id": run.id,
            "status": run.status,
            "summary": run.summary,
            "report_id": run.report_id,
            "stored_report_path": run.stored_report_path,
            "steps": automation_steps(run),
        }
    backup_sqlite_persistent_copy()
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
