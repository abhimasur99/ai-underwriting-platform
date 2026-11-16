"""One-page memo PDF (reportlab). Every number is filled from the result by code.

Sections: header, recommendation and reasons, deal snapshot, metrics table, exit analysis,
reconciliation and flags, open questions, risks, footer.
"""
from datetime import date
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from bridge.core import format as f
from bridge.core.placeholders import fill
from bridge.core.schema import Deal, RuleCheck, UnderwritingResult

FOOTER = ("Sample data. Illustrative thresholds, not a real lender's box. "
          "A human approves every decision.")
CALL_COLOR = {"screen": colors.HexColor("#1B7F3B"), "watch": colors.HexColor("#B26B00"),
              "decline": colors.HexColor("#B3261E")}
STATUS_COLOR = {"pass": colors.HexColor("#1B7F3B"), "watch": colors.HexColor("#B26B00"),
                "decline": colors.HexColor("#B3261E")}
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=7.6, leading=9.4)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7, leading=8.6)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=8.6, leading=10.5,
                    spaceBefore=4, spaceAfter=1.5, textColor=colors.HexColor("#1F3A5F"))
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=13, leading=15)
GRID = TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 7.4),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.4),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE6F0")),
    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2CC")),
    ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
])

_FORMATS = {"ltc": f.pct, "ltv_as_is": f.pct, "loan_to_arv": f.pct, "implied_cap_rate": f.pct,
            "rent_roll_vs_t12": f.pct, "sources_vs_uses": f.pct, "exit_dscr": f.mult,
            "refi_cushion": f.usd, "refi_cushion_stress": f.usd}


def _threshold_text(c: RuleCheck) -> str:
    fmt = _FORMATS[c.metric]
    sign = ">" if c.direction == "above" else "<"
    parts = []
    if c.watch_threshold is not None:
        parts.append(f"watch {sign}{fmt(c.watch_threshold)}")
    if c.decline_threshold is not None:
        parts.append(f"decline {sign}{fmt(c.decline_threshold)}")
    return ", ".join(parts)


def _section(title: str):
    return Paragraph(title, H2)


