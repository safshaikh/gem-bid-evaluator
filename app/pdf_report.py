"""Generate comprehensive executive PDF evaluation report using ReportLab."""

import io
from typing import List
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.jobs import Tender
from app.matrix import build_matrix
from app.schemas import EvaluationResult, Verdict


def generate_pdf_report(tender: Tender) -> bytes:
    """Generate a formal PDF evaluation report for procurement records."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    bold_body_style = ParagraphStyle(
        "ReportBoldBody",
        parent=body_style,
        fontName="Helvetica-Bold",
    )

    story = []

    # Title & Subtitle
    story.append(Paragraph("BidParakh - GeM Technical Bid Evaluation Report", title_style))
    story.append(
        Paragraph(
            f"<b>Tender ID:</b> {tender.tender_id} &nbsp;|&nbsp; <b>Philosophy:</b> AI reads, code decides.",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 8))

    eval_res: EvaluationResult = tender.evaluation_result or EvaluationResult(tender_id=tender.tender_id)
    bidder_names = [b.name for b in tender.bidders]

    # Section 1: Executive Summary Metrics
    story.append(Paragraph("1. Executive Summary", h2_style))
    pass_cnt = sum(1 for r in eval_res.results if r.verdict == Verdict.PASS)
    fail_cnt = sum(1 for r in eval_res.results if r.verdict == Verdict.FAIL)
    rev_cnt = sum(1 for r in eval_res.results if r.verdict == Verdict.REVIEW)
    override_cnt = len(eval_res.overrides)

    summary_data = [
        [
            Paragraph("<b>Total Bidders</b>", bold_body_style),
            Paragraph(str(len(tender.bidders)), body_style),
            Paragraph("<b>Resolved Criteria</b>", bold_body_style),
            Paragraph(str(len(eval_res.criteria)), body_style),
        ],
        [
            Paragraph("<b>Passed Checks</b>", bold_body_style),
            Paragraph(f"<font color='#16a34a'>{pass_cnt}</font>", body_style),
            Paragraph("<b>Failed Checks</b>", bold_body_style),
            Paragraph(f"<font color='#dc2626'>{fail_cnt}</font>", body_style),
        ],
        [
            Paragraph("<b>Under Review</b>", bold_body_style),
            Paragraph(f"<font color='#d97706'>{rev_cnt}</font>", body_style),
            Paragraph("<b>Officer Overrides</b>", bold_body_style),
            Paragraph(f"<font color='#7c3aed'>{override_cnt}</font>", body_style),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[120, 130, 130, 140])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # Section 2: Verdict Matrix
    story.append(Paragraph("2. Technical Evaluation Matrix", h2_style))
    matrix_rows = build_matrix(eval_res.criteria, eval_res.results)

    # Build override lookup: (crit_id, bidder_name) -> OfficerOverride
    override_map = {(o.criterion_id, o.bidder_name): o for o in eval_res.overrides}

    header_row = [Paragraph("<b>Evaluation Criterion</b>", bold_body_style)]
    for b_name in bidder_names:
        header_row.append(Paragraph(f"<b>{b_name}</b>", bold_body_style))

    table_data = [header_row]
    for row in matrix_rows:
        crit_title = row[0]
        # find criterion id
        matching_crit = next((c for c in eval_res.criteria if c.title == crit_title), None)
        crit_id = matching_crit.id if matching_crit else ""

        table_row = [Paragraph(f"<b>{crit_title}</b>", body_style)]
        for idx, verdict in enumerate(row[1:]):
            b_name = bidder_names[idx] if idx < len(bidder_names) else ""
            override = override_map.get((crit_id, b_name))

            if override:
                cell_text = (
                    f"<b>{override.new_verdict.value}</b><br/>"
                    f"<font size='7' color='#7c3aed'>(Override: {verdict})</font>"
                )
            elif verdict == "PASS":
                cell_text = "<font color='#15803d'><b>PASS</b></font>"
            elif verdict == "FAIL":
                cell_text = "<font color='#b91c1c'><b>FAIL</b></font>"
            else:
                cell_text = "<font color='#b45309'><b>REVIEW</b></font>"

            table_row.append(Paragraph(cell_text, body_style))
        table_data.append(table_row)

    col_w = 540 / max(len(header_row), 1)
    matrix_table = Table(table_data, colWidths=[col_w] * len(header_row))
    matrix_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(matrix_table)
    story.append(Spacer(1, 12))

    # Section 3: Statutory Overrides by Procurement Officer
    if eval_res.overrides:
        story.append(Paragraph("3. Officer Statutory Overrides Audit Log", h2_style))
        override_headers = [
            Paragraph("<b>Criterion</b>", bold_body_style),
            Paragraph("<b>Bidder</b>", bold_body_style),
            Paragraph("<b>Change</b>", bold_body_style),
            Paragraph("<b>Mandatory Legal Justification</b>", bold_body_style),
            Paragraph("<b>Timestamp</b>", bold_body_style),
        ]
        override_table_data = [override_headers]
        for o in eval_res.overrides:
            override_table_data.append(
                [
                    Paragraph(o.criterion_id, body_style),
                    Paragraph(o.bidder_name, body_style),
                    Paragraph(f"{o.old_verdict.value} &rarr; <b>{o.new_verdict.value}</b>", body_style),
                    Paragraph(o.justification, body_style),
                    Paragraph(o.timestamp[:19].replace("T", " "), body_style),
                ]
            )
        ov_table = Table(override_table_data, colWidths=[90, 100, 80, 180, 90])
        ov_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ede9fe")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c4b5fd")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(ov_table)
        story.append(Spacer(1, 12))

    # Section 4: Draft Speaking Orders for Rejections
    fail_results = [r for r in eval_res.results if r.verdict == Verdict.FAIL and r.speaking_order_line]
    if fail_results:
        sec_num = 4 if eval_res.overrides else 3
        story.append(Paragraph(f"{sec_num}. Draft Rejection Speaking Orders", h2_style))
        for r in fail_results:
            p_text = f"&bull; <b>{r.bidder_name}:</b> {r.speaking_order_line}"
            story.append(Paragraph(p_text, body_style))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 8))

    doc.build(story)
    return buf.getvalue()
