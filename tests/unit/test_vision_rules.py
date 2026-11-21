"""Unit tests for deterministic scan-derived evidence rules and vision safety invariant."""

try:
    import pytest
except ImportError:
    class _MockPytest:
        @staticmethod
        def fixture(func):
            return func
    pytest = _MockPytest()

from app.rules import evaluate
from app.schemas import (
    BidderEvidence,
    Criterion,
    DocumentPresent,
    ExtractedField,
    RuleType,
    Verdict,
)


@pytest.fixture
def min_count_criterion():
    return Criterion(
        id="exp_orders",
        title="Past Completed Orders",
        rule_type=RuleType.MIN_COUNT.value,
        threshold=2,
        unit="orders",
        source_doc="tender.pdf",
        source_page=1,
        source_quote="Provide at least two orders",
    )


@pytest.fixture
def turnover_criterion():
    return Criterion(
        id="avg_turnover",
        title="Average Annual Turnover",
        rule_type=RuleType.MIN_AVG_VALUE.value,
        threshold=5000000.0,
        unit="INR",
        source_doc="tender.pdf",
        source_page=1,
        source_quote="Average turnover Rs 50 lakh",
    )


def test_scan_derived_meeting_threshold_yields_pass(min_count_criterion):
    """Scan-derived fields that agree and meet threshold may produce PASS."""
    evidence = BidderEvidence(
        bidder_name="ScanPassBidder",
        fields=[
            ExtractedField(
                criterion_id="exp_orders",
                page=1,
                quote="2 government orders",
                raw_text="2 orders",
                value=2,
                source_kind="vision",
                guard_passed=True,
                disputed=False,
                bounding_box=[100, 100, 200, 500],
            )
        ],
    )
    res = evaluate(min_count_criterion, evidence)
    assert res.verdict == Verdict.PASS
    assert res.source_kind == "vision"
    assert res.bounding_box == [100, 100, 200, 500]


def test_scan_derived_below_threshold_never_yields_fail(min_count_criterion):
    """CRITICAL SAFETY INVARIANT: Scan-derived evidence must NEVER produce automatic FAIL."""
    # Count is 1, but threshold is 2
    evidence = BidderEvidence(
        bidder_name="ScanLowBidder",
        fields=[
            ExtractedField(
                criterion_id="exp_orders",
                page=1,
                quote="1 completed order",
                raw_text="1 order",
                value=1,
                source_kind="vision",
                guard_passed=True,
                disputed=False,
                bounding_box=[300, 100, 400, 600],
            )
        ],
    )
    res = evaluate(min_count_criterion, evidence)
    # Must be downgraded to REVIEW, NEVER FAIL
    assert res.verdict == Verdict.REVIEW
    assert "Value read from scanned image; officer must confirm" in res.reason
    assert res.speaking_order_line is None
    assert res.source_kind == "vision"


def test_scan_derived_turnover_below_threshold_downgrades_to_review(turnover_criterion):
    """Scan-derived turnover below threshold downgrades to REVIEW without speaking order."""
    evidence = BidderEvidence(
        bidder_name="ScanTurnoverLow",
        fields=[
            ExtractedField(
                criterion_id="avg_turnover",
                page=1,
                quote="Rs 30,00,000",
                raw_text="Rs 30 lakh",
                value=3000000.0,
                source_kind="vision",
                guard_passed=True,
                disputed=False,
            ),
            ExtractedField(
                criterion_id="avg_turnover",
                page=1,
                quote="Rs 35,00,000",
                raw_text="Rs 35 lakh",
                value=3500000.0,
                source_kind="vision",
                guard_passed=True,
                disputed=False,
            ),
            ExtractedField(
                criterion_id="avg_turnover",
                page=1,
                quote="Rs 25,00,000",
                raw_text="Rs 25 lakh",
                value=2500000.0,
                source_kind="vision",
                guard_passed=True,
                disputed=False,
            ),
        ],
    )
    res = evaluate(turnover_criterion, evidence)
    # Average is 30 lakh, threshold is 50 lakh -> would fail on digital text, but MUST REVIEW on vision
    assert res.verdict == Verdict.REVIEW
    assert "Value read from scanned image; officer must confirm" in res.reason
    assert res.speaking_order_line is None


def test_scan_derived_disputed_fields_yield_review(min_count_criterion):
    """Disputed scan fields (disagreement across dual calls) produce REVIEW."""
    evidence = BidderEvidence(
        bidder_name="ScanDisputedBidder",
        fields=[
            ExtractedField(
                criterion_id="exp_orders",
                page=1,
                quote="orders uncertain",
                raw_text="2 or 3 orders",
                value=2,
                source_kind="vision",
                guard_passed=False,
                disputed=True,  # Disagreed in dual extraction
            )
        ],
    )
    res = evaluate(min_count_criterion, evidence)
    assert res.verdict == Verdict.REVIEW
    assert "No verified evidence found" in res.reason


def test_missing_document_in_scanned_pack_downgrades_to_review():
    """Missing document when evidence was scanned yields REVIEW, not FAIL."""
    oem_crit = Criterion(
        id="oem_auth",
        title="OEM Authorisation",
        rule_type=RuleType.OEM_OR_AUTHORISED.value,
        source_doc="tender.pdf",
        source_page=1,
        source_quote="OEM authorisation required",
    )
    evidence = BidderEvidence(
        bidder_name="ScanBidderNoOem",
        documents_present=[
            DocumentPresent(doc_type="undertaking", page=1, quote="Undertaking", source_kind="vision")
        ],
        fields=[],
    )
    res = evaluate(oem_crit, evidence)
    assert res.verdict == Verdict.REVIEW
    assert "Value read from scanned image; officer must confirm" in res.reason
    assert res.speaking_order_line is None
