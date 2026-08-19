from pydantic import BaseModel, Field


class AnalyzeJobRequest(BaseModel):
    job_title: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    skills: list[str] = Field(default_factory=list)
    experience: str = Field(..., min_length=1)
    job_description: str = Field(..., min_length=1)
    resume_text: str | None = None


class AnalyzeJobResponse(BaseModel):
    match_score: int
    matching_skills: list[str]
    missing_skills: list[str]
    recommendation: str
    explanation: str
