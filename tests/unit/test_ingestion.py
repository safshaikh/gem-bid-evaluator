"""Unit tests for pluggable ingestion layer with local and mock GeM sources."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.db import (
    append_audit,
    db_create_tender,
    db_find_tender_by_source,
    db_get_latest_evaluation,
    db_get_tender_details,
    db_save_evaluation,
    db_update_tender_status,
    init_db,
    verify_audit_chain,
)
from app.gem_fetcher import (
    CorruptPacketError,
    HttpGemSource,
    IngestionError,
    InvalidBidIdError,
    LocalFolderSource,
    MockGemSource,
    TenderDocument,
    TenderPacket,
    get_source,
    list_enabled_sources,
    validate_bid_id,
)
from app.jobs import create_tender, get_tender, persist_tender_document
from app.resolver import resolve_criteria
from app.schemas import Criterion, RuleType
from app.storage import LocalStorageProvider


class TestIngestion(unittest.TestCase):
    """Test suite covering Phase P10 pluggable ingestion, sorting, security, and updates."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="bidparakh_ingest_test_")
        self.db_path = Path(self.temp_dir) / "test_ingest.db"
        self.vault_dir = Path(self.temp_dir) / "vault"
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.db_path)
        self.storage = LocalStorageProvider(self.vault_dir)

        # Isolated copy of mock gem fixtures
        self.mock_dir = Path(self.temp_dir) / "mock_gem"
        if Path("data/mock_gem").is_dir():
            shutil.copytree(Path("data/mock_gem"), self.mock_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_manifest_ordering(self):
        """Test 1: Manifest with out-of-order corrigenda is sorted strictly by published_at ascending, sequence tie-breaker."""
        source_dir = Path(self.temp_dir) / "sources"
        bid_folder = source_dir / "GEM_2026_B_ORDERTEST"
        bid_folder.mkdir(parents=True, exist_ok=True)

        # Create dummy PDF files
        main_pdf = bid_folder / "main.pdf"
        c1_pdf = bid_folder / "c1.pdf"
        c2_pdf = bid_folder / "c2.pdf"
        c3_pdf = bid_folder / "c3.pdf"

        main_pdf.write_bytes(b"%PDF-1.4 main document")
        c1_pdf.write_bytes(b"%PDF-1.4 corrigendum 1")
        c2_pdf.write_bytes(b"%PDF-1.4 corrigendum 2")
        c3_pdf.write_bytes(b"%PDF-1.4 corrigendum 3")

        # Manifest lists corrigenda deliberately in reverse order and with tie-break sequence
        manifest_data = {
            "title": "Reverse Order Test Tender",
            "main_document": {
                "file": "main.pdf",
                "published_at": "2026-08-01T10:00:00Z"
            },
            "corrigenda": [
                {
                    "file": "c3.pdf",
                    "published_at": "2026-08-20T10:00:00Z",
                    "sequence": 3
                },
                {
                    "file": "c1.pdf",
                    "published_at": "2026-08-10T10:00:00Z",
                    "sequence": 1
                },
                {
                    "file": "c2.pdf",
                    "published_at": "2026-08-10T10:00:00Z",
                    "sequence": 2
                }
            ]
        }
        (bid_folder / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        source = LocalFolderSource(source_dir)
        packet = source.resolve("GEM/2026/B/ORDERTEST")

        self.assertEqual(packet.main_document.name, "main.pdf")
        self.assertEqual(len(packet.corrigenda), 3)

        # Expected chronological order: c1 (Aug 10 seq 1), c2 (Aug 10 seq 2), c3 (Aug 20 seq 3)
        self.assertEqual(packet.corrigenda[0].name, "c1.pdf")
        self.assertEqual(packet.corrigenda[1].name, "c2.pdf")
        self.assertEqual(packet.corrigenda[2].name, "c3.pdf")

    def test_golden_criteria_resolution(self):
        """Test 2: Ingest dummy test pack (GEM/2026/B/DEMO0001) and confirm chronological criteria resolution."""
        mock_source = MockGemSource(mock_dir=self.mock_dir)
        packet = mock_source.resolve("GEM/2026/B/DEMO0001")

        self.assertEqual(packet.bid_id, "GEM/2026/B/DEMO0001")
        self.assertEqual(len(packet.corrigenda), 2)  # Notice + C1 + C2 initially published

        # Model criteria corresponding to the 3 documents in chronological order
        # Doc 0 (Main): turnover >= 5 Cr (50,000,000 INR)
        doc0_criteria = [
            Criterion(
                id="annual_turnover",
                title="Annual Turnover",
                rule_type=RuleType.MIN_AVG_VALUE.value,
                threshold=50000000.0,
                unit="INR",
                source_doc=packet.main_document.name,
                source_page=1,
                source_quote="Average annual turnover must be at least Rs 5.0 Crore",
                supersedes=[],
            )
        ]
        # Doc 1 (Corrigendum 1): turnover lowered to >= 3 Cr (30,000,000 INR)
        doc1_criteria = [
            Criterion(
                id="annual_turnover",
                title="Annual Turnover (Revised)",
                rule_type=RuleType.MIN_AVG_VALUE.value,
                threshold=30000000.0,
                unit="INR",
                source_doc=packet.corrigenda[0].name,
                source_page=1,
                source_quote="Turnover requirement relaxed from 5.0 Crore to 3.0 Crore",
                supersedes=[],
            )
        ]
        # Doc 2 (Corrigendum 2): MSME EMD exemption added
        doc2_criteria = [
            Criterion(
                id="emd_msme_exemption",
                title="EMD Exemption for MSE",
                rule_type=RuleType.DOC_PRESENT.value,
                threshold=None,
                unit=None,
                source_doc=packet.corrigenda[1].name,
                source_page=1,
                source_quote="Micro and Small Enterprises (MSEs) are exempted from EMD submission",
                supersedes=[],
            )
        ]

        resolved = resolve_criteria([doc0_criteria, doc1_criteria, doc2_criteria])
        crit_map = {c.id: c for c in resolved}

        self.assertIn("annual_turnover", crit_map)
        self.assertEqual(crit_map["annual_turnover"].threshold, 30000000.0)
        self.assertEqual(crit_map["annual_turnover"].source_doc, packet.corrigenda[0].name)
        self.assertIn("annual_turnover", crit_map["annual_turnover"].supersedes)

        self.assertIn("emd_msme_exemption", crit_map)
        self.assertEqual(crit_map["emd_msme_exemption"].source_doc, packet.corrigenda[1].name)

    def test_path_traversal_and_security(self):
        """Test 3: Malicious, escaping, or unapproved bid IDs are rejected before any filesystem call."""
        invalid_ids = [
            "../etc/passwd",
            "..\\..\\windows",
            "a/b/../../../secret",
            "has space in id",
            "bad$char*here",
            "",
            "A" * 65,  # Exceeds max 64 chars
            "../../secret",
            "/absolute/path",
        ]

        for bad_id in invalid_ids:
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(InvalidBidIdError):
                    validate_bid_id(bad_id)

        source = MockGemSource()
        for bad_id in invalid_ids:
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(InvalidBidIdError):
                    source.resolve(bad_id)

    def test_http_source_raises_not_implemented(self):
        """Test 4: HttpGemSource strictly raises NotImplementedError and is not in default registry."""
        sources = list_enabled_sources()
        source_names = [s["name"] for s in sources]
        self.assertNotIn("http", source_names)

        # get_source("http") raises IngestionError/ValueError because it is excluded from active registry
        with self.assertRaises((IngestionError, ValueError, NotImplementedError)):
            get_source("http")

        # Direct instantiation of HttpGemSource raises NotImplementedError on resolve
        http_source = HttpGemSource()
        with self.assertRaises(NotImplementedError):
            http_source.resolve("GEM/2026/B/123456")

        with self.assertRaises(NotImplementedError):
            http_source.list_updates("GEM/2026/B/123456", [])

    def test_idempotent_ingestion(self):
        """Test 5: Ingesting the same bid twice returns the existing tender without duplicating database records."""
        source_name = "demo"
        bid_id = "GEM/2026/B/DEMO0001"

        # 1. First ingestion
        source = get_source(source_name)
        packet = source.resolve(bid_id)

        tender_id = "tender_idempotent_test_1"
        db_create_tender(
            tender_id=tender_id,
            title=packet.title,
            actor="officer_test",
            source_name=source_name,
            source_bid_id=bid_id,
            db_path=self.db_path,
        )

        all_docs = [packet.main_document] + packet.corrigenda
        for idx, doc in enumerate(all_docs):
            sha = self.storage.put(doc.bytes, doc.name)
            from app.db import db_add_tender_doc
            db_add_tender_doc(
                doc_id=f"doc_{idx}",
                tender_id=tender_id,
                filename=doc.name,
                sha256=sha,
                order_index=idx,
                page_count=1,
                actor="officer_test",
                db_path=self.db_path,
            )

        # 2. Second ingestion attempt (lookup by source and bid_id)
        existing = db_find_tender_by_source(source_name, bid_id, db_path=self.db_path)
        self.assertIsNotNone(existing)
        self.assertEqual(existing["tender_id"], tender_id)

        # Verify document count remains exactly 3
        details = db_get_tender_details(tender_id, db_path=self.db_path)
        self.assertEqual(len(details["documents"]), 3)

    def test_updates_flow_and_audit_integrity(self):
        """Test 6: Ingestion, update detection, applying corrigendum, stale status, re-evaluation, and audit integrity."""
        mock_source = MockGemSource(mock_dir=self.mock_dir)
        bid_id = "GEM/2026/B/DEMO0001"
        packet = mock_source.resolve(bid_id)

        tender_id = "tender_updates_test_1"
        db_create_tender(
            tender_id=tender_id,
            title=packet.title,
            actor="officer_test",
            source_name="demo",
            source_bid_id=bid_id,
            db_path=self.db_path,
        )

        # Store initial 3 documents
        all_docs = [packet.main_document] + packet.corrigenda
        known_shas = []
        for idx, doc in enumerate(all_docs):
            sha = self.storage.put(doc.bytes, doc.name)
            known_shas.append(sha)
            from app.db import db_add_tender_doc
            db_add_tender_doc(
                doc_id=f"doc_initial_{idx}",
                tender_id=tender_id,
                filename=doc.name,
                sha256=sha,
                order_index=idx,
                page_count=1,
                actor="officer_test",
                db_path=self.db_path,
            )

        # Initially, no updates exist
        initial_updates = mock_source.list_updates(bid_id, known_shas)
        self.assertEqual(len(initial_updates), 0)

        # Simulate initial evaluation
        initial_eval_json = json.dumps({"evaluation": "PASS_V1", "criteria_count": 2})
        db_save_evaluation(
            evaluation_id="eval_v1",
            tender_id=tender_id,
            input_hash="hash_v1",
            result_json=initial_eval_json,
            db_path=self.db_path,
        )
        initial_tender = db_get_tender_details(tender_id, db_path=self.db_path)
        self.assertEqual(initial_tender["status"], "evaluated")

        # Publish Corrigendum 3 via publish_next
        publish_res = mock_source.publish_next(bid_id)
        self.assertTrue(publish_res["published"])
        self.assertEqual(publish_res["new_corrigendum"], "corrigendum_3_late_support.pdf")

        # Now list_updates detects 1 new corrigendum
        pending_updates = mock_source.list_updates(bid_id, known_shas)
        self.assertEqual(len(pending_updates), 1)
        self.assertEqual(pending_updates[0].name, "corrigendum_3_late_support.pdf")

        # Apply updates: add document, mark tender status as stale
        for offset, doc in enumerate(pending_updates):
            new_sha = self.storage.put(doc.bytes, doc.name)
            from app.db import db_add_tender_doc
            db_add_tender_doc(
                doc_id=f"doc_update_{offset}",
                tender_id=tender_id,
                filename=doc.name,
                sha256=new_sha,
                order_index=len(all_docs) + offset,
                page_count=1,
                actor="officer_test",
                db_path=self.db_path,
            )
            append_audit(
                action="corrigendum_applied",
                tender_id=tender_id,
                actor="officer_test",
                payload={"corrigendum": doc.name, "sha256": new_sha},
                db_path=self.db_path,
            )

        db_update_tender_status(tender_id, "stale", db_path=self.db_path)

        # Verify tender status is stale and document count is 4
        updated_details = db_get_tender_details(tender_id, db_path=self.db_path)
        self.assertEqual(updated_details["status"], "stale")
        self.assertEqual(len(updated_details["documents"]), 4)

        # Verify old evaluation is still preserved and readable
        old_eval = db_get_latest_evaluation(tender_id, db_path=self.db_path)
        self.assertIsNotNone(old_eval)
        self.assertIn("PASS_V1", old_eval["result_json"])

        # Re-evaluate with updated documents: status becomes evaluated again
        re_eval_json = json.dumps({"evaluation": "PASS_V2", "criteria_count": 3})
        db_save_evaluation(
            evaluation_id="eval_v2",
            tender_id=tender_id,
            input_hash="hash_v2",
            result_json=re_eval_json,
            db_path=self.db_path,
        )
        re_evaluated_details = db_get_tender_details(tender_id, db_path=self.db_path)
        self.assertEqual(re_evaluated_details["status"], "evaluated")

        # Verify hash chain is intact across all operations
        audit_check = verify_audit_chain(db_path=self.db_path)
        self.assertTrue(audit_check["ok"])
        self.assertIsNone(audit_check["first_broken_id"])

    def test_error_handling_local_folder_source(self):
        """Test 7: LocalFolderSource error handling for invalid JSON, missing PDFs, and unparsable dates."""
        base_dir = Path(self.temp_dir) / "corrupt_sources"

        # Case A: Invalid JSON manifest
        folder_a = base_dir / "GEM_2026_B_CORRUPTJSON"
        folder_a.mkdir(parents=True, exist_ok=True)
        (folder_a / "manifest.json").write_text("{ unclosed json: true, ", encoding="utf-8")
        src_a = LocalFolderSource(base_dir)
        with self.assertRaises(CorruptPacketError):
            src_a.resolve("GEM/2026/B/CORRUPTJSON")

        # Case B: Missing PDF referenced by manifest
        folder_b = base_dir / "GEM_2026_B_MISSINGPDF"
        folder_b.mkdir(parents=True, exist_ok=True)
        manifest_b = {
            "title": "Missing File Tender",
            "main_document": {"file": "non_existent.pdf", "published_at": "2026-08-01T10:00:00Z"}
        }
        (folder_b / "manifest.json").write_text(json.dumps(manifest_b), encoding="utf-8")
        src_b = LocalFolderSource(base_dir)
        with self.assertRaises(CorruptPacketError):
            src_b.resolve("GEM/2026/B/MISSINGPDF")

        # Case C: Unparsable date in manifest
        folder_c = base_dir / "GEM_2026_B_BADDATE"
        folder_c.mkdir(parents=True, exist_ok=True)
        (folder_c / "main.pdf").write_bytes(b"%PDF-1.4 dummy")
        manifest_c = {
            "title": "Bad Date Tender",
            "main_document": {"file": "main.pdf", "published_at": "not-a-date-string"}
        }
        (folder_c / "manifest.json").write_text(json.dumps(manifest_c), encoding="utf-8")
        src_c = LocalFolderSource(base_dir)
        with self.assertRaises(CorruptPacketError):
            src_c.resolve("GEM/2026/B/BADDATE")


if __name__ == "__main__":
    unittest.main()
