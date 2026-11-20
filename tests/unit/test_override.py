"""Unit tests for officer statutory verdict overrides and PDF export."""

from fastapi.testclient import TestClient
import pytest

from app.jobs import BidderPack, create_tender, UploadedDoc
from app.main import app
from app.schemas import Criterion, CriterionResult, EvaluationResult, Verdict

client = TestClient(app)


@pytest.fixture
def evaluated_tender():
    """Create a tender with evaluated results for testing overrides."""
    tender = create_tender()
    crit = Criterion(
        id="exp_orders",
        title="Experience Orders",
        rule_type="MIN_COUNT",
        threshold=2,
        source_doc="doc.pdf",
        source_page=1,
        source_quote="Provide at least 2 orders",
    )
    res_pass = CriterionResult(
        bidder_name="Bidder A",
        criterion_id="exp_orders",
        verdict=Verdict.PASS,
        reason="Verified 2 orders.",
    )
    res_review = CriterionResult(
        bidder_name="Bidder B",
        criterion_id="exp_orders",
        verdict=Verdict.REVIEW,
        reason="Disputed quote.",
    )

    tender.evaluation_result = EvaluationResult(
        tender_id=tender.tender_id,
        criteria=[crit],
        results=[res_pass, res_review],
    )
    tender.bidders = [
        BidderPack(name="Bidder A", documents=[]),
        BidderPack(name="Bidder B", documents=[]),
    ]
    return tender


def test_override_preserves_original_verdict(evaluated_tender):
    """Verify override does not mutate the original rule verdict in results list."""
    tid = evaluated_tender.tender_id
    payload = {
        "criterion_id": "exp_orders",
        "bidder_name": "Bidder B",
        "new_verdict": "PASS",
        "justification": "Officer verified the physical original CA certificate during technical scrutiny meeting.",
        "officer_name": "Senior Procurement Officer",
    }
    response = client.post(f"/tenders/{tid}/override", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Original result must still be REVIEW (never mutated)
    orig_res = next(r for r in data["results"] if r["bidder_name"] == "Bidder B")
    assert orig_res["verdict"] == "REVIEW"

    # Override list must contain the record
    assert len(data["overrides"]) == 1
    ov = data["overrides"][0]
    assert ov["criterion_id"] == "exp_orders"
    assert ov["bidder_name"] == "Bidder B"
    assert ov["old_verdict"] == "REVIEW"
    assert ov["new_verdict"] == "PASS"
    assert ov["officer_name"] == "Senior Procurement Officer"
    assert "Officer verified" in ov["justification"]
    assert "timestamp" in ov


def test_override_requires_min_20_chars_justification(evaluated_tender):
    """Verify override is rejected with 400 when justification is too short."""
    tid = evaluated_tender.tender_id
    payload = {
        "criterion_id": "exp_orders",
        "bidder_name": "Bidder B",
        "new_verdict": "PASS",
        "justification": "Too short",
    }
    response = client.post(f"/tenders/{tid}/override", json=payload)
    assert response.status_code == 400
    assert "at least 20 characters" in response.json()["detail"]


def test_override_not_found(evaluated_tender):
    """Verify 404 is returned when criterion or bidder does not exist."""
    tid = evaluated_tender.tender_id
    payload = {
        "criterion_id": "non_existent",
        "bidder_name": "Bidder B",
        "new_verdict": "PASS",
        "justification": "Valid length justification text for testing non-existent.",
    }
    response = client.post(f"/tenders/{tid}/override", json=payload)
    assert response.status_code == 404


def test_export_pdf_endpoint(evaluated_tender):
    """Verify GET /tenders/{id}/export/pdf returns valid PDF bytes."""
    tid = evaluated_tender.tender_id
    response = client.get(f"/tenders/{tid}/export/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
