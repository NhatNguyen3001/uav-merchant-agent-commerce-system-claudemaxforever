#!/usr/bin/env bash
# One-shot hosted deploy. Requires: gcloud + firebase CLIs logged in, ANTHROPIC_API_KEY in the shell.
set -euo pipefail
PROJECT=merchant-agent-commerce-system
REGION=australia-southeast1
SERVICE=macs-api
REPO=macs
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/$SERVICE:$(date +%Y%m%d%H%M%S)"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com aiplatform.googleapis.com firestore.googleapis.com --project "$PROJECT"

# Idempotent: a transient failure of the describe check must not abort the deploy on "already exists".
gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location "$REGION" --project "$PROJECT" 2>&1 | grep -v ALREADY_EXISTS || true

if ! gcloud secrets describe anthropic-api-key --project "$PROJECT" >/dev/null 2>&1; then
  printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=- --project "$PROJECT"
fi

# The Cloud Run revision runs as the compute default service account; grant it Firestore, Vertex and the secret BEFORE deploying.
SA="$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')-compute@developer.gserviceaccount.com"
for ROLE in roles/datastore.user roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role "$ROLE" --quiet >/dev/null
done

gcloud builds submit backend --tag "$IMAGE" --project "$PROJECT"

gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --project "$PROJECT" \
  --allow-unauthenticated --min-instances 1 --max-instances 1 --memory 1Gi --timeout 900 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,FAKE_LLM=0,REPLAY=${REPLAY:-1},RULES_LOCKED=${RULES_LOCKED:-1},MACS_MODEL=${MACS_MODEL:-claude-sonnet-5}" \
  --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest"

# Firebase Hosting buffers rewritten responses, which breaks Server-Sent Events. The console therefore calls
# the Cloud Run service directly (CORS is open on the API); Hosting only serves the static files.
API_URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format 'value(status.url)')
(cd frontend && npm ci && VITE_API_BASE="$API_URL" npm run build)
firebase deploy --only hosting --project "$PROJECT"

echo "API:  $API_URL"
echo "Web:  https://$PROJECT.web.app"
