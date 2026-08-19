from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_jobs_successful_mock_search():
    response = client.post(
        "/api/jobs/search",
        json={"query": "Python Backend Developer", "location": "Bangalore", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "jobs" in payload
    assert len(payload["jobs"]) >= 1
    assert payload["jobs"][0]["title"]
    assert payload["jobs"][0]["location"] == "Bangalore"


def test_search_jobs_empty_query():
    response = client.post(
        "/api/jobs/search",
        json={"query": "", "location": "Bangalore", "limit": 5},
    )

    assert response.status_code == 422


def test_search_jobs_empty_location():
    response = client.post(
        "/api/jobs/search",
        json={"query": "Python Developer", "location": "", "limit": 5},
    )

    assert response.status_code == 422


def test_search_jobs_limit_validation():
    response = client.post(
        "/api/jobs/search",
        json={"query": "Python Developer", "location": "Bangalore", "limit": 100},
    )

    assert response.status_code == 422


def test_search_jobs_multiple_jobs_returned():
    response = client.post(
        "/api/jobs/search",
        json={"query": "Python", "location": "Bangalore", "limit": 10},
    )

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) >= 2
    assert {job["company"] for job in jobs}


def test_search_jobs_provider_failure_handling():
    with patch("app.discovery.JobDiscoveryService.search_jobs", side_effect=RuntimeError("provider unavailable")):
        response = client.post(
            "/api/jobs/search",
            json={"query": "Python Developer", "location": "Bangalore", "limit": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"] == []
    assert "provider unavailable" in payload.get("error", "")
