"""FastAPI main application module for BidParakh tender evaluation."""

import html
from typing import List
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, Response

from app.atc_flag import flag_clause
from app.config import get_fallback_model, get_model, is_ai_configured
from app.evidence_guard import apply_guard
import app.gemini_client as gemini_client
from app.jobs import (
    BidderPack,
    Tender,
    UploadedDoc,
    cache_key,
    create_tender,
    get_tender,
    load_cached,
    save_cached,
)
from app.matrix import build_matrix, to_csv, to_html
from app.pdf_text import extract_pages
from app.resolver import resolve_criteria, resolve_void_list
from app.rules import evaluate
from app.schemas import (
    AtcClause,
    AtcFlag,
    Criterion,
    CriterionResult,
    EvaluationResult,
    Verdict,
    VoidListItem,
)

app = FastAPI(
    title="BidParakh",
    description="Officer-side GeM bid evaluation: AI reads, code decides.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    """Return application health status and AI configuration."""
    return {
        "status": "ok",
        "ai_configured": is_ai_configured(),
        "model": get_model(),
        "fallback_model": get_fallback_model(),
    }


@app.post("/tenders")
async def create_tender_endpoint(files: List[UploadFile] = File(...)) -> dict:
    """Upload tender PDFs preserving order (main bid first, then corrigenda)."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    tender = create_tender()
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")
        content = await f.read()
        pages = extract_pages(content)
        tender.documents.append(UploadedDoc(name=f.filename, bytes_data=content, pages=pages))

    total_pages = sum(len(d.pages) for d in tender.documents)
    return {
        "tender_id": tender.tender_id,
        "documents": [d.name for d in tender.documents],
        "total_pages": total_pages,
    }


@app.post("/tenders/{tender_id}/bidders")
async def add_bidder_endpoint(
    tender_id: str,
    name: str = Form(...),
    files: List[UploadFile] = File(...),
) -> dict:
    """Add a bidder pack with evidence PDFs to a tender."""
    tender = get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")

    docs: List[UploadedDoc] = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")
        content = await f.read()
        pages = extract_pages(content)
        docs.append(UploadedDoc(name=f.filename, bytes_data=content, pages=pages))

    tender.bidders.append(BidderPack(name=name, documents=docs))
    return {
        "bidder_name": name,
        "documents": [d.name for d in docs],
    }


def _run_pipeline(tender: Tender) -> EvaluationResult:
    """Run extraction, resolution, ATC check, guard, and rules engine."""
    # 1. Extraction per document in stored order
    criteria_by_doc: List[List[Criterion]] = []
    void_lists_by_doc: List[List[VoidListItem]] = []
    all_atc_clauses: List[AtcClause] = []

    for doc in tender.documents:
        criteria_by_doc.append(gemini_client.extract_criteria(doc.pages, doc.name))
        void_lists_by_doc.append(gemini_client.extract_void_list(doc.pages, doc.name))
        all_atc_clauses.extend(gemini_client.extract_atc_clauses(doc.pages, doc.name))

    # 2. Resolver merge
    merged_criteria = resolve_criteria(criteria_by_doc)
    merged_void_list = resolve_void_list(void_lists_by_doc)

    # 3. Classify ATC clauses
    atc_flags = [flag_clause(cl, merged_void_list) for cl in all_atc_clauses]

    # 4. Bidder evaluation
    all_results: List[CriterionResult] = []
    for bidder in tender.bidders:
        bidder_pages = [p for d in bidder.documents for p in d.pages]
        evidence = gemini_client.extract_bidder_evidence(bidder_pages, bidder.name, merged_criteria)
        evidence.fields = apply_guard(evidence.fields, bidder_pages)

        for crit in merged_criteria:
            res = evaluate(crit, evidence)
            res.bidder_name = bidder.name
            all_results.append(res)

    return EvaluationResult(
        tender_id=tender.tender_id,
        cached=False,
        degraded=False,
        criteria=merged_criteria,
        void_list=merged_void_list,
        atc_flags=atc_flags,
        results=all_results,
        warnings=[],
    )


@app.post("/tenders/{tender_id}/evaluate", response_model=EvaluationResult)
def evaluate_tender_endpoint(tender_id: str) -> EvaluationResult:
    """Execute evaluation pipeline with disk replay caching and non-500 degraded safety."""
    tender = get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")

    # Check replay cache
    ckey = cache_key(tender)
    cached_res = load_cached(ckey)
    if cached_res:
        tender.evaluation_result = cached_res
        return cached_res

    # Unconfigured AI safety
    if not is_ai_configured():
        crit_placeholder = [
            Criterion(
                id="default_check",
                title="Eligibility Verification",
                rule_type="MANUAL",
                source_doc="tender",
                source_page=1,
                source_quote="Eligibility Verification",
            )
        ]
        degraded_res = EvaluationResult(
            tender_id=tender_id,
            cached=False,
            degraded=True,
            criteria=crit_placeholder,
            results=[
                CriterionResult(
                    bidder_name=b.name,
                    criterion_id="default_check",
                    verdict=Verdict.REVIEW,
                    reason="AI not configured",
                )
                for b in tender.bidders
            ],
            warnings=["AINotConfigured"],
        )
        tender.evaluation_result = degraded_res
        return degraded_res

    try:
        eval_res = _run_pipeline(tender)
        save_cached(ckey, eval_res)
        tender.evaluation_result = eval_res
        return eval_res
    except Exception as exc:
        exc_name = type(exc).__name__
        degraded_res = EvaluationResult(
            tender_id=tender_id,
            cached=False,
            degraded=True,
            criteria=[],
            void_list=[],
            atc_flags=[],
            results=[
                CriterionResult(
                    bidder_name=b.name,
                    criterion_id="general",
                    verdict=Verdict.REVIEW,
                    reason=f"AI extraction failure ({exc_name})",
                )
                for b in tender.bidders
            ],
            warnings=[exc_name],
        )
        tender.evaluation_result = degraded_res
        return degraded_res


@app.get("/tenders/{tender_id}/matrix.csv")
def export_matrix_csv(tender_id: str) -> Response:
    """Export criteria-by-bidder verdict matrix as a downloadable CSV."""
    tender = get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")
    if not tender.evaluation_result:
        raise HTTPException(status_code=409, detail="Evaluation not yet run for this tender")

    res = tender.evaluation_result
    bidder_names = [b.name for b in tender.bidders]
    matrix = build_matrix(res.criteria, res.results)
    csv_content = to_csv(matrix, bidder_names)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="tender_{tender_id}_matrix.csv"'},
    )


