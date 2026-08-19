from unittest.mock import MagicMock

from app.taskmaster import FirestoreWorkflowRepository, InMemoryWorkflowRepository, WorkflowRecord


class DummyDocument:
    def __init__(self, data):
        self._data = data
        self.exists = True

    def to_dict(self):
        return self._data


class DummyCollection:
    def __init__(self):
        self.documents = {}

    def document(self, workflow_id):
        return DummyDocumentReference(self.documents, workflow_id)


class DummyDocumentReference:
    def __init__(self, documents, workflow_id):
        self.documents = documents
        self.workflow_id = workflow_id

    def get(self):
        data = self.documents.get(self.workflow_id)
        if data is None:
            return DummyDocument(None)
        return DummyDocument(data)

    def set(self, data):
        self.documents[self.workflow_id] = data


def test_in_memory_repository_create_and_get_workflow():
    repo = InMemoryWorkflowRepository()
    workflow = WorkflowRecord(workflow_id="wf-1", job_title="Python Developer", location="Bangalore")

    repo.create_workflow(workflow)
    stored = repo.get_workflow("wf-1")

    assert stored is not None
    assert stored.workflow_id == "wf-1"
    assert stored.job_title == "Python Developer"


def test_in_memory_repository_update_workflow():
    repo = InMemoryWorkflowRepository()
    workflow = WorkflowRecord(workflow_id="wf-2", status="queued")
    repo.create_workflow(workflow)

    workflow.status = "completed"
    repo.update_workflow(workflow)

    assert repo.get_workflow("wf-2").status == "completed"


def test_in_memory_repository_save_workflow_results():
    repo = InMemoryWorkflowRepository()
    workflow = WorkflowRecord(workflow_id="wf-3", status="discovering")
    repo.create_workflow(workflow)

    repo.save_workflow_results("wf-3", {"status": "completed", "requires_human_review": True})

    assert repo.get_workflow("wf-3").status == "completed"
    assert repo.get_workflow("wf-3").requires_human_review is True


def test_firestore_repository_uses_mocked_client():
    collection = DummyCollection()
    client = MagicMock()
    client.collection.return_value = collection

    repo = FirestoreWorkflowRepository(client=client, collection_name="test-workflows")
    workflow = WorkflowRecord(workflow_id="wf-firestore", job_title="Data Engineer", location="Remote")

    repo.create_workflow(workflow)
    fetched = repo.get_workflow("wf-firestore")

    assert fetched is not None
    assert fetched.job_title == "Data Engineer"
    assert fetched.location == "Remote"


def test_firestore_repository_handles_failure_persistence():
    collection = DummyCollection()
    client = MagicMock()
    client.collection.return_value = collection

    repo = FirestoreWorkflowRepository(client=client, collection_name="test-workflows")
    workflow = WorkflowRecord(workflow_id="wf-fail", status="failed", error="provider down")
    repo.create_workflow(workflow)

    assert repo.get_workflow("wf-fail").error == "provider down"


def test_repository_interface_behavior():
    repo = InMemoryWorkflowRepository()
    workflow = WorkflowRecord(workflow_id="wf-interface", status="queued")
    repo.create_workflow(workflow)

    assert repo.get_workflow("wf-interface")
    repo.save_workflow_results("wf-interface", {"status": "waiting_for_review", "requires_human_review": True})
    assert repo.get_workflow("wf-interface").status == "waiting_for_review"
