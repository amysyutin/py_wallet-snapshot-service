import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.chain_config import (
    SUPPORTED_CHAINS,
    get_chain_configs,
    get_enabled_chains,
    get_solana_rpc_urls,
)


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


def test_solana_rpc_url_supports_ordered_failover_endpoints():
    settings = make_settings(
        solana_rpc_url=" https://primary.test,https://backup.test, https://primary.test "
    )

    assert get_solana_rpc_urls(settings) == (
        "https://primary.test",
        "https://backup.test",
        "https://primary.test",
    )


def test_enabled_chains_filters_unknown_values_and_preserves_unique_order():
    settings = make_settings(snapshot_enabled_chains=" base,unknown,mainnet,base, bnb, ")

    assert get_enabled_chains(settings) == ("base", "mainnet", "bnb")


def test_enabled_chains_falls_back_to_all_supported_chains():
    settings = make_settings(snapshot_enabled_chains="unknown,also-unknown")

    assert get_enabled_chains(settings) == SUPPORTED_CHAINS


def test_chain_configs_apply_rpc_timeout_and_provider_metadata():
    settings = make_settings(
        chain_timeout_seconds=7,
        ethereum_timeout_seconds=11,
        ethereum_rpc_url=" https://mainnet-primary.test, ,https://mainnet-backup.test ",
        base_rpc_url="https://base.test",
        arbitrum_rpc_url="https://arbitrum.test",
        bnb_rpc_url="https://bnb.test",
        linea_rpc_url="",
    )

    configs = get_chain_configs(settings)

    assert tuple(configs) == SUPPORTED_CHAINS
    assert configs["mainnet"].rpc_urls == (
        "https://mainnet-primary.test",
        "https://mainnet-backup.test",
    )
    assert configs["mainnet"].rpc_url == "https://mainnet-primary.test"
    assert configs["mainnet"].timeout_seconds == 11
    assert configs["mainnet"].expected_chain_id == 1
    assert configs["mainnet"].coingecko_platform == "ethereum"
    assert configs["base"].rpc_urls == ("https://base.test",)
    assert configs["base"].timeout_seconds == 7
    assert configs["base"].expected_chain_id == 8453
    assert configs["arbitrum"].coingecko_platform == "arbitrum-one"
    assert configs["bnb"].native_symbol == "BNB"
    assert configs["bnb"].coingecko_platform == "binance-smart-chain"
    assert configs["linea"].rpc_urls == ()
    assert configs["linea"].rpc_url == ""
