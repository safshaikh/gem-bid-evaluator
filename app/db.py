"""Persistent database layer for BidParakh using Python standard library sqlite3.

Features:
- Pure stdlib sqlite3 (no external ORM dependencies).
- Versioned, idempotent migrations.
- WAL mode, foreign keys enabled, write locking.
- Replay caching based on input_hash.
- Tamper-evident hash-chained audit log with SQLite triggers preventing UPDATE/DELETE.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level lock for concurrent thread write protection
_DB_WRITE_LOCK = threading.RLock()


def get_db_path() -> Path:
    """Resolve database path from environment variable or default location."""
    raw = os.environ.get("DATABASE_PATH", os.path.join("data", "bidparakh.db"))
    p = Path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open connection with foreign keys and WAL mode configured."""
    target = db_path or get_db_path()
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


# --- Versioned Migrations ---

def _migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    """Create initial core tables and indices."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tenders (
        tender_id TEXT PRIMARY KEY,
        title TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'not_evaluated',
        actor TEXT NOT NULL DEFAULT 'demo-officer',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tender_documents (
        doc_id TEXT PRIMARY KEY,
        tender_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        order_index INTEGER NOT NULL,
        page_count INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (tender_id) REFERENCES tenders(tender_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS bidders (
        bidder_id TEXT PRIMARY KEY,
        tender_id TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (tender_id) REFERENCES tenders(tender_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS bidder_documents (
        doc_id TEXT PRIMARY KEY,
        bidder_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        page_count INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (bidder_id) REFERENCES bidders(bidder_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS evaluations (
        evaluation_id TEXT PRIMARY KEY,
        tender_id TEXT NOT NULL,
        input_hash TEXT NOT NULL,
        result_json TEXT NOT NULL,
        model_id TEXT NOT NULL DEFAULT '',
        fallback_model_id TEXT NOT NULL DEFAULT '',
        is_replay_hit INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (tender_id) REFERENCES tenders(tender_id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_evaluations_input_hash ON evaluations(input_hash);
    CREATE INDEX IF NOT EXISTS idx_evaluations_tender_id ON evaluations(tender_id);

    CREATE TABLE IF NOT EXISTS overrides (
        override_id TEXT PRIMARY KEY,
        tender_id TEXT NOT NULL,
        bidder_id TEXT NOT NULL,
        criterion_id TEXT NOT NULL,
        old_verdict TEXT NOT NULL,
        new_verdict TEXT NOT NULL,
        justification TEXT NOT NULL,
        actor TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (tender_id) REFERENCES tenders(tender_id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_overrides_tender_id ON overrides(tender_id);

    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'procurement_officer',
        created_at TEXT NOT NULL
    );
    """)


def _migration_002_tamper_evident_audit_log(conn: sqlite3.Connection) -> None:
    """Create immutable hash-chained audit_logs table with blocking triggers."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        tender_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        row_hash TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_logs_tender_id ON audit_logs(tender_id);

    CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
    BEFORE UPDATE ON audit_logs
    BEGIN
        SELECT RAISE(ABORT, 'audit_logs entries are immutable and cannot be updated');
    END;

    CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
    BEFORE DELETE ON audit_logs
    BEGIN
        SELECT RAISE(ABORT, 'audit_logs entries are immutable and cannot be deleted');
    END;
    """)


MIGRATIONS = [
    (1, "001_initial_schema", _migration_001_initial_schema),
    (2, "002_tamper_evident_audit_log", _migration_002_tamper_evident_audit_log),
]


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize database and execute unapplied migrations sequentially."""
    target = db_path or get_db_path()
    with _DB_WRITE_LOCK:
        conn = get_connection(target)
        try:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """)
            conn.commit()

            cur = conn.cursor()
            cur.execute("SELECT version FROM schema_version ORDER BY version ASC;")
            applied = {row[0] for row in cur.fetchall()}

            for v, name, func in MIGRATIONS:
                if v not in applied:
                    logger.info(f"Applying migration {v}: {name}")
                    func(conn)
                    now_utc = datetime.now(timezone.utc).isoformat()
                    conn.execute(
                        "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?);",
                        (v, name, now_utc),
                    )
                    conn.commit()
        finally:
            conn.close()


