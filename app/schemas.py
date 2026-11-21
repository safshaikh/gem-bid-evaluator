"""Pydantic data models for BidParakh - single source of truth for data shapes."""

from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class Verdict(str, Enum):
    """Evaluation verdict with exactly three outcomes."""
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class RuleType(str, Enum):
    """Supported rule evaluation types."""
    MIN_COUNT = "MIN_COUNT"
    MIN_AVG_VALUE = "MIN_AVG_VALUE"
    DOC_PRESENT = "DOC_PRESENT"
    UNDERTAKING_PRESENT = "UNDERTAKING_PRESENT"
    OEM_OR_AUTHORISED = "OEM_OR_AUTHORISED"
    MANUAL = "MANUAL"


class AtcVerdict(str, Enum):
    """Legality verdict for Additional Terms and Conditions clauses."""
    FLAG = "FLAG"
    CLEAR = "CLEAR"
    REVIEW = "REVIEW"


class PageText(BaseModel):
    """Text extracted from a single 1-based PDF page."""
    page: int
    text: str


class AtcClause(BaseModel):
    """Buyer-added bid-specific ATC clause."""
    source_doc: str
    source_page: int
    text: str


class AtcFlag(BaseModel):
    """Classification of an ATC clause against the null-and-void disclaimer list."""
    clause_quote: str
    clause_text: str
    matched_void_index: Optional[int] = None
    reason: str
    verdict: str
    void_quote: str


class DocumentPresent(BaseModel):
    """Evidence of a recognized document type present in a bidder pack."""
    doc_type: str
    page: int
    quote: str
    bounding_box: Optional[List[int]] = None
    source_kind: str = "text_layer"


class ExtractedField(BaseModel):
    """Individual extracted field value supporting a criterion."""
    criterion_id: str
    disputed: bool = False
    guard_passed: bool = False
    page: int
    quote: str
    raw_text: str
    value: Optional[Union[float, int, str]] = None
    bounding_box: Optional[List[int]] = None
    source_kind: str = "text_layer"
    confidence: Optional[str] = "high"


class BidderEvidence(BaseModel):
    """Extracted evidence bundle for a single bidder."""
    bidder_name: str
    documents_present: List[DocumentPresent] = Field(default_factory=list)
    fields: List[ExtractedField] = Field(default_factory=list)


class Criterion(BaseModel):
    """Evaluation criterion extracted from a tender or corrigendum."""
    id: str
    title: str
    rule_type: str
    threshold: Optional[float] = None
    unit: Optional[str] = None
    accepted_doc_types: List[str] = Field(default_factory=list)
    source_doc: str
    source_page: int
    source_quote: str
    supersedes: List[str] = Field(default_factory=list)


class CriterionResult(BaseModel):
    """Deterministic verdict and audit reason for a bidder under one criterion."""
    bidder_name: str = ""
    criterion_id: str
    verdict: Verdict
    reason: str
    evidence_page: Optional[int] = None
    evidence_quote: Optional[str] = None
    speaking_order_line: Optional[str] = None
    source_kind: Optional[str] = "text_layer"
    bounding_box: Optional[List[int]] = None


class VoidListItem(BaseModel):
    """Single null-and-void clause category from the GeM Disclaimer list."""
    index: int
    source_page: int
    source_quote: str
    text: str


class OfficerOverride(BaseModel):
    """Immutable audit record of an officer manual verdict override."""
    criterion_id: str
    bidder_name: str
    old_verdict: Verdict
    new_verdict: Verdict
    justification: str
    officer_name: str = "Procurement Officer"
    timestamp: str


class OverrideRequest(BaseModel):
    """Payload to record an officer verdict override."""
    criterion_id: str
    bidder_name: str
    new_verdict: Verdict
    justification: str
    officer_name: Optional[str] = "Procurement Officer"


class EvaluationResult(BaseModel):
    """Complete evaluation report for a tender across all submitted bidders."""
    tender_id: str
    cached: bool = False
    degraded: bool = False
    criteria: List[Criterion] = Field(default_factory=list)
    void_list: List[VoidListItem] = Field(default_factory=list)
    atc_flags: List[AtcFlag] = Field(default_factory=list)
    results: List[CriterionResult] = Field(default_factory=list)
    overrides: List[OfficerOverride] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
