from __future__ import annotations

from html import escape
import json
import textwrap

from app.models import IntelligenceReport


def report_filename(report: IntelligenceReport, export_format: str) -> str:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in report.report_name.lower()).strip("-")
    extension = {"md": "md", "html": "html", "json": "json", "txt": "txt", "pdf": "pdf"}.get(export_format, "md")
    return f"{safe_name or 'data-intelligence-report'}-{report.id}.{extension}"


def _html_report(report: IntelligenceReport) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(report.report_name)}</title>
  <style>
    body {{ margin: 0; font-family: Aptos, Segoe UI, Arial, sans-serif; color: #11141c; background: #f4f6fb; }}
    main {{ max-width: 980px; margin: 32px auto; padding: 34px; border-top: 7px solid #4b155f; background: #fff; box-shadow: 0 18px 46px rgba(24,32,56,.14); }}
    h1 {{ margin: 0 0 8px; color: #111a3a; }}
    .meta {{ color: #626b7d; font-size: 13px; }}
    pre {{ white-space: pre-wrap; font: 14px/1.55 ui-monospace, Consolas, monospace; }}
  </style>
</head>
<body><main><h1>{escape(report.report_name)}</h1><p class="meta">Data Intelligence Portal export</p><pre>{escape(report.markdown)}</pre></main></body>
</html>"""


def _pdf_literal(text: str) -> bytes:
    value = text.encode("cp1252", errors="replace")
    value = value.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + value + b")"


def _pdf_text_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw in markdown.splitlines():
        text = raw.strip()
        if not text:
            lines.append("")
            continue
        text = text.replace("**", "").replace("`", "")
        if text.startswith("#"):
            text = text.lstrip("#").strip().upper()
        wrapped = textwrap.wrap(text, width=92, replace_whitespace=False) or [""]
        lines.extend(wrapped)
    return lines


def _content_stream(report: IntelligenceReport, page_number: int, page_count: int, lines: list[str]) -> bytes:
    parts: list[bytes] = [
        b"BT /F1 9 Tf 50 760 Td " + _pdf_literal("DATA INTELLIGENCE PORTAL | COF DEMO PACK") + b" Tj ET",
        b"0.30 0.08 0.38 rg 50 742 512 3 re f",
        b"BT /F1 17 Tf 50 712 Td " + _pdf_literal(report.report_name[:72]) + b" Tj ET",
        b"BT /F1 9 Tf 50 690 Td " + _pdf_literal(f"Generated report export | page {page_number} of {page_count}") + b" Tj ET",
        b"BT /F1 9 Tf 50 668 Td 13 TL",
    ]
    for line in lines:
        parts.append(_pdf_literal(line[:115]) + b" Tj T*")
    parts.extend(
        [
            b"ET",
            b"BT /F1 8 Tf 50 34 Td " + _pdf_literal("Decision-support intelligence only. Requires human review before onward use.") + b" Tj ET",
        ]
    )
    return b"\n".join(parts)


def _pdf_report(report: IntelligenceReport) -> bytes:
    lines = _pdf_text_lines(report.markdown)
    body_lines_per_page = 46
    pages = [lines[index : index + body_lines_per_page] for index in range(0, len(lines), body_lines_per_page)] or [[]]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    page_refs: list[int] = []
    next_obj = 4
    for page_index, page_lines in enumerate(pages, start=1):
        page_obj = next_obj
        stream_obj = next_obj + 1
        next_obj += 2
        page_refs.append(page_obj)
        stream = _content_stream(report, page_index, len(pages), page_lines)
        objects[stream_obj] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        objects[page_obj] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
            + str(stream_obj).encode("ascii")
            + b" 0 R >>"
        )
    kids = b" ".join(str(ref).encode("ascii") + b" 0 R" for ref in page_refs)
    objects[2] = b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_refs)).encode("ascii") + b" >>"

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {0: 0}
    for obj_num in sorted(objects):
        offsets[obj_num] = len(pdf)
        pdf.extend(str(obj_num).encode("ascii") + b" 0 obj\n" + objects[obj_num] + b"\nendobj\n")
    xref_at = len(pdf)
    max_obj = max(objects)
    pdf.extend(b"xref\n0 " + str(max_obj + 1).encode("ascii") + b"\n")
    pdf.extend(b"0000000000 65535 f \n")
    for obj_num in range(1, max_obj + 1):
        pdf.extend(f"{offsets.get(obj_num, 0):010d} 00000 n \n".encode("ascii"))
    pdf.extend(b"trailer\n<< /Size " + str(max_obj + 1).encode("ascii") + b" /Root 1 0 R >>\nstartxref\n")
    pdf.extend(str(xref_at).encode("ascii") + b"\n%%EOF\n")
    return bytes(pdf)


def report_export(report: IntelligenceReport, export_format: str) -> tuple[bytes, str, str]:
    export_format = (export_format or "md").lower()
    if export_format == "html":
        return _html_report(report).encode("utf-8"), "text/html", report_filename(report, "html")
    if export_format == "pdf":
        return _pdf_report(report), "application/pdf", report_filename(report, "pdf")
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
