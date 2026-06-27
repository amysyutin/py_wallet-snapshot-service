def test_internal_token_required(client):
    response = client.post(
        "/internal/snapshot-jobs",
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )

    assert response.status_code == 401


def test_can_create_all_job(client):
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )

    assert response.status_code == 200
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

