from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agent import JobPilotAgent
from app.discovery import Job, JobDiscoveryService

WORKFLOW_STATES = {
    "queued",
    "discovering",
    "analyzing",
    "ranking",
    "preparing",
    "waiting_for_review",
    "completed",
    "failed",
}

WORKFLOW_STAGES = [
    "DISCOVER",
    "ANALYZE",
    "RANK",
    "PREPARE",
    "HUMAN_REVIEW",
]


@dataclass
class WorkflowRecord:
    workflow_id: str
    status: str = "queued"
    current_stage: str = "DISCOVER"
    job_title: str = ""
    location: str = ""
    skills: list[str] = field(default_factory=list)
    experience: str = ""
    resume_text: str | None = None
    discovered_jobs: list[dict[str, Any]] = field(default_factory=list)
    analyzed_jobs: list[dict[str, Any]] = field(default_factory=list)
    ranked_jobs: list[dict[str, Any]] = field(default_factory=list)
    strong_matches: list[dict[str, Any]] = field(default_factory=list)
    preparation_packages: list[dict[str, Any]] = field(default_factory=list)
    requires_human_review: bool = False
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkflowRecord":
        return cls(
            workflow_id=str(payload.get("workflow_id", "")),
            status=str(payload.get("status", "queued")),
            current_stage=str(payload.get("current_stage", "DISCOVER")),
            job_title=str(payload.get("job_title", "")),
            location=str(payload.get("location", "")),
            skills=[str(skill) for skill in payload.get("skills", [])],
            experience=str(payload.get("experience", "")),
            resume_text=payload.get("resume_text"),
            discovered_jobs=list(payload.get("discovered_jobs") or []),
            analyzed_jobs=list(payload.get("analyzed_jobs") or []),
            ranked_jobs=list(payload.get("ranked_jobs") or []),
            strong_matches=list(payload.get("strong_matches") or []),
            preparation_packages=list(payload.get("preparation_packages") or []),
            requires_human_review=bool(payload.get("requires_human_review", False)),
            error=payload.get("error"),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "job_title": self.job_title,
            "location": self.location,
            "skills": self.skills,
            "experience": self.experience,
            "resume_text": self.resume_text,
            "jobs_discovered": len(self.discovered_jobs),
            "jobs_analyzed": len(self.analyzed_jobs),
            "strong_matches": len(self.strong_matches),
            "application_preparation_count": len(self.preparation_packages),
            "requires_human_review": self.requires_human_review,
            "discovered_jobs": self.discovered_jobs,
            "analyzed_jobs": self.analyzed_jobs,
            "ranked_jobs": self.ranked_jobs,
            "strong_matches": self.strong_matches,
            "preparation_packages": self.preparation_packages,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class WorkflowRepository(ABC):
    @abstractmethod
    def create_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        raise NotImplementedError

    @abstractmethod
    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        raise NotImplementedError

    @abstractmethod
    def update_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        raise NotImplementedError

    @abstractmethod
    def save_workflow_results(self, workflow_id: str, workflow_data: dict[str, Any]) -> WorkflowRecord:
        raise NotImplementedError


class InMemoryWorkflowRepository(WorkflowRepository):
    _shared_store: dict[str, WorkflowRecord] = {}

    def __init__(self):
        self._store = self.__class__._shared_store

    def create_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        self._store[workflow.workflow_id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        return self._store.get(workflow_id)

    def update_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        self._store[workflow.workflow_id] = workflow
        return workflow

    def save_workflow_results(self, workflow_id: str, workflow_data: dict[str, Any]) -> WorkflowRecord:
        workflow = self._store.get(workflow_id)
        if workflow is None:
            raise KeyError(f"Workflow {workflow_id} not found")

        for key, value in workflow_data.items():
            if hasattr(workflow, key):
                setattr(workflow, key, value)
        self._store[workflow_id] = workflow
        return workflow


class FirestoreWorkflowRepository(WorkflowRepository):
    def __init__(self, client: Any | None = None, collection_name: str | None = None):
        if client is None:
            try:
                from google.cloud import firestore
            except ImportError as exc:  # pragma: no cover - dependency checks handled by factory.
                raise RuntimeError("google-cloud-firestore is not installed.") from exc
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("FIRESTORE_PROJECT_ID") or "jobpilot-local"
            client = firestore.Client(project=project_id)

        self._client = client
        self._collection_name = collection_name or os.getenv("WORKFLOW_COLLECTION", "jobpilot-workflows")
        self._collection = self._client.collection(self._collection_name)

    def create_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        self._collection.document(workflow.workflow_id).set(workflow.to_dict())
        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        document = self._collection.document(workflow_id).get()
        if document is None or not document.exists:
            return None
        return WorkflowRecord.from_dict(document.to_dict())

    def update_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        self._collection.document(workflow.workflow_id).set(workflow.to_dict())
        return workflow

    def save_workflow_results(self, workflow_id: str, workflow_data: dict[str, Any]) -> WorkflowRecord:
        document = self._collection.document(workflow_id)
        current = document.get()
        if current is None or not current.exists:
            raise KeyError(f"Workflow {workflow_id} not found")

        merged = current.to_dict() | workflow_data
        document.set(merged)
        return WorkflowRecord.from_dict(merged)


class ApplicationPreparationService:
    def generate_preparation(self, *, candidate: dict[str, Any], job: Job, analysis: Any) -> dict[str, Any]:
        why_match = []
        if analysis.matching_skills:
            why_match.append(f"Strong overlap with core skills: {', '.join(analysis.matching_skills[:3])}.")
        if candidate.get("experience"):
            why_match.append(f"Experience level aligns with the role requirements: {candidate['experience']}.")
        if not why_match:
            why_match.append("The candidate profile is relevant enough to review with a human before applying.")

        missing = list(analysis.missing_skills or [])
        resume_bullets = []
        if analysis.matching_skills:
            resume_bullets.append(
                f"Built and maintained solutions involving {', '.join(analysis.matching_skills[:3])} in production-facing work."
            )
        if missing:
            resume_bullets.append(
                f"Prepared to close skill gaps by deepening experience in {', '.join(missing[:2])} and related tooling."
            )
        if not resume_bullets:
            resume_bullets.append("Focused on shipping high-quality, user-centered software improvements and collaboration across teams.")

        cover_letter_draft = (
            f"Dear Hiring Team,\n\n"
            f"I am excited to apply for the {job.title} role at {job.company}. "
            f"My background in {candidate.get('job_title', 'software engineering')} and my experience in "
            f"{candidate.get('experience', 'relevant engineering work')} align well with this opportunity. "
            f"I bring experience with {', '.join(analysis.matching_skills[:3]) if analysis.matching_skills else 'relevant technologies'}, "
            f"and I am prepared to continue improving in {', '.join(missing[:2]) if missing else 'key role requirements'}. "
            f"This draft is AI-generated and requires human review before submission.\n\n"
            f"Sincerely,\n{candidate.get('job_title', 'Candidate')}"
        )

        return {
            "job_id": job.id,
            "match_score": int(analysis.match_score),
            "why_match": why_match,
            "missing_skills": missing,
            "resume_bullet_suggestions": resume_bullets,
            "cover_letter_draft": cover_letter_draft,
            "requires_human_review": True,
            "review_status": "pending",
            "reviewed_at": None,
            "application_status": "not_submitted",
        }


_DEFAULT_IN_MEMORY_REPOSITORY = InMemoryWorkflowRepository()


def get_workflow_repository() -> WorkflowRepository:
    repository_mode = (os.getenv("WORKFLOW_REPOSITORY_MODE") or "memory").strip().lower()
    if repository_mode == "firestore":
        try:
            return FirestoreWorkflowRepository()
        except Exception:
            return _DEFAULT_IN_MEMORY_REPOSITORY

    if os.getenv("FIRESTORE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT"):
        try:
            return FirestoreWorkflowRepository()
        except Exception:
            return _DEFAULT_IN_MEMORY_REPOSITORY

    return _DEFAULT_IN_MEMORY_REPOSITORY


class WorkflowService:
    def __init__(
        self,
        repository: WorkflowRepository | None = None,
        discovery_service: JobDiscoveryService | None = None,
        agent: JobPilotAgent | None = None,
    ):
        self.repository = repository or get_workflow_repository()
        self.discovery_service = discovery_service or JobDiscoveryService()
        self.agent = agent or JobPilotAgent()
        self.preparation_service = ApplicationPreparationService()

    def create_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_id = uuid4().hex
        record = WorkflowRecord(
            workflow_id=workflow_id,
            status="queued",
            current_stage="DISCOVER",
            job_title=str(payload.get("job_title") or payload.get("preferred_job_title") or "").strip(),
            location=str(payload.get("location") or payload.get("preferred_location") or "").strip(),
            skills=[str(skill).strip() for skill in payload.get("skills", []) if str(skill).strip()],
            experience=str(payload.get("experience") or payload.get("experience_level") or "").strip(),
            resume_text=(payload.get("resume_text") or payload.get("resume") or None),
            created_at=self._timestamp(),
            updated_at=self._timestamp(),
        )
        self.repository.create_workflow(record)
        return {"workflow_id": workflow_id, "status": "queued"}

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        record = self.repository.get_workflow(workflow_id)
        if record is None:
            return None
        return record.to_dict()

    def execute_workflow(self, workflow_id: str) -> WorkflowRecord:
        record = self.repository.get_workflow(workflow_id)
        if record is None:
            raise KeyError(f"Workflow {workflow_id} not found")

        try:
            record.status = "discovering"
            record.current_stage = "DISCOVER"
            record.updated_at = self._timestamp()
            self.repository.update_workflow(record)

            discovered_jobs = self.discovery_service.search_jobs(
                query=record.job_title,
                location=record.location,
                limit=10,
            )
            record.discovered_jobs = [job.to_dict() for job in discovered_jobs]
            record.updated_at = self._timestamp()
            self.repository.save_workflow_results(workflow_id, {"discovered_jobs": record.discovered_jobs, "updated_at": record.updated_at})

            record.status = "analyzing"
            record.current_stage = "ANALYZE"
            record.updated_at = self._timestamp()
            analyzed_jobs = []
            for job in discovered_jobs:
                analysis = self.agent.analyze_job(
                    job_title=record.job_title,
                    location=record.location,
                    skills=record.skills,
                    experience=record.experience,
                    job_description=job.description,
                    resume_text=record.resume_text,
                )
                analyzed_jobs.append(
                    {
                        "job_id": job.id,
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "match_score": analysis.match_score,
                        "matching_skills": analysis.matching_skills,
                        "missing_skills": analysis.missing_skills,
                        "recommendation": analysis.recommendation,
                        "explanation": analysis.explanation,
                    }
                )
            record.analyzed_jobs = analyzed_jobs
            self.repository.save_workflow_results(workflow_id, {"analyzed_jobs": analyzed_jobs, "updated_at": record.updated_at})

            record.status = "ranking"
            record.current_stage = "RANK"
            record.updated_at = self._timestamp()
            ranked_jobs = sorted(analyzed_jobs, key=lambda item: item.get("match_score", 0), reverse=True)
            record.ranked_jobs = ranked_jobs
            record.strong_matches = [job for job in ranked_jobs if job.get("match_score", 0) >= 75]
            self.repository.save_workflow_results(workflow_id, {
                "status": record.status,
                "current_stage": record.current_stage,
                "ranked_jobs": ranked_jobs,
                "strong_matches": record.strong_matches,
                "updated_at": record.updated_at,
            })

            record.status = "preparing"
            record.current_stage = "PREPARE"
            record.updated_at = self._timestamp()
            self.repository.save_workflow_results(workflow_id, {
                "status": record.status,
                "current_stage": record.current_stage,
                "updated_at": record.updated_at,
            })

            preparation_packages = []
            for job in discovered_jobs:
                job_analysis = next((item for item in ranked_jobs if item.get("job_id") == job.id), None)
                if job_analysis is None or job_analysis.get("match_score", 0) < 75:
                    continue

                analysis = self.agent.analyze_job(
                    job_title=record.job_title,
                    location=record.location,
                    skills=record.skills,
                    experience=record.experience,
                    job_description=job.description,
                    resume_text=record.resume_text,
                )
                preparation = self.preparation_service.generate_preparation(
                    candidate={
                        "job_title": record.job_title,
                        "location": record.location,
                        "skills": record.skills,
                        "experience": record.experience,
                        "resume_text": record.resume_text,
                    },
                    job=job,
                    analysis=analysis,
                )
                preparation_packages.append(preparation)

            record.preparation_packages = preparation_packages
            record.requires_human_review = bool(preparation_packages)
            record.status = "waiting_for_review"
            record.current_stage = "HUMAN_REVIEW"
            record.updated_at = self._timestamp()
            self.repository.save_workflow_results(workflow_id, {
                "preparation_packages": preparation_packages,
                "requires_human_review": True,
                "status": record.status,
                "current_stage": record.current_stage,
                "updated_at": record.updated_at,
            })

            record.status = "completed"
            record.updated_at = self._timestamp()
            self.repository.save_workflow_results(workflow_id, {
                "status": record.status,
                "updated_at": record.updated_at,
            })
            return self.repository.get_workflow(workflow_id) or record
        except Exception as exc:
            record.status = "failed"
            record.current_stage = "HUMAN_REVIEW"
            record.error = str(exc)
            record.updated_at = self._timestamp()
            self.repository.update_workflow(record)
            return record

    def review_preparation_package(self, workflow_id: str, job_id: str, decision: str) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ValueError("Review decision must be approve or reject.")

        record = self.repository.get_workflow(workflow_id)
        if record is None:
            raise KeyError(f"Workflow {workflow_id} not found")

        package = next((item for item in record.preparation_packages if item.get("job_id") == job_id), None)
        if package is None:
            raise KeyError(f"Preparation package {job_id} not found")

        package["review_status"] = "approved" if decision == "approve" else "rejected"
        package["reviewed_at"] = self._timestamp()
        package["application_status"] = "not_submitted"
        self.repository.save_workflow_results(
            workflow_id,
            {
                "preparation_packages": record.preparation_packages,
                "updated_at": package["reviewed_at"],
            },
        )
        return package

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
