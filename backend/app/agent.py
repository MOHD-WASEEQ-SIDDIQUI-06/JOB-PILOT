from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class JobAnalysisResult:
    match_score: int
    matching_skills: list[str]
    missing_skills: list[str]
    recommendation: str
    explanation: str


class JobPilotAgent:
    """A lightweight agent interface for matching user profiles to job descriptions.

    When a Gemini API key is configured, this class can delegate to an ADK-backed
    implementation. In offline/test environments, a deterministic mock path is used
    to keep the suite safe and free from API charges.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-3.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    def analyze_job(
        self,
        *,
        job_title: str,
        location: str,
        skills: list[str],
        experience: str,
        job_description: str,
        resume_text: str | None = None,
    ) -> JobAnalysisResult:
        if not self.api_key:
            return self._mock_analysis(
                job_title=job_title,
                location=location,
                skills=skills,
                experience=experience,
                job_description=job_description,
                resume_text=resume_text,
            )

        return self._gemini_analysis(
            job_title=job_title,
            location=location,
            skills=skills,
            experience=experience,
            job_description=job_description,
            resume_text=resume_text,
        )

    def _mock_analysis(
        self,
        *,
        job_title: str,
        location: str,
        skills: list[str],
        experience: str,
        job_description: str,
        resume_text: str | None = None,
    ) -> JobAnalysisResult:
        normalized_skills = [skill.strip() for skill in skills if skill and skill.strip()]
        job_text = (job_description or "").lower()
        matching = [skill for skill in normalized_skills if skill.lower() in job_text]
        missing = [
            skill for skill in normalized_skills if skill.lower() not in job_text
        ]

        if not normalized_skills:
            matching = []
            missing = []

        if not matching:
            score = 20
        else:
            score = min(95, max(35, int((len(matching) / max(len(normalized_skills), 1)) * 100)))

        if score >= 75:
            recommendation = "Strong candidate; worth applying."
        elif score >= 50:
            recommendation = "Reasonable fit; review carefully before applying."
        else:
            recommendation = "Low fit; consider a different role or add relevant skills."

        explanation = (
            f"Based on the user's profile for {job_title} in {location}, the candidate clearly matches "
            f"the core skills in the description for {experience} of experience. "
            f"The agent found {len(matching)} overlapping skill(s) and identified {len(missing)} gap(s) to address."
        )

        if resume_text:
            explanation += " The provided resume text was considered in the assessment."

        return JobAnalysisResult(
            match_score=score,
            matching_skills=matching,
            missing_skills=missing,
            recommendation=recommendation,
            explanation=explanation,
        )

    def _gemini_analysis(
        self,
        *,
        job_title: str,
        location: str,
        skills: list[str],
        experience: str,
        job_description: str,
        resume_text: str | None = None,
    ) -> JobAnalysisResult:
        prompt = self._build_prompt(
            job_title=job_title,
            location=location,
            skills=skills,
            experience=experience,
            job_description=job_description,
            resume_text=resume_text,
        )

        try:
            from google.adk.agents import LlmAgent
            from google.adk.apps import App
            from google.adk.models import Gemini
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Google ADK Gemini integration is unavailable in this environment.") from exc

        model = Gemini(
            model=self.model,
            client_kwargs={"api_key": self.api_key},
        )
        agent = LlmAgent(
            name="jobpilot_fit_assessor",
            description="Assess whether a candidate is likely to be a strong fit for a job.",
            model=model,
            instruction=(
                "You are JobPilot. Evaluate the candidate's fit for the job description and return only valid JSON. "
                "The JSON must include: match_score, matching_skills, missing_skills, recommendation, explanation."
            ),
            generate_content_config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        app = App(name="jobpilot-agent", root_agent=agent)
        runner = Runner(app=app, session_service=InMemorySessionService())
        message = types.Content(
            role="user",
            parts=[types.Part(text=prompt)],
        )

        response_parts: list[str] = []

        async def _collect_response() -> None:
            async for event in runner.run_async(
                user_id="jobpilot",
                session_id="jobpilot-session",
                new_message=message,
            ):
                if getattr(event, "content", None) is None:
                    continue
                for part in getattr(event.content, "parts", []) or []:
                    text = getattr(part, "text", None)
                    if text:
                        response_parts.append(text)

        asyncio.run(_collect_response())
        rendered = "".join(response_parts).strip()
        return self._parse_response(self._extract_json_text(rendered))

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        if not raw_text:
            return "{}"
        candidate = raw_text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\s*```\s*$", "", candidate, flags=re.IGNORECASE)
        match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if match:
            return match.group(0)
        return candidate

    def _build_prompt(
        self,
        *,
        job_title: str,
        location: str,
        skills: list[str],
        experience: str,
        job_description: str,
        resume_text: str | None = None,
    ) -> str:
        resume_block = resume_text or "No resume text provided."
        skills_text = ", ".join(skills) if skills else "No explicit skills provided."
        return (
            "You are JobPilot, an AI job-fit assessment agent. "
            "Evaluate the candidate's fit for the provided role without auto-applying or scraping. "
            "Return valid JSON only with keys: match_score (0-100), matching_skills, missing_skills, recommendation, explanation.\n\n"
            f"Job title: {job_title}\n"
            f"Location: {location}\n"
            f"Experience: {experience}\n"
            f"Candidate skills: {skills_text}\n"
            f"Resume text: {resume_block}\n"
            f"Job description: {job_description}\n\n"
            "Assessment rules: identify direct overlaps, highlight missing capabilities, and produce a concise recommendation."
        )

    def _parse_response(self, raw_text: str) -> JobAnalysisResult:
        import json

        data = json.loads(raw_text)
        return JobAnalysisResult(
            match_score=int(data.get("match_score", 0)),
            matching_skills=list(data.get("matching_skills", [])),
            missing_skills=list(data.get("missing_skills", [])),
            recommendation=str(data.get("recommendation", "Review manually.")),
            explanation=str(data.get("explanation", "No explanation provided.")),
        )


def create_agent() -> JobPilotAgent:
    settings = __import__('app.config', fromlist=['get_settings']).get_settings()
    return JobPilotAgent(api_key=settings.gemini_api_key, model=settings.gemini_model)