@app.get("/tenders/{tender_id}/report", response_class=HTMLResponse)
def view_report_endpoint(tender_id: str) -> HTMLResponse:
    """Render a standalone HTML report with criteria, matrix, ATC flags, and speaking orders."""
    tender = get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")
    if not tender.evaluation_result:
        raise HTTPException(status_code=409, detail="Evaluation not yet run for this tender")

    res = tender.evaluation_result
    bidder_names = [b.name for b in tender.bidders]
    mat = build_matrix(res.criteria, res.results)
    mat_html = to_html(mat, bidder_names)

    # Rejection speaking orders
    fail_results = [r for r in res.results if r.verdict == Verdict.FAIL and r.speaking_order_line]
    orders_html = "".join(f"<li style='margin-bottom:8px; line-height:1.4;'>{html.escape(r.speaking_order_line)}</li>" for r in fail_results)
    if not orders_html:
        orders_html = "<p style='color:#6c757d;'>No rejected bids. All criteria passed or under review.</p>"

    # Resolved criteria rows
    crit_rows = "".join(
        f"<tr><td style='border:1px solid #dee2e6; padding:8px;'><b>{html.escape(c.title)}</b><br><small style='color:#6c757d;'>{html.escape(c.id)} ({c.rule_type})</small></td>"
        f"<td style='border:1px solid #dee2e6; padding:8px;'>{c.threshold or 'N/A'} {c.unit or ''}</td>"
        f"<td style='border:1px solid #dee2e6; padding:8px;'>{html.escape(c.source_doc)} (p. {c.source_page})</td>"
        f"<td style='border:1px solid #dee2e6; padding:8px; font-style:italic;'>\"{html.escape(c.source_quote)}\"</td>"
        f"<td style='border:1px solid #dee2e6; padding:8px;'>{', '.join(c.supersedes) if c.supersedes else '—'}</td></tr>"
        for c in res.criteria
    )

    # Null and void categories
    void_rows = "".join(
        f"<tr><td style='border:1px solid #dee2e6; padding:6px; text-align:center;'>{v.index}</td>"
        f"<td style='border:1px solid #dee2e6; padding:6px;'>{html.escape(v.text)}</td></tr>"
        for v in res.void_list
    )

    # ATC Flags
    flags_html = "".join(
        f"<tr><td style='border:1px solid #dee2e6; padding:8px;'>{html.escape(f.clause_text)}</td>"
        f"<td style='border:1px solid #dee2e6; padding:8px; text-align:center;'><b>{f.matched_void_index or '—'}</b></td>"
        f"<td style='border:1px solid #dee2e6; padding:8px; text-align:center;'><span style='padding:4px 8px; border-radius:4px; font-weight:bold; background-color:{'#f8d7da' if f.verdict=='FLAG' else '#fff3cd' if f.verdict=='REVIEW' else '#d4edda'}; color:{'#721c24' if f.verdict=='FLAG' else '#856404' if f.verdict=='REVIEW' else '#155724'};'>{f.verdict}</span></td>"
        f"<td style='border:1px solid #dee2e6; padding:8px;'>{html.escape(f.reason)}</td></tr>"
        for f in res.atc_flags
    )

    badge = ""
    if res.cached:
        badge = "<span style='background:#17a2b8; color:white; padding:4px 8px; border-radius:4px; font-size:12px; margin-left:10px;'>REPLAY CACHED</span>"
    if res.degraded:
        badge += "<span style='background:#dc3545; color:white; padding:4px 8px; border-radius:4px; font-size:12px; margin-left:10px;'>DEGRADED MODE</span>"

    page = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>BidParakh Evaluation Report - {tender_id[:8]}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #fdfdfd; color: #212529; margin: 0; padding: 24px;">
  <div style="max-width: 1100px; margin: 0 auto; background: white; border: 1px solid #e9ecef; border-radius: 8px; padding: 32px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
    <div style="border-bottom: 2px solid #343a40; padding-bottom: 16px; margin-bottom: 24px;">
      <h1 style="margin: 0 0 8px 0; font-size: 26px;">BidParakh Tender Evaluation Report {badge}</h1>
      <p style="margin: 0; color: #6c757d; font-size: 14px;">Tender ID: <code>{tender_id}</code> | Officer-side GeM bid evaluation: AI reads, code decides.</p>
    </div>

    <h2 style="font-size: 18px; margin-top: 24px; border-bottom: 1px solid #dee2e6; padding-bottom: 6px;">1. Bidder Verdict Matrix</h2>
    {mat_html}

    <h2 style="font-size: 18px; margin-top: 32px; border-bottom: 1px solid #dee2e6; padding-bottom: 6px;">2. Draft Speaking Orders for Rejections</h2>
    <ul style="background: #fff8f8; border: 1px solid #f5c6cb; border-radius: 6px; padding: 16px 24px;">{orders_html}</ul>

    <h2 style="font-size: 18px; margin-top: 32px; border-bottom: 1px solid #dee2e6; padding-bottom: 6px;">3. Resolved Tender Eligibility Criteria</h2>
    <table style="border-collapse: collapse; width: 100%; font-size: 13px;">
      <thead><tr style="background:#f8f9fa;">
        <th style="border:1px solid #dee2e6; padding:8px; text-align:left;">Criterion</th>
        <th style="border:1px solid #dee2e6; padding:8px; text-align:left;">Threshold</th>
        <th style="border:1px solid #dee2e6; padding:8px; text-align:left;">Source</th>
        <th style="border:1px solid #dee2e6; padding:8px; text-align:left;">Source Quote</th>
        <th style="border:1px solid #dee2e6; padding:8px; text-align:left;">Supersedes</th>
      </tr></thead>
      <tbody>{crit_rows or '<tr><td colspan="5" style="padding:10px; text-align:center;">No criteria resolved</td></tr>'}</tbody>
    </table>

    <h2 style="font-size: 18px; margin-top: 32px; border-bottom: 1px solid #dee2e6; padding-bottom: 6px;">4. Buyer Added Terms (ATC) Legality Review</h2>
    <table style="border-collapse: collapse; width: 100%; font-size: 13px;">
      <thead><tr style="background:#f8f9fa;">
        <th style="border:1px solid #dee2e6; padding:8px; text-align:left;">Clause</th>
        <th style="border:1px solid #dee2e6; padding:8px; text-align:center;">Void Item #</th>
        <th style="border:1px solid #dee2e6; padding:8px; text-align:center;">Verdict</th>
        <th style="border:1px solid #dee2e6; padding:8px; text-align:left;">Legal Findings</th>
      </tr></thead>
      <tbody>{flags_html or '<tr><td colspan="4" style="padding:10px; text-align:center;">No ATC clauses extracted</td></tr>'}</tbody>
    </table>

    <h2 style="font-size: 18px; margin-top: 32px; border-bottom: 1px solid #dee2e6; padding-bottom: 6px;">5. GeM Disclaimer Null-and-Void Categories</h2>
    <table style="border-collapse: collapse; width: 100%; font-size: 13px;">
      <thead><tr style="background:#f8f9fa;">
        <th style="border:1px solid #dee2e6; padding:6px; width:60px; text-align:center;">#</th>
        <th style="border:1px solid #dee2e6; padding:6px; text-align:left;">Category Description</th>
      </tr></thead>
      <tbody>{void_rows or '<tr><td colspan="2" style="padding:10px; text-align:center;">No disclaimer items extracted</td></tr>'}</tbody>
    </table>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=page)
