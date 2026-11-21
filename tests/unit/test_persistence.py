"""Unit tests for persistent storage, vault deduplication, audit chain, and migrations."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from app.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db import (
    GENESIS_HASH,
    MIGRATIONS,
    append_audit,
    canonical_payload_str,
    compute_audit_hash,
    db_add_bidder,
    db_add_bidder_doc,
    db_add_tender_doc,
    db_create_tender,
    db_get_evaluation_by_input_hash,
    db_get_latest_evaluation,
    db_get_overrides,
    db_get_tender_audit,
    db_get_tender_details,
    db_save_evaluation,
    db_save_override,
    get_connection,
    init_db,
    verify_audit_chain,
)
from app.storage import LocalStorageProvider, sanitize_filename


class TestPersistence(unittest.TestCase):
    """Test suite covering Phase P9 database, vault, replay caching, and audit logging."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="bidparakh_test_")
        self.db_path = Path(self.temp_dir) / "test_bidparakh.db"
        self.vault_dir = Path(self.temp_dir) / "vault"
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.storage = LocalStorageProvider(self.vault_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_migrations_empty_db_and_idempotence(self):
        """Migrations apply cleanly on an empty DB and a second init_db() is a no-op."""
        # First initialization creates schema_version and all tables
        init_db(self.db_path)
        self.assertTrue(self.db_path.is_file())

        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cur.fetchall()}
        conn.close()

        required_tables = {
            "schema_version",
            "tenders",
            "tender_documents",
            "bidders",
            "bidder_documents",
            "evaluations",
            "overrides",
            "audit_logs",
            "users",
        }
        self.assertTrue(required_tables.issubset(tables), f"Missing tables: {required_tables - tables}")

        # Second initialization is a safe no-op
        init_db(self.db_path)

        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM schema_version;")
        migration_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(migration_count, len(MIGRATIONS))

    def test_vault_deduplication_and_path_traversal(self):
        """Vault stores by SHA-256 deduplicated, sanitizes filenames, and resists path traversal."""
        data1 = b"PDF tender content for qualification"
        sha1 = self.storage.put(data1, "tender.pdf")

        # Deduplication: storing same bytes under another name produces same SHA-256 and single file
        sha2 = self.storage.put(data1, "duplicate_copy.pdf")
        self.assertEqual(sha1, sha2)
        files = list(self.vault_dir.glob("*.bin"))
        self.assertEqual(len(files), 1)

        # Content retrieval matches exactly
        retrieved = self.storage.get(sha1)
        self.assertEqual(retrieved, data1)

        # Path traversal protection
        unsafe_name = "../../etc/passwd.pdf"
        sanitized = sanitize_filename(unsafe_name)
        self.assertNotIn("/", sanitized)
        self.assertNotIn("\\", sanitized)
        self.assertNotIn("..", sanitized)

        # Storing with malicious name stays confined to vault_dir
        sha3 = self.storage.put(b"other content", unsafe_name)
        file_path = self.vault_dir / f"{sha3}.bin"
        self.assertTrue(file_path.is_file())
        self.assertTrue(str(file_path.resolve()).startswith(str(self.vault_dir.resolve())))

    def test_tender_bidders_evaluation_survive_restart(self):
        """Tender, documents, bidders, and evaluation survive simulated application restart."""
        init_db(self.db_path)
        tender_id = "test_tender_101"

        db_create_tender(tender_id, title="IT Hardware Procurement", actor="officer_arman", db_path=self.db_path)
        db_add_tender_doc("doc_1", tender_id, "main_bid.pdf", "sha_doc_1", order_index=0, page_count=5, db_path=self.db_path)
        db_add_tender_doc("doc_2", tender_id, "corrigendum.pdf", "sha_doc_2", order_index=1, page_count=2, db_path=self.db_path)

        bidder_id = "bidder_001"
        db_add_bidder(bidder_id, tender_id, "Apex Tech Solutions", actor="officer_arman", db_path=self.db_path)
        db_add_bidder_doc("bdoc_1", bidder_id, tender_id, "experience_cert.pdf", "sha_bdoc_1", page_count=3, db_path=self.db_path)

        eval_result = {
            "tender_id": tender_id,
            "results": [{"bidder_name": "Apex Tech Solutions", "criterion_id": "exp_orders", "verdict": "PASS"}],
        }
        db_save_evaluation(
            evaluation_id="eval_001",
            tender_id=tender_id,
            input_hash="hash_input_123",
            result_json=json.dumps(eval_result),
            model_id="gemini-3.8-flash",
            db_path=self.db_path,
        )

        # Simulate fresh app instance reading from disk database
        details = db_get_tender_details(tender_id, db_path=self.db_path)
        self.assertIsNotNone(details)
        self.assertEqual(details["tender_id"], tender_id)
        self.assertEqual(details["title"], "IT Hardware Procurement")
        self.assertEqual(len(details["documents"]), 2)
        self.assertEqual(len(details["bidders"]), 1)
        self.assertEqual(len(details["bidders"][0]["documents"]), 1)

        eval_row = db_get_latest_evaluation(tender_id, db_path=self.db_path)
        self.assertIsNotNone(eval_row)
        loaded_res = json.loads(eval_row["result_json"])
        self.assertEqual(loaded_res["results"][0]["verdict"], "PASS")

    def test_replay_cache_by_input_hash(self):
        """Identical input_hash returns stored evaluation without requiring new model calls."""
        init_db(self.db_path)
        input_hash = hashlib.sha256(b"combined_tender_and_bidder_bytes").hexdigest()
        eval_payload = {"verdicts": ["PASS", "FAIL"], "cached": False}

        db_create_tender("t_cache", title="Replay Cache Test", db_path=self.db_path)
        db_save_evaluation(
            evaluation_id="eval_cache_1",
            tender_id="t_cache",
            input_hash=input_hash,
            result_json=json.dumps(eval_payload),
            model_id="gemini-3.8-flash",
            db_path=self.db_path,
        )

        # Replay lookup
        cached = db_get_evaluation_by_input_hash(input_hash, db_path=self.db_path)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["input_hash"], input_hash)
        res_data = json.loads(cached["result_json"])
        self.assertEqual(res_data["verdicts"], ["PASS", "FAIL"])

    def test_override_immutability_and_validation(self):
        """Overrides validate minimum length, preserve computed verdicts, and append audit rows."""
        init_db(self.db_path)
        tender_id = "t_override"
        db_create_tender(tender_id, title="Override Test", db_path=self.db_path)

        # Validation: under 20 characters must be rejected
        short_justification = "Too short"
        with self.assertRaises(ValueError):
            db_save_override(
                override_id="ov_1",
                tender_id=tender_id,
                bidder_id="Bidder1",
                criterion_id="exp_orders",
                old_verdict="FAIL",
                new_verdict="PASS",
                justification=short_justification,
                actor="officer_arman",
                db_path=self.db_path,
            )

        # Valid override (>= 20 characters) succeeds
        valid_justification = "Clarification received on stamp authenticity from competent authority."
        db_save_override(
            override_id="ov_2",
            tender_id=tender_id,
            bidder_id="Bidder1",
            criterion_id="exp_orders",
            old_verdict="FAIL",
            new_verdict="PASS",
            justification=valid_justification,
            actor="officer_arman",
            db_path=self.db_path,
        )

        overrides = db_get_overrides(tender_id, db_path=self.db_path)
        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0]["old_verdict"], "FAIL")
        self.assertEqual(overrides[0]["new_verdict"], "PASS")

        # Verify audit row was recorded for override
        audit = db_get_tender_audit(tender_id, db_path=self.db_path)
        actions = [a["action"] for a in audit]
        self.assertIn("override_recorded", actions)

    def test_audit_chain_integrity_triggers_and_tamper_detection(self):
        """Audit chain passes clean verification, triggers block mutations, and tampering is detected."""
        init_db(self.db_path)
        tender_id = "t_audit"

        # 1. Clean append operations
        append_audit("tender_created", tender_id, "officer", {"name": "Tender 1"}, db_path=self.db_path)
        append_audit("document_added", tender_id, "officer", {"file": "doc.pdf"}, db_path=self.db_path)
        append_audit("evaluation_run", tender_id, "officer", {"status": "ok"}, db_path=self.db_path)

        # 2. Verification on clean log passes
        verify = verify_audit_chain(self.db_path)
        self.assertTrue(verify["ok"])
        self.assertEqual(verify["rows_checked"], 3)
        self.assertIsNone(verify["first_broken_id"])

        # 3. Triggers block UPDATE and DELETE
        conn = get_connection(self.db_path)
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_logs SET actor = 'malicious' WHERE id = 1;")
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_logs WHERE id = 1;")
        conn.close()

        # 4. Bypass triggers to simulate out-of-band tampering (e.g. raw disk edit)
        conn = get_connection(self.db_path)
        conn.execute("DROP TRIGGER audit_logs_no_update;")
        conn.execute("UPDATE audit_logs SET payload_json = '{\"tampered\": true}' WHERE id = 2;")
        conn.commit()
        conn.close()

        # Verification must now catch the broken link at row 2
        tampered_verify = verify_audit_chain(self.db_path)
        self.assertFalse(tampered_verify["ok"])
        self.assertEqual(tampered_verify["first_broken_id"], 2)
        self.assertIn("Tampered row_hash", tampered_verify["reason"])

    def test_auth_roles_and_token_validation(self):
        """Scrypt password hashing, verification, and HS256 JWT tokens with role checks."""
        init_db(self.db_path)

        # Scrypt hashing and verification
        p_hash, salt = hash_password("SecretOfficer@2026")
        self.assertTrue(verify_password("SecretOfficer@2026", p_hash, salt))
        self.assertFalse(verify_password("WrongPassword", p_hash, salt))

        # User creation and authentication
        create_user("officer_jane", "JanePass@123", role="procurement_officer", db_path=self.db_path)
        create_user("auditor_bob", "BobPass@123", role="auditor", db_path=self.db_path)

        user_officer = authenticate_user("officer_jane", "JanePass@123", db_path=self.db_path)
        self.assertIsNotNone(user_officer)
        self.assertEqual(user_officer["role"], "procurement_officer")

        user_auditor = authenticate_user("auditor_bob", "BobPass@123", db_path=self.db_path)
        self.assertIsNotNone(user_auditor)
        self.assertEqual(user_auditor["role"], "auditor")

        # JWT creation and decoding
        token = create_access_token({"sub": "officer_jane", "role": "procurement_officer"})
        decoded = decode_access_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["sub"], "officer_jane")
        self.assertEqual(decoded["role"], "procurement_officer")

        # Expired token is rejected
        expired_token = create_access_token({"sub": "officer_jane", "role": "procurement_officer"}, expires_in_seconds=-10)
        self.assertIsNone(decode_access_token(expired_token))


if __name__ == "__main__":
    unittest.main()
