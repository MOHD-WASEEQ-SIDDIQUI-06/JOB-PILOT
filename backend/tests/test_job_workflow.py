from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent import JobAnalysisResult
from app.main import app

client = TestClient(app)


def build_payload():
    return {
        "candidate": {
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "experience": "2 years",
            "resume_text": "Python engineer with FastAPI and PostgreSQL experience.",
        },
        "jobs": [
            {
                "id": "job-1",
                "title": "Python Backend Developer",
                "company": "Acme Labs",
                "location": "Bangalore",
                "description": "We are looking for a Python developer with FastAPI and PostgreSQL experience.",
                "url": "https://example.com/jobs/1",
                "source": "mock-source",
            },
            {
                "id": "job-2",
                "title": "Frontend Engineer",
                "company": "Nova Systems",
                "location": "Remote",
                "description": "We need a React developer with TypeScript and CSS experience.",
                "url": "https://example.com/jobs/2",
                "source": "mock-source",
            },
        ],
    }


def test_analyze_jobs_valid_candidate_and_jobs():
    with patch("app.main.JobPilotWorkflow.analyze_jobs") as mock_analyze:
        mock_analyze.return_value = [
            JobAnalysisResult(
                match_score=90,
                matching_skills=["Python", "FastAPI", "PostgreSQL"],
                missing_skills=["Docker"],
                recommendation="strong_match",
                explanation="Strong fit based on experience and skills.",
            )
        ]

        response = client.post("/api/agent/analyze-jobs", json=build_payload())

    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert len(data["jobs"]) == 2
    assert data["jobs"][0]["match_score"] == 90
    assert data["jobs"][0]["recommendation"] == "strong_match"


def test_analyze_jobs_empty_job_list():
    payload = {"candidate": build_payload()["candidate"], "jobs": []}
    response = client.post("/api/agent/analyze-jobs", json=payload)

    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_analyze_jobs_invalid_job_data():
    payload = {
        "candidate": build_payload()["candidate"],
        "jobs": [{
            "id": "",
            "title": "",
            "company": "",
            "location": "",
            "description": "",
            "url": "",
            "source": "",
        }],
    }

    response = client.post("/api/agent/analyze-jobs", json=payload)
    assert response.status_code == 422


def test_analyze_jobs_multiple_jobs_response_shape():
    response = client.post("/api/agent/analyze-jobs", json=build_payload())
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    first_key_set = set(jobs[0].keys())
    expected = {"id", "title", "company", "location", "match_score", "matching_skills", "missing_skills", "recommendation", "explanation"}
    assert expected.issubset(first_key_set)


def test_analyze_jobs_requires_valid_candidate():
    payload = {
        "candidate": {
            "job_title": "",
            "location": "",
            "skills": [],
            "experience": "",
        },
        "jobs": [
            {
                "id": "job-1",
                "title": "Python Engineer",
                "company": "Acme",
                "location": "Bangalore",
                "description": "Python and FastAPI role.",
                "url": "https://example.com/jobs/1",
                "source": "mock-source",
            }
        ],
    }
    response = client.post("/api/agent/analyze-jobs", json=payload)
    assert response.status_code == 422
