from __future__ import annotations

from html import escape
import json

from app.models import IntelligenceReport


def report_filename(report: IntelligenceReport, export_format: str) -> str:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in report.report_name.lower()).strip("-")
    extension = {"md": "md", "html": "html", "json": "json", "txt": "txt"}.get(export_format, "md")
    return f"{safe_name or 'data-intelligence-report'}-{report.id}.{extension}"


def report_export(report: IntelligenceReport, export_format: str) -> tuple[bytes, str, str]:
    export_format = (export_format or "md").lower()
    if export_format == "html":
        body = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{escape(report.report_name)}</title></head>
<body><main><pre>{escape(report.markdown)}</pre></main></body>
</html>"""
        return body.encode("utf-8"), "text/html", report_filename(report, "html")
    if export_format == "json":
        payload = {
            "id": report.id,
            "report_name": report.report_name,
            "report_type": report.report_type,
            "generated_at": report.generated_at.isoformat(),
            "customer_id": report.customer_id,
            "business_unit_id": report.business_unit_id,
            "markdown": report.markdown,
        }
        return json.dumps(payload, indent=2, default=str).encode("utf-8"), "application/json", report_filename(report, "json")
    if export_format == "txt":
        return report.markdown.encode("utf-8"), "text/plain", report_filename(report, "txt")
    return report.markdown.encode("utf-8"), "text/markdown", report_filename(report, "md")
