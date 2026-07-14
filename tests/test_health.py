def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_metrics_exposes_snapshot_metrics(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "snapshot_worker_jobs_total" in response.text
