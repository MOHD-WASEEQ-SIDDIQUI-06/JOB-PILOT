from __future__ import annotations

from typing import Any

from app.taskmaster import WorkflowService


class WorkflowWorker:
    def __init__(self, workflow_service: WorkflowService | None = None):
        self.workflow_service = workflow_service or WorkflowService()

    def extract_workflow_id(self, message: dict[str, Any]) -> str:
        return str(message.get("workflow_id") or "")

    def process_workflow(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.workflow_service.get_workflow(workflow_id)
        if workflow is None:
            return {"workflow_id": workflow_id, "status": "failed", "error": "Workflow not found"}

        try:
            record = self.workflow_service.execute_workflow(workflow_id)
            payload = record.to_dict() if hasattr(record, "to_dict") else workflow
            payload["workflow_id"] = workflow_id
            return payload
        except Exception as exc:  # pragma: no cover - defensive guard
            failed = self.workflow_service.get_workflow(workflow_id) or {"workflow_id": workflow_id, "status": "failed"}
            failed["status"] = "failed"
            failed["error"] = str(exc)
            return failed


class BackgroundWorkflowRunner:
    def __init__(self, publisher: Any | None = None, worker: WorkflowWorker | None = None):
        self.publisher = publisher
        self.worker = worker or WorkflowWorker()

    def receive_message(self, message: dict[str, Any]) -> dict[str, Any]:
        workflow_id = self.worker.extract_workflow_id(message)
        if not workflow_id:
            return {"status": "failed", "error": "Workflow ID missing"}
        return self.worker.process_workflow(workflow_id)
