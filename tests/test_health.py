def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"
    assert response.json()["version"] == "0.1.0"
    assert response.json()["build_sha"] == "unknown"


def test_metrics_exposes_snapshot_metrics(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "snapshot_worker_jobs_total" in response.text
    assert 'snapshot_service_build_info{build_sha="unknown",environment="local"' in response.text
    assert "snapshot_worker_oldest_pending_job_age_seconds" in response.text
    assert "snapshot_worker_heartbeat_timestamp_seconds" in response.text
    assert "snapshot_scheduler_heartbeat_timestamp_seconds" in response.text
    assert "snapshot_background_tick_errors_total" in response.text
    assert "snapshot_database_errors_total" in response.text
