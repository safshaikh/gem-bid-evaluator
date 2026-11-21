"""Pluggable tender ingestion layer supporting local folders and mock GeM sources.

Strictly excludes automated web scraping or unauthorized live network calls to the GeM portal.
All ingestion sources implement the TenderSource interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Allowed Bid ID pattern: letters, digits, slash, hyphen, underscore; max 64 chars
BID_ID_REGEX = re.compile(r"^[a-zA-Z0-9/\-_]{1,64}$")


class IngestionError(Exception):
    """Base exception for tender packet ingestion and resolution failures."""
    pass


class InvalidBidIdError(IngestionError):
    """Raised when bid identifier fails validation or attempts path escape."""
    pass


class CorruptPacketError(IngestionError):
    """Raised when manifest contains invalid dates, missing files, or duplicate hashes."""
    pass


@dataclass
class TenderDocument:
    """A single document within a tender packet."""
    name: str
    content: bytes
    sha256: str
    published_at: datetime
    kind: str  # "main" | "corrigendum"
    sequence: int = 0

    @property
    def bytes(self) -> bytes:
        return self.content


@dataclass
class TenderPacket:
    """A resolved, chronologically ordered tender packet."""
    bid_id: str
    title: str
    main_document: TenderDocument
    corrigenda: List[TenderDocument] = field(default_factory=list)

    @property
    def all_documents(self) -> List[TenderDocument]:
        """All documents in authoritative resolution order: main first, then ordered corrigenda."""
        return [self.main_document] + self.corrigenda


def validate_bid_id(bid_id: str) -> str:
    """Validate bid ID format and return sanitized folder name mapping '/' to '_'."""
    if not bid_id or not isinstance(bid_id, str):
        raise InvalidBidIdError("Bid ID must be a non-empty string.")
    clean = bid_id.strip()
    if len(clean) > 64:
        raise InvalidBidIdError(f"Bid ID exceeds maximum length of 64 characters: {clean[:20]}...")
    if not BID_ID_REGEX.match(clean):
        raise InvalidBidIdError(f"Invalid characters in Bid ID: '{clean}'. Allowed: a-z, 0-9, '/', '-', '_'.")
    if clean.startswith("/") or clean.startswith("\\"):
        raise InvalidBidIdError("Bid ID cannot start with '/' or '\\'.")
    if ".." in clean:
        raise InvalidBidIdError("Path traversal sequence '..' forbidden in Bid ID.")
    return clean


def bid_id_to_folder_name(bid_id: str) -> str:
    """Convert valid Bid ID into a safe directory name (mapping '/' to '_')."""
    valid = validate_bid_id(bid_id)
    return valid.replace("/", "_")


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO or common date string into timezone-aware UTC datetime."""
    if not dt_str or not isinstance(dt_str, str):
        raise CorruptPacketError(f"Missing or invalid published_at date: {dt_str}")
    clean = dt_str.strip()
    try:
        # Try standard ISO format
        dt = datetime.fromisoformat(clean)
    except ValueError:
        # Fallback formats like DD-MM-YYYY or YYYY-MM-DD
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(clean, fmt)
                break
            except ValueError:
                continue
        else:
            raise CorruptPacketError(f"Cannot parse date '{clean}'. Use ISO-8601 format.")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TenderSource(ABC):
    """Abstract base class for tender ingestion sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Machine identifier for this source."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for UI display."""
        pass

    @abstractmethod
    def resolve(self, bid_id: str) -> TenderPacket:
        """Resolve a full tender packet by bid ID."""
        pass

    @abstractmethod
    def list_updates(self, bid_id: str, known_sha256s: Set[str]) -> List[TenderDocument]:
        """Return any newly published corrigenda not present in known_sha256s."""
        pass


