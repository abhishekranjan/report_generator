"""Lay out a computed report + its narrative as a PDF (ReportLab)."""
from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from . import charts, config

# DejaVu ships with matplotlib: portable, and it has ₹ and accented Latin glyphs.
_FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
pdfmetrics.registerFont(TTFont("Body", str(_FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Body-Bold", str(_FONT_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")
_GLYPHS = set(pdfmetrics.getFont("Body").face.charWidths)

INK, INK2, MUTED, HAIR, TINT = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#f4f5f7"
W, H = A4
MARGIN = 18 * mm
CONTENT_W = W - 2 * MARGIN


def tx(s) -> str:
    """Escape for Paragraph markup and drop characters the font cannot draw."""
    s = "".join(ch for ch in str(s or "") if ord(ch) in _GLYPHS or ch in "\n\t")
    return escape(s)


def _hex(c, default="#1c5cab"):
    return c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else default


def _mix(hex_, t):
    """Blend a colour towards white by t (0..1)."""
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(v + (255 - v) * t) for v in (r, g, b))


def _on(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#ffffff" if lum < 0.45 else "#0b0b0b"


def _styles(accent):
    on = _on(accent)
    heading = accent if _on(accent) == "#ffffff" else INK  # light accents are unreadable as text
    P = ParagraphStyle
    return {
        "body": P("body", fontName="Body", fontSize=9.5, leading=14.5, textColor=colors.HexColor(INK), spaceAfter=6),
        "lead": P("lead", fontName="Body", fontSize=11, leading=16.5, textColor=colors.HexColor(INK), spaceAfter=8),
        "h2": P("h2", fontName="Body-Bold", fontSize=13.5, leading=18, textColor=colors.HexColor(heading), spaceBefore=14, spaceAfter=6),
        "label": P("label", fontName="Body-Bold", fontSize=7.5, leading=10, textColor=colors.HexColor(MUTED), spaceAfter=3),
        "bullet": P("bullet", fontName="Body", fontSize=9.5, leading=14.5, textColor=colors.HexColor(INK), leftIndent=13,
                    bulletIndent=2, spaceAfter=4),
        "small": P("small", fontName="Body", fontSize=7.8, leading=11, textColor=colors.HexColor(INK2), spaceAfter=3),
        "cov_kicker": P("ck", fontName="Body-Bold", fontSize=8, leading=11, textColor=colors.HexColor(on)),
        "cov_title": P("ct", fontName="Body-Bold", fontSize=23, leading=28, textColor=colors.HexColor(on), spaceBefore=6),
        "cov_sub": P("cs", fontName="Body", fontSize=11, leading=15.5, textColor=colors.HexColor(on), spaceBefore=6),
        "cov_meta": P("cm", fontName="Body", fontSize=8.5, leading=12.5, textColor=colors.HexColor(on), spaceBefore=10),
        "kpi_value": P("kv", fontName="Body-Bold", fontSize=15, leading=19, textColor=colors.HexColor(INK)),
        "kpi_label": P("kl", fontName="Body-Bold", fontSize=7.6, leading=10.5, textColor=colors.HexColor(INK2)),
        "kpi_note": P("kn", fontName="Body", fontSize=7, leading=9.5, textColor=colors.HexColor(MUTED)),
        "th": P("th", fontName="Body-Bold", fontSize=7.8, leading=10.5, textColor=colors.HexColor(INK2)),
        "th_r": P("thr", fontName="Body-Bold", fontSize=7.8, leading=10.5, textColor=colors.HexColor(INK2), alignment=TA_RIGHT),
        "td": P("td", fontName="Body", fontSize=8.2, leading=11.2, textColor=colors.HexColor(INK)),
        "td_r": P("tdr", fontName="Body", fontSize=8.2, leading=11.2, textColor=colors.HexColor(INK), alignment=TA_RIGHT),
        "box": P("box", fontName="Body", fontSize=9.5, leading=14.5, textColor=colors.HexColor(INK), leftIndent=13,
                 bulletIndent=2, spaceAfter=4),
    }


def _cover(st, accent, kicker, title, sub, meta_lines):
    cell = [Paragraph(tx(kicker.upper()), st["cov_kicker"]), Paragraph(tx(title), st["cov_title"])]
    if sub:
        cell.append(Paragraph(tx(sub), st["cov_sub"]))
    cell.append(Paragraph("<br/>".join(tx(m) for m in meta_lines if m), st["cov_meta"]))
    t = Table([[cell]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(accent)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 18), ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                           ("TOPPADDING", (0, 0), (-1, -1), 18), ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
                           ("ROUNDEDCORNERS", [6, 6, 6, 6])]))
    return t


