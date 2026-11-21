"""Gemini Multimodal Vision client for scanned PDF ingestion."""

import io
import logging
from typing import List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from app.config import get_fallback_model, get_model
from app.gemini_client import ExtractionError, get_client
from app.numbers import parse_count, parse_money_to_inr
from app.schemas import BidderEvidence, Criterion, DocumentPresent, ExtractedField

logger = logging.getLogger(__name__)


class VisionField(BaseModel):
    """Raw field extracted by Gemini Vision from an image."""
    criterion_id: str
    raw_text: str
    value: Optional[Union[float, int, str]] = None
    quote: str = ""
    bounding_box: Optional[List[int]] = None  # [ymin, xmin, ymax, xmax] 0-1000
    confidence: str = "high"  # "high" | "low"


class VisionDoc(BaseModel):
    """Document detected by Gemini Vision on a scanned page."""
    doc_type: str
    quote: str = ""
    bounding_box: Optional[List[int]] = None
    confidence: str = "high"


class VisionExtractionOutput(BaseModel):
    """Structured response container for multimodal page analysis."""
    fields: List[VisionField] = Field(default_factory=list)
    documents_present: List[VisionDoc] = Field(default_factory=list)


def rasterize_pdf(pdf_bytes: bytes) -> List[Tuple[int, bytes]]:
    """Rasterize PDF pages into PNG image bytes (1-based page index)."""
    # 1. Try PyMuPDF (fitz) for high-fidelity rendering
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages: List[Tuple[int, bytes]] = []
        for idx, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            pages.append((idx + 1, pix.tobytes("png")))
        if pages:
            return pages
    except Exception as exc:
        logger.debug(f"PyMuPDF rasterization unavailable or failed: {exc}")

    # 2. Fallback to extracting embedded scanned images with pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for idx, page in enumerate(reader.pages):
            if page.images:
                # Scanned documents have one full-page image per page
                pages.append((idx + 1, page.images[0].data))
        if pages:
            return pages
    except Exception as exc:
        logger.debug(f"pypdf image extraction failed: {exc}")

    return []


def _call_vision_model(
    client: genai.Client,
    image_bytes: bytes,
    prompt: str,
) -> VisionExtractionOutput:
    """Call Gemini Vision model with image part and structured schema."""
    primary = get_model()
    fallback = get_fallback_model()
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=VisionExtractionOutput,
        temperature=0.0,
    )

    for model in (primary, primary, fallback):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[image_part, prompt],
                config=config,
            )
            return VisionExtractionOutput.model_validate_json(resp.text)
        except Exception as exc:
            logger.warning(f"Vision generation attempt with {model} failed: {exc}")

    raise ExtractionError("Vision extraction failed after retry and fallback.")


def extract_scanned_bidder_evidence(
    pdf_bytes: bytes,
    bidder_name: str,
    criteria: List[Criterion],
) -> BidderEvidence:
    """Ingest scanned PDF pages with double multimodal vision and agreement verification."""
    page_images = rasterize_pdf(pdf_bytes)
    if not page_images:
        logger.warning(f"No readable images could be extracted from scanned PDF for {bidder_name}")
        return BidderEvidence(bidder_name=bidder_name, documents_present=[], fields=[])

    client = get_client()
    crit_desc = "\n".join(
        f"- ID: '{c.id}', Title: '{c.title}', Rule: '{c.rule_type}', Threshold: {c.threshold} {c.unit or ''}"
        for c in criteria
    )

    aggregated_fields: List[ExtractedField] = []
    aggregated_docs: List[DocumentPresent] = []

    for page_num, img_bytes in page_images:
        # Prompt 1 (Audit perspective)
        prompt1 = (
            f"You are inspecting page {page_num} of a scanned bidder submission pack for '{bidder_name}'.\n"
            f"Extract all qualification evidence matching these criteria:\n{crit_desc}\n\n"
            "For each field, extract criterion_id, exact read quote, numeric/text value, confidence ('high' or 'low'), "
            "and bounding_box [ymin, xmin, ymax, xmax] normalized on a 0-1000 scale.\n"
            "Also detect any present documents (e.g. 'OEM authorisation', 'undertaking', 'turnover certificate')."
        )

        # Prompt 2 (Independent extraction with varied phrasing)
        prompt2 = (
            f"Carefully examine this scanned technical bid certificate (Page {page_num}) submitted by '{bidder_name}'.\n"
            f"Identify values and certificates corresponding to the following requirements:\n{crit_desc}\n\n"
            "Return criterion_id, value, quoted text, confidence, and bounding box coordinates [ymin, xmin, ymax, xmax] 0-1000.\n"
            "Identify all recognized official document types present."
        )

        try:
            out1 = _call_vision_model(client, img_bytes, prompt1)
            out2 = _call_vision_model(client, img_bytes, prompt2)
        except Exception as exc:
            logger.error(f"Vision calls failed for page {page_num}: {exc}")
            continue

        # Map run 2 fields by criterion_id for agreement check
        map2 = {f.criterion_id: f for f in out2.fields}

        for f1 in out1.fields:
            cid = f1.criterion_id
            f2 = map2.get(cid)

            # Normalize values for agreement comparison
            val1 = f1.value
            val2 = f2.value if f2 else None

            # Check monetary or count normalization
            norm1 = parse_money_to_inr(str(val1)) or parse_count(str(val1)) or val1
            norm2 = (parse_money_to_inr(str(val2)) or parse_count(str(val2)) or val2) if f2 else None

            agreed = (f2 is not None) and (norm1 == norm2) and (f1.confidence == "high") and (f2.confidence == "high")

            field = ExtractedField(
                criterion_id=cid,
                disputed=not agreed,
                guard_passed=agreed,
                page=page_num,
                quote=f1.quote or f1.raw_text,
                raw_text=f1.raw_text,
                value=norm1,
                bounding_box=f1.bounding_box or (f2.bounding_box if f2 else None),
                source_kind="vision",
                confidence="high" if agreed else "low",
            )
            aggregated_fields.append(field)

        # Merge documents detected by vision
        doc_names_run2 = {d.doc_type.lower() for d in out2.documents_present}
        for d1 in out1.documents_present:
            if d1.doc_type.lower() in doc_names_run2 or d1.confidence == "high":
                aggregated_docs.append(
                    DocumentPresent(
                        doc_type=d1.doc_type,
                        page=page_num,
                        quote=d1.quote,
                        bounding_box=d1.bounding_box,
                        source_kind="vision",
                    )
                )

    return BidderEvidence(
        bidder_name=bidder_name,
        documents_present=aggregated_docs,
        fields=aggregated_fields,
    )


# Alias for backwards compatibility with tests and callers
extract_bidder_evidence_vision = extract_scanned_bidder_evidence

