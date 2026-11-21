"""Gemini Multimodal Vision client for scanned PDF ingestion without text layers."""

import io
import logging
from typing import List, Optional, Union
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import get_api_key, get_fallback_model, get_model
from app.numbers import parse_count, parse_money_to_inr
from app.schemas import BidderEvidence, Criterion, DocumentPresent, ExtractedField

logger = logging.getLogger(__name__)


class VisionExtractedItem(BaseModel):
    """Single criterion evidence field extracted from an image by vision model."""
    criterion_id: str
    raw_text: str = ""
    quote: str = ""
    value: Optional[Union[float, int, str]] = None
    bounding_box: Optional[List[int]] = None  # [ymin, xmin, ymax, xmax] normalized 0-1000
    confidence: str = "high"  # "high" | "medium" | "low"


class VisionDocItem(BaseModel):
    """Document presence extracted from image by vision model."""
    doc_type: str
    quote: str = ""
    confidence: str = "high"


class VisionPageOutput(BaseModel):
    """Strict structured response schema for a single scanned page."""
    documents_present: List[VisionDocItem] = Field(default_factory=list)
    fields: List[VisionExtractedItem] = Field(default_factory=list)


def rasterize_pdf_page(pdf_bytes: bytes, page_index: int = 0) -> Optional[bytes]:
    """Rasterize a single PDF page into PNG/JPEG bytes using PyMuPDF or pypdf image extraction."""
    # 1. Try PyMuPDF (fitz) if installed
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if 0 <= page_index < len(doc):
            pix = doc[page_index].get_pixmap(dpi=150)
            return pix.tobytes("png")
    except Exception:
        pass

    # 2. Try pypdf embedded image extraction (scanned PDFs have full-page images)
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if 0 <= page_index < len(reader.pages):
            page = reader.pages[page_index]
            if page.images:
                # Return the primary full-page scanned image
                return page.images[0].data
    except Exception:
        pass

    # 3. Try pdf2image if installed
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(pdf_bytes, first_page=page_index + 1, last_page=page_index + 1)
        if images:
            buf = io.BytesIO()
            images[0].save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        pass

    return None


def _call_gemini_vision(
    client: genai.Client,
    image_bytes: bytes,
    prompt: str,
) -> VisionPageOutput:
    """Call Gemini vision with image part and structured schema."""
    primary = get_model()
    fallback = get_fallback_model()

    part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=VisionPageOutput,
        temperature=0.0,
    )

    for model in (primary, fallback):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[part, prompt],
                config=config,
            )
            return VisionPageOutput.model_validate_json(resp.text)
        except Exception as exc:
            logger.warning(f"Vision extraction failed on {model}: {exc}")

    return VisionPageOutput()


def normalize_value_for_comparison(val: Optional[Union[float, int, str]], raw_text: str) -> Optional[Union[float, int, str]]:
    """Normalize numeric, money, or text value for deterministic agreement checks."""
    if val is not None:
        if isinstance(val, (int, float)):
            return float(val)
        money = parse_money_to_inr(str(val))
        if money is not None:
            return money
        cnt = parse_count(str(val))
        if cnt is not None:
            return cnt
        return str(val).strip().lower()

    if raw_text:
        money = parse_money_to_inr(raw_text)
        if money is not None:
            return money
        cnt = parse_count(raw_text)
        if cnt is not None:
            return cnt
        return raw_text.strip().lower()

    return None


def extract_bidder_evidence_vision(
    pdf_bytes: bytes,
    bidder_name: str,
    criteria: List[Criterion],
    num_pages: int = 1,
) -> BidderEvidence:
    """Extract evidence from scanned PDF using independent dual vision calls and strict agreement check."""
    key = get_api_key()
    if not key:
        return BidderEvidence(bidder_name=bidder_name)

    client = genai.Client(api_key=key)
    crit_desc = "\n".join(
        f"- {c.id} ({c.title}): rule={c.rule_type}, threshold={c.threshold} {c.unit or ''}"
        for c in criteria
    )

    all_fields: List[ExtractedField] = []
    all_docs: List[DocumentPresent] = []

    for p_idx in range(num_pages):
        page_num = p_idx + 1
        img_bytes = rasterize_pdf_page(pdf_bytes, page_index=p_idx)
        if not img_bytes:
            continue

        prompt_1 = (
            f"You are evaluating a scanned technical bid certificate for bidder '{bidder_name}'.\n"
            f"Target criteria:\n{crit_desc}\n\n"
            "Task:\n"
            "1. Extract exact numerical/textual values and character-for-character quotes for each matching criterion.\n"
            "2. Identify present document types: 'OEM authorisation', 'undertaking', 'execution certificate', etc.\n"
            "3. Provide bounding_box [ymin, xmin, ymax, xmax] normalized on 0-1000 scale for each field.\n"
            "4. Set confidence to 'high', 'medium', or 'low'. Set to 'low' if text is blurry, occluded, or ambiguous."
        )

        prompt_2 = (
            f"Independent document analysis for bidder '{bidder_name}'.\n"
            f"Qualification criteria:\n{crit_desc}\n\n"
            "Inspect the scanned image carefully. Extract all qualification values, quotes, and document types.\n"
            "Provide bounding_box [ymin, xmin, ymax, xmax] 0-1000. Mark confidence 'low' if handwriting or blur is unclear."
        )

        # Independent Double Vision Extraction
        run1 = _call_gemini_vision(client, img_bytes, prompt_1)
        run2 = _call_gemini_vision(client, img_bytes, prompt_2)

        # Map run2 fields for cross-validation
        run2_map = {f.criterion_id: f for f in run2.fields}

        for f1 in run1.fields:
            cid = f1.criterion_id
            f2 = run2_map.get(cid)

            val1 = normalize_value_for_comparison(f1.value, f1.raw_text)
            val2 = normalize_value_for_comparison(f2.value, f2.raw_text) if f2 else None

            # Agreement condition: both runs return non-null and equal normalized value
            is_agreed = (val1 is not None and val2 is not None and val1 == val2)
            is_low_conf = (f1.confidence.lower() == "low" or (f2 and f2.confidence.lower() == "low"))

            field = ExtractedField(
                criterion_id=cid,
                page=page_num,
                quote=f1.quote or f1.raw_text,
                raw_text=f1.raw_text,
                value=f1.value,
                bounding_box=f1.bounding_box,
                source_kind="vision",
                disputed=not is_agreed or is_low_conf,
                guard_passed=is_agreed and not is_low_conf,
            )
            all_fields.append(field)

        # Document presence agreement
        run2_docs = {d.doc_type.lower(): d for d in run2.documents_present}
        for d1 in run1.documents_present:
            d2 = run2_docs.get(d1.doc_type.lower())
            if d2 and d1.confidence.lower() != "low" and d2.confidence.lower() != "low":
                all_docs.append(
                    DocumentPresent(
                        doc_type=d1.doc_type,
                        page=page_num,
                        quote=d1.quote,
                        source_kind="vision",
                    )
                )

    return BidderEvidence(
        bidder_name=bidder_name,
        documents_present=all_docs,
        fields=all_fields,
    )
