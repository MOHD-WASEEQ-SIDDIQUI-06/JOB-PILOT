from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_workflow_creation():
    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "experience": "2 years",
            "resume_text": "Python backend engineer with FastAPI and SQL experience.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "workflow_id" in data
    assert data["status"] == "queued"


def test_workflow_status():
    create_response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI"],
            "experience": "2 years",
            "resume_text": "Python engineer.",
        },
    )
    workflow_id = create_response.json()["workflow_id"]

    response = client.get(f"/api/workflows/{workflow_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_id"] == workflow_id
    assert payload["status"] in {"queued", "completed", "failed", "discovering", "analyzing", "ranking", "preparing", "waiting_for_review"}


def test_discovery_stage():
    with patch("app.taskmaster.JobDiscoveryService.search_jobs") as mock_search:
        mock_search.return_value = [
            type("Job", (), {
                "id": "job-1",
                "title": "Python Backend Developer",
                "company": "Acme Labs",
                "location": "Bangalore",
                "description": "Python, FastAPI, and SQL work.",
                "url": "https://example.com/1",
                "source": "mock",
                "to_dict": lambda self: {
                    "id": self.id,
                    "title": self.title,
                    "company": self.company,
                    "location": self.location,
                    "description": self.description,
                    "url": self.url,
                    "source": self.source,
                },
            })()
        ]
        response = client.post(
            "/api/workflows",
            json={
                "job_title": "Python Backend Developer",
                "location": "Bangalore",
                "skills": ["Python", "FastAPI"],
                "experience": "2 years",
            },
        )

    assert response.status_code == 200
    workflow_id = response.json()["workflow_id"]
    workflow = client.get(f"/api/workflows/{workflow_id}").json()
    assert workflow["jobs_discovered"] >= 1


def test_analysis_stage():
    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "experience": "2 years",
        },
    )
    workflow = client.get(f"/api/workflows/{response.json()['workflow_id']}").json()
    assert workflow["jobs_analyzed"] >= 1


def test_ranking_stage():
    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI"],
            "experience": "2 years",
        },
    )
    workflow = client.get(f"/api/workflows/{response.json()['workflow_id']}").json()
    assert len(workflow["ranked_jobs"]) >= 1
    assert workflow["strong_matches"] or workflow["ranked_jobs"]


def test_preparation_stage():
    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "experience": "2 years",
        },
    )
    workflow = client.get(f"/api/workflows/{response.json()['workflow_id']}").json()
    assert workflow["application_preparation_count"] >= 0


def test_failed_workflow():
    with patch("app.taskmaster.JobDiscoveryService.search_jobs", side_effect=RuntimeError("provider down")):
        response = client.post(
            "/api/workflows",
            json={
                "job_title": "Python Backend Developer",
                "location": "Bangalore",
                "skills": ["Python"],
                "experience": "2 years",
            },
        )

    assert response.status_code == 200
    workflow_id = response.json()["workflow_id"]
    workflow = client.get(f"/api/workflows/{workflow_id}").json()
    assert workflow["status"] == "failed"
    assert "provider down" in workflow["error"]


def test_human_review_requirement():
    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "experience": "2 years",
        },
    )
    workflow = client.get(f"/api/workflows/{response.json()['workflow_id']}").json()
    assert workflow["status"] in {"waiting_for_review", "completed"}
    if workflow["preparation_packages"]:
        assert workflow["preparation_packages"][0]["requires_human_review"] is True


def test_no_automatic_application_submission():
    response = client.post(
        "/api/workflows",
        json={
            "job_title": "Python Backend Developer",
            "location": "Bangalore",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "experience": "2 years",
        },
    )
    workflow = client.get(f"/api/workflows/{response.json()['workflow_id']}").json()
    assert workflow["status"] in {"waiting_for_review", "completed"}
    for package in workflow["preparation_packages"]:
        assert package.get("application_status") in {None, "not_submitted"}


def test_human_review_approve_persists_without_submission():
    workflow_service = __import__("app.taskmaster", fromlist=["WorkflowService"]).WorkflowService()
    workflow_id = workflow_service.create_workflow({
        "job_title": "Python Backend Developer",
        "location": "Bangalore",
    })["workflow_id"]
    workflow_service.repository.save_workflow_results(workflow_id, {
        "preparation_packages": [{
            "job_id": "job-approval",
            "requires_human_review": True,
            "review_status": "pending",
            "application_status": "not_submitted",
        }],
        "requires_human_review": True,
    })

    response = client.post(
        f"/api/workflows/{workflow_id}/preparation-packages/job-approval/review",
        json={"decision": "approve"},
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"
    assert response.json()["application_status"] == "not_submitted"
    stored = client.get(f"/api/workflows/{workflow_id}").json()
    assert stored["preparation_packages"][0]["review_status"] == "approved"
    assert stored["preparation_packages"][0]["application_status"] == "not_submitted"


def test_human_review_reject_persists_without_submission():
    workflow_service = __import__("app.taskmaster", fromlist=["WorkflowService"]).WorkflowService()
    workflow_id = workflow_service.create_workflow({
        "job_title": "Python Backend Developer",
        "location": "Bangalore",
    })["workflow_id"]
    workflow_service.repository.save_workflow_results(workflow_id, {
        "preparation_packages": [{
            "job_id": "job-rejection",
            "requires_human_review": True,
            "review_status": "pending",
            "application_status": "not_submitted",
        }],
        "requires_human_review": True,
    })

    response = client.post(
        f"/api/workflows/{workflow_id}/preparation-packages/job-rejection/review",
        json={"decision": "reject"},
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "rejected"
    assert response.json()["application_status"] == "not_submitted"
    stored = client.get(f"/api/workflows/{workflow_id}").json()
    assert stored["preparation_packages"][0]["review_status"] == "rejected"
