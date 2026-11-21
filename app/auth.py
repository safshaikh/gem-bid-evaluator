"""Lightweight, standard-library-only authentication and JWT HS256 module.

Gated by AUTH_ENABLED environment variable (default: false).
Uses stdlib hashlib.scrypt for password hashing (no passlib).
Uses stdlib hmac and hashlib.sha256 for JWT HS256 (no PyJWT).
"""

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
from typing import Any, Dict, Optional, Tuple

from app.db import get_connection

logger = logging.getLogger(__name__)


def is_auth_enabled() -> bool:
    """Return True only if AUTH_ENABLED is explicitly set to true/1."""
    return os.environ.get("AUTH_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def get_jwt_secret() -> str:
    """Retrieve JWT secret from environment or raise if auth is enabled without secret."""
    secret = os.environ.get("JWT_SECRET")
    if not secret and is_auth_enabled():
        raise RuntimeError("JWT_SECRET environment variable is mandatory when AUTH_ENABLED=true.")
    return secret or "bidparakh-dev-insecure-secret"


# --- Stdlib Password Hashing with scrypt ---

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash password using stdlib hashlib.scrypt and return (hash_hex, salt_hex)."""
    salt_hex = salt or secrets.token_hex(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_hex.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
    )
    return key.hex(), salt_hex


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify password matches stored scrypt hash in constant time."""
    computed_hash, _ = hash_password(password, salt=salt)
    return hmac.compare_digest(computed_hash, password_hash)


# --- Stdlib JWT HS256 Implementation ---

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data_str: str) -> bytes:
    padding = "=" * (4 - len(data_str) % 4) if len(data_str) % 4 != 0 else ""
    return base64.urlsafe_b64decode(data_str + padding)


def create_access_token(
    payload: Dict[str, Any],
    expires_in_seconds: int = 86400,
) -> str:
    """Create signed HS256 JWT using standard library hmac and hashlib."""
    secret = get_jwt_secret()
    header = {"alg": "HS256", "typ": "JWT"}
    token_payload = dict(payload)
    token_payload["exp"] = int(datetime.now(timezone.utc).timestamp()) + expires_in_seconds

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(token_payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify HS256 signature and expiration, returning payload if valid."""
    secret = get_jwt_secret()
    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()

    try:
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None

        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        now = int(datetime.now(timezone.utc).timestamp())
        if payload.get("exp", 0) < now:
            return None

        return payload
    except Exception:
        return None


# --- Database User Management ---

def create_user(
    username: str,
    password: str,
    role: str = "procurement_officer",
    db_path: Optional[Path] = None,
) -> None:
    """Create user record with scrypt hash and salt."""
    p_hash, salt = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO users (username, password_hash, salt, role, created_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (username.strip().lower(), p_hash, salt, role, now),
        )
        conn.commit()
    finally:
        conn.close()


def authenticate_user(
    username: str,
    password: str,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Validate user credentials and return user info dict with role."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, password_hash, salt, role FROM users WHERE username = ?;",
            (username.strip().lower(),),
        )
        row = cur.fetchone()
        if not row:
            return None
        if verify_password(password, row["password_hash"], row["salt"]):
            return {"username": row["username"], "role": row["role"]}
        return None
    finally:
        conn.close()
