"""In-memory tender job store and on-disk SHA-256 replay cache."""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from app.schemas import EvaluationResult, OfficerOverride, PageText

CACHE_DIR = Path("cache")


@dataclass
class UploadedDoc:
    """An uploaded document with its filename, raw bytes, and parsed pages."""
    name: str
    bytes_data: bytes
    pages: List[PageText]


@dataclass
class BidderPack:
    """A bidder pack containing the bidder name and uploaded evidence PDFs."""
    name: str
    documents: List[UploadedDoc] = field(default_factory=list)


@dataclass
class Tender:
    """In-memory tender entity holding documents in upload order and bidder packs."""
    tender_id: str
    documents: List[UploadedDoc] = field(default_factory=list)
    bidders: List[BidderPack] = field(default_factory=list)
    evaluation_result: Optional[EvaluationResult] = None
    overrides: List[OfficerOverride] = field(default_factory=list)


# Global in-memory storage of tenders
tenders_store: Dict[str, Tender] = {}


def create_tender() -> Tender:
    """Create and register a new Tender with a random hex UUID."""
    tid = uuid.uuid4().hex
    t = Tender(tender_id=tid)
    tenders_store[tid] = t
    return t


def get_tender(tender_id: str) -> Optional[Tender]:
    """Retrieve a Tender by tender_id or None if not found."""
    return tenders_store.get(tender_id)


def cache_key(tender: Tender) -> str:
    """Compute deterministic SHA-256 hex digest of tender document bytes followed by bidder bytes."""
    hasher = hashlib.sha256()
    for doc in tender.documents:
        hasher.update(doc.bytes_data)
    for bidder in tender.bidders:
        for doc in bidder.documents:
            hasher.update(doc.bytes_data)
    return hasher.hexdigest()


def load_cached(key: str) -> Optional[EvaluationResult]:
    """Load cached EvaluationResult from cache/{key}.json with cached set to True."""
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.is_file():
        try:
            data = cache_file.read_text(encoding="utf-8")
            result = EvaluationResult.model_validate_json(data)
            result.cached = True
            return result
        except Exception:
            return None
    return None


def save_cached(key: str, result: EvaluationResult) -> None:
    """Persist EvaluationResult JSON to cache/{key}.json."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{key}.json"
    cache_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
