from app.metrics import jobs_enqueued_total


def test_internal_token_required(client):
    response = client.post(
        "/internal/snapshot-jobs",
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )

    assert response.status_code == 401


def test_invalid_internal_token_rejected(client):
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "wrong-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )

    assert response.status_code == 401


def test_can_create_all_job(client):
    enqueued_before = jobs_enqueued_total.labels("api", "manual", "all")._value.get()
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert jobs_enqueued_total.labels("api", "manual", "all")._value.get() == enqueued_before + 1


def test_can_get_job_status(client):
    created = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )
    job_id = created.json()["job_id"]

    response = client.get(
        f"/internal/snapshot-jobs/{job_id}",
        headers={"X-Internal-Token": "test-token"},
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    assert response.json()["status"] == "pending"


def test_can_create_group_job(client):
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "group", "group_id": 10},
    )

    assert response.status_code == 200


def test_can_create_wallet_job(client):
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "wallet", "wallet_id": 25},
    )

    assert response.status_code == 200


def test_invalid_scope_validation(client):
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "group"},
    )

    assert response.status_code == 422
