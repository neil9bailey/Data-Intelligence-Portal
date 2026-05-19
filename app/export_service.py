from __future__ import annotations

from html import escape
import json
import textwrap

from app.models import IntelligenceReport
from app.settings import get_settings


REPORT_CAVEAT = "Human review required. Not a bid, legal, procurement or compliance decision."


def sanitize_pdf_text(value: str) -> str:
    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\ufffd": "",
    }
    text = str(value or "")
    for source, target in replacements.items():
        text = text.replace(source, target)
    return "".join(ch if ch in {"\n", "\t"} or ord(ch) >= 32 else " " for ch in text)


def report_filename(report: IntelligenceReport, export_format: str) -> str:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in report.report_name.lower()).strip("-")
    extension = {"md": "md", "html": "html", "json": "json", "txt": "txt", "pdf": "pdf"}.get(export_format, "md")
    return f"{safe_name or 'data-intelligence-report'}-{report.id}.{extension}"


def _html_report(report: IntelligenceReport) -> str:
    settings = get_settings()
    brand = settings.report_brand_name or "Contracted Opportunity Finder"
    prepared_for = settings.report_prepared_for or "Procter Street"
    footer = settings.report_footer or REPORT_CAVEAT
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(report.report_name)}</title>
  <style>
    :root {{ --ink:#121621; --muted:#5d6678; --purple:#4b155f; --cyan:#00a7bd; --line:#dbe2ee; --soft:#f5f7fb; }}
    body {{ margin: 0; font-family: Aptos, Segoe UI, sans-serif; color: var(--ink); background: #eef2f7; }}
    main {{ max-width: 1080px; margin: 28px auto; background: #fff; box-shadow: 0 22px 52px rgba(22,30,46,.16); }}
    header {{ padding: 38px 42px 30px; background: linear-gradient(135deg, var(--purple), #25314f 58%, var(--cyan)); color: #fff; }}
    section {{ padding: 28px 42px 38px; }}
    h1 {{ margin: 0 0 10px; font-size: 36px; letter-spacing: 0; }}
    h2 {{ margin: 30px 0 10px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--purple); }}
    h3 {{ margin: 22px 0 8px; color: #24304c; }}
    p, li {{ line-height: 1.55; }}
    ul {{ padding-left: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0 18px; font-size: 13px; }}
    th {{ text-align: left; color: var(--purple); background: #f0edf5; }}
    th, td {{ border: 1px solid var(--line); padding: 8px 9px; vertical-align: top; }}
    .meta {{ color: #dfe8f2; font-size: 13px; }}
    .caveat {{ margin: 0; padding: 14px 42px; background: #fff2c7; color: #493300; font-weight: 700; }}
    .brand-kicker {{ text-transform: uppercase; letter-spacing: .12em; font-size: 12px; font-weight: 800; }}
    .footer {{ padding: 18px 42px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }}
  </style>
</head>
<body><main><header><div class="brand-kicker">{escape(brand)}</div><h1>{escape(report.report_name)}</h1><p class="meta">Prepared for {escape(prepared_for)} | {escape(report.report_type)}</p></header><p class="caveat">{escape(footer)}</p><section>{_markdown_to_html(report.markdown)}</section><div class="footer">{escape(footer)}</div></main></body>
</html>"""


def _markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    in_table = False
    table_rows: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            blocks.append("</ul>")
            in_list = False

    def close_table() -> None:
        nonlocal in_table, table_rows
        if in_table:
            blocks.append("<table>" + "".join(table_rows) + "</table>")
            table_rows = []
            in_table = False

    for raw in markdown.splitlines():
        line = sanitize_pdf_text(raw).strip()
        if not line:
            close_list()
            close_table()
            continue
        if line.startswith("|") and line.endswith("|"):
            close_list()
            cells = [escape(cell.strip()).replace("**", "") for cell in line.strip("|").split("|")]
            if all(set(cell.replace(":", "").replace("-", "").strip()) == set() for cell in cells):
                in_table = True
                continue
            tag = "th" if not in_table else "td"
            table_rows.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            in_table = True
            continue
        close_table()
        if line.startswith("#"):
            level = min(3, max(1, len(line) - len(line.lstrip("#"))))
            blocks.append(f"<h{level}>{escape(line.lstrip('#').strip()).replace('**', '')}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{_inline_markdown(line[2:])}</li>")
        else:
            close_list()
            blocks.append(f"<p>{_inline_markdown(line)}</p>")
    close_list()
    close_table()
    return "\n".join(blocks)


def _inline_markdown(text: str) -> str:
    escaped = escape(text)
    return re_bold(escaped)


def re_bold(text: str) -> str:
    import re

    return re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)


def _pdf_literal(text: str) -> bytes:
    value = sanitize_pdf_text(text).encode("cp1252", errors="replace")
    value = value.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + value + b")"


def _pdf_text_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw in markdown.splitlines():
        text = sanitize_pdf_text(raw).strip()
        if not text:
            lines.append("")
            continue
        text = text.replace("**", "").replace("`", "")
        if text.startswith("|") and text.endswith("|"):
            cells = [cell.strip() for cell in text.strip("|").split("|")]
            if all(set(cell.replace(":", "").replace("-", "").strip()) == set() for cell in cells):
                continue
            text = "   ".join(cell for cell in cells if cell)
        if text.startswith("#"):
            text = text.lstrip("#").strip().upper()
        wrapped = textwrap.wrap(text, width=92, replace_whitespace=False) or [""]
        lines.extend(wrapped)
    return lines


def _content_stream(report: IntelligenceReport, page_number: int, page_count: int, lines: list[str]) -> bytes:
    settings = get_settings()
    brand = settings.report_brand_name or "Contracted Opportunity Finder"
    prepared_for = settings.report_prepared_for or "Procter Street"
    footer = settings.report_footer or REPORT_CAVEAT
    parts: list[bytes] = [
        b"BT /F1 9 Tf 50 760 Td " + _pdf_literal(f"{brand.upper()} | WEEKLY OPPORTUNITY PACK") + b" Tj ET",
        b"0.30 0.08 0.38 rg 50 742 512 3 re f",
        b"BT /F1 17 Tf 50 712 Td " + _pdf_literal(sanitize_pdf_text(report.report_name)[:72]) + b" Tj ET",
        b"BT /F1 9 Tf 50 690 Td " + _pdf_literal(f"Prepared for {prepared_for} | page {page_number} of {page_count}") + b" Tj ET",
        b"BT /F1 9 Tf 50 668 Td 13 TL",
    ]
    for line in lines:
        parts.append(_pdf_literal(line[:115]) + b" Tj T*")
    parts.extend(
        [
            b"ET",
            b"BT /F1 8 Tf 50 34 Td " + _pdf_literal(footer[:115]) + b" Tj ET",
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
        settings = get_settings()
        readiness = _report_readiness_metadata(report.markdown)
        payload = {
            "id": report.id,
            "report_name": report.report_name,
            "report_type": report.report_type,
            "brand": settings.report_brand_name,
            "prepared_for": settings.report_prepared_for,
            "readiness": readiness,
            "generated_at": report.generated_at.isoformat(),
            "customer_id": report.customer_id,
            "business_unit_id": report.business_unit_id,
            "caveat": settings.report_footer or REPORT_CAVEAT,
            "markdown": report.markdown,
        }
        return json.dumps(payload, indent=2, default=str).encode("utf-8"), "application/json", report_filename(report, "json")
    if export_format == "txt":
        return report.markdown.encode("utf-8"), "text/plain", report_filename(report, "txt")
    return report.markdown.encode("utf-8"), "text/markdown", report_filename(report, "md")


def _report_readiness_metadata(markdown: str) -> dict[str, object]:
    status = ""
    blockers: list[str] = []
    warnings: list[str] = []
    current = ""
    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if line.startswith("**Status:**"):
            status = line.split(":", 1)[1].replace("**", "").strip()
        elif line.startswith("### Final Pack Readiness Blockers"):
            current = "warnings"
        elif line.startswith("### Operating Attention Items"):
            current = "warnings"
        elif line.startswith("### Readiness Warnings"):
            current = "warnings"
        elif line.startswith("## "):
            current = ""
        elif line.startswith("- ") and current == "blockers":
            blockers.append(line[2:])
        elif line.startswith("- ") and current == "warnings":
            warnings.append(line[2:])
    return {"status": status, "ready_for_weekly_send": status.lower() == "ready for weekly send", "blockers": blockers, "warnings": warnings}