# --- Tamper-Evident Audit Logging ---

GENESIS_HASH = "0" * 64


def canonical_payload_str(payload: Any) -> str:
    """Serialize payload to canonical JSON with sorted keys and minimal whitespace."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_audit_hash(
    prev_hash: str,
    ts: str,
    actor: str,
    action: str,
    tender_id: str,
    payload_json: str,
) -> str:
    """Compute deterministic SHA-256 hash for audit chain link."""
    payload_clean = canonical_payload_str(payload_json)
    chain_input = f"{prev_hash}{ts}{actor}{action}{tender_id}{payload_clean}"
    return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()


def append_audit(
    action: str,
    tender_id: str,
    actor: str = "demo-officer",
    payload: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Append a row to the audit chain inside an atomic BEGIN IMMEDIATE transaction."""
    payload = payload or {}
    payload_str = canonical_payload_str(payload)
    ts = datetime.now(timezone.utc).isoformat()

    with _DB_WRITE_LOCK:
        conn = get_connection(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            cur.execute("SELECT row_hash FROM audit_logs ORDER BY id DESC LIMIT 1;")
            last = cur.fetchone()
            prev_hash = last["row_hash"] if last else GENESIS_HASH

            row_hash = compute_audit_hash(prev_hash, ts, actor, action, tender_id, payload_str)

            cur.execute(
                """
                INSERT INTO audit_logs (ts, actor, action, tender_id, payload_json, prev_hash, row_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (ts, actor, action, tender_id, payload_str, prev_hash, row_hash),
            )
            inserted_id = cur.lastrowid
            conn.commit()
            return int(inserted_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def verify_audit_chain(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Verify hash chain integrity across all audit_logs rows."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, ts, actor, action, tender_id, payload_json, prev_hash, row_hash FROM audit_logs ORDER BY id ASC;")
        rows = cur.fetchall()

        if not rows:
            return {"ok": True, "rows_checked": 0, "first_broken_id": None, "reason": None}

        expected_prev = GENESIS_HASH
        for idx, row in enumerate(rows):
            rid = row["id"]
            if row["prev_hash"] != expected_prev:
                return {
                    "ok": False,
                    "rows_checked": idx + 1,
                    "first_broken_id": rid,
                    "reason": f"Mismatched prev_hash at row {rid}. Expected {expected_prev[:12]}..., found {row['prev_hash'][:12]}...",
                }

            expected_row_hash = compute_audit_hash(
                row["prev_hash"],
                row["ts"],
                row["actor"],
                row["action"],
                row["tender_id"],
                row["payload_json"],
            )

            if row["row_hash"] != expected_row_hash:
                return {
                    "ok": False,
                    "rows_checked": idx + 1,
                    "first_broken_id": rid,
                    "reason": f"Tampered row_hash at row {rid}. Computed {expected_row_hash[:12]}..., found {row['row_hash'][:12]}...",
                }

            expected_prev = row["row_hash"]

        return {"ok": True, "rows_checked": len(rows), "first_broken_id": None, "reason": None}
    finally:
        conn.close()


# --- Database Entity Operations ---

def db_create_tender(
    tender_id: str,
    title: str = "",
    actor: str = "demo-officer",
    db_path: Optional[Path] = None,
) -> None:
    """Register tender entity and write audit log."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_WRITE_LOCK:
        conn = get_connection(db_path)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO tenders (tender_id, title, status, actor, created_at, updated_at)
                VALUES (?, ?, 'not_evaluated', ?, ?, ?);
                """,
                (tender_id, title, actor, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    append_audit(
        action="tender_created",
        tender_id=tender_id,
        actor=actor,
        payload={"title": title},
        db_path=db_path,
    )


def db_add_tender_doc(
    doc_id: str,
    tender_id: str,
    filename: str,
    sha256: str,
    order_index: int,
    page_count: int = 1,
    actor: str = "demo-officer",
    db_path: Optional[Path] = None,
) -> None:
    """Record tender document association and append audit."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_WRITE_LOCK:
        conn = get_connection(db_path)
        try:
            conn.execute(
                """
                INSERT INTO tender_documents (doc_id, tender_id, filename, sha256, order_index, page_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (doc_id, tender_id, filename, sha256, order_index, page_count, now),
            )
            conn.commit()
        finally:
            conn.close()

    append_audit(
        action="document_added",
        tender_id=tender_id,
        actor=actor,
        payload={"doc_id": doc_id, "filename": filename, "sha256": sha256, "order_index": order_index},
        db_path=db_path,
    )


def db_add_bidder(
    bidder_id: str,
    tender_id: str,
    name: str,
    actor: str = "demo-officer",
    db_path: Optional[Path] = None,
) -> None:
    """Record bidder registration and append audit."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_WRITE_LOCK:
        conn = get_connection(db_path)
        try:
            conn.execute(
                """
                INSERT INTO bidders (bidder_id, tender_id, name, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (bidder_id, tender_id, name, now),
            )
            conn.commit()
        finally:
            conn.close()

    append_audit(
        action="bidder_added",
        tender_id=tender_id,
        actor=actor,
        payload={"bidder_id": bidder_id, "bidder_name": name},
        db_path=db_path,
    )


def db_add_bidder_doc(
    doc_id: str,
    bidder_id: str,
    tender_id: str,
    filename: str,
    sha256: str,
    page_count: int = 1,
    actor: str = "demo-officer",
    db_path: Optional[Path] = None,
) -> None:
    """Record bidder document association."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_WRITE_LOCK:
        conn = get_connection(db_path)
        try:
            conn.execute(
                """
                INSERT INTO bidder_documents (doc_id, bidder_id, filename, sha256, page_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (doc_id, bidder_id, filename, sha256, page_count, now),
            )
            conn.commit()
        finally:
            conn.close()

    append_audit(
        action="bidder_document_added",
        tender_id=tender_id,
        actor=actor,
        payload={"bidder_id": bidder_id, "doc_id": doc_id, "filename": filename, "sha256": sha256},
        db_path=db_path,
    )


def db_save_evaluation(
    evaluation_id: str,
    tender_id: str,
    input_hash: str,
    result_json: str,
    model_id: str = "",
    fallback_model_id: str = "",
    is_replay_hit: bool = False,
    actor: str = "demo-officer",
    db_path: Optional[Path] = None,
) -> None:
    """Persist evaluation result, update tender status, and record audit log."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_WRITE_LOCK:
        conn = get_connection(db_path)
        try:
            conn.execute(
                """
                INSERT INTO evaluations (
                    evaluation_id, tender_id, input_hash, result_json,
                    model_id, fallback_model_id, is_replay_hit, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    evaluation_id,
                    tender_id,
                    input_hash,
                    result_json,
                    model_id,
                    fallback_model_id,
                    1 if is_replay_hit else 0,
                    now,
                ),
            )
            conn.execute(
                "UPDATE tenders SET status = 'evaluated', updated_at = ? WHERE tender_id = ?;",
                (now, tender_id),
            )
            conn.commit()
        finally:
            conn.close()

    append_audit(
        action="evaluation_run",
        tender_id=tender_id,
        actor=actor,
        payload={
            "evaluation_id": evaluation_id,
            "input_hash": input_hash,
            "is_replay_hit": is_replay_hit,
            "model_id": model_id,
        },
        db_path=db_path,
    )


def db_get_evaluation_by_input_hash(
    input_hash: str,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve evaluation row matching input_hash for instantaneous replay caching."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT evaluation_id, tender_id, input_hash, result_json, model_id, created_at
            FROM evaluations
            WHERE input_hash = ?
            ORDER BY created_at DESC LIMIT 1;
            """,
            (input_hash,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def db_get_latest_evaluation(
    tender_id: str,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve latest evaluation result for a tender."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT evaluation_id, tender_id, input_hash, result_json, model_id, created_at
            FROM evaluations
            WHERE tender_id = ?
            ORDER BY created_at DESC LIMIT 1;
            """,
            (tender_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def db_save_override(
    override_id: str,
    tender_id: str,
    bidder_id: str,
    criterion_id: str,
    old_verdict: str,
    new_verdict: str,
    justification: str,
    actor: str = "demo-officer",
    db_path: Optional[Path] = None,
) -> None:
    """Store officer override, mark tender status as overridden, and append audit log."""
    if len(justification.strip()) < 20:
        raise ValueError("Justification must be at least 20 characters long.")

    now = datetime.now(timezone.utc).isoformat()
    with _DB_WRITE_LOCK:
        conn = get_connection(db_path)
        try:
            conn.execute(
                """
                INSERT INTO overrides (
                    override_id, tender_id, bidder_id, criterion_id,
                    old_verdict, new_verdict, justification, actor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    override_id,
                    tender_id,
                    bidder_id,
                    criterion_id,
                    old_verdict,
                    new_verdict,
                    justification.strip(),
                    actor,
                    now,
                ),
            )
            conn.execute(
                "UPDATE tenders SET status = 'overridden', updated_at = ? WHERE tender_id = ?;",
                (now, tender_id),
            )
            conn.commit()
        finally:
            conn.close()

    append_audit(
        action="override_recorded",
        tender_id=tender_id,
        actor=actor,
        payload={
            "override_id": override_id,
            "bidder_id": bidder_id,
            "criterion_id": criterion_id,
            "old_verdict": old_verdict,
            "new_verdict": new_verdict,
            "justification": justification.strip(),
        },
        db_path=db_path,
    )


def db_get_overrides(
    tender_id: str,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all overrides for a tender in chronological order."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT override_id, tender_id, bidder_id, criterion_id,
                   old_verdict, new_verdict, justification, actor, created_at
            FROM overrides
            WHERE tender_id = ?
            ORDER BY created_at ASC;
            """,
            (tender_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def db_list_tenders(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List all tenders with bidder counts and evaluation status."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.tender_id, t.title, t.status, t.actor, t.created_at, t.updated_at,
                   COUNT(DISTINCT b.bidder_id) as bidder_count,
                   COUNT(DISTINCT td.doc_id) as document_count
            FROM tenders t
            LEFT JOIN bidders b ON t.tender_id = b.tender_id
            LEFT JOIN tender_documents td ON t.tender_id = td.tender_id
            GROUP BY t.tender_id
            ORDER BY t.created_at DESC;
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def db_get_tender_details(
    tender_id: str,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve full tender details including documents, bidders, and bidder documents."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tender_id, title, status, actor, created_at, updated_at FROM tenders WHERE tender_id = ?;",
            (tender_id,),
        )
        t_row = cur.fetchone()
        if not t_row:
            return None

        tender_dict = dict(t_row)

        # Tender documents
        cur.execute(
            "SELECT doc_id, filename, sha256, order_index, page_count, created_at FROM tender_documents WHERE tender_id = ? ORDER BY order_index ASC;",
            (tender_id,),
        )
        tender_dict["documents"] = [dict(r) for r in cur.fetchall()]

        # Bidders
        cur.execute(
            "SELECT bidder_id, name, created_at FROM bidders WHERE tender_id = ? ORDER BY created_at ASC;",
            (tender_id,),
        )
        bidders = [dict(r) for r in cur.fetchall()]
        for b in bidders:
            cur.execute(
                "SELECT doc_id, filename, sha256, page_count, created_at FROM bidder_documents WHERE bidder_id = ? ORDER BY created_at ASC;",
                (b["bidder_id"],),
            )
            b["documents"] = [dict(r) for r in cur.fetchall()]

        tender_dict["bidders"] = bidders
        return tender_dict
    finally:
        conn.close()


def db_get_tender_audit(
    tender_id: str,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieve chronological audit trail for a specific tender."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, ts, actor, action, tender_id, payload_json, prev_hash, row_hash
            FROM audit_logs
            WHERE tender_id = ?
            ORDER BY id ASC;
            """,
            (tender_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
