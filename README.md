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

---

## Ingestion & GeM Sources

BidParakh includes a pluggable ingestion layer (`app/gem_fetcher.py`) that ingests tender packages, validates manifests, enforces chronological corrigenda ordering, and monitors for subsequent amendments.

### Registered Sources

| Source Identifier | Implementation | Purpose |
| :--- | :--- | :--- |
| `demo` | `MockGemSource` | Curated sample bids in `data/mock_gem/` (e.g. `GEM/2026/B/DEMO0001` with progressive corrigenda). |
| `local` | `LocalFolderSource` | Ingests from a local inbox directory (`data/gem_inbox/` or configured root). |
| `http` | `HttpGemSource` | *(Disabled / Stub)* Raises `NotImplementedError`. Automated web scraping or direct HTTP extraction of the live GeM portal is disabled due to authorization, CAPTCHA, and portal terms of use boundaries. |

### Manifest Format & Invariants

Local and mock tender packets reside in directories mapped from Bid IDs (e.g., `GEM/2026/B/DEMO0001` -> `GEM_2026_B_DEMO0001/`) containing a `manifest.json`:

```json
{
  "title": "Supply and Maintenance of High-Capacity Enterprise Networking Switches",
  "main_document": {
    "filename": "tender_notice_main.pdf",
    "published_at": "2026-08-01T10:00:00Z"
  },
  "corrigenda": [
    {
      "filename": "corrigendum_1_turnover.pdf",
      "published_at": "2026-08-10T11:00:00Z",
      "sequence": 1
    },
    {
      "filename": "corrigendum_2_experience.pdf",
      "published_at": "2026-08-18T15:30:00Z",
      "sequence": 2
    }
  ],
  "unpublished_corrigenda": [
    {
      "filename": "corrigendum_3_late_support.pdf",
      "published_at": "2026-08-25T16:00:00Z",
      "sequence": 3
    }
  ]
}
```

- **Chronological Sorting Guarantee:** Irrespective of the order listed in `manifest.json`, documents are strictly sorted by `published_at` ascending, breaking ties by `sequence` and `filename`.
- **Idempotency:** Ingesting an identical `(source, bid_id)` returns the existing tender without duplicating documents in the vault or rows in SQLite.
- **Corrigenda Tracking & Stale Detection:** When a newer corrigendum is detected (`POST /tenders/{id}/check-updates`), applying it (`POST /tenders/{id}/apply-updates`) adds the file to the tender in sequence, records a tamper-evident audit entry, and sets the tender status to `stale` until re-evaluated.
- **Security Boundaries:** Bid IDs are strictly validated (`^[a-zA-Z0-9/\-_]{1,64}$`), path separators are sanitized, and all resolved paths must remain inside the configured source directory. Direct live portal scraping is prohibited.



