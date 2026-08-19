from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    job_title: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    skills: list[str] = Field(default_factory=list)
    experience: str = Field(..., min_length=1)
    resume_text: str | None = None


class JobOpportunity(BaseModel):
    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)


class JobAnalysisResult(BaseModel):
    id: str
    title: str
    company: str
    location: str
    match_score: int = Field(ge=0, le=100)
    matching_skills: list[str]
    missing_skills: list[str]
    recommendation: str
    explanation: str


class AnalyzeJobsRequest(BaseModel):
    candidate: CandidateProfile
    jobs: list[JobOpportunity]


class AnalyzeJobsResponse(BaseModel):
    jobs: list[JobAnalysisResult]
