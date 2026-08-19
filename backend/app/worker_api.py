from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from fastapi import FastAPI, HTTPException

from app.worker import WorkflowWorker

app = FastAPI(title="JobPilot Workflow Worker", version="0.1.0")
worker = WorkflowWorker()


def extract_workflow_id(envelope: dict[str, Any]) -> str:
    message = envelope.get("message")
    if not isinstance(message, dict):
        raise ValueError("Pub/Sub message is missing")

    encoded_data = message.get("data")
    if not isinstance(encoded_data, str) or not encoded_data:
        raise ValueError("Pub/Sub message data is missing")

    try:
        decoded_data = base64.b64decode(encoded_data, validate=True).decode("utf-8")
        payload = json.loads(decoded_data)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Pub/Sub message data is not valid base64 JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_id"), str):
        raise ValueError("workflow_id is missing from Pub/Sub message data")

    workflow_id = payload["workflow_id"].strip()
    if not workflow_id:
        raise ValueError("workflow_id is empty")
    return workflow_id


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "jobpilot-worker"}


@app.post("/api/internal/pubsub/workflows")
def receive_pubsub_push(envelope: dict[str, Any]) -> dict[str, Any]:
    try:
        workflow_id = extract_workflow_id(envelope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = worker.process_workflow(workflow_id)
    return {"status": "processed", "workflow_id": workflow_id, "workflow": result}