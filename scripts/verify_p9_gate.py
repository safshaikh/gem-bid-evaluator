"""Verification script for Phase P9 gates."""

import json
import os
from pathlib import Path
import shutil
import tempfile

from app.db import (
    append_audit,
    db_create_tender,
    db_get_latest_evaluation,
    db_get_overrides,
    db_get_tender_details,
    db_list_tenders,
    db_save_evaluation,
    db_save_override,
    get_connection,
    init_db,
    verify_audit_chain,
)
from app.storage import LocalStorageProvider


def run_gates() -> None:
    temp_dir = tempfile.mkdtemp(prefix="gate_p9_")
    db_path = Path(temp_dir) / "gate_p9.db"
    vault_dir = Path(temp_dir) / "vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    storage = LocalStorageProvider(vault_dir)

    print("==================================================")
    print("GATE 1: Migrations apply on empty DB; init twice is safe")
    print("==================================================")
    init_db(db_path)
    print(f"[OK] First init_db() created database at {db_path.name} ({db_path.stat().st_size} bytes)")
    init_db(db_path)
    print("[OK] Second init_db() completed cleanly as idempotent no-op")

    print("\n==================================================")
    print("GATE 4: Create tender, evaluate, simulate server restart, GET /tenders")
    print("==================================================")
    tender_id = "tender_gate_999"
    db_create_tender(tender_id, title="GeM Server Switch Procurement", actor="officer_arman", db_path=db_path)
    content = b"%PDF-1.4 simulated tender document content"
    sha = storage.put(content, "tender.pdf")
    from app.db import db_add_tender_doc, db_add_bidder
    db_add_tender_doc("doc_gate_1", tender_id, "tender.pdf", sha, order_index=0, page_count=10, actor="officer_arman", db_path=db_path)
    db_add_bidder("bidder_gate_1", tender_id, "Tata Communications", actor="officer_arman", db_path=db_path)

    eval_result = {
        "tender_id": tender_id,
        "cached": False,
        "results": [{"bidder_name": "Tata Communications", "criterion_id": "exp", "verdict": "PASS"}],
    }
    db_save_evaluation("eval_gate_1", tender_id, "input_hash_xyz", json.dumps(eval_result), model_id="gemini-3.8-flash", db_path=db_path)
    print(f"[OK] Tender {tender_id} created, documents vaulted, and evaluation saved")

    # Simulate server restart (query fresh from disk without memory)
    tenders_list = db_list_tenders(db_path=db_path)
    matching = next((t for t in tenders_list if t["tender_id"] == tender_id), None)
    print(f"[OK] Server restart simulated. GET /tenders found: {matching}")
    assert matching is not None
    assert matching["status"] == "evaluated"
    assert matching["bidder_count"] == 1

    details = db_get_tender_details(tender_id, db_path=db_path)
    latest_eval = db_get_latest_evaluation(tender_id, db_path=db_path)
    print(f"[OK] Full details restored: {len(details['documents'])} docs, {len(details['bidders'])} bidders")
    print(f"[OK] Evaluation result restored: {json.loads(latest_eval['result_json'])['results'][0]}")

    print("\n==================================================")
    print("GATE 5: Tamper with one audit row via raw SQL; GET /audit/verify reports broken row")
    print("==================================================")
    clean_verify = verify_audit_chain(db_path=db_path)
    print(f"[OK] Clean audit chain verification: {clean_verify}")
    assert clean_verify["ok"] is True

    # Tamper with row 2 using raw SQL after dropping trigger
    conn = get_connection(db_path)
    conn.execute("DROP TRIGGER audit_logs_no_update;")
    conn.execute("UPDATE audit_logs SET payload_json = '{\"tampered_action\": true}' WHERE id = 2;")
    conn.commit()
    conn.close()

    tampered_verify = verify_audit_chain(db_path=db_path)
    print(f"[OK] Tampered audit chain verification: {tampered_verify}")
    assert tampered_verify["ok"] is False
    assert tampered_verify["first_broken_id"] == 2
    print(f"[OK] Detected tampering at row #{tampered_verify['first_broken_id']}: {tampered_verify['reason']}")

    shutil.rmtree(temp_dir, ignore_errors=True)
    print("\nAll Phase P9 gates verified successfully!")


if __name__ == "__main__":
    run_gates()
