"""FastAPI main application module for BidParakh tender evaluation."""

from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import List
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

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
from app.pdf_report import generate_pdf_report
from app.pdf_text import extract_pages, has_text_layer
from app.resolver import resolve_criteria, resolve_void_list
from app.rules import evaluate
import app.vision_client as vision_client
from app.schemas import (
    AtcClause,
    AtcFlag,
    Criterion,
    CriterionResult,
    EvaluationResult,
    OfficerOverride,
    OverrideRequest,
    RuleType,
    Verdict,
    VoidListItem,
)

app = FastAPI(
    title="BidParakh",
    description="Officer-side GeM bid evaluation: AI reads, code decides.",
    version="1.0.0",
)

# CORS enabled for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        
        # Fallback order: text layer first (cheap, verifiable). Vision only when no text layer.
        if has_text_layer(bidder_pages):
            evidence = gemini_client.extract_bidder_evidence(bidder_pages, bidder.name, merged_criteria)
            evidence.fields = apply_guard(evidence.fields, bidder_pages)
        else:
            combined_bytes = b"".join(d.bytes_data for d in bidder.documents)
            num_pages = sum(len(d.pages) for d in bidder.documents) or 1
            evidence = vision_client.extract_bidder_evidence_vision(
                combined_bytes, bidder.name, merged_criteria, num_pages=num_pages
            )

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
        save_cached(ckey, degraded_res)
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
        save_cached(ckey, degraded_res)
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


@app.post("/tenders/{tender_id}/override", response_model=EvaluationResult)
def override_verdict_endpoint(tender_id: str, req: OverrideRequest) -> EvaluationResult:
    """Record an officer manual verdict override with statutory justification without mutating rule verdicts."""
    tender = get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")
    if not tender.evaluation_result:
        raise HTTPException(status_code=409, detail="Evaluation not yet run for this tender")

    justification = req.justification.strip()
    if len(justification) < 20:
        raise HTTPException(
            status_code=400,
            detail="Justification must be at least 20 characters long.",
        )

    orig_res = next(
        (
            r
            for r in tender.evaluation_result.results
            if r.criterion_id == req.criterion_id and r.bidder_name == req.bidder_name
        ),
        None,
    )
    if not orig_res:
        raise HTTPException(
            status_code=404,
            detail=f"Result not found for criterion '{req.criterion_id}' and bidder '{req.bidder_name}'.",
        )

    override = OfficerOverride(
        criterion_id=req.criterion_id,
        bidder_name=req.bidder_name,
        old_verdict=orig_res.verdict,
        new_verdict=req.new_verdict,
        justification=justification,
        officer_name=req.officer_name or "Procurement Officer",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Append to immutable override audit list (never mutates original rule verdict in results)
    tender.overrides.append(override)
    tender.evaluation_result.overrides.append(override)

    # Update cache if key exists
    ckey = cache_key(tender)
    save_cached(ckey, tender.evaluation_result)

    return tender.evaluation_result


@app.get("/tenders/{tender_id}/export/pdf")
def export_report_pdf(tender_id: str) -> Response:
    """Export executive evaluation report with summary, matrix, overrides, and speaking orders as PDF."""
    tender = get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")
    if not tender.evaluation_result:
        raise HTTPException(status_code=409, detail="Evaluation not yet run for this tender")

    pdf_bytes = generate_pdf_report(tender)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="evaluation_report_{tender_id[:8]}.pdf"'},
    )


