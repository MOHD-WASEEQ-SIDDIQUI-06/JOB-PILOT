import base64
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.pubsub import GooglePubSubPublisher, InMemoryPubSubPublisher, PubSubPublisher, get_publisher
from app.worker import WorkflowWorker
import app.worker_api as worker_module
from app.worker_api import app as worker_app
from app.worker_api import extract_workflow_id

client = TestClient(app)
worker_client = TestClient(worker_app)


def test_pubsub_publisher_interface_contract():
    assert issubclass(PubSubPublisher, object)
    assert hasattr(PubSubPublisher, "publish_workflow")


def test_in_memory_publisher_queue_message():
    publisher = InMemoryPubSubPublisher()
    publisher.reset()

    message = publisher.publish_workflow("wf-queue")

    assert message == {"workflow_id": "wf-queue"}
    assert publisher.peek() == {"workflow_id": "wf-queue"}


def test_google_pubsub_publisher_uses_mocked_client():
    mock_client = MagicMock()
    mock_future = MagicMock()
    mock_client.publish.return_value = mock_future

    publisher = GooglePubSubPublisher(publisher_client=mock_client, project_id="test-project", topic_name="jobpilot-workflows")
    message = publisher.publish_workflow("wf-google")

    assert message == {"workflow_id": "wf-google"}
    mock_client.publish.assert_called_once()
    published_data = mock_client.publish.call_args.kwargs["data"]
    assert json.loads(published_data) == {"workflow_id": "wf-google"}


def test_pubsub_push_message_extracts_workflow_id():
    encoded = base64.b64encode(json.dumps({"workflow_id": "wf-push"}).encode()).decode()

    assert extract_workflow_id({"message": {"data": encoded}}) == "wf-push"


def test_pubsub_push_worker_endpoint_invokes_existing_worker(monkeypatch):
    recorded = {}

    def fake_process(workflow_id):
        recorded["workflow_id"] = workflow_id
        return {"workflow_id": workflow_id, "status": "completed"}

    monkeypatch.setattr(worker_module, "worker", MagicMock(process_workflow=fake_process))
    encoded = base64.b64encode(json.dumps({"workflow_id": "wf-endpoint"}).encode()).decode()

    response = worker_client.post("/api/internal/pubsub/workflows", json={"message": {"data": encoded}})

    assert response.status_code == 200
    assert recorded["workflow_id"] == "wf-endpoint"
    assert response.json()["workflow_id"] == "wf-endpoint"


def test_pubsub_push_worker_endpoint_rejects_malformed_messages():
    response = worker_client.post("/api/internal/pubsub/workflows", json={"message": {"data": "%%%"}})

    assert response.status_code == 400


def test_pubsub_push_worker_endpoint_rejects_missing_workflow_id():
    encoded = base64.b64encode(json.dumps({"other_id": "wf-missing"}).encode()).decode()

    response = worker_client.post("/api/internal/pubsub/workflows", json={"message": {"data": encoded}})

    assert response.status_code == 400


def test_workflow_message_creation():
    publisher = InMemoryPubSubPublisher()
    publisher.reset()

    payload = publisher.create_message("wf-message")

    assert payload == {"workflow_id": "wf-message"}


def test_worker_receives_workflow_id_from_message():
    worker = WorkflowWorker()
    message = {"workflow_id": "wf-worker-1"}

    assert worker.extract_workflow_id(message) == "wf-worker-1"


def test_worker_executes_workflow_and_updates_state():
    worker = WorkflowWorker()
    workflow_service = worker.workflow_service
    workflow_id = workflow_service.create_workflow({
        "job_title": "Python Backend Developer",
        "location": "Bangalore",
        "skills": ["Python", "FastAPI"],
        "experience": "2 years",
    })["workflow_id"]

    result = worker.process_workflow(workflow_id)

    assert result["workflow_id"] == workflow_id
    assert result["status"] in {"waiting_for_review", "completed", "failed"}


def test_worker_handles_workflow_failure():
    worker = WorkflowWorker()
    workflow_service = worker.workflow_service
    workflow_id = workflow_service.create_workflow({
        "job_title": "Broken",
        "location": "Remote",
        "skills": ["Python"],
        "experience": "1 year",
    })["workflow_id"]

    workflow_service.repository.save_workflow_results(workflow_id, {"status": "queued"})

    with MagicMock() as mock_execute:
        mock_execute.side_effect = RuntimeError("provider down")
        worker.workflow_service.execute_workflow = mock_execute

        result = worker.process_workflow(workflow_id)

    assert result["status"] == "failed"
    assert "provider down" in result["error"]


def test_api_publishes_queued_workflow():
    publisher = get_publisher()
    if hasattr(publisher, "reset"):
        publisher.reset()

    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI"],
            "experience": "2 years",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert publisher.peek() == {"workflow_id": payload["workflow_id"]}


def test_get_workflow_retrieves_updated_state():
    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI"],
            "experience": "2 years",
        },
    )
    workflow_id = response.json()["workflow_id"]

    state = client.get(f"/api/workflows/{workflow_id}")

    assert state.status_code == 200
    assert state.json()["workflow_id"] == workflow_id
    assert state.json()["status"] in {"queued", "discovering", "analyzing", "ranking", "preparing", "waiting_for_review", "completed", "failed"}


def test_no_google_credentials_required_for_tests():
    publisher = InMemoryPubSubPublisher()
    publisher.reset()

    assert publisher.publish_workflow("wf-local") == {"workflow_id": "wf-local"}
    assert publisher.peek() == {"workflow_id": "wf-local"}
