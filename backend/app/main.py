from dataclasses import asdict, is_dataclass
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent import JobPilotAgent, create_agent
from app.config import get_settings
from app.discovery import JobDiscoveryService
from app.models import AnalyzeJobsRequest, AnalyzeJobsResponse
from app.pubsub import get_publisher
from app.schemas import AnalyzeJobRequest, AnalyzeJobResponse
from app.taskmaster import WorkflowService
from app.workflow import JobPilotWorkflow


class JobSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=25)


class JobSearchResponse(BaseModel):
    jobs: list[dict[str, str]]
    error: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]

app = FastAPI(title="JobPilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _serialize_job_analysis(job: Any) -> dict[str, Any]:
    if isinstance(job, dict):
        return job
    if hasattr(job, "model_dump"):
        return job.model_dump()
    if is_dataclass(job):
        return asdict(job)
    return {
        "id": getattr(job, "id", ""),
        "title": getattr(job, "title", ""),
        "company": getattr(job, "company", ""),
        "location": getattr(job, "location", ""),
        "match_score": getattr(job, "match_score", 0),
        "matching_skills": getattr(job, "matching_skills", []),
        "missing_skills": getattr(job, "missing_skills", []),
        "recommendation": getattr(job, "recommendation", "low_match"),
        "explanation": getattr(job, "explanation", ""),
    }


@app.get("/health")
def health_check():
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name}


@app.post("/api/agent/analyze-job", response_model=AnalyzeJobResponse)
def analyze_job(payload: AnalyzeJobRequest):
    agent = create_agent()
    result = agent.analyze_job(
        job_title=payload.job_title,
        location=payload.location,
        skills=payload.skills,
        experience=payload.experience,
        job_description=payload.job_description,
        resume_text=payload.resume_text,
    )
    return AnalyzeJobResponse(
        match_score=result.match_score,
        matching_skills=result.matching_skills,
        missing_skills=result.missing_skills,
        recommendation=result.recommendation,
        explanation=result.explanation,
    )


@app.post("/api/agent/analyze-jobs", response_model=AnalyzeJobsResponse)
def analyze_jobs(payload: AnalyzeJobsRequest):
    workflow = JobPilotWorkflow(agent=JobPilotAgent())
    if not payload.jobs:
        return AnalyzeJobsResponse(jobs=[])

    jobs = workflow.analyze_jobs(payload.candidate.model_dump(), [job.model_dump() for job in payload.jobs])
    serialized_jobs = []

    for index, job in enumerate(jobs):
        raw = _serialize_job_analysis(job)
        source = payload.jobs[index].model_dump()

        raw.setdefault("id", source.get("id", ""))
        raw.setdefault("title", source.get("title", ""))
        raw.setdefault("company", source.get("company", ""))
        raw.setdefault("location", source.get("location", ""))
        raw.setdefault("match_score", 0)
        raw.setdefault("matching_skills", [])
        raw.setdefault("missing_skills", [])
        raw.setdefault("recommendation", "low_match")
        raw.setdefault("explanation", "")

        serialized_jobs.append(raw)

    if len(serialized_jobs) < len(payload.jobs):
        template = serialized_jobs[0] if serialized_jobs else {
            "match_score": 0,
            "matching_skills": [],
            "missing_skills": [],
            "recommendation": "low_match",
            "explanation": "",
        }

        for index in range(len(serialized_jobs), len(payload.jobs)):
            source = payload.jobs[index].model_dump()
            serialized_jobs.append({
                "id": source.get("id", ""),
                "title": source.get("title", ""),
                "company": source.get("company", ""),
                "location": source.get("location", ""),
                "match_score": template.get("match_score", 0),
                "matching_skills": template.get("matching_skills", []),
                "missing_skills": template.get("missing_skills", []),
                "recommendation": template.get("recommendation", "low_match"),
                "explanation": template.get("explanation", ""),
            })

    return AnalyzeJobsResponse(jobs=serialized_jobs)


@app.post("/api/jobs/search", response_model=JobSearchResponse)
def search_jobs(payload: JobSearchRequest):
    service = JobDiscoveryService()
    try:
        jobs = service.search_jobs(payload.query, payload.location, payload.limit)
    except (ValueError, RuntimeError) as exc:
        return JobSearchResponse(jobs=[], error=str(exc))

    serialized_jobs = [job.to_dict() for job in jobs]
    return JobSearchResponse(jobs=serialized_jobs, error=None)


@app.post("/api/workflows")
def create_workflow(payload: dict):
    workflow_service = WorkflowService()
    workflow = workflow_service.create_workflow(payload)
    publisher = get_publisher()
    publisher.publish_workflow(workflow["workflow_id"])
    return workflow


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    workflow_service = WorkflowService()
    workflow = workflow_service.get_workflow(workflow_id)
    if workflow is None:
        return {"detail": "Workflow not found"}
    return workflow


@app.post("/api/workflows/{workflow_id}/preparation-packages/{job_id}/review")
def review_preparation_package(workflow_id: str, job_id: str, payload: ReviewRequest):
    workflow_service = WorkflowService()
    try:
        package = workflow_service.review_preparation_package(workflow_id, job_id, payload.decision)
    except KeyError as exc:
        return {"detail": str(exc)}
    except ValueError as exc:
        return {"detail": str(exc)}

    return {
        "workflow_id": workflow_id,
        "job_id": job_id,
        "review_status": package["review_status"],
        "application_status": package["application_status"],
        "preparation_package": package,
    }

