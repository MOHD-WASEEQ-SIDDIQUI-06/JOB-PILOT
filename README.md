# JobPilot

JobPilot is a hackathon project for an autonomous AI job-search and application-preparation agent. The goal is to help a user discover relevant opportunities, assess fit, prepare personalized application materials, and keep a human in the loop before any submission is made.

## Current architecture

The repository is organized as a monorepo with a backend API, a frontend dashboard, and supporting documentation.

- Backend: Python + FastAPI service with a Gemini-powered analysis agent
- Frontend: React + TypeScript + Vite dashboard for workflow controls and status display
- Infrastructure: Cloud Run, Firestore, and Pub/Sub deployment preparation
- Docs: project design and setup references
- Tests: API validation and safe agent mocks

## Firestore persistent state architecture

JobPilot keeps workflow state in a repository abstraction so the business logic remains unchanged whether the data is stored in memory or in Firestore.

- `WorkflowRepository` defines the persistence contract.
- `InMemoryWorkflowRepository` is used for local development and automated tests.
- `FirestoreWorkflowRepository` is the production-backed repository for Google Cloud Firestore.
- `WorkflowService` depends on the repository interface, not on Firestore directly.

This keeps the workflow engine portable while allowing Cloud Run to use Firestore without rewriting the state machine logic.

## Firestore collection structure

The workflow records are stored in a `jobpilot-workflows` collection by default.

Each document contains:
- workflow_id
- job_title
- location
- skills
- experience
- status
- current_stage
- created_at
- updated_at
- discovered_jobs
- analyzed_jobs
- ranked_jobs
- strong_matches
- preparation_packages
- requires_human_review
- error

No API keys or secrets are stored in workflow records.

## Environment variables

For local development and tests, use the in-memory repository:

```env
WORKFLOW_REPOSITORY_MODE=memory
WORKFLOW_COLLECTION=jobpilot-workflows
GOOGLE_CLOUD_PROJECT=jobpilot-local
FIRESTORE_PROJECT_ID=jobpilot-local
```

For a real Google Cloud Firestore setup, configure it explicitly. Cloud Run should use Application Default Credentials from its runtime service account; a credential file is only for local developer setup:

```env
WORKFLOW_REPOSITORY_MODE=firestore
GOOGLE_CLOUD_PROJECT=your-project-id
FIRESTORE_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

Do not commit service-account JSON files, credentials, or `.env` files containing secrets.

## Local development instructions

The application remains testable without real Google Cloud credentials because the default repository mode is in-memory unless Firestore is explicitly configured.

```bash
cd backend
copy .env.example .env
pytest -q
```

If Firebase or Firestore credentials are not available, the app automatically falls back to the in-memory repository.

## Pub/Sub asynchronous workflow architecture

JobPilot now supports asynchronous workflow execution without requiring real Google Cloud credentials in local development.

- `PubSubPublisher` defines the message contract for queueing a workflow.
- `InMemoryPubSubPublisher` is the default local implementation for tests and demos.
- `GooglePubSubPublisher` is the production implementation that sends a minimal message payload with only the `workflow_id`.
- `WorkflowWorker` receives the workflow ID, loads the current record from the repository, runs the existing Taskmaster flow, and updates the persisted workflow state.

The API layer creates a queued workflow record, publishes the workflow ID, and returns immediately so the user sees a fast response while the background worker processes the task.

### Local demo mode

For local demonstrations, the in-memory publisher simulates Pub/Sub delivery by starting a background thread that invokes the same worker interface the production path uses.

This means the code path is structurally the same, but no Google credentials or service-account files are needed to demo the workflow.

### Production configuration

```env
PUBSUB_MODE=google
PUBSUB_PROJECT_ID=your-project-id
PUBSUB_TOPIC=jobpilot-workflows
GOOGLE_CLOUD_PROJECT=your-project-id
```

A real Pub/Sub setup requires a topic and a subscription for the worker to consume workflow messages. The messages themselves contain only the workflow ID, not candidate data or secrets.

### Worker startup

In production, the worker runs as a separate Cloud Run HTTP service. A Pub/Sub authenticated push subscription posts the standard Pub/Sub envelope to `/api/internal/pubsub/workflows`. The endpoint decodes the base64 JSON payload, extracts `workflow_id`, and calls the existing `WorkflowWorker`. The worker updates Firestore as the workflow moves through:

- queued
- discovering
- analyzing
- ranking
- preparing
- waiting_for_review
- completed
- failed

The system never auto-submits applications. It only prepares human-review packages and keeps the application status as `not_submitted` unless a person explicitly chooses to act.

## Step 9: Cloud Run deployment preparation

Step 9 prepares the containers and IAM configuration but does not deploy anything. The production flow is:

```text
API Cloud Run -> Pub/Sub topic -> authenticated push subscription
-> Worker Cloud Run HTTP endpoint -> WorkflowWorker -> Firestore
```

### Containers

Build from the `backend` directory with the files already provided:

- `Dockerfile` starts `app.main:app` for the API service.
- `Dockerfile.worker` starts `app.worker_api:app` for the worker service.
- Both images listen on the Cloud Run `PORT` value, defaulting to `8080`.
- `.dockerignore` excludes `.env`, virtual environments, tests, and local caches.

The worker endpoint is:

```http
POST /api/internal/pubsub/workflows
```

Cloud Run IAM authenticates the Pub/Sub push request. The application validates the envelope and message data; it does not accept service-account keys or bearer secrets from environment variables.

### Google Cloud identities and permissions

Use separate user-managed service accounts for the API and worker. Grant only the permissions required by each service:

- API runtime: Firestore read/write access and Pub/Sub publisher access.
- Worker runtime: Firestore read/write access.
- Pub/Sub push-authentication service account: permission to invoke the worker Cloud Run service.

Cloud Run supplies Application Default Credentials automatically through the attached runtime service account. Do not set `GOOGLE_APPLICATION_CREDENTIALS` in Cloud Run and never commit a service-account JSON file. For local development only, that variable may point to a developer-owned file outside the repository.

### Preparation commands

Run these only after selecting the intended Google Cloud project and reviewing IAM policy. They are documented preparation steps and have not been run by this project session:

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com firestore.googleapis.com pubsub.googleapis.com artifactregistry.googleapis.com

gcloud firestore databases create --location=YOUR_FIRESTORE_REGION --type=firestore-native
gcloud pubsub topics create jobpilot-workflows
```

