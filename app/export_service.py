from __future__ import annotations

from io import BytesIO
from html import escape
import json
import re
import textwrap

from app.models import IntelligenceReport
from app.settings import get_settings

try:  # pragma: no cover - fallback kept for extremely small/offline runtimes.
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError:  # pragma: no cover
    colors = None
    A4 = landscape = mm = None
    ParagraphStyle = getSampleStyleSheet = None
    PageBreak = Paragraph = SimpleDocTemplate = Spacer = Table = TableStyle = None


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


def _legacy_pdf_report(report: IntelligenceReport) -> bytes:
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


def _pdf_report(report: IntelligenceReport) -> bytes:
    if SimpleDocTemplate is None:
        return _legacy_pdf_report(report)

    settings = get_settings()
    brand = settings.report_brand_name or "Contracted Opportunity Finder"
    prepared_for = settings.report_prepared_for or "Procter Street"
    footer = settings.report_footer or REPORT_CAVEAT
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=sanitize_pdf_text(report.report_name),
        author=brand,
        pageCompression=0,
    )
    styles = _pdf_styles()
    story: list = [
        Paragraph(escape(brand.upper()), styles["Kicker"]),
        Paragraph(escape(report.report_name), styles["Title"]),
        Paragraph(escape(f"Prepared for {prepared_for} | {report.report_type}"), styles["Meta"]),
        Spacer(1, 5 * mm),
        Table(
            [[Paragraph(escape(footer), styles["Caveat"])]],
            colWidths=[doc.width],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff2c7")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e1c45c")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            ),
        ),
        Spacer(1, 7 * mm),
    ]
    story.extend(_markdown_to_pdf_flowables(report.markdown, styles, doc.width))
    doc.build(story, onFirstPage=_pdf_footer(footer), onLaterPages=_pdf_footer(footer))
    return buffer.getvalue()


def _pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Kicker": ParagraphStyle(
            "Kicker",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#00a7bd"),
            spaceAfter=4,
        ),
        "Title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=colors.HexColor("#2b113a"),
            spaceAfter=6,
        ),
        "Meta": ParagraphStyle("Meta", parent=base["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#546071")),
        "H1": ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#2b113a"), spaceBefore=8, spaceAfter=8),
        "H2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#4b155f"), spaceBefore=10, spaceAfter=6),
        "H3": ParagraphStyle("H3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#25314f"), spaceBefore=7, spaceAfter=4),
        "Body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=8.6, leading=11.2, textColor=colors.HexColor("#172033"), spaceAfter=3),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontSize=8.4,
            leading=10.8,
            leftIndent=9,
            firstLineIndent=-5,
            bulletIndent=0,
            textColor=colors.HexColor("#172033"),
            spaceAfter=2.5,
        ),
        "Detail": ParagraphStyle("Detail", parent=base["BodyText"], fontSize=7.9, leading=10.2, leftIndent=14, textColor=colors.HexColor("#4f5b70"), spaceAfter=2),
        "Caveat": ParagraphStyle("Caveat", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor("#4b3300"), alignment=TA_LEFT),
    }


def _markdown_to_pdf_flowables(markdown: str, styles: dict[str, ParagraphStyle], width: float) -> list:
    flowables: list = []
    table_rows: list[list[str]] = []
    section_count = 0

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        header, rows = table_rows[0], table_rows[1:]
        if rows and all(set(cell.replace(":", "").replace("-", "").strip()) == set() for cell in rows[0]):
            rows = rows[1:]
        data = [[Paragraph(_pdf_inline(cell), styles["Body"]) for cell in header]]
        data.extend([[Paragraph(_pdf_inline(cell), styles["Body"]) for cell in row] for row in rows])
        column_count = max(1, len(header))
        table = Table(data, colWidths=[width / column_count] * column_count, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0edf5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#4b155f")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9deea")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        flowables.extend([table, Spacer(1, 4 * mm)])
        table_rows = []

    for raw in markdown.splitlines():
        line = sanitize_pdf_text(raw).rstrip()
        stripped = line.strip()
        if not stripped:
            flush_table()
            flowables.append(Spacer(1, 1.8 * mm))
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip().replace("**", "") for cell in stripped.strip("|").split("|")]
            table_rows.append(cells)
            continue
        flush_table()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            text = stripped.lstrip("#").strip()
            style = styles["H1"] if hashes == 1 else styles["H2"] if hashes == 2 else styles["H3"]
            if hashes == 2:
                section_count += 1
                if section_count in {5, 9, 13}:
                    flowables.append(PageBreak())
            flowables.append(Paragraph(_pdf_inline(text), style))
        elif stripped.startswith("- "):
            flowables.append(Paragraph(_pdf_inline(stripped[2:]), styles["Bullet"], bulletText="-"))
        elif line.startswith("  "):
            flowables.append(Paragraph(_pdf_inline(stripped), styles["Detail"]))
        else:
            flowables.append(Paragraph(_pdf_inline(stripped), styles["Body"]))
    flush_table()
    return flowables


def _pdf_inline(text: str) -> str:
    safe = escape(sanitize_pdf_text(text)).replace("**", "")
    safe = re.sub(r"`([^`]+)`", r"\1", safe)
    return safe


def _pdf_footer(footer: str):
    safe_footer = sanitize_pdf_text(footer)

    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d9deea"))
        canvas.setLineWidth(0.4)
        canvas.line(doc.leftMargin, 12 * mm, doc.pagesize[0] - doc.rightMargin, 12 * mm)
        canvas.setFillColor(colors.HexColor("#5d6678"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(doc.leftMargin, 7.5 * mm, safe_footer)
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 7.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


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
