"""Tender job store backed by persistent SQLite database, storage vault, and replay cache."""

from dataclasses import dataclass, field
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from app.db import (
    db_add_bidder,
    db_add_bidder_doc,
    db_add_tender_doc,
    db_create_tender,
    db_get_evaluation_by_input_hash,
    db_get_latest_evaluation,
    db_get_overrides,
    db_get_tender_details,
    db_save_evaluation,
    init_db,
)
try:
    from app.pdf_text import extract_pages
except ImportError:
    def extract_pages(content: bytes) -> List[PageText]:
        return []
from app.schemas import EvaluationResult, OfficerOverride, PageText
import app.storage as storage

logger = logging.getLogger(__name__)

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
    """In-memory representation of a tender, backed by persistent SQLite and vault."""
    tender_id: str
    documents: List[UploadedDoc] = field(default_factory=list)
    bidders: List[BidderPack] = field(default_factory=list)
    evaluation_result: Optional[EvaluationResult] = None
    overrides: List[OfficerOverride] = field(default_factory=list)


# In-memory dictionary cache for backwards compatibility and high-speed lookups
tenders_store: Dict[str, Tender] = {}


def create_tender(actor: str = "demo-officer", title: str = "") -> Tender:
    """Create and register a new Tender in both memory and persistent database."""
    init_db()
    tid = uuid.uuid4().hex
    t = Tender(tender_id=tid)
    tenders_store[tid] = t

    try:
        db_create_tender(tender_id=tid, title=title, actor=actor)
    except Exception as exc:
        logger.warning(f"Failed to persist tender creation to db: {exc}")

    return t


def persist_tender_document(
    tender_id: str,
    filename: str,
    bytes_data: bytes,
    pages: List[PageText],
    order_index: int,
    actor: str = "demo-officer",
) -> UploadedDoc:
    """Store document bytes in content-addressable vault and associate with tender in DB."""
    doc = UploadedDoc(name=filename, bytes_data=bytes_data, pages=pages)
    try:
        sha = storage.put(bytes_data, filename)
        doc_id = uuid.uuid4().hex
        db_add_tender_doc(
            doc_id=doc_id,
            tender_id=tender_id,
            filename=filename,
            sha256=sha,
            order_index=order_index,
            page_count=len(pages),
            actor=actor,
        )
    except Exception as exc:
        logger.warning(f"Failed to persist tender document {filename} to vault/db: {exc}")
    return doc


def persist_bidder(
    tender_id: str,
    name: str,
    actor: str = "demo-officer",
) -> str:
    """Register bidder in DB and return bidder_id."""
    bidder_id = uuid.uuid4().hex
    try:
        db_add_bidder(bidder_id=bidder_id, tender_id=tender_id, name=name, actor=actor)
    except Exception as exc:
        logger.warning(f"Failed to persist bidder {name} to db: {exc}")
    return bidder_id


def persist_bidder_document(
    bidder_id: str,
    tender_id: str,
    filename: str,
    bytes_data: bytes,
    pages: List[PageText],
    actor: str = "demo-officer",
) -> UploadedDoc:
    """Store bidder document in vault and record in DB."""
    doc = UploadedDoc(name=filename, bytes_data=bytes_data, pages=pages)
    try:
        sha = storage.put(bytes_data, filename)
        doc_id = uuid.uuid4().hex
        db_add_bidder_doc(
            doc_id=doc_id,
            bidder_id=bidder_id,
            tender_id=tender_id,
            filename=filename,
            sha256=sha,
            page_count=len(pages),
            actor=actor,
        )
    except Exception as exc:
        logger.warning(f"Failed to persist bidder document {filename} to vault/db: {exc}")
    return doc


def get_tender(tender_id: str) -> Optional[Tender]:
    """Retrieve Tender from memory or restore completely from persistent database and vault."""
    if tender_id in tenders_store:
        return tenders_store[tender_id]

    try:
        details = db_get_tender_details(tender_id)
        if not details:
            return None

        # Reconstruct tender from database and vault
        tender = Tender(tender_id=tender_id)

        # Restore tender documents from vault
        for d in details.get("documents", []):
            content = storage.get(d["sha256"]) or b""
            pages = extract_pages(content) if content else []
            tender.documents.append(
                UploadedDoc(name=d["filename"], bytes_data=content, pages=pages)
            )

        # Restore bidders and bidder documents from vault
        for b in details.get("bidders", []):
            pack = BidderPack(name=b["name"])
            for bd in b.get("documents", []):
                content = storage.get(bd["sha256"]) or b""
                pages = extract_pages(content) if content else []
                pack.documents.append(
                    UploadedDoc(name=bd["filename"], bytes_data=content, pages=pages)
                )
            tender.bidders.append(pack)

        # Restore latest evaluation
        eval_row = db_get_latest_evaluation(tender_id)
        if eval_row:
            try:
                tender.evaluation_result = EvaluationResult.model_validate_json(
                    eval_row["result_json"]
                )
            except Exception as exc:
                logger.warning(f"Failed to parse evaluation result from db for {tender_id}: {exc}")

        # Restore overrides
        overrides_data = db_get_overrides(tender_id)
        for o in overrides_data:
            try:
                tender.overrides.append(
                    OfficerOverride(
                        criterion_id=o["criterion_id"],
                        bidder_id=o["bidder_id"],
                        new_verdict=o["new_verdict"],
                        justification=o["justification"],
                        officer_name=o["actor"],
                        timestamp=o["created_at"],
                    )
                )
            except Exception as exc:
                logger.warning(f"Failed to parse override row for {tender_id}: {exc}")

        tenders_store[tender_id] = tender
        return tender
    except Exception as exc:
        logger.warning(f"Error restoring tender {tender_id} from database: {exc}")
        return None


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
    """Load cached EvaluationResult from database evaluations table or disk cache."""
    # 1. Try database evaluation cache first
    try:
        row = db_get_evaluation_by_input_hash(key)
        if row:
            result = EvaluationResult.model_validate_json(row["result_json"])
            result.cached = True
            return result
    except Exception as exc:
        logger.debug(f"DB replay cache lookup failed: {exc}")

    # 2. Fallback to on-disk cache file
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


def save_cached(
    key: str,
    result: EvaluationResult,
    tender_id: Optional[str] = None,
    model_id: str = "",
    actor: str = "demo-officer",
) -> None:
    """Persist EvaluationResult to database evaluations table and disk cache."""
    tid = tender_id or getattr(result, "tender_id", None) or "unknown"
    eval_id = uuid.uuid4().hex

    # 1. Persist to database
    try:
        db_save_evaluation(
            evaluation_id=eval_id,
            tender_id=tid,
            input_hash=key,
            result_json=result.model_dump_json(indent=2),
            model_id=model_id,
            is_replay_hit=getattr(result, "cached", False),
            actor=actor,
        )
    except Exception as exc:
        logger.warning(f"Failed to persist evaluation to database: {exc}")

    # 2. Persist to on-disk JSON file
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"{key}.json"
        cache_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Failed to persist evaluation to disk cache: {exc}")
