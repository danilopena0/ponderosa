# GCP Setup Guide for Ponderosa

This guide walks you through setting up Google Cloud Platform for the Ponderosa podcast intelligence pipeline.

## 1. Create a GCP Account and Project

### Get $300 Free Credits

1. Go to [cloud.google.com](https://cloud.google.com/)
2. Click "Get started for free" or "Start free"
3. Sign in with your Google account
4. Enter billing information (required but won't be charged during free trial)
5. You'll receive **$300 in credits valid for 90 days**

### Create a Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click the project dropdown at the top
3. Click "New Project"
4. Name it something like `ponderosa-podcast` or `podcast-intelligence`
5. Note your **Project ID** (you'll need this)

## 2. Enable Required APIs

Run these commands in Cloud Shell or your terminal (after installing gcloud CLI):

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable all required APIs
gcloud services enable \
    aiplatform.googleapis.com \
    speech.googleapis.com \
    storage.googleapis.com \
    bigquery.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com
```

Or enable them via the console:
1. Go to "APIs & Services" > "Enable APIs and Services"
2. Search for and enable each:
   - **Vertex AI API**
   - **Cloud Speech-to-Text API**
   - **Cloud Storage API** (usually enabled by default)
   - **BigQuery API**
   - **Cloud Run API**
   - **Cloud Build API**

## 3. Create a Cloud Storage Bucket

```bash
# Create bucket (names must be globally unique)
gcloud storage buckets create gs://YOUR_PROJECT_ID-ponderosa \
    --location=us-central1 \
    --uniform-bucket-level-access
```

Or via console:
1. Go to Cloud Storage > Buckets
2. Click "Create"
3. Name: `YOUR_PROJECT_ID-ponderosa` (or similar unique name)
4. Location: us-central1 (cheapest for Vertex AI)
5. Storage class: Standard
6. Access control: Uniform

## 4. Set Up Authentication

### Option A: Local Development with User Credentials (Easiest)

```bash
# Install gcloud CLI if not already installed
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth application-default login

# Set project
gcloud config set project YOUR_PROJECT_ID
```

### Option B: Service Account (For Production)

```bash
# Create service account
gcloud iam service-accounts create ponderosa-sa \
    --display-name="Ponderosa Pipeline Service Account"

# Grant required roles
PROJECT_ID=$(gcloud config get-value project)
SA_EMAIL="ponderosa-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/speech.editor"

# Create and download key
gcloud iam service-accounts keys create ~/ponderosa-sa-key.json \
    --iam-account=$SA_EMAIL

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS=~/ponderosa-sa-key.json
```

## 5. Configure Environment Variables

Create a `.env` file in your project root:

```bash
# .env
GCP_PROJECT_ID=your-project-id
GCP_REGION=us-central1
GCP_BUCKET_NAME=your-project-id-ponderosa

# Optional: Set for service account auth
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

## 6. Set Up Billing Alerts

**Important:** Protect yourself from unexpected charges.

1. Go to Billing > Budgets & alerts
2. Click "Create Budget"
3. Set budget to $50 (or your comfort level)
4. Add alert thresholds at 50%, 90%, 100%
5. Enable email notifications

Recommended alerts:
- $50 - First warning
- $100 - Caution
- $200 - Near limit

## 7. Verify Setup

Test your configuration:

```bash
# Check authentication
gcloud auth list

# Check project
gcloud config get-value project

# Test bucket access
gcloud storage ls gs://YOUR_BUCKET_NAME/

# Test Speech-to-Text API (quick test)
gcloud ml speech recognize \
    'gs://cloud-samples-data/speech/brooklyn_bridge.flac' \
    --language-code='en-US'
```

## Cost Optimization Tips

### Speech-to-Text
- Use **batch mode** for podcasts (75% cheaper than real-time)
- Dynamic Batch rate: ~$0.004/minute vs $0.016/minute

### Vertex AI Vector Search
- **Deploy endpoints only when demoing** - costs ~$1.50/hour when deployed
- Use `undeploy_index` when not in use

### General
- Delete old pipeline runs (they store artifacts)
- Use `us-central1` region (cheapest for AI services)
- Process during off-peak hours when possible

## Quick Reference

| Service | Free Tier | Paid Rate |
|---------|-----------|-----------|
| Speech-to-Text | 60 min/month | $0.016/min (standard) |
| Vertex AI Pipelines | Free (preview) | - |
| Cloud Storage | 5 GB | $0.020/GB/month |
| BigQuery | 1 TB queries/month | $5/TB |

## Troubleshooting

### "Permission denied" errors
```bash
# Re-authenticate
gcloud auth application-default login

# Or check service account permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount"
```

### "API not enabled" errors
```bash
# Enable the specific API
gcloud services enable API_NAME.googleapis.com
```

### Quota exceeded
- Check quotas at: console.cloud.google.com/iam-admin/quotas
- Request increases if needed (usually approved quickly)

## Next Steps

Once setup is complete:

1. Run the RSS parser test:
   ```bash
   uv run ponderosa parse-feed "https://flirtingwithmodels.libsyn.com/rss"
   ```

2. Download a test episode:
   ```bash
   uv run ponderosa download "https://flirtingwithmodels.libsyn.com/rss" -n 1 -o ./downloads
   ```

3. Upload to GCS (requires bucket):
   ```bash
   uv run ponderosa download "https://flirtingwithmodels.libsyn.com/rss" -n 1 --upload
   ```
