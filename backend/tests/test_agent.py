import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.agent import JobPilotAgent

client = TestClient(app)


def test_agent_uses_adk_stack_when_api_key_is_present(monkeypatch):
    recorded = {}

    class FakePart:
        def __init__(self, text):
            self.text = text

    class FakeContent:
        def __init__(self, text):
            self.parts = [FakePart(text)]

    class FakeEvent:
        def __init__(self, text):
            self.content = FakeContent(text)

    class FakeRunner:
        def __init__(self, **kwargs):
            recorded["runner"] = kwargs

        async def run_async(self, **kwargs):
            yield FakeEvent(
                '{"match_score": 88, "matching_skills": ["Python", "FastAPI"], '
                '"missing_skills": ["PostgreSQL"], "recommendation": "Strong candidate; worth applying.", '
                '"explanation": "Good fit for the role."}'
            )

    class FakeSessionService:
        def __init__(self):
            recorded["session_service"] = True

        async def create_session(self, **kwargs):
            class FakeSession:
                id = "session-123"
                user_id = "jobpilot"
            return FakeSession()

    class FakeApp:
        def __init__(self, **kwargs):
            recorded["app"] = kwargs

    class FakeGemini:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model")
            self.client_kwargs = kwargs.get("client_kwargs", {})
            recorded["gemini"] = self

    class FakeLlmAgent:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model")
            recorded["llm_agent"] = kwargs

    monkeypatch.setattr("google.adk.models.Gemini", FakeGemini, raising=False)
    monkeypatch.setattr("google.adk.agents.LlmAgent", FakeLlmAgent, raising=False)
    monkeypatch.setattr("google.adk.apps.App", FakeApp, raising=False)
    monkeypatch.setattr("google.adk.runners.Runner", FakeRunner, raising=False)
    monkeypatch.setattr("google.adk.sessions.InMemorySessionService", FakeSessionService, raising=False)

    agent = JobPilotAgent(api_key="test-key", model="gemini-3.5-flash")
    result = agent._gemini_analysis(
        job_title="Python Backend Developer",
        location="Bangalore",
        skills=["Python", "FastAPI"],
        experience="2 years",
        job_description="We need Python and FastAPI experience.",
        resume_text="Python backend engineer.",
    )

    assert result.match_score == 88
    assert "Python" in result.matching_skills
    assert "PostgreSQL" in result.missing_skills
    assert recorded["gemini"].model == "gemini-3.5-flash"
    assert recorded["llm_agent"]["model"] is recorded["gemini"]


def test_agent_endpoint_uses_mock_path_without_api_key():
    payload = {
        "job_title": "Python Backend Developer",
        "location": "Bangalore",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "experience": "2 years",
        "job_description": "We are looking for a Python developer with FastAPI and PostgreSQL experience. Docker is a plus.",
    }

    response = client.post("/api/agent/analyze-job", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "match_score" in data
    assert "matching_skills" in data
    assert "missing_skills" in data
    assert "recommendation" in data
    assert "explanation" in data
    assert "Python" in data["matching_skills"]
    assert data["match_score"] >= 0
    assert data["match_score"] <= 100