Create runtime service accounts and grant least-privilege roles according to your organization policy. Build and deploy the API and worker as separate Cloud Run services, setting these production variables on both services as appropriate:

```env
APP_NAME=jobpilot-api
ENVIRONMENT=production
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
FIRESTORE_PROJECT_ID=YOUR_PROJECT_ID
WORKFLOW_REPOSITORY_MODE=firestore
WORKFLOW_COLLECTION=jobpilot-workflows
PUBSUB_MODE=google
PUBSUB_PROJECT_ID=YOUR_PROJECT_ID
PUBSUB_TOPIC=jobpilot-workflows
GEMINI_MODEL=gemini-3.5-flash
GEMINI_API_KEY=provided-through-your-approved-secret-management-process
```

After the worker service exists, create a Pub/Sub push subscription targeting its HTTPS URL and configure an OIDC token using the Pub/Sub push-authentication service account. Grant that identity Cloud Run Invoker on the worker service. Do not make the worker endpoint public merely to avoid configuring IAM.

### Local and offline verification

Local defaults remain `WORKFLOW_REPOSITORY_MODE=memory` and `PUBSUB_MODE=memory`. No Google credentials are needed for the test suite. Firestore tests use a fake client, Pub/Sub tests use a fake publisher, and worker push tests use FastAPI `TestClient` with locally constructed base64 envelopes.

From the repository root:

```bash
cd backend
.venv\\Scripts\\python -m pytest -q
docker build -f Dockerfile -t jobpilot-api:local .
docker build -f Dockerfile.worker -t jobpilot-worker:local .
cd ..\\frontend
npm run build
```

These checks validate application behavior and image construction without deploying to Google Cloud or requiring production credentials.

## Step 10: deployment automation and billing-safe validation

Step 10 adds reproducible deployment configuration under `infrastructure/`. Nothing in this step deploys resources automatically. The scripts require an active billing account before they can provision or deploy.

### Validate locally without billing

From PowerShell at the repository root:

```powershell
.\infrastructure\validate.ps1
cd backend
.venv\Scripts\python -m pytest -q
cd ..\frontend
npm run build
```

`frontend/.env.example` preserves the local API at `http://localhost:8000`. For a deployed frontend, copy `frontend/.env.production.example` to `.env.production` and set `VITE_API_URL` to the API Cloud Run HTTPS URL.

### Google Cloud preparation and deployment

First authenticate, select the project, and check prerequisites. The following command is read-only until `-Deploy` is supplied:

```powershell
gcloud auth login
gcloud auth application-default login
.\infrastructure\deploy.ps1 -Target Provision -ProjectId YOUR_PROJECT_ID
```

After billing is enabled and reviewed, run these targets in order:

```powershell
.\infrastructure\deploy.ps1 -Target Provision -ProjectId YOUR_PROJECT_ID -Deploy
.\infrastructure\deploy.ps1 -Target Api -ProjectId YOUR_PROJECT_ID -Region us-central1 -Deploy
.\infrastructure\deploy.ps1 -Target Worker -ProjectId YOUR_PROJECT_ID -Region us-central1 -Deploy
.\infrastructure\deploy.ps1 -Target Subscription -ProjectId YOUR_PROJECT_ID -Region us-central1 -Deploy
```

