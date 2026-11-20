# ==============================================================================
# BidParakh (gem-bid-evaluator) Cloud Run Deployment Script (PowerShell)
# Phase P6: Secret Manager + Cloud Run (asia-south1, single instance)
# ==============================================================================

param (
    [string]$ProjectId = "project-3a9bb8a8-c1b7-4379-b38",
    [string]$SecretName = "gemini-api-key",
    [string]$Region = "asia-south1",
    [string]$ServiceName = "gem-bid-evaluator",
    [string]$GeminiModel = "gemini-3.8-flash",
    [string]$GeminiFallbackModel = "gemini-3.5-flash-lite"
)

$ErrorActionPreference = "Stop"

if (-not $ProjectId -or $ProjectId -eq "<YOUR_GCP_PROJECT_ID>") {
    Write-Host "Error: Please specify -ProjectId or set env:PROJECT_ID." -ForegroundColor Red
    Write-Host "Example: .\deploy.ps1 -ProjectId 'my-gcp-project-123'"
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "BidParakh: Deploying $ServiceName to Google Cloud Run" -ForegroundColor Cyan
Write-Host "Project ID:      $ProjectId"
Write-Host "Region:          $Region"
Write-Host "Secret Name:     $SecretName"
Write-Host "Primary Model:   $GeminiModel"
Write-Host "Fallback Model:  $GeminiFallbackModel"
Write-Host "============================================================"

# 1. Configure Project & APIs
Write-Host "`n==> [1/5] Setting active project..." -ForegroundColor Yellow
gcloud config set project $ProjectId

Write-Host "==> [2/5] Enabling Cloud Run and Secret Manager APIs..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com

# 2. Secret Manager
Write-Host "==> [3/5] Checking secret in Secret Manager..." -ForegroundColor Yellow
$secretExists = $false
try {
    gcloud secrets describe $SecretName 2>$null
    $secretExists = ($LASTEXITCODE -eq 0)
} catch {
    $secretExists = $false
}

if (-not $secretExists) {
    Write-Host "Creating secret '$SecretName'..."
    gcloud secrets create $SecretName --replication-policy="automatic"
    $apiKey = Read-Host -Prompt "Enter Gemini API Key (plain text)"
    $apiKey | gcloud secrets versions add $SecretName --data-file=-
} else {
    Write-Host "Secret '$SecretName' already exists."
}

# 3. Grant IAM Permission
$projectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$serviceAccount = "$projectNumber-compute@developer.gserviceaccount.com"

Write-Host "==> [4/5] Granting secretAccessor permission to $serviceAccount..." -ForegroundColor Yellow
gcloud secrets add-iam-policy-binding $SecretName `
    --member="serviceAccount:$serviceAccount" `
    --role="roles/secretmanager.secretAccessor"

# 4. Deploy to Cloud Run
Write-Host "==> [5/5] Deploying container to Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --source . `
    --region $Region `
    --allow-unauthenticated `
    --min-instances 1 `
    --max-instances 1 `
    --memory 1Gi `
    --timeout 300 `
    --set-secrets "GEMINI_API_KEY=$SecretName`:latest" `
    --set-env-vars "GEMINI_MODEL=$GeminiModel,GEMINI_FALLBACK_MODEL=$GeminiFallbackModel"

$serviceUrl = (gcloud run services describe $ServiceName --region $Region --format="value(status.url)").Trim()

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "Deployment Succeeded!" -ForegroundColor Green
Write-Host "Service URL: $serviceUrl" -ForegroundColor Green
Write-Host "============================================================"

Write-Host "`n==> Verifying /health endpoint:"
Invoke-RestMethod -Uri "$serviceUrl/health" | ConvertTo-Json

Write-Host "`n==> Run Phase P6 Preflight Gate command:" -ForegroundColor Cyan
Write-Host "python scripts/preflight.py --base-url $serviceUrl --runs 10"
