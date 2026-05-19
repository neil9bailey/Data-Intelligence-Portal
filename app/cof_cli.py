from __future__ import annotations

import json

from sqlmodel import Session, select

from app.database import backup_sqlite_persistent_copy, engine, init_db
from app.intelligence_packs import apply_intelligence_pack, get_preconfigured_customer_pack
from app.models import Customer, DigestProfile, IntelligenceReport, Opportunity


def main() -> int:
    init_db()
    with Session(engine) as session:
        pack = get_preconfigured_customer_pack("procter_street_cof")
        apply_intelligence_pack(session, pack, actor="cof-cli")
        counts = {
            "cof_clients": len([item for item in session.exec(select(Customer)) if item.customer_name.startswith("COF Client ")]),
            "cof_opportunities": len([item for item in session.exec(select(Opportunity)) if str(item.notice_identifier).startswith(("cof-pipeline", "cof-live-pilot"))]),
            "cof_digest_profiles": len(list(session.exec(select(DigestProfile).where(DigestProfile.name == "COF Monday report send")))),
            "cof_reports": len(list(session.exec(select(IntelligenceReport).where(IntelligenceReport.report_type.in_(["cof_internal_review_pack", "cof_final_customer_pack", "cof_weekly_portfolio_report"]))))),
        }
    backup_sqlite_persistent_copy()
    print(json.dumps(counts, indent=2))
    return 0 if counts["cof_clients"] >= 11 and counts["cof_opportunities"] >= 10 and counts["cof_reports"] >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
