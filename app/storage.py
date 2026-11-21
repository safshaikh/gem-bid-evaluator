"""Content-addressable file vault with SHA-256 deduplication and optional GCS adapter.

Design:
- Files are stored on disk strictly by their hex SHA-256 digest (e.g. data/vault/<sha256>.bin).
- Filenames are metadata-only to completely eliminate path traversal risks.
- If GCS_BUCKET environment variable is configured, GCS adapter is loaded lazily.
"""

import hashlib
import logging
import os
from pathlib import Path
import re
from typing import Optional

logger = logging.getLogger(__name__)


def get_vault_dir() -> Path:
    """Resolve vault directory from VAULT_DIR environment variable or default."""
    raw = os.environ.get("VAULT_DIR", os.path.join("data", "vault"))
    p = Path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_filename(filename: str) -> str:
    """Sanitize original filename for safe metadata storage."""
    base = os.path.basename(filename)
    # Remove control chars and path separators
    clean = re.sub(r'[\r\n\t\\/:]', '_', base).strip()
    return clean or "document.pdf"


class LocalStorageProvider:
    """Content-addressable local filesystem storage."""

    def __init__(self, vault_dir: Optional[Path] = None):
        self.vault_dir = vault_dir or get_vault_dir()

    def _file_path(self, digest: str) -> Path:
        # Enforce valid sha256 hex string to prevent any path injection
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError(f"Invalid SHA-256 digest format: {digest}")
        return self.vault_dir / f"{digest.lower()}.bin"

    def put(self, content: bytes, filename: str = "") -> str:
        """Store content deduplicated by SHA-256. Returns hex digest."""
        digest = hashlib.sha256(content).hexdigest()
        dest = self._file_path(digest)
        if not dest.is_file():
            # Write atomically via temp file
            temp_path = dest.with_suffix(".tmp")
            temp_path.write_bytes(content)
            temp_path.replace(dest)
        return digest

    def get(self, digest: str) -> Optional[bytes]:
        """Retrieve file bytes by SHA-256 digest or None if missing."""
        path = self._file_path(digest)
        if path.is_file():
            return path.read_bytes()
        return None

    def exists(self, digest: str) -> bool:
        """Return True if content exists in vault."""
        return self._file_path(digest).is_file()


class GCSStorageProvider:
    """Lazy GCS storage provider used only when GCS_BUCKET is provided."""

    def __init__(self, bucket_name: str):
        # Lazy import so google-cloud-storage is not required when running locally
        try:
            from google.cloud import storage  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-storage is required when GCS_BUCKET is configured."
            ) from exc

        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def put(self, content: bytes, filename: str = "") -> str:
        digest = hashlib.sha256(content).hexdigest()
        blob = self.bucket.blob(f"vault/{digest}.bin")
        if not blob.exists():
            blob.upload_from_string(content, content_type="application/pdf")
        return digest

    def get(self, digest: str) -> Optional[bytes]:
        blob = self.bucket.blob(f"vault/{digest}.bin")
        if blob.exists():
            return blob.download_as_bytes()
        return None

    def exists(self, digest: str) -> bool:
        return self.bucket.blob(f"vault/{digest}.bin").exists()


_PROVIDER = None


def get_storage():
    """Return active storage provider (Local by default, GCS if GCS_BUCKET set)."""
    global _PROVIDER
    if _PROVIDER is None:
        gcs_bucket = os.environ.get("GCS_BUCKET")
        if gcs_bucket:
            logger.info(f"Using GCS Storage Provider with bucket: {gcs_bucket}")
            _PROVIDER = GCSStorageProvider(gcs_bucket)
        else:
            _PROVIDER = LocalStorageProvider()
    return _PROVIDER


def put(content: bytes, filename: str = "") -> str:
    """Store bytes in vault. Returns SHA-256 hex string."""
    return get_storage().put(content, filename)


def get(digest: str) -> Optional[bytes]:
    """Retrieve raw bytes by SHA-256 hex string."""
    return get_storage().get(digest)


def exists(digest: str) -> bool:
    """Check existence by SHA-256 hex string."""
    return get_storage().exists(digest)
