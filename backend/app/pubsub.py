from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from typing import Any

from app.worker import WorkflowWorker


class PubSubPublisher(ABC):
    @abstractmethod
    def create_message(self, workflow_id: str) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def publish_workflow(self, workflow_id: str) -> dict[str, str]:
        raise NotImplementedError


class InMemoryPubSubPublisher(PubSubPublisher):
    _queue: list[dict[str, str]] = []

    def __init__(self):
        self._messages = self.__class__._queue
        self._worker = WorkflowWorker()

    def create_message(self, workflow_id: str) -> dict[str, str]:
        return {"workflow_id": workflow_id}

    def publish_workflow(self, workflow_id: str) -> dict[str, str]:
        message = self.create_message(workflow_id)
        self._messages.append(message)

        thread = threading.Thread(
            target=self._deliver_message,
            args=(message,),
            daemon=True,
        )
        thread.start()
        return message

    def _deliver_message(self, message: dict[str, str]) -> None:
        workflow_id = message.get("workflow_id")
        if workflow_id:
            self._worker.process_workflow(workflow_id)

    def peek(self) -> dict[str, str] | None:
        if not self._messages:
            return None
        return self._messages[-1]

    def drain(self) -> list[dict[str, str]]:
        result = list(self._messages)
        self._messages.clear()
        return result

    def reset(self) -> None:
        self._messages.clear()


class GooglePubSubPublisher(PubSubPublisher):
    def __init__(
        self,
        publisher_client: Any | None = None,
        project_id: str | None = None,
        topic_name: str | None = None,
    ):
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PUBSUB_PROJECT_ID") or "jobpilot-local"
        self.topic_name = topic_name or os.getenv("PUBSUB_TOPIC", "jobpilot-workflows")
        self._client = publisher_client

        if self._client is None:
            try:
                from google.cloud import pubsub_v1
            except ImportError as exc:  # pragma: no cover - dependency checks handled by factory.
                raise RuntimeError("google-cloud-pubsub is not installed.") from exc

            self._client = pubsub_v1.PublisherClient()

    def create_message(self, workflow_id: str) -> dict[str, str]:
        return {"workflow_id": workflow_id}

    def publish_workflow(self, workflow_id: str) -> dict[str, str]:
        message = self.create_message(workflow_id)
        topic_path = self._client.topic_path(self.project_id, self.topic_name)
        self._client.publish(topic_path, data=json.dumps(message).encode("utf-8"))
        return message


_DEFAULT_IN_MEMORY_PUBLISHER = InMemoryPubSubPublisher()


def get_publisher() -> PubSubPublisher:
    publisher_mode = (os.getenv("PUBSUB_MODE") or "memory").strip().lower()
    if publisher_mode == "google":
        try:
            return GooglePubSubPublisher()
        except Exception:
            return _DEFAULT_IN_MEMORY_PUBLISHER

    if os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PUBSUB_PROJECT_ID"):
        try:
            return GooglePubSubPublisher()
        except Exception:
            return _DEFAULT_IN_MEMORY_PUBLISHER

    return _DEFAULT_IN_MEMORY_PUBLISHER