@app.post("/tenders/demo")
def load_demo_tender() -> dict:
    """Load IIT Kanpur hero tender fixture and 3 synthetic bidders for instant demonstration."""
    fixtures_dir = Path("fixtures")
    main_bid = fixtures_dir / "GEM-2026-B-7945477-main-bid.pdf"
    corrigendum = fixtures_dir / "GEM-2026-B-7945477-C5-corrigendum.pdf"

    if not main_bid.is_file() or not corrigendum.is_file():
        raise HTTPException(status_code=404, detail="Hero fixture files missing on disk")

    tender = create_tender()
    for fpath in (main_bid, corrigendum):
        content = fpath.read_bytes()
        pages = extract_pages(content)
        tender.documents.append(UploadedDoc(name=fpath.name, bytes_data=content, pages=pages))

    bidders_data = [
        ("PassBidder Pvt Ltd", fixtures_dir / "bidder_pass.pdf"),
        ("FailBidder Pvt Ltd", fixtures_dir / "bidder_fail.pdf"),
        ("ReviewBidder Pvt Ltd", fixtures_dir / "bidder_review.pdf"),
    ]
    for b_name, b_path in bidders_data:
        if b_path.is_file():
            b_bytes = b_path.read_bytes()
            b_pages = extract_pages(b_bytes)
            tender.bidders.append(
                BidderPack(
                    name=b_name,
                    documents=[UploadedDoc(name=b_path.name, bytes_data=b_bytes, pages=b_pages)],
                )
            )

    # Use offline golden fixtures for instant and reliable evaluation
    golden_criteria = [
        Criterion(
            id="exp_orders",
            title="Past Experience (Completed Government Orders)",
            rule_type=RuleType.MIN_COUNT.value,
            threshold=2,
            unit="orders",
            source_doc="GEM-2026-B-7945477-C5-corrigendum.pdf",
            source_page=2,
            source_quote="at least two orders from IITs, NITs or any other government organisation",
            supersedes=["GEM-2026-B-7945477-main-bid.pdf"],
        ),
        Criterion(
            id="oem_authorisation",
            title="Manufacturer / OEM Authorization",
            rule_type=RuleType.OEM_OR_AUTHORISED.value,
            source_doc="GEM-2026-B-7945477-C5-corrigendum.pdf",
            source_page=1,
            source_quote="Authorisation Form / Certificate with OEM details furnished",
        ),
        Criterion(
            id="liquidation_undertaking",
            title="Financial Standing / No-Liquidation Undertaking",
            rule_type=RuleType.UNDERTAKING_PRESENT.value,
            source_doc="GEM-2026-B-7945477-C5-corrigendum.pdf",
            source_page=1,
            source_quote="undertaking to the effect of financial standing and no liquidation",
        ),
    ]

    golden_results = [
        # PassBidder
        CriterionResult(
            bidder_name="PassBidder Pvt Ltd",
            criterion_id="exp_orders",
            verdict=Verdict.PASS,
            reason="Verified count 2 meets or exceeds required threshold 2.",
            evidence_page=1,
            evidence_quote="Successfully completed 2 government orders for IT equipment.",
        ),
        CriterionResult(
            bidder_name="PassBidder Pvt Ltd",
            criterion_id="oem_authorisation",
            verdict=Verdict.PASS,
            reason="OEM authorisation document is present in bidder pack.",
            evidence_page=1,
            evidence_quote="Authorisation Form / Certificate with OEM details furnished.",
        ),
        CriterionResult(
            bidder_name="PassBidder Pvt Ltd",
            criterion_id="liquidation_undertaking",
            verdict=Verdict.PASS,
            reason="Undertaking document is present in bidder pack.",
            evidence_page=1,
            evidence_quote="Undertaking to the effect of financial standing and no liquidation.",
        ),
        # FailBidder
        CriterionResult(
            bidder_name="FailBidder Pvt Ltd",
            criterion_id="exp_orders",
            verdict=Verdict.FAIL,
            reason="Verified count 1 is below required threshold 2.",
            evidence_page=1,
            evidence_quote="Successfully completed 1 order only for IT equipment.",
            speaking_order_line="The bid of FailBidder Pvt Ltd is rejected under Past Experience (Completed Government Orders) (GEM-2026-B-7945477-C5-corrigendum.pdf, page 2): Verified count 1 is below required threshold 2. Criterion as per tender: at least two orders from IITs, NITs or any other government organisation",
        ),
        CriterionResult(
            bidder_name="FailBidder Pvt Ltd",
            criterion_id="oem_authorisation",
            verdict=Verdict.FAIL,
            reason="The tender makes an offer liable to rejection when a sought document is not uploaded. OEM authorisation document missing.",
            evidence_page=1,
            evidence_quote="Not applicable / Reseller without OEM authorization.",
            speaking_order_line="The bid of FailBidder Pvt Ltd is rejected under Manufacturer / OEM Authorization (GEM-2026-B-7945477-C5-corrigendum.pdf, page 1): The tender makes an offer liable to rejection when a sought document is not uploaded. OEM authorisation document missing. Criterion as per tender: Authorisation Form / Certificate with OEM details furnished",
        ),
        CriterionResult(
            bidder_name="FailBidder Pvt Ltd",
            criterion_id="liquidation_undertaking",
            verdict=Verdict.PASS,
            reason="Undertaking document is present in bidder pack.",
            evidence_page=1,
            evidence_quote="Undertaking to the effect of financial standing and no liquidation.",
        ),
        # ReviewBidder
        CriterionResult(
            bidder_name="ReviewBidder Pvt Ltd",
            criterion_id="exp_orders",
            verdict=Verdict.REVIEW,
            reason="No verified evidence found. Quote verification failed against PDF text layer.",
            evidence_page=1,
            evidence_quote="Successfully completed two commercial contracts in hardware supply.",
        ),
        CriterionResult(
            bidder_name="ReviewBidder Pvt Ltd",
            criterion_id="oem_authorisation",
            verdict=Verdict.REVIEW,
            reason="Needs officer judgement. Non-standard reseller authorization document.",
        ),
        CriterionResult(
            bidder_name="ReviewBidder Pvt Ltd",
            criterion_id="liquidation_undertaking",
            verdict=Verdict.PASS,
            reason="Undertaking document is present in bidder pack.",
        ),
    ]

    golden_flags = [
        AtcFlag(
            clause_text="At least two orders from IITs, NITs or any other government organisation",
            matched_void_index=8,
            verdict="REVIEW",
            reason="Clause is ambiguous: specifies particular organizations (IITs/NITs) but also permits any government organisation. Disclaimer item 8.",
            clause_quote="orders from IITs, NITs",
            void_quote="seeking experience from a specific organisation only",
        ),
        AtcFlag(
            clause_text="Dedicated toll-free number for service support",
            matched_void_index=None,
            verdict="CLEAR",
            reason="Standard commercial support requirement; does not violate any GeM disclaimer item.",
            clause_quote="",
            void_quote="",
        ),
    ]

    void_list = [
        VoidListItem(
            index=i,
            source_page=3,
            source_quote=f"Disclaimer Category {i}",
            text=f"GeM Disclaimer Category {i}: Restrictive/anti-competitive procurement condition",
        )
        for i in range(1, 15)
    ]

    eval_res = EvaluationResult(
        tender_id=tender.tender_id,
        cached=True,
        degraded=False,
        criteria=golden_criteria,
        void_list=void_list,
        atc_flags=golden_flags,
        results=golden_results,
        overrides=[],
        warnings=[],
    )
    tender.evaluation_result = eval_res
    save_cached(cache_key(tender), eval_res)

    return {
        "tender_id": tender.tender_id,
        "evaluation": eval_res,
    }


# Static frontend mount
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

