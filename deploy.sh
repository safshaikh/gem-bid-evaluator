#!/usr/bin/env bash
# ==============================================================================
# BidParakh (gem-bid-evaluator) Cloud Run Deployment Script
# Phase P6: Secret Manager + Cloud Run (asia-south1, single instance)
# ==============================================================================
set -euo pipefail

# ------------------------------------------------------------------------------
# 1. Configuration & Placeholders (EDIT THESE OR PASS AS ENVIRONMENT VARIABLES)
# ------------------------------------------------------------------------------
PROJECT_ID="${PROJECT_ID:-project-3a9bb8a8-c1b7-4379-b38}"
SECRET_NAME="${SECRET_NAME:-gemini-api-key}"
REGION="${REGION:-asia-south1}"
SERVICE_NAME="gem-bid-evaluator"

# Model names (matching app/config.py defaults or custom overrides)
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
GEMINI_FALLBACK_MODEL="${GEMINI_FALLBACK_MODEL:-gemini-3.5-flash-lite}"

echo "============================================================"
echo "BidParakh: Deploying ${SERVICE_NAME} to Google Cloud Run"
echo "Project ID:      ${PROJECT_ID}"
echo "Region:          ${REGION}"
echo "Secret Name:     ${SECRET_NAME}"
echo "Primary Model:   ${GEMINI_MODEL}"
echo "Fallback Model:  ${GEMINI_FALLBACK_MODEL}"
echo "============================================================"

if [ "${PROJECT_ID}" = "<YOUR_GCP_PROJECT_ID>" ]; then
  echo ""
  echo "Error: Please specify your GCP Project ID before deploying."
  echo "Example usage:"
  echo "  PROJECT_ID=my-gcp-project-123 ./deploy.sh"
  exit 1
fi

# ------------------------------------------------------------------------------
# 2. Set Active GCP Project & Enable APIs
# ------------------------------------------------------------------------------
echo "==> [1/5] Configuring active project: ${PROJECT_ID}..."
gcloud config set project "${PROJECT_ID}"

echo "==> [2/5] Enabling required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com

# ------------------------------------------------------------------------------
# 3. Create or Verify Secret in Google Secret Manager
# ------------------------------------------------------------------------------
echo "==> [3/5] Verifying secret '${SECRET_NAME}' in Secret Manager..."
if ! gcloud secrets describe "${SECRET_NAME}" >/dev/null 2>&1; then
  echo "Secret '${SECRET_NAME}' not found. Creating new secret in Secret Manager..."
  gcloud secrets create "${SECRET_NAME}" --replication-policy="automatic"
  echo "Enter your Gemini API key (input hidden):"
  read -s API_KEY_INPUT
  echo -n "${API_KEY_INPUT}" | gcloud secrets versions add "${SECRET_NAME}" --data-file=-
  echo "Secret version added."
else
  echo "Secret '${SECRET_NAME}' exists."
fi

# Grant Secret Accessor role to Compute Engine default service account used by Cloud Run
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "==> [4/5] Granting Secret Accessor role to service account: ${SERVICE_ACCOUNT}..."
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

# ------------------------------------------------------------------------------
# 4. Deploy to Google Cloud Run
# ------------------------------------------------------------------------------
echo "==> [5/5] Deploying container to Cloud Run (region: ${REGION}, instances: 1 min / 1 max)..."
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --min-instances 1 \
  --max-instances 1 \
  --memory 1Gi \
  --timeout 300 \
  --set-secrets GEMINI_API_KEY="${SECRET_NAME}:latest" \
  --set-env-vars GEMINI_MODEL="${GEMINI_MODEL}",GEMINI_FALLBACK_MODEL="${GEMINI_FALLBACK_MODEL}"

# Retrieve deployed Service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')

echo ""
echo "============================================================"
echo "Deployment Succeeded!"
echo "Service URL: ${SERVICE_URL}"
echo "============================================================"
echo ""
echo "==> Verifying /health endpoint on deployed service:"
curl -s "${SERVICE_URL}/health"
echo ""
echo ""
echo "==> Run Phase P6 Preflight Gate command:"
echo "python scripts/preflight.py --base-url ${SERVICE_URL} --runs 10"
echo "============================================================"