def _kpis(st, kpis, per_row=3):
    cells = []
    for k in kpis:
        c = [Paragraph(tx(k["value"]), st["kpi_value"]), Paragraph(tx(k["label"]), st["kpi_label"])]
        if k.get("note"):
            c.append(Paragraph(tx(k["note"]), st["kpi_note"]))
        cells.append(c)
    while len(cells) % per_row:
        cells.append("")
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    t = Table(rows, colWidths=[CONTENT_W / per_row] * per_row)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(TINT)),
                           ("GRID", (0, 0), (-1, -1), 4, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    return t


def _table(st, tb, max_rows=None):
    rows = tb["rows"][:max_rows] if max_rows else tb["rows"]
    al = tb["align"]
    head = [Paragraph(tx(c), st["th_r"] if al[i] == "r" else st["th"]) for i, c in enumerate(tb["columns"])]
    body = [[Paragraph(tx(c), st["td_r"] if al[i] == "r" else st["td"]) for i, c in enumerate(r)] for r in rows]
    widths = tb.get("widths") or [1] * len(tb["columns"])
    total = float(sum(widths))
    t = Table([head] + body, colWidths=[CONTENT_W * w / total for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.HexColor("#c3c2b7")),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(HAIR)),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _chart(spec, width=CONTENT_W):
    png, ratio = charts.render(spec)
    return Image(io.BytesIO(png), width=width, height=width * ratio)


def _bullets(st, items, style="bullet"):
    return [Paragraph(tx(i), st[style], bulletText="•") for i in items]


def _numbered(st, items):
    return [Paragraph(tx(t), st["box"], bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def _callout(st, accent, title, flow):
    inner = [Paragraph(tx(title.upper()), st["label"])] + flow
    t = Table([[inner]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_mix(accent, 0.92))),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(accent)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                           ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def build_pdf(path, report: dict, narrative: dict, meta: dict) -> int:
    """meta: client_name, format, accent, module_name, source_label, dates, prompt, generated. Returns page count."""
    accent = _hex(meta.get("accent"))
    st = _styles(accent)
    newsletter = meta.get("format") == "newsletter"
    when = meta.get("generated") or datetime.now()
    title = narrative["title"]
    client = meta.get("client_name") or ""
    story = []

    if newsletter:
        story.append(_cover(st, accent, f"{config.COMPANY_NAME}  ·  Digital shelf briefing  ·  {when:%d %B %Y}",
                            narrative["headline"], title,
                            [f"Prepared for {client}", f"{meta['module_name']}  ·  {report['subject']}  ·  data: {meta['dates']}"]))
        story.append(Spacer(1, 10))
        for para in narrative["summary"][:1]:
            story.append(Paragraph(tx(para), st["lead"]))
        story.append(Paragraph("BY THE NUMBERS", st["label"]))
        story.append(_kpis(st, report["kpis"][:6]))
        secs = [s for s in report["sections"] if s["chart"]][:3] or report["sections"][:3]
        for s in secs:
            block = [Paragraph(tx(s["title"]), st["h2"]), Paragraph(tx(narrative["sections"].get(s["id"], "")), st["body"])]
            if s["chart"]:
                block.append(_chart(s["chart"], CONTENT_W * 0.8))
            elif s["table"]:
                block.append(_table(st, s["table"], 5))
            story.append(KeepTogether(block))
        if narrative["takeaways"]:
            story.append(Spacer(1, 8))
            story.append(KeepTogether([Paragraph("Also worth knowing", st["h2"])] + _bullets(st, narrative["takeaways"][:4])))
        if narrative["recommendations"]:
            story.append(Spacer(1, 8))
            story.append(KeepTogether([_callout(st, accent, "What to do next", _numbered(st, narrative["recommendations"][:4]))]))
    else:
        story.append(_cover(st, accent, f"{config.COMPANY_NAME}  ·  {meta['module_name']}", title, narrative["headline"],
                            [f"Prepared for {client}   ·   {when:%d %B %Y}",
                             f"Subject: {report['subject']}   ·   Data: {meta['dates']}"]))
        story.append(Spacer(1, 12))
        story.append(_kpis(st, report["kpis"]))
        story.append(Paragraph("Executive summary", st["h2"]))
        for para in narrative["summary"]:
            story.append(Paragraph(tx(para), st["body"]))
        if narrative["takeaways"]:
            story.append(Spacer(1, 4))
            story.append(KeepTogether([_callout(st, accent, "Key takeaways", _bullets(st, narrative["takeaways"], "box"))]))
        for s in report["sections"]:
            head = [Paragraph(tx(s["title"]), st["h2"]), Paragraph(tx(narrative["sections"].get(s["id"], "")), st["body"])]
            if s["chart"]:
                head.append(_chart(s["chart"]))
                story.append(CondPageBreak(60 * mm))
                story.append(KeepTogether(head))
                if s["table"]:
                    story.append(Spacer(1, 6))
                    story.append(_table(st, s["table"]))
            else:
                story.append(CondPageBreak(50 * mm))
                story.extend(head)
                if s["table"]:
                    story.append(_table(st, s["table"]))
        if narrative["recommendations"]:
            story.append(CondPageBreak(55 * mm))
            story.append(Paragraph("Recommended next steps", st["h2"]))
            story.append(_callout(st, accent, "Actions", _numbered(st, narrative["recommendations"])))

    # methodology / data notes
    story.append(Spacer(1, 12))
    notes = [Paragraph("ABOUT THIS BRIEFING", st["label"]) if newsletter else Paragraph("About this report", st["h2"]),
             Paragraph(tx(f"Source: {meta['source_label']}, crawled {meta['dates']}; {report['rows']:,} records in scope. "
                          f"Scope: {report['scope']}."), st["small"])]
    if not newsletter:
        notes += [Paragraph(tx(d), st["small"], bulletText="•") for d in report["definitions"]]
        if meta.get("prompt"):
            notes.append(Paragraph(tx(f"Request: “{meta['prompt'][:400]}”"), st["small"]))
    who = (f"Commentary written by {narrative.get('model') or config.GEMINI_MODEL} from these computed figures; review before external distribution."
           if narrative.get("source") == "gemini" else "Commentary assembled from the computed figures using standard templates.")
    notes.append(Paragraph(tx("All figures are calculated directly from the crawl data. " + who +
                              " Figures describe what was visible on the platform at crawl time, not sales."), st["small"]))
    story.append(KeepTogether(notes))

    site = re.sub(r"^https?://|/+$", "", config.COMPANY_WEBSITE)
    footer = "  ·  ".join(x for x in (config.COMPANY_NAME, site, f"Prepared for {client}" if client else "") if x)

    def _page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Body", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(MARGIN, 10 * mm, tx_plain(footer))
        canvas.drawRightString(W - MARGIN, 10 * mm, f"Page {doc.page}")
        if doc.page > 1:
            canvas.drawString(MARGIN, H - 11 * mm, tx_plain(title)[:95])
            canvas.setStrokeColor(colors.HexColor(HAIR))
            canvas.setLineWidth(0.5)
            canvas.line(MARGIN, H - 13 * mm, W - MARGIN, H - 13 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=17 * mm,
                            bottomMargin=17 * mm, title=tx_plain(title), author=config.COMPANY_NAME,
                            subject=tx_plain(f"{meta['module_name']} – {report['subject']}"))
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return doc.page


def tx_plain(s) -> str:
    return "".join(ch for ch in str(s or "") if ord(ch) in _GLYPHS)
