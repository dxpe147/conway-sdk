# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.0.0] — 2026-02-25

### Added

- **Initial public release** of the Conway SDK.

- `conway_sdk.models` — Typed `Agent` and `PaymentIntent` dataclasses backed
  entirely by the Python standard library (no third-party runtime dependencies).

- `conway_sdk.execution_adapter` — `ExecutionAdapter` ABC and `ExecutionResult`
  dataclass defining the contract for payment execution implementations.

- `conway_sdk.config` — `SdkConfig` dataclass for configuring payment timeout
  and maximum authorization window bounds.

- `conway_sdk.wallet.base` — `AbstractWallet` ABC, `ECDSASignature`, and
  `WalletProtocol` structural protocol for flexible wallet integration.

- `conway_sdk.wallet.local` — `LocalWallet`: in-process EIP-712 wallet backed
  by eth-account, supporting sync and async signing, plus BIP-39 mnemonic
  derivation.

- `conway_sdk.wallet.redis_nonce_cache` — `RedisNonceCache`: distributed nonce
  deduplication using Redis `SET NX EX` (first-writer-wins semantics) for
  multi-instance deployments.

- `conway_sdk.wallet.kms` — `KMSWallet` and `KMSWalletStub` for AWS KMS-backed
  production signing with eager address resolution and configurable boto3
  timeouts. Requires `conway-sdk[kms]`.

- `conway_sdk.payment.caip2` — CAIP-2 chain identifier parsing and building
  utilities (`parse_caip2_chain_id`, `parse_caip2_asset`, `build_caip2`,
  `CAIP2ParseError`).

- `conway_sdk.payment.models` — Pydantic v2 `PaymentRequirements` and
  `PaymentAuthorization` models for the x402 HTTP payment protocol, including
  `PAYMENT-REQUIRED` header parsing and `PAYMENT-SIGNATURE` header serialization.

- `conway_sdk.payment.eip3009` — `EIP3009Signer`: orchestrates EIP-3009
  `transferWithAuthorization` signing with configurable authorization windows,
  CSPRNG nonce generation, and both sync (`sign`) and async (`sign_async`)
  variants.

- `conway_sdk.exceptions` — Full exception hierarchy rooted at `ConwayError`,
  covering HTTP errors, payment errors, signing errors, and retry errors.

[Unreleased]: https://github.com/dxpe_7/conway-sdk/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/dxpe_7/conway-sdk/releases/tag/v1.0.0
