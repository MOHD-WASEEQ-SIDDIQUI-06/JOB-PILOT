from __future__ import annotations

from app.agent import JobPilotAgent
from app.models import AnalyzeJobsRequest, AnalyzeJobsResponse, JobAnalysisResult, JobOpportunity


class JobPilotWorkflow:
    def __init__(self, agent: JobPilotAgent | None = None):
        self.agent = agent or JobPilotAgent()

    def analyze_jobs(self, candidate: dict, jobs: list[dict]) -> list[JobAnalysisResult]:
        results: list[JobAnalysisResult] = []

        for job in jobs:
            job_data = JobOpportunity(**job)
            analysis = self.agent.analyze_job(
                job_title=candidate.get("job_title", ""),
                location=candidate.get("location", ""),
                skills=candidate.get("skills", []),
                experience=candidate.get("experience", ""),
                job_description=job_data.description,
                resume_text=candidate.get("resume_text"),
            )

            recommendation = analysis.recommendation.lower()
            if recommendation.startswith("strong"):
                rec = "strong_match"
            elif recommendation.startswith("reasonable") or recommendation.startswith("possible"):
                rec = "possible_match"
            else:
                rec = "low_match"

            results.append(
                JobAnalysisResult(
                    id=job_data.id,
                    title=job_data.title,
                    company=job_data.company,
                    location=job_data.location,
                    match_score=analysis.match_score,
                    matching_skills=analysis.matching_skills,
                    missing_skills=analysis.missing_skills,
                    recommendation=rec,
                    explanation=analysis.explanation,
                )
            )

        return results


def analyze_jobs_payload(payload: AnalyzeJobsRequest) -> AnalyzeJobsResponse:
    workflow = JobPilotWorkflow()
    analyzed_jobs = workflow.analyze_jobs(payload.candidate.model_dump(), [job.model_dump() for job in payload.jobs])
    return AnalyzeJobsResponse(jobs=analyzed_jobs)
