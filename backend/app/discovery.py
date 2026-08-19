from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(slots=True)
class Job:
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "Job":
        if not isinstance(payload, dict):
            raise ValueError("Job payload must be a dictionary.")

        required_keys = ["id", "title", "company", "location", "description", "url", "source"]
        missing = [key for key in required_keys if key not in payload]
        if missing:
            raise ValueError(f"Missing required job fields: {', '.join(missing)}")

        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            company=str(payload["company"]),
            location=str(payload["location"]),
            description=str(payload["description"]),
            url=str(payload["url"]),
            source=str(payload["source"]),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class JobProvider(ABC):
    @abstractmethod
    def search_jobs(self, query: str, location: str, limit: int) -> list[Job]:
        raise NotImplementedError


class MockJobProvider(JobProvider):
    def __init__(self):
        self._jobs = [
            Job(
                id="mock-python-backend-bengaluru",
                title="Python Backend Developer",
                company="Acme Labs",
                location="Bangalore",
                description="Build and maintain Python services with FastAPI, PostgreSQL, and cloud deployment workflow.",
                url="https://example.com/jobs/mock-python-backend-bengaluru",
                source="mock",
            ),
            Job(
                id="mock-senior-python-engineer",
                title="Senior Python Engineer",
                company="Orbit Systems",
                location="Bangalore",
                description="Lead backend architecture for APIs, data pipelines, and observability for enterprise products.",
                url="https://example.com/jobs/mock-senior-python-engineer",
                source="mock",
            ),
            Job(
                id="mock-data-engineer",
                title="Data Engineer",
                company="QuantFlow",
                location="Hyderabad",
                description="Work with Python, ETL pipelines, and production data orchestration in a distributed environment.",
                url="https://example.com/jobs/mock-data-engineer",
                source="mock",
            ),
            Job(
                id="mock-fullstack-platform",
                title="Full Stack Platform Engineer",
                company="SignalIQ",
                location="Remote",
                description="Develop platform tooling and application services with Python, TypeScript, and infrastructure automation.",
                url="https://example.com/jobs/mock-fullstack-platform",
                source="mock",
            ),
        ]

    def search_jobs(self, query: str, location: str, limit: int) -> list[Job]:
        query_term = (query or "").strip().lower()
        location_term = (location or "").strip().lower()

        matches: list[Job] = []
        for job in self._jobs:
            haystack = f"{job.title} {job.company} {job.description} {job.location}".lower()
            if query_term and query_term not in haystack:
                continue
            if location_term and location_term not in job.location.lower():
                continue
            matches.append(job)

        return matches[: max(1, min(limit, 25))]


class ExternalJobProvider(JobProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or os.getenv("JOB_PROVIDER_BASE_URL") or "").strip()
        self.api_key = (api_key or os.getenv("JOB_PROVIDER_API_KEY") or "").strip()
        self.timeout = timeout

    def _request_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def search_jobs(self, query: str, location: str, limit: int) -> list[Job]:
        if not self.base_url:
            raise RuntimeError("JOB_PROVIDER_BASE_URL is not configured.")
        if not self.api_key:
            raise RuntimeError("JOB_PROVIDER_API_KEY is not configured.")

        params = {"q": query, "location": location, "limit": max(1, min(limit, 25))}
        request_url = f"{self.base_url}?{urlencode(params)}"
        request = Request(request_url, headers=self._request_headers(), method="GET")

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, ValueError, TimeoutError) as exc:
            raise RuntimeError(f"External job provider request failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("External provider returned a malformed response payload.")

        raw_jobs = payload.get("jobs") or payload.get("results") or payload.get("data") or []
        if not isinstance(raw_jobs, list):
            raise ValueError("External provider response did not include a valid jobs list.")

        jobs: list[Job] = []
        for item in raw_jobs:
            try:
                jobs.append(Job.from_mapping(item))
            except ValueError:
                continue
        return jobs[: max(1, min(limit, 25))]


class JobDiscoveryService:
    def __init__(self, provider: JobProvider | None = None):
        self.provider = provider or self._default_provider()

    @staticmethod
    def _default_provider() -> JobProvider:
        mode = (os.getenv("JOB_PROVIDER_MODE") or "mock").strip().lower()
        if mode == "external":
            return ExternalJobProvider()
        return MockJobProvider()

    def search_jobs(self, query: str, location: str, limit: int = 10) -> list[Job]:
        normalized_query = (query or "").strip()
        normalized_location = (location or "").strip()

        if not normalized_query:
            raise ValueError("Query cannot be empty.")
        if not normalized_location:
            raise ValueError("Location cannot be empty.")

        safe_limit = max(1, min(int(limit), 25))
        try:
            jobs = self.provider.search_jobs(normalized_query, normalized_location, safe_limit)
        except Exception as exc:  # pragma: no cover - provider-specific errors surfaced to the API layer
            raise RuntimeError(str(exc)) from exc

        valid_jobs: list[Job] = []
        for item in jobs:
            if isinstance(item, Job):
                valid_jobs.append(item)
                continue
            try:
                valid_jobs.append(Job.from_mapping(item))
            except (TypeError, ValueError):
                continue

        return valid_jobs[:safe_limit]
