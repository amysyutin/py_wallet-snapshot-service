from app.metrics import jobs_enqueued_total
from app.models.snapshots import SnapshotRun


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
    assert response.json()["reused"] is False
    assert jobs_enqueued_total.labels("api", "manual", "all")._value.get() == enqueued_before + 1


def test_active_job_is_reused_for_the_same_user_and_scope(client, db_session):
    enqueued_before = jobs_enqueued_total.labels("api", "manual", "all")._value.get()
    first = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )
    second = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )

    assert second.status_code == 200
    assert second.json() == {
        "job_id": first.json()["job_id"],
        "status": "pending",
        "reused": True,
    }
    assert db_session.query(SnapshotRun).count() == 1
    assert jobs_enqueued_total.labels("api", "manual", "all")._value.get() == enqueued_before + 1


def test_active_job_reuse_is_scoped_by_user_and_target(client, db_session):
    all_job = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "all"},
    )
    wallet_job = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "wallet", "wallet_id": 25},
    )
    other_user_job = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 2, "trigger_type": "manual", "scope_type": "all"},
    )

    assert all_job.json()["reused"] is False
    assert wallet_job.json()["reused"] is False
    assert other_user_job.json()["reused"] is False
    assert db_session.query(SnapshotRun).count() == 3


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


def test_first_wallet_job_persists_bounded_activation_channel(client, db_session):
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={
            "user_id": 1,
            "trigger_type": "auto",
            "scope_type": "wallet",
            "wallet_id": 25,
            "activation_channel": "telegram",
        },
    )

    assert response.status_code == 200
    assert db_session.query(SnapshotRun).one().activation_channel == "telegram"


def test_activation_channel_rejects_unbounded_or_non_auto_values(client):
    unbounded = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={
            "user_id": 1,
            "trigger_type": "auto",
            "scope_type": "wallet",
            "wallet_id": 25,
            "activation_channel": "user-123",
        },
    )
    manual = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={
            "user_id": 1,
            "trigger_type": "manual",
            "scope_type": "wallet",
            "wallet_id": 25,
            "activation_channel": "web",
        },
    )

    assert unbounded.status_code == 422
    assert manual.status_code == 422


def test_invalid_scope_validation(client):
    response = client.post(
        "/internal/snapshot-jobs",
        headers={"X-Internal-Token": "test-token"},
        json={"user_id": 1, "trigger_type": "manual", "scope_type": "group"},
    )

    assert response.status_code == 422