def render_memo(deal: Deal, result: UnderwritingResult, path: str | Path,
                as_of: date | None = None) -> Path:
    # Plain (uncompressed, non-ASCII85) streams keep the text extractable for the checker.
    rl_config.useA85 = 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    as_of = as_of or date.today()
    m, ex, st = result.metrics, result.exit, result.stress
    lr, val = deal.loan_request, deal.valuation
    holdback = lr.loan_commitment.value - lr.initial_advance.value

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(0.55 * inch, 0.4 * inch, FOOTER)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.55 * inch,
                            rightMargin=0.55 * inch, topMargin=0.45 * inch,
                            bottomMargin=0.6 * inch, pageCompression=0,
                            title=f"{deal.deal_id} screening memo", author="Bridge Loan Platform")
    width = letter[0] - 1.1 * inch
    story = []

    # header
    call_cell = Paragraph(f"CALL: {result.call.upper()}", ParagraphStyle(
        "call", parent=BODY, fontName="Helvetica-Bold", fontSize=11, leading=13,
        textColor=colors.white, alignment=1))
    head = Table([[Paragraph("Bridge loan screening memo", TITLE), call_cell],
                  [Paragraph(f"{deal.deal_id} | {deal.name}", BODY),
                   Paragraph(f"Date: {as_of.isoformat()}", BODY)]],
                 colWidths=[width * 0.72, width * 0.28])
    head.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, 0), CALL_COLOR[result.call]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story += [head]

    # recommendation (leads with the exit) and reasons
    story += [_section("Recommendation"),
              Paragraph(fill(result.narrative["summary"], result), BODY), Spacer(1, 2),
              Paragraph(fill(result.narrative["exit"], result), BODY)]
    if result.reasons:
        rows = [["Reason code", "Severity", "Detail"]] + [
            [r.code, r.severity, f.describe_reason(r)] for r in result.reasons]
        t = Table(rows, colWidths=[width * 0.30, width * 0.10, width * 0.60])
        t.setStyle(GRID)
        story += [Spacer(1, 3), t]
    else:
        story += [Spacer(1, 2), Paragraph("No rule was triggered.", BODY)]

    # snapshot
    story.append(_section("Deal snapshot"))
    su_rows = max(len(deal.sources_uses.sources), len(deal.sources_uses.uses))
    snapshot = [
        ["Property", f"{deal.property.address.value}", "Loan commitment",
         f.usd(lr.loan_commitment.value)],
        ["Type | units", f"{deal.property.asset_type.value} | {deal.property.unit_count.value} "
                         f"units, {deal.property.occupied_units.value} occupied",
         "Initial advance | holdback",
         f"{f.usd(lr.initial_advance.value)} | {f.usd(holdback)}"],
        ["Sponsor", deal.sponsor.name.value, "Note rate (interest-only)",
         f.pct(lr.note_rate.value)],
        ["As-is value | ARV", f"{f.usd(val.as_is_value.value)} | {f.usd(val.arv.value)}",
         "Purchase price | renovation",
         f"{f.usd(deal.purchase.purchase_price.value)} | "
         f"{f.usd(deal.renovation.renovation_budget.value)}"],
        ["Stabilized NOI", f.usd(deal.pro_forma.stabilized_noi.value) + " (borrower pro forma)",
         "In-place NOI (T-12)", f.usd(deal.t12.in_place_noi.value)],
    ]
    t = Table(snapshot, colWidths=[width * 0.16, width * 0.34, width * 0.22, width * 0.28])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.4),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 7.4),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 7.4),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2CC")),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]))
    story.append(t)
    su = [["Sources", "Amount", "Uses", "Amount"]]
    for i in range(su_rows):
        s = deal.sources_uses.sources[i] if i < len(deal.sources_uses.sources) else None
        u = deal.sources_uses.uses[i] if i < len(deal.sources_uses.uses) else None
        su.append([s.name if s else "", f.usd(s.amount) if s else "",
                   u.name if u else "", f.usd(u.amount) if u else ""])
    su.append(["Total sources", f.usd(sum(r.amount for r in deal.sources_uses.sources)),
               "Total uses", f.usd(sum(r.amount for r in deal.sources_uses.uses))])
    t = Table(su, colWidths=[width * 0.3, width * 0.2, width * 0.3, width * 0.2])
    t.setStyle(GRID)
    story += [Spacer(1, 3), t]

    # metrics
    story.append(_section("Metrics"))
    rows = [["Metric", "Value", "Threshold", "Status"]]
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 7.4),
             ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.4),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE6F0")),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2CC")),
             ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]
    for i, c in enumerate(result.rule_checks, start=1):
        rows.append([c.label, _FORMATS[c.metric](c.value), _threshold_text(c), c.status])
        style.append(("TEXTCOLOR", (3, i), (3, i), STATUS_COLOR[c.status]))
    rows.append(["Debt yield (stabilized)", f.pct(m.debt_yield_stabilized), "informational", "-"])
    rows.append(["DSCR (in place)", f.mult(m.dscr_in_place), "informational", "-"])
    t = Table(rows, colWidths=[width * 0.28, width * 0.17, width * 0.43, width * 0.12])
    t.setStyle(TableStyle(style))
    story.append(t)

    # exit analysis
    story.append(_section("Exit analysis (take-out sizing)"))
    exit_rows = [
        ["", "Base", "Stress"],
        ["NOI | take-out rate", f"{f.usd(ex.noi)} | {f.pct(ex.rate)}",
         f"{f.usd(st.noi)} | {f.pct(st.rate)}"],
        ["DSCR cap", f.usd(ex.caps.dscr), f.usd(st.caps.dscr)],
        ["LTV cap", f.usd(ex.caps.ltv), f.usd(st.caps.ltv)],
        ["Debt yield cap", f.usd(ex.caps.debt_yield), f.usd(st.caps.debt_yield)],
        ["Binding cap | take-out max", f"{f.BINDING_LABEL[ex.binding]} | {f.usd(ex.takeout_max)}",
         f"{f.BINDING_LABEL[st.binding]} | {f.usd(st.takeout_max)}"],
        ["Payoff | refi cushion", f"{f.usd(ex.payoff)} | {f.usd(ex.refi_cushion)}",
         f"{f.usd(st.payoff)} | {f.usd(st.refi_cushion)}"],
        ["Exit DSCR", f.mult(ex.exit_dscr), f.mult(st.exit_dscr)],
    ]
    t = Table(exit_rows, colWidths=[width * 0.30, width * 0.35, width * 0.35])
    t.setStyle(GRID)
    story.append(t)

    # reconciliation and flags
    story.append(_section("Reconciliation and flags"))
    rec = [["Check", "Result", "Status"]]
    style = list(GRID.getCommands())
    for i, item in enumerate(result.reconciliation, start=1):
        if item.gap is not None:
            text = f"{f.pct(item.gap)} gap ({f.usd(item.a)} vs {f.usd(item.b)})"
        else:
            text = f"stated {item.a:g} vs rent roll {item.b:g}"
        rec.append([item.name, text, item.status])
        style.append(("TEXTCOLOR", (2, i), (2, i), STATUS_COLOR[item.status]))
    t = Table(rec, colWidths=[width * 0.25, width * 0.63, width * 0.12])
    t.setStyle(TableStyle(style))
    story.append(t)
    for flag in result.flags:
        story.append(Paragraph(f"Flag {flag.code}: {flag.message}", SMALL))

    # open questions and risks
    story.append(_section("Open questions"))
    if result.open_questions:
        for q in result.open_questions:
            story.append(Paragraph(f"- {q}", SMALL))
    else:
        story.append(Paragraph("None.", SMALL))
    story += [_section("Risks and limits"),
              Paragraph(fill(result.narrative["risks"], result), SMALL)]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