`Provision` enables Cloud Run, Firestore, Pub/Sub, and Artifact Registry APIs, creates the Firestore database, topic, repository, runtime service accounts, and least-privilege IAM bindings. `Api` and `Worker` build the existing `backend/Dockerfile` and `backend/Dockerfile.worker` images and deploy private Cloud Run services. `Subscription` grants the authenticated Pub/Sub push identity Cloud Run Invoker and creates the push subscription targeting `/api/internal/pubsub/workflows`.

The scripts do not create service-account keys. Supply `GEMINI_API_KEY` through approved secret management when the API service is deployed; never place it in `infrastructure/env.production.example` or a committed environment file. The worker remains private and accepts only authenticated Pub/Sub pushes.

### Current billing limitation

For the current project, `gcloud billing projects describe` reports `billingEnabled: false`. The required API activation command is blocked with `UREQ_PROJECT_BILLING_NOT_FOUND` for `run.googleapis.com`, `artifactregistry.googleapis.com`, and the transitive `containerregistry.googleapis.com`. Consequently, Firestore database creation, Pub/Sub topic/subscription creation, service accounts/IAM changes for this deployment, Cloud Build, and Cloud Run deployment remain pending. No deployment command has been run.

## Job provider architecture

JobPilot also uses a replaceable job discovery layer that separates provider selection from the rest of the application.

- `JobProvider` is the abstraction for source-agnostic job search.
- `MockJobProvider` gives deterministic sample jobs for offline tests and local development.
- `ExternalJobProvider` is prepared for an authorized public job API connection later.
- `JobDiscoveryService` normalizes the provider response into a safe internal `Job` model.

This keeps JobPilot free from scraping and avoids shipping API credentials in code or configuration files.

## Mock provider

The default backend configuration uses the mock provider so tests remain offline-safe and independent of network access.

```python
JobDiscoveryService().search_jobs("Python Backend Developer", "Bangalore", 5)
```

## Real authorized external provider (future configuration)

If an authorized public job API is later added, configure it through environment variables instead of hard-coding credentials.

```env
JOB_PROVIDER_MODE=external
JOB_PROVIDER_BASE_URL=https://api.example.com/jobs
JOB_PROVIDER_API_KEY=your_authorized_api_key_here
```

The provider must:
- respect rate limits and provider terms of service,
- use environment variables only,
- avoid scraping or bypassing authentication boundaries,
- handle malformed responses gracefully.

## Job discovery API

The job discovery endpoint is available at:

```http
POST /api/jobs/search
```

Example request:

```json
{
  "query": "Python Backend Developer",
  "location": "Bangalore",
  "limit": 10
}
```

Example response:

```json
{
  "jobs": [
    {
      "id": "mock-python-backend-bengaluru",
      "title": "Python Backend Developer",
      "company": "Acme Labs",
      "location": "Bangalore",
      "description": "Build and maintain Python services with FastAPI, PostgreSQL, and cloud deployment workflow.",
      "url": "https://example.com/jobs/mock-python-backend-bengaluru",
      "source": "mock"
    }
  ],
  "error": null
}
```

## Gemini + ADK setup

This step adds the Google Agent Development Kit (ADK) and the Gemini API integration layer.

1. Create a Gemini API key in Google AI Studio or a supported Google Cloud setup.
2. Copy the backend environment template:

```bash
cd backend
copy .env.example .env
```

3. Update the `.env` file with your own key:

```env
APP_NAME=jobpilot-api
ENVIRONMENT=development
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
```

## Install dependencies

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[dev]
pip install google-adk google-generativeai python-dotenv
```

### Frontend

```bash
cd frontend
npm install
```

## Run the backend

```bash
cd backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then test:

```bash
curl http://localhost:8000/health
```

## Agent endpoint

The agent endpoint is available at:

```http
POST /api/agent/analyze-job
```

Example request:

```json
{
  "job_title": "Python Backend Developer",
  "location": "Bangalore",
  "skills": ["Python", "FastAPI", "PostgreSQL"],
  "experience": "2 years",
  "job_description": "We are looking for a Python developer with FastAPI and PostgreSQL experience. Docker and cloud deployments are a plus."
}
```

Example response:

```json
{
  "match_score": 84,
  "matching_skills": ["Python", "FastAPI", "PostgreSQL"],
  "missing_skills": ["Docker", "Cloud deployment"],
  "recommendation": "Strong candidate; worth applying.",
  "explanation": "The user's background aligns strongly with the core role requirements and responsibilities."
}
```

## Run the frontend

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

## Test the backend

```bash
cd backend
.\.venv\Scripts\activate
pytest -q
```

## Notes

- No real job scraping is used in this step.
- No automatic application submission is implemented.
- If no `GEMINI_API_KEY` is set, the backend uses a safe mock assessment path so tests remain offline-safe and do not charge an API account.
- The agent is designed to analyze a supplied job description and provide a structured recommendation, not to submit applications.
#   J O B - P I L O T  
 