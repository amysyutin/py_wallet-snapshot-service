# Changelog

## [Unreleased]

### Added

- Resolve blank manual-asset prices from crypto tickers through CoinGecko and
  ISO 4217 fiat tickers through Frankfurter exchange rates.
- Price configured ERC-20 balances by CoinGecko asset platform and contract,
  starting with mainnet WETH and WBTC while retaining symbol fallback.
- Collect native SOL and official mainnet SPL USDC/USDT balances for Solana wallets,
  with bounded RPC failover, retry support, and normalized snapshot persistence.
