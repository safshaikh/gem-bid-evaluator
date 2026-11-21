# BidParakh: GeM Bid Evaluator

> Officer-side GeM bid evaluation: AI reads, code decides.

BidParakh helps government procurement officers evaluate technical bids submitted on the GeM portal. It resolves corrigenda criteria, extracts null-and-void lists, validates evidence quotes against PDF text layers, and executes deterministic rule evaluations.

---

## Development Setup

```bash
# 1. Environment and dependencies
.venv/bin/pip install -r requirements.txt

# 2. Run unit tests
.venv/bin/python -m pytest tests/unit -q

# 3. Run application server
.venv/bin/uvicorn app.main:app --port 8080 --reload
```

---

## End-to-End Demo Sequence (cURL)

> **Important Ordering Rule:** Tender upload order matters! Always upload the **main bid PDF first**, followed by **corrigenda in date order**. This guarantees that the resolver's newest-wins rule applies correctly and supersedes older criteria.

### 1. Upload Tender Documents (Main Bid first, then Corrigendum)
```bash
# Response returns tender_id (e.g. "a1b2c3d4...")
TENDER_ID=$(curl -s -X POST http://localhost:8080/tenders \
  -F "files=@fixtures/GEM-2026-B-7945477-main-bid.pdf" \
  -F "files=@fixtures/GEM-2026-B-7945477-C5-corrigendum.pdf" \
  | jq -r .tender_id)

echo "Created Tender ID: $TENDER_ID"
```

### 2. Add Bidder Submission Packs
```bash
# Add Bidder 1 (Pass pack)
curl -s -X POST "http://localhost:8080/tenders/$TENDER_ID/bidders" \
  -F "name=Alpha Solutions Pvt Ltd" \
  -F "files=@fixtures/GEM-2026-B-7945477-C5-corrigendum.pdf"

# Add Bidder 2 (Fail pack)
curl -s -X POST "http://localhost:8080/tenders/$TENDER_ID/bidders" \
  -F "name=Beta Technologies" \
  -F "files=@fixtures/GEM-2026-B-7945477-C5-corrigendum.pdf"

# Add Bidder 3 (Review pack)
curl -s -X POST "http://localhost:8080/tenders/$TENDER_ID/bidders" \
  -F "name=Gamma Infotech" \
  -F "files=@fixtures/GEM-2026-B-7945477-C5-corrigendum.pdf"
```

### 3. Run Evaluation Pipeline
```bash
# Runs extraction, quote verification, rules engine, and caches result to disk
curl -s -X POST "http://localhost:8080/tenders/$TENDER_ID/evaluate" | jq .
```

### 4. Download Verdict Matrix (CSV)
```bash
curl -s "http://localhost:8080/tenders/$TENDER_ID/matrix.csv" -o matrix.csv
cat matrix.csv
```

### 5. View Procurement Officer Report (HTML)
Open in your browser:
```bash
open "http://localhost:8080/tenders/$TENDER_ID/report"
```
Or retrieve raw HTML via curl:
```bash
curl -s "http://localhost:8080/tenders/$TENDER_ID/report"
```

---

## Preflight Verification

Verify verdict stability across multiple runs:

```bash
# Generate synthetic bidder fixture PDFs (if not already present)
.venv/bin/python scripts/make_fixtures.py

# Run preflight against local server or deployed URL
.venv/bin/python scripts/preflight.py --base-url http://localhost:8080 --runs 10
```

---

## Persistence & Storage Architecture

BidParakh utilizes a standard library SQLite database (`app/db.py`) and a content-addressable local vault (`app/storage.py`) for tender persistence, replay caching, officer overrides, and tamper-evident audit logging.

> [!WARNING]
> **Ephemeral Storage on Google Cloud Run:**
> SQLite and the local file vault (`data/vault/`) on Cloud Run are **ephemeral**. Any instance restart or redeployment resets local disk contents.
> 
> - **Hackathon / Single-Instance Deployment:** Keep `--max-instances 1` on Cloud Run so all requests route to the same container instance.
> - **Production Roadmap:** True production environments require managed Cloud SQL (PostgreSQL) and a Google Cloud Storage (GCS) bucket for the document vault. PostgreSQL support is planned for future phases behind the database abstraction layer.

### Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DATABASE_PATH` | `data/bidparakh.db` | File path for SQLite database. Created automatically if missing. |
| `VAULT_DIR` | `data/vault` | Content-addressable directory storing uploaded PDFs by SHA-256 digest. |
| `GCS_BUCKET` | *(unset)* | Google Cloud Storage bucket for document storage. If unset, uses local vault. |
| `AUTH_ENABLED` | `false` | When `false`, demo mode runs with zero login friction (`demo-officer`). When `true`, requires JWT HS256 authentication. |
| `JWT_SECRET` | *(unset)* | Secret key for signing and verifying JWT tokens when `AUTH_ENABLED=true`. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Primary Gemini model for extraction and multimodal vision. |
| `GEMINI_FALLBACK_MODEL` | `gemini-3.5-flash-lite` | Secondary fallback model. |


