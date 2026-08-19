[CmdletBinding()]
param(
    [ValidateSet('Provision', 'Api', 'Worker', 'Subscription')]
    [string]$Target = 'Provision',
    [string]$ProjectId = $(if ($env:GOOGLE_CLOUD_PROJECT) { $env:GOOGLE_CLOUD_PROJECT } else { 'REPLACE_WITH_PROJECT_ID' }),
    [string]$Region = 'us-central1',
    [string]$FirestoreLocation = 'nam5',
    [string]$ImageTag = 'step10',
    [switch]$Deploy
)

$ErrorActionPreference = 'Stop'
if ($ProjectId -eq 'REPLACE_WITH_PROJECT_ID') { throw 'Set -ProjectId or GOOGLE_CLOUD_PROJECT before using deployment scripts.' }

function Invoke-Gcloud { param([string[]]$Arguments) & gcloud @Arguments; if ($LASTEXITCODE -ne 0) { throw "gcloud failed: $($Arguments -join ' ')" } }
function Assert-Ready {
    Invoke-Gcloud @('auth', 'list', '--filter=status:ACTIVE', '--format=value(account)')
    $adc = gcloud auth application-default print-access-token --quiet 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adc)) { throw 'Application Default Credentials are unavailable.' }
    $billing = gcloud billing projects describe $ProjectId --format='value(billingEnabled)' 2>$null
    if ($billing -ne 'True') { throw "Billing is disabled for $ProjectId. No resources or deployments will be attempted." }
}

Assert-Ready
if (-not $Deploy) { Write-Output "Checks passed. Add -Deploy to execute target '$Target'. No deployment was performed."; exit 0 }

$apiAccount = "jobpilot-api-runtime@$ProjectId.iam.gserviceaccount.com"
$workerAccount = "jobpilot-worker-runtime@$ProjectId.iam.gserviceaccount.com"
$pushAccount = "jobpilot-pubsub-push@$ProjectId.iam.gserviceaccount.com"
$repo = 'jobpilot'
$topic = 'jobpilot-workflows'
$subscription = 'jobpilot-workflows-push'

if ($Target -eq 'Provision') {
    Invoke-Gcloud @('services', 'enable', 'run.googleapis.com', 'firestore.googleapis.com', 'pubsub.googleapis.com', 'artifactregistry.googleapis.com', '--project', $ProjectId)
    Invoke-Gcloud @('artifacts', 'repositories', 'create', $repo, '--repository-format=docker', "--location=$Region", '--description=JobPilot container images', '--project', $ProjectId)
    Invoke-Gcloud @('firestore', 'databases', 'create', '--location', $FirestoreLocation, '--type=firestore-native', '--project', $ProjectId)
    foreach ($account in @($apiAccount, $workerAccount, $pushAccount)) { Invoke-Gcloud @('iam', 'service-accounts', 'create', ($account.Split('@')[0]), '--display-name', "JobPilot $($account.Split('@')[0])", '--project', $ProjectId) }
    Invoke-Gcloud @('projects', 'add-iam-policy-binding', $ProjectId, '--member', "serviceAccount:$apiAccount", '--role', 'roles/datastore.user')
    Invoke-Gcloud @('projects', 'add-iam-policy-binding', $ProjectId, '--member', "serviceAccount:$apiAccount", '--role', 'roles/pubsub.publisher')
    Invoke-Gcloud @('projects', 'add-iam-policy-binding', $ProjectId, '--member', "serviceAccount:$workerAccount", '--role', 'roles/datastore.user')
    Invoke-Gcloud @('pubsub', 'topics', 'create', $topic, '--project', $ProjectId)
}

if ($Target -eq 'Api' -or $Target -eq 'Worker') {
    $name = if ($Target -eq 'Api') { 'jobpilot-api' } else { 'jobpilot-worker' }
    $account = if ($Target -eq 'Api') { $apiAccount } else { $workerAccount }
    $image = "$Region-docker.pkg.dev/$ProjectId/$repo/${name}:$ImageTag"
    $buildConfig = if ($Target -eq 'Api') { 'infrastructure/cloudbuild-api.yaml' } else { 'infrastructure/cloudbuild-worker.yaml' }
    Invoke-Gcloud @('builds', 'submit', 'backend', "--config=$buildConfig", "--substitutions=_IMAGE=$image", '--project', $ProjectId)
    Invoke-Gcloud @('run', 'deploy', $name, "--image=$image", "--region=$Region", "--service-account=$account", '--no-allow-unauthenticated', '--project', $ProjectId, '--set-env-vars', "GOOGLE_CLOUD_PROJECT=$ProjectId,FIRESTORE_PROJECT_ID=$ProjectId,PUBSUB_PROJECT_ID=$ProjectId")
}

if ($Target -eq 'Subscription') {
    $workerUrl = gcloud run services describe jobpilot-worker --region=$Region --project=$ProjectId --format='value(status.url)'
    Invoke-Gcloud @('run', 'services', 'add-iam-policy-binding', 'jobpilot-worker', '--region', $Region, '--member', "serviceAccount:$pushAccount", '--role', 'roles/run.invoker', '--project', $ProjectId)
    Invoke-Gcloud @('pubsub', 'subscriptions', 'create', $subscription, "--topic=$topic", "--push-endpoint=$workerUrl/api/internal/pubsub/workflows", "--push-auth-service-account=$pushAccount", '--project', $ProjectId)
}