class LocalFolderSource(TenderSource):
    """Ingests tender packets from a local filesystem root."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()

    @property
    def name(self) -> str:
        return "local"

    @property
    def description(self) -> str:
        return f"Local Filesystem Folder ({self.root_dir})"

    def _resolve_bid_folder(self, bid_id: str) -> Path:
        folder_name = bid_id_to_folder_name(bid_id)
        candidate = (self.root_dir / folder_name).resolve()
        # Security check: must stay strictly inside root_dir
        try:
            candidate.relative_to(self.root_dir)
        except ValueError:
            raise InvalidBidIdError(f"Resolved path escapes source root directory: {candidate}")
        if not candidate.is_dir():
            raise IngestionError(f"Tender packet folder not found for bid ID '{bid_id}' at {candidate.name}")
        return candidate

    def _resolve_file_path(self, folder: Path, filename: str) -> Path:
        target = (folder / filename).resolve()
        try:
            target.relative_to(folder)
        except ValueError:
            raise InvalidBidIdError(f"Document filename attempts path traversal: '{filename}'")
        if not target.is_file():
            raise CorruptPacketError(f"Referenced document missing from disk: '{filename}'")
        return target

    def _parse_manifest(self, folder: Path, bid_id: str) -> Tuple[str, TenderDocument, List[TenderDocument]]:
        manifest_file = folder / "manifest.json"
        if not manifest_file.is_file():
            raise CorruptPacketError(f"Missing manifest.json in tender folder '{folder.name}'")

        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CorruptPacketError(f"Corrupt manifest.json in '{folder.name}': {exc}")

        title = data.get("title", f"Tender {bid_id}")
        main_spec = data.get("main_document")
        main_filename = main_spec.get("filename") or main_spec.get("file") if isinstance(main_spec, dict) else None
        if not main_filename:
            raise CorruptPacketError("Manifest missing required 'main_document' filename or file.")

        # Load main document
        main_path = self._resolve_file_path(folder, main_filename)
        main_bytes = main_path.read_bytes()
        main_sha = hashlib.sha256(main_bytes).hexdigest()
        main_pub = parse_iso_datetime(main_spec.get("published_at", "2026-01-01T00:00:00Z"))
        main_doc = TenderDocument(
            name=main_filename,
            content=main_bytes,
            sha256=main_sha,
            published_at=main_pub,
            kind="main",
            sequence=0,
        )

        # Load corrigenda
        corrigenda_specs = data.get("corrigenda", [])
        corrigenda_list: List[TenderDocument] = []
        seen_hashes: Set[str] = {main_sha}

        for idx, spec in enumerate(corrigenda_specs):
            fname = spec.get("filename") or spec.get("file")
            if not fname:
                raise CorruptPacketError(f"Corrigendum entry #{idx+1} missing filename.")
            fpath = self._resolve_file_path(folder, fname)
            fbytes = fpath.read_bytes()
            fsha = hashlib.sha256(fbytes).hexdigest()

            if fsha in seen_hashes:
                raise CorruptPacketError(f"Duplicate document hash detected in packet: {fname} ({fsha[:12]})")
            seen_hashes.add(fsha)

            pub_dt = parse_iso_datetime(spec.get("published_at"))
            seq = spec.get("sequence", idx + 1)

            corrigenda_list.append(
                TenderDocument(
                    name=fname,
                    content=fbytes,
                    sha256=fsha,
                    published_at=pub_dt,
                    kind="corrigendum",
                    sequence=seq,
                )
            )

        # Authoritative ordering: published_at ascending, sequence ascending, name ascending
        # The manifest ordering NEVER dictates resolution order!
        corrigenda_list.sort(key=lambda d: (d.published_at, d.sequence, d.name))

        return title, main_doc, corrigenda_list

    def resolve(self, bid_id: str) -> TenderPacket:
        folder = self._resolve_bid_folder(bid_id)
        title, main_doc, corrigenda = self._parse_manifest(folder, bid_id)
        return TenderPacket(
            bid_id=bid_id,
            title=title,
            main_document=main_doc,
            corrigenda=corrigenda,
        )

    def list_updates(self, bid_id: str, known_sha256s: Set[str]) -> List[TenderDocument]:
        packet = self.resolve(bid_id)
        return [c for c in packet.corrigenda if c.sha256 not in known_sha256s]


class MockGemSource(TenderSource):
    """Built-in demo source with simulated GeM tender packs and late corrigendum publication."""

    def __init__(self, mock_dir: Optional[Path] = None):
        self.mock_dir = (mock_dir or Path("data/mock_gem")).resolve()
        self._unpublished_corrigenda: Dict[str, List[TenderDocument]] = {}
        self._ensure_demo_data()

    @property
    def name(self) -> str:
        return "demo"

    @property
    def description(self) -> str:
        return "Demo GeM Source (Offline Simulation with Corrigenda Updates)"

    def _ensure_demo_data(self) -> None:
        """Create mock GeM tender fixtures if missing on disk."""
        demo_bid = "GEM/2026/B/DEMO0001"
        folder = self.mock_dir / bid_id_to_folder_name(demo_bid)
        folder.mkdir(parents=True, exist_ok=True)

        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            # Create synthetic PDF documents using standard PDF header
            main_pdf = folder / "tender_notice_main.pdf"
            corr1_pdf = folder / "corrigendum_1_turnover.pdf"
            corr2_pdf = folder / "corrigendum_2_experience.pdf"
            corr3_pdf = folder / "corrigendum_3_late_support.pdf"

            main_content = (
                b"%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\n"
                b"% Demo Main Tender Notice: Annual turnover Rs 5.00 Crore, 3 orders required\n"
            )
            corr1_content = (
                b"%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\n"
                b"% Corrigendum 1: Turnover threshold relaxed from 5.00 Crore to Rs 3.00 Crore\n"
            )
            corr2_content = (
                b"%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\n"
                b"% Corrigendum 2: Minimum completed past orders requirement relaxed to 2 orders\n"
            )
            corr3_content = (
                b"%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\n"
                b"% Corrigendum 3: Late clarification regarding 24x7 local support service\n"
            )

            main_pdf.write_bytes(main_content)
            corr1_pdf.write_bytes(corr1_content)
            corr2_pdf.write_bytes(corr2_content)
            corr3_pdf.write_bytes(corr3_content)

            # Write manifest intentionally with OUT-OF-ORDER entries to prove sorting!
            # Corrigendum 2 (18-08-2026) listed BEFORE Corrigendum 1 (10-08-2026)
            manifest = {
                "title": "Supply and Maintenance of High-Capacity Enterprise Networking Switches",
                "main_document": {
                    "filename": "tender_notice_main.pdf",
                    "published_at": "2026-08-01T10:00:00Z",
                },
                "corrigenda": [
                    {
                        "filename": "corrigendum_2_experience.pdf",
                        "published_at": "2026-08-18T15:30:00Z",
                        "sequence": 2,
                    },
                    {
                        "filename": "corrigendum_1_turnover.pdf",
                        "published_at": "2026-08-10T11:00:00Z",
                        "sequence": 1,
                    },
                ],
                "unpublished_corrigenda": [
                    {
                        "filename": "corrigendum_3_late_support.pdf",
                        "published_at": "2026-08-25T16:00:00Z",
                        "sequence": 3,
                    }
                ],
            }
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def resolve(self, bid_id: str) -> TenderPacket:
        source = LocalFolderSource(self.mock_dir)
        return source.resolve(bid_id)

    def publish_next(self, bid_id: str) -> Dict[str, Any]:
        """Publish the next pending corrigendum for the specified bid ID."""
        folder = self.mock_dir / bid_id_to_folder_name(bid_id)
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            return {"published": False, "reason": f"Manifest not found for bid '{bid_id}'"}

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        unpub = data.get("unpublished_corrigenda", [])
        if not unpub:
            return {"published": False, "reason": "no more unpublished corrigenda"}

        # Pop the first unpublished corrigendum
        next_spec = unpub.pop(0)
        data.setdefault("corrigenda", []).append(next_spec)
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        fpath = folder / next_spec["filename"]
        content = fpath.read_bytes()
        doc = TenderDocument(
            name=next_spec["filename"],
            content=content,
            sha256=hashlib.sha256(content).hexdigest(),
            published_at=parse_iso_datetime(next_spec["published_at"]),
            kind="corrigendum",
            sequence=next_spec.get("sequence", 99),
        )
        return {
            "published": True,
            "new_corrigendum": doc.name,
            "document": doc,
        }

    def list_updates(self, bid_id: str, known_sha256s: Set[str]) -> List[TenderDocument]:
        source = LocalFolderSource(self.mock_dir)
        return source.list_updates(bid_id, known_sha256s)


class HttpGemSource(TenderSource):
    """Stub for live HTTP GeM portal access. Strictly disabled and not implemented."""

    @property
    def name(self) -> str:
        return "gem_http"

    @property
    def description(self) -> str:
        return "Live GeM Portal (Not Implemented / Requires Authorization)"

    def resolve(self, bid_id: str) -> TenderPacket:
        raise NotImplementedError(
            "Live GeM fetching is not implemented. It needs official access or permission."
        )

    def list_updates(self, bid_id: str, known_sha256s: Set[str]) -> List[TenderDocument]:
        raise NotImplementedError(
            "Live GeM fetching is not implemented. It needs official access or permission."
        )


# Global registry of enabled sources
_SOURCES: Dict[str, TenderSource] = {}


def get_source(name: str) -> TenderSource:
    """Retrieve enabled source by identifier. Default: 'demo' and 'local'."""
    clean = name.strip().lower()
    if clean not in _SOURCES:
        if clean in ("demo", "mock"):
            _SOURCES[clean] = MockGemSource()
        elif clean in ("local", "folder"):
            root = Path(os.environ.get("LOCAL_TENDERS_DIR", "data/tenders"))
            _SOURCES[clean] = LocalFolderSource(root)
        elif clean == "gem_http":
            # HttpGemSource is never in default registry and always raises NotImplementedError
            raise NotImplementedError(
                "Live GeM fetching is not implemented. It needs official access or permission."
            )
        else:
            raise IngestionError(f"Unknown tender source: '{name}'. Available: 'demo', 'local'.")
    return _SOURCES[clean]


def list_enabled_sources() -> List[Dict[str, str]]:
    """List all enabled and available tender sources with metadata."""
    demo = get_source("demo")
    local = get_source("local")
    return [
        {
            "name": "demo",
            "id": "demo",
            "display_name": "Demo GeM Source",
            "kind": "demo",
            "description": demo.description,
        },
        {
            "name": "local",
            "id": "local",
            "display_name": "Local Folder Source",
            "kind": "local",
            "description": local.description,
        },
    ]
