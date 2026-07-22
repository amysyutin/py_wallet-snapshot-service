import pytest
from pydantic import ValidationError

from app.config import Settings


def make_settings(**overrides) -> Settings:
    values = {"internal_api_token": "local-test-token", **overrides}
    return Settings(_env_file=None, **values)


def test_internal_api_token_is_required_in_every_environment():
    with pytest.raises(ValidationError, match="INTERNAL_API_TOKEN is required"):
        make_settings(internal_api_token="")


def test_production_rejects_documented_placeholder():
    with pytest.raises(ValidationError, match="known placeholder"):
        make_settings(environment="production", internal_api_token="change-me")


def test_production_rejects_short_internal_api_token():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        make_settings(environment="production", internal_api_token="too-short")


def test_production_accepts_strong_internal_api_token():
    token = "a-strong-production-internal-token-value"

    settings = make_settings(environment=" PRODUCTION ", internal_api_token=token)

    assert settings.environment == "production"
    assert settings.internal_api_token == token


def test_validation_error_does_not_echo_token():
    token = "weak-secret"

    with pytest.raises(ValidationError) as exc_info:
        make_settings(environment="production", internal_api_token=token)

    assert token not in str(exc_info.value)


def test_snapshot_job_lease_has_safe_bounds():
    assert make_settings().snapshot_job_lease_seconds == 1800

    with pytest.raises(ValidationError):
        make_settings(snapshot_job_lease_seconds=59)
