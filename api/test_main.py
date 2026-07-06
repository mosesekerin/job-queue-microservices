import fakeredis
import main
from fastapi.testclient import TestClient

# Swap the real Redis for a fake one BEFORE any test runs
main.r = fakeredis.FakeRedis()

client = TestClient(main.app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job_returns_id_and_queues_it():
    response = client.post("/jobs")
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    # the status board must say "queued"
    assert main.r.hget(f"job:{job_id}", "status") == b"queued"
    # and the job must be in the queue
    assert main.r.lrange("job", 0, -1) == [job_id.encode()]


def test_get_existing_job_status():
    job_id = client.post("/jobs").json()["job_id"]
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_get_missing_job_returns_404():
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404
