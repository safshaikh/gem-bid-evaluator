"""Pure deterministic verdict evaluation engine for tender criteria."""

from typing import List
from app.numbers import parse_count, parse_money_to_inr
from app.schemas import BidderEvidence, Criterion, CriterionResult, RuleType, Verdict
from app.speaking_order import line_for


def evaluate(criterion: Criterion, evidence: BidderEvidence) -> CriterionResult:
    """Evaluate a single criterion against extracted bidder evidence without I/O or network."""
    rtype = criterion.rule_type
    bidder_name = evidence.bidder_name

    # Check if bidder submission contains scanned vision evidence
    is_scanned_pack = any(
        getattr(d, "source_kind", "text_layer") == "vision"
        for d in evidence.documents_present
    ) or any(
        getattr(f, "source_kind", "text_layer") == "vision"
        for f in evidence.fields
    )

    # Rule: MANUAL always returns REVIEW with reason 'Needs officer judgement'
    if rtype == RuleType.MANUAL or rtype == "MANUAL":
        return CriterionResult(
            bidder_name="",
            criterion_id=criterion.id,
            verdict=Verdict.REVIEW,
            reason="Needs officer judgement",
        )

    # Rule: DOC_PRESENT
    if rtype == RuleType.DOC_PRESENT or rtype == "DOC_PRESENT":
        present_doc = None
        if criterion.accepted_doc_types:
            accepted_lower = [a.lower() for a in criterion.accepted_doc_types]
            present_doc = next(
                (d for d in evidence.documents_present if d.doc_type.lower() in accepted_lower),
                None,
            )
        elif evidence.documents_present:
            present_doc = evidence.documents_present[0]

        if present_doc:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.PASS,
                reason="Required document is uploaded and present in bidder pack.",
                evidence_page=present_doc.page,
                evidence_quote=present_doc.quote,
                source_kind=getattr(present_doc, "source_kind", "text_layer"),
                bounding_box=getattr(present_doc, "bounding_box", None),
            )

        # Scanned packs must never automatically FAIL on missing document
        if is_scanned_pack:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.REVIEW,
                reason="Value read from scanned image; officer must confirm. Document not detected with certainty in scanned pack.",
                source_kind="vision",
            )

        res = CriterionResult(
            bidder_name="",
            criterion_id=criterion.id,
            verdict=Verdict.FAIL,
            reason="The tender makes an offer liable to rejection when a sought document is not uploaded.",
        )
        res.speaking_order_line = line_for(bidder_name, criterion, res)
        return res

    # Rule: UNDERTAKING_PRESENT
    if rtype == RuleType.UNDERTAKING_PRESENT or rtype == "UNDERTAKING_PRESENT":
        present_doc = next(
            (d for d in evidence.documents_present if d.doc_type.lower() == "undertaking"),
            None,
        )
        if present_doc:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.PASS,
                reason="Undertaking document is present in bidder pack.",
                evidence_page=present_doc.page,
                evidence_quote=present_doc.quote,
                source_kind=getattr(present_doc, "source_kind", "text_layer"),
                bounding_box=getattr(present_doc, "bounding_box", None),
            )

        if is_scanned_pack:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.REVIEW,
                reason="Value read from scanned image; officer must confirm. Undertaking not detected with certainty in scanned pack.",
                source_kind="vision",
            )

        res = CriterionResult(
            bidder_name="",
            criterion_id=criterion.id,
            verdict=Verdict.FAIL,
            reason="The tender makes an offer liable to rejection when a sought document is not uploaded. Undertaking document missing.",
        )
        res.speaking_order_line = line_for(bidder_name, criterion, res)
        return res

    # Rule: OEM_OR_AUTHORISED
    if rtype == RuleType.OEM_OR_AUTHORISED or rtype == "OEM_OR_AUTHORISED":
        present_doc = next(
            (
                d for d in evidence.documents_present
                if d.doc_type.lower() in ("oem authorisation", "oem authorization", "oem certificate")
            ),
            None,
        )
        if present_doc:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.PASS,
                reason="OEM authorisation document is present in bidder pack.",
                evidence_page=present_doc.page,
                evidence_quote=present_doc.quote,
                source_kind=getattr(present_doc, "source_kind", "text_layer"),
                bounding_box=getattr(present_doc, "bounding_box", None),
            )

        if is_scanned_pack:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.REVIEW,
                reason="Value read from scanned image; officer must confirm. OEM authorisation document missing or unclear in scanned pack.",
                source_kind="vision",
            )

        res = CriterionResult(
            bidder_name="",
            criterion_id=criterion.id,
            verdict=Verdict.FAIL,
            reason="The tender makes an offer liable to rejection when a sought document is not uploaded. OEM authorisation document missing.",
        )
        res.speaking_order_line = line_for(bidder_name, criterion, res)
        return res

    # Filter guard-passed, non-disputed fields for count and money rules
    valid_fields = [
        f for f in evidence.fields
        if f.criterion_id == criterion.id and f.guard_passed and not f.disputed
    ]

    # Rule: MIN_COUNT
    if rtype == RuleType.MIN_COUNT or rtype == "MIN_COUNT":
        if not valid_fields:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.REVIEW,
                reason="No verified evidence found",
            )
        field = valid_fields[0]
        val = field.value
        if val is None or not isinstance(val, (int, float)):
            val = parse_count(field.raw_text) or 0
        threshold = criterion.threshold or 0.0

        if val >= threshold:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.PASS,
                reason=f"Verified count {int(val)} meets or exceeds required threshold {int(threshold)}.",
                evidence_page=field.page,
                evidence_quote=field.quote,
                source_kind=getattr(field, "source_kind", "text_layer"),
                bounding_box=getattr(field, "bounding_box", None),
            )

        # CRITICAL SAFETY RULE: Scan-derived data must NEVER produce an automatic FAIL
        if getattr(field, "source_kind", "text_layer") == "vision":
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.REVIEW,
                reason="Value read from scanned image; officer must confirm",
                evidence_page=field.page,
                evidence_quote=field.quote,
                source_kind="vision",
                bounding_box=getattr(field, "bounding_box", None),
            )

        res = CriterionResult(
            bidder_name="",
            criterion_id=criterion.id,
            verdict=Verdict.FAIL,
            reason=f"Verified count {int(val)} is below required threshold {int(threshold)}.",
            evidence_page=field.page,
            evidence_quote=field.quote,
        )
        res.speaking_order_line = line_for(bidder_name, criterion, res)
        return res

    # Rule: MIN_AVG_VALUE
    if rtype == RuleType.MIN_AVG_VALUE or rtype == "MIN_AVG_VALUE":
        yearly_values: List[float] = []
        is_vision = any(getattr(f, "source_kind", "text_layer") == "vision" for f in valid_fields)

        for f in valid_fields:
            if isinstance(f.value, (int, float)):
                yearly_values.append(float(f.value))
            elif isinstance(f.value, str):
                parsed = parse_money_to_inr(f.value)
                if parsed is not None:
                    yearly_values.append(parsed)
            elif f.raw_text:
                parsed = parse_money_to_inr(f.raw_text)
                if parsed is not None:
                    yearly_values.append(parsed)

        if len(yearly_values) < 3:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.REVIEW,
                reason=f"Found {len(yearly_values)} yearly values (fewer than 3 required for 3-year average turnover).",
                source_kind="vision" if is_vision else "text_layer",
            )

        avg_val = sum(yearly_values) / len(yearly_values)
        threshold = criterion.threshold or 0.0
        first_field = valid_fields[0]

        if avg_val >= threshold:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.PASS,
                reason=f"Average turnover Rs {avg_val:,.2f} meets or exceeds required threshold Rs {threshold:,.2f}.",
                evidence_page=first_field.page,
                evidence_quote=first_field.quote,
                source_kind="vision" if is_vision else "text_layer",
                bounding_box=getattr(first_field, "bounding_box", None),
            )

        # CRITICAL SAFETY RULE: Scan-derived data must NEVER produce an automatic FAIL
        if is_vision:
            return CriterionResult(
                bidder_name="",
                criterion_id=criterion.id,
                verdict=Verdict.REVIEW,
                reason="Value read from scanned image; officer must confirm",
                evidence_page=first_field.page,
                evidence_quote=first_field.quote,
                source_kind="vision",
                bounding_box=getattr(first_field, "bounding_box", None),
            )

        res = CriterionResult(
            bidder_name="",
            criterion_id=criterion.id,
            verdict=Verdict.FAIL,
            reason=f"Average turnover Rs {avg_val:,.2f} is below required threshold Rs {threshold:,.2f}.",
        )
        res.speaking_order_line = line_for(bidder_name, criterion, res)
        return res

    # Default fallback
    return CriterionResult(
        bidder_name="",
        criterion_id=criterion.id,
        verdict=Verdict.REVIEW,
        reason=f"Unsupported rule type: {rtype}",
    )
