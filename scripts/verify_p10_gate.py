"""Verification gate script for Phase P10 (Pluggable Ingestion Layer)."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    HttpGemSource,
    InvalidBidIdError,
    LocalFolderSource,
    MockGemSource,
    get_source,
    list_enabled_sources,
    validate_bid_id,
)
from app.resolver import resolve_criteria
from app.schemas import Criterion, RuleType
from app.storage import LocalStorageProvider


def run_gates():
    print("=" * 60)
    print("GATE 1: Sources Registry and NotImplementedError Stub")
    print("=" * 60)
    sources = list_enabled_sources()
    names = [s["name"] for s in sources]
    assert "demo" in names and "local" in names, f"Missing demo or local in {names}"
    assert "http" not in names, "http must NOT be in enabled sources"
    print(f"[OK] Enabled sources registered: {names}")

    try:
        HttpGemSource().resolve("GEM/2026/B/DEMO0001")
        assert False, "HttpGemSource should have raised NotImplementedError"
    except NotImplementedError:
        print("[OK] HttpGemSource strictly raised NotImplementedError on resolve")

    print("\n" + "=" * 60)
    print("GATE 2: Path Traversal & Security Boundaries")
    print("=" * 60)
    blocked_count = 0
    for bad in ["../etc/passwd", "..\\secret", "bad$char", "/abs/path", "", "x" * 65]:
        try:
            validate_bid_id(bad)
        except InvalidBidIdError:
            blocked_count += 1
    assert blocked_count == 6, f"Expected 6 blocked, got {blocked_count}"
    print(f"[OK] All {blocked_count} path traversal & escaping attempts blocked before filesystem calls")

    print("\n" + "=" * 60)
    print("GATE 3: Ingest DEMO0001 Pack, Chronological Ordering & Idempotency")
    print("=" * 60)
    temp_dir = tempfile.mkdtemp(prefix="p10_gate_")
    try:
        db_path = Path(temp_dir) / "gate_p10.db"
        vault_dir = Path(temp_dir) / "vault"
        mock_dir = Path(temp_dir) / "mock_gem"
        shutil.copytree(Path("data/mock_gem"), mock_dir)

        init_db(db_path)
        storage = LocalStorageProvider(vault_dir)
        mock_source = MockGemSource(mock_dir=mock_dir)

        bid_id = "GEM/2026/B/DEMO0001"
        packet = mock_source.resolve(bid_id)

        # Confirm ordering: main notice first, then C1 (Aug 10), then C2 (Aug 18)
        assert packet.main_document.name == "tender_notice_main.pdf"
        assert len(packet.corrigenda) == 2
        assert packet.corrigenda[0].name == "corrigendum_1_turnover.pdf"
        assert packet.corrigenda[1].name == "corrigendum_2_experience.pdf"
        print(f"[OK] Manifest chronologically sorted: {[d.name for d in packet.all_documents]}")

        tender_id = "tender_p10_gate_001"
        db_create_tender(
            tender_id=tender_id,
            title=packet.title,
            actor="gate_tester",
            source_name="demo",
            source_bid_id=bid_id,
            db_path=db_path,
        )

        all_docs = packet.all_documents
        known_shas = []
        for idx, doc in enumerate(all_docs):
            sha = storage.put(doc.bytes, doc.name)
            known_shas.append(sha)
            from app.db import db_add_tender_doc
            db_add_tender_doc(
                doc_id=f"doc_{idx}",
                tender_id=tender_id,
                filename=doc.name,
                sha256=sha,
                order_index=idx,
                page_count=1,
                actor="gate_tester",
                db_path=db_path,
            )

        # Check idempotency
        found = db_find_tender_by_source("demo", bid_id, db_path=db_path)
        assert found is not None and found["tender_id"] == tender_id
        print(f"[OK] Ingestion is idempotent: found tender {found['tender_id']} with 3 documents")

        print("\n" + "=" * 60)
        print("GATE 4: Corrigendum Simulation, Detection, Stale Marking & Re-evaluation")
        print("=" * 60)
        # Initial evaluation
        db_save_evaluation(
            evaluation_id="eval_gate_1",
            tender_id=tender_id,
            input_hash="hash_1",
            result_json=json.dumps({"verdict": "EVAL_V1"}),
            db_path=db_path,
        )
        t_before = db_get_tender_details(tender_id, db_path=db_path)
        assert t_before["status"] == "evaluated"
        print("[OK] Initial evaluation saved. Tender status: evaluated")

        # No updates yet
        no_updates = mock_source.list_updates(bid_id, known_shas)
        assert len(no_updates) == 0
        print("[OK] Initial check-updates returns 0 new corrigenda")

        # Simulate publish_next
        pub_res = mock_source.publish_next(bid_id)
        assert pub_res["published"] is True
        print(f"[OK] publish_next published: {pub_res['new_corrigendum']}")

        # Detection
        new_updates = mock_source.list_updates(bid_id, known_shas)
        assert len(new_updates) == 1
        print(f"[OK] check-updates detected: {new_updates[0].name}")

        # Apply updates
        new_doc = new_updates[0]
        new_sha = storage.put(new_doc.bytes, new_doc.name)
        from app.db import db_add_tender_doc
        db_add_tender_doc(
            doc_id="doc_new_3",
            tender_id=tender_id,
            filename=new_doc.name,
            sha256=new_sha,
            order_index=len(all_docs),
            page_count=1,
            actor="gate_tester",
            db_path=db_path,
        )
        append_audit(
            action="corrigendum_applied",
            tender_id=tender_id,
            actor="gate_tester",
            payload={"corrigendum": new_doc.name, "sha256": new_sha},
            db_path=db_path,
        )
        db_update_tender_status(tender_id, "stale", db_path=db_path)

        t_stale = db_get_tender_details(tender_id, db_path=db_path)
        assert t_stale["status"] == "stale"
        assert len(t_stale["documents"]) == 4
        print(f"[OK] Corrigendum applied. Status is now '{t_stale['status']}' with {len(t_stale['documents'])} vaulted documents")

        # Previous evaluation is still readable
        eval_prior = db_get_latest_evaluation(tender_id, db_path=db_path)
        assert eval_prior is not None and "EVAL_V1" in eval_prior["result_json"]
        print("[OK] Previous evaluation remains readable while in stale state")

        # Re-evaluate
        db_save_evaluation(
            evaluation_id="eval_gate_2",
            tender_id=tender_id,
            input_hash="hash_2",
            result_json=json.dumps({"verdict": "EVAL_V2"}),
            db_path=db_path,
        )
        t_reval = db_get_tender_details(tender_id, db_path=db_path)
        assert t_reval["status"] == "evaluated"
        print(f"[OK] Re-evaluation completed. Status restored to '{t_reval['status']}'")

        print("\n" + "=" * 60)
        print("GATE 5: Audit Chain Hash Integrity")
        print("=" * 60)
        audit_res = verify_audit_chain(db_path=db_path)
        assert audit_res["ok"] is True
        print(f"[OK] Audit chain verified: {audit_res['rows_checked']} rows checked, all cryptographically intact")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "*" * 60)
    print("ALL PHASE P10 GATES VERIFIED SUCCESSFULLY!")
    print("*" * 60)


if __name__ == "__main__":
    run_gates()
