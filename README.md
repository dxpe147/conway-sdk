# Conway SDK

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![PyPI](https://img.shields.io/pypi/v/conway-sdk)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-stable-brightgreen)

**Conway SDK** is a Python library for building payment-enabled autonomous agents
using the [x402](https://x402.org) protocol with EIP-3009 delegated USDC transfers.

It provides everything you need to sign, model, and execute on-chain payment
authorizations — without bundling runtime, persistence, or orchestration logic.
Those belong in the application layer built on top.

```
Your Agent  →  conway-sdk (signing + models)  →  x402 facilitator  →  on-chain
```

---

## Table of Contents

1. [Installation](#installation)
2. [Core Concepts](#core-concepts)
3. [Wallets](#wallets)
4. [Signing a Payment](#signing-a-payment)
5. [Parsing x402 Responses](#parsing-x402-responses)
6. [Async Signing](#async-signing)
7. [Agent and PaymentIntent Models](#agent-and-paymentintent-models)
8. [ExecutionAdapter — Custom Payment Logic](#executionadapter--custom-payment-logic)
9. [Redis Nonce Deduplication](#redis-nonce-deduplication)
10. [CAIP-2 Network Utilities](#caip-2-network-utilities)
11. [Connecting with the ATR Runtime](#connecting-with-the-atr-runtime)
12. [Building a Custom Wallet](#building-a-custom-wallet)
13. [Module Reference](#module-reference)
14. [Exception Hierarchy](#exception-hierarchy)
15. [Security](#security)

---

## Installation

```bash
pip install conway-sdk
```

### Optional extras

```bash
# Redis nonce deduplication — required for multi-instance deployments
pip install "conway-sdk[redis]"

# AWS KMS wallet — required for production signing (keys never in memory)
pip install "conway-sdk[kms]"

# PostgreSQL distributed persistence (used by the ATR runtime)
pip install "conway-sdk[distributed]"

# Everything at once
pip install "conway-sdk[redis,kms,distributed]"

# Development tooling (pytest, ruff, mypy)
pip install "conway-sdk[dev]"
```

---

## Core Concepts

### How x402 works

The x402 protocol extends HTTP: a server returns `402 Payment Required` with
a `PAYMENT-REQUIRED` header describing what it needs. The client signs a
`TransferWithAuthorization` EIP-3009 authorization and retries with a
`PAYMENT-SIGNATURE` header. The server forwards it to a facilitator for
on-chain settlement.

```
Client                          Server                    Facilitator
  |                               |                           |
  |── GET /resource ─────────────▶|                           |
  |◀─ 402 PAYMENT-REQUIRED ───────|                           |
  |                               |                           |
  |  [sign EIP-3009 auth]         |                           |
  |                               |                           |
  |── GET /resource ─────────────▶|                           |
  |   PAYMENT-SIGNATURE: ...      |── forward auth ──────────▶|
  |                               |                    [settle on-chain]
  |◀─ 200 OK ─────────────────────|◀──────────────────────────|
```

### What the SDK provides

| Component | Purpose |
|---|---|
| `LocalWallet` / `KMSWallet` | Signs EIP-712 structured data |
| `EIP3009Signer` | Builds and signs the full `TransferWithAuthorization` payload |
| `PaymentRequirements` | Parses the `PAYMENT-REQUIRED` challenge from a server |
| `PaymentAuthorization` | Holds the signed result + header encoding |
| `Agent` / `PaymentIntent` | Typed models for agent-scoped economic operations |
| `ExecutionAdapter` | ABC for implementing custom payment execution logic |
| `RedisNonceCache` | Cross-instance nonce deduplication via Redis |
| CAIP-2 utilities | Parse and build `eip155:<chain_id>` network identifiers |

---

## Wallets

### LocalWallet — development and testing

Holds the private key in process memory. Use only with short-lived keys loaded
from a secrets manager. **Never use in production with real funds.**

```python
from conway_sdk import LocalWallet

# From hex string (with or without 0x prefix)
wallet = LocalWallet("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")

print(wallet.address)
# → "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
```

### KMSWallet — production

Private keys never leave AWS KMS. The Ethereum address is resolved eagerly at
construction time, validating connectivity and IAM permissions immediately.

```python
from conway_sdk.wallet.kms import KMSWallet

# Requires: pip install "conway-sdk[kms]"
# Key type must be ECC_SECQ_P256K1, signing algorithm ECDSA_SHA_256

wallet = KMSWallet(
    key_id="alias/conway-signing-key",    # ARN or alias
    region_name="us-east-1",             # default
)

print(wallet.address)  # Derived from KMS public key — no private key in process
```

With custom session and timeout:

```python
import boto3
from botocore.config import Config

session = boto3.Session(
    aws_access_key_id="...",      # or use IAM role / env vars
    aws_secret_access_key="...",
)

wallet = KMSWallet(
    key_id="alias/conway-signing-key",
    boto_session=session,
    boto3_config=Config(connect_timeout=3, read_timeout=7),
)
```

### KMSWalletStub — unit tests

Drop-in replacement for `KMSWallet` in tests. Delegates to a `LocalWallet`
internally — no real AWS calls.

```python
from conway_sdk.wallet.kms import KMSWalletStub

wallet = KMSWalletStub("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
assert wallet.address == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
```

---

## Signing a Payment

### Full flow from scratch

```python
from conway_sdk import LocalWallet, EIP3009Signer
from conway_sdk.config import SdkConfig
from conway_sdk.payment.models import PaymentRequirements

wallet = LocalWallet("0x<private_key>")

config = SdkConfig(
    payment_timeout_seconds=300,           # Authorization window (5 min)
    max_authorization_window_seconds=86400, # Reject challenges > 24h
)
signer = EIP3009Signer(config)

requirements = PaymentRequirements(
    amount=1_000_000,          # 1 USDC in atomic units (6 decimals)
    chain_id=84532,            # Base Sepolia testnet
    verifying_contract="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    pay_to="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    network="eip155:84532",    # CAIP-2 format
)

# Sign — returns a PaymentAuthorization
authorization = signer.sign(wallet, requirements)

# Attach to your HTTP retry request
headers = authorization.to_payment_headers()
# → {"PAYMENT-SIGNATURE": "<base64-encoded JSON>"}

print(authorization.nonce)      # 0x... — 32-byte unique nonce
print(authorization.valid_before)  # Unix timestamp
```

### Inspecting the authorization

```python
print(authorization.amount)             # 1000000
print(authorization.from_address)       # wallet.address
print(authorization.to_address)         # pay_to
print(authorization.verifying_contract) # USDC contract
print(authorization.nonce)              # 0x<64-char hex>
print(authorization.valid_after)        # 0 (immediate)
print(authorization.valid_before)       # now + timeout - 5s safety buffer
```

---

## Parsing x402 Responses

### From the PAYMENT-REQUIRED header

```python
from conway_sdk.payment.models import PaymentRequirements

# Raw header value from the 402 response
header = response.headers["PAYMENT-REQUIRED"]
requirements = PaymentRequirements.from_payment_required_header(header)

print(requirements.amount)             # e.g. 1000000
print(requirements.chain_id)           # e.g. 84532
print(requirements.verifying_contract) # USDC contract on that chain
print(requirements.pay_to)             # recipient address
```

### From a JSON body (fallback)

```python
import json

body = response.json()
requirements = PaymentRequirements.from_dict(body)
```

### Complete 402 → sign → retry pattern

```python
import httpx
from conway_sdk import LocalWallet, EIP3009Signer
from conway_sdk.config import SdkConfig
from conway_sdk.payment.models import PaymentRequirements

wallet = LocalWallet("0x<private_key>")
signer = EIP3009Signer(SdkConfig())

with httpx.Client() as client:
    response = client.get("https://api.example.com/data")

    if response.status_code == 402:
        requirements = PaymentRequirements.from_payment_required_header(
            response.headers["PAYMENT-REQUIRED"]
        )
        authorization = signer.sign(wallet, requirements)

        # Retry with payment attached
        response = client.get(
            "https://api.example.com/data",
            headers=authorization.to_payment_headers(),
        )

    response.raise_for_status()
    print(response.json())
```

---

## Async Signing

All signing operations have async equivalents. Use these in async frameworks
(FastAPI, aiohttp, asyncio) to avoid blocking the event loop.

```python
import asyncio
from conway_sdk import LocalWallet, EIP3009Signer
from conway_sdk.config import SdkConfig
from conway_sdk.payment.models import PaymentRequirements

wallet = LocalWallet("0x<private_key>")
signer = EIP3009Signer(SdkConfig())

async def pay_and_fetch(url: str) -> dict:
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(url)

        if response.status_code == 402:
            requirements = PaymentRequirements.from_payment_required_header(
                response.headers["PAYMENT-REQUIRED"]
            )
            # Non-blocking — runs signing in a thread executor
            authorization = await signer.sign_async(wallet, requirements)

            response = await client.get(
                url,
                headers=authorization.to_payment_headers(),
            )

        return response.json()

result = asyncio.run(pay_and_fetch("https://api.example.com/data"))
```

---

## Agent and PaymentIntent Models

Use these models when building agent-scoped payment systems on top of the SDK.

### Agent

```python
from conway_sdk import Agent

# Factory method — generates UUIDs automatically
agent = Agent.create(
    treasury_id=...,           # UUID of the treasury this agent belongs to
    environment="development", # or "production"
    metadata={"name": "trading-agent-1", "strategy": "arb"},
)

print(agent.agent_id)    # UUID
print(agent.treasury_id) # UUID
print(agent.environment) # "development"
```

### PaymentIntent

```python
from conway_sdk import PaymentIntent
from uuid import UUID

intent = PaymentIntent(
    agent_id=agent.agent_id,
    bucket_id="primary",
    asset="USDC",
    network="eip155:84532",
    amount=1_000_000,          # 1 USDC
    destination="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    verifying_contract="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    metadata={"order_id": "ord_123", "service": "inference-api"},
)

print(intent.intent_id)  # Auto-generated UUID
print(intent.amount)     # 1000000
```

---

## ExecutionAdapter — Custom Payment Logic

`ExecutionAdapter` is the integration contract between your payment orchestration
layer and the SDK's signing primitives. Implement it to wire any custom logic —
pre-flight checks, logging, dry-run modes — around the signing flow.

**Contract:** `execute()` must never raise. All errors are returned as
`ExecutionResult(success=False, error=exc)`.

### Implementing a simple adapter

```python
from conway_sdk import ExecutionAdapter, ExecutionResult, EIP3009Signer, LocalWallet
from conway_sdk.config import SdkConfig
from conway_sdk.models import PaymentIntent
from conway_sdk.payment.models import PaymentRequirements

class MyPaymentAdapter(ExecutionAdapter):
    def __init__(self, wallet: LocalWallet, signer: EIP3009Signer):
        self._wallet = wallet
        self._signer = signer

    def execute(self, intent: PaymentIntent) -> ExecutionResult:
        try:
            requirements = PaymentRequirements(
                amount=intent.amount,
                chain_id=84532,
                verifying_contract=intent.verifying_contract,
                pay_to=intent.destination,
                network=intent.network,
            )
            auth = self._signer.sign(self._wallet, requirements)
            return ExecutionResult(
                success=True,
                intent_id=intent.intent_id,
                nonce=auth.nonce,
                authorization=auth,
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                intent_id=intent.intent_id,
                error=exc,
            )

# Usage
wallet = LocalWallet("0x<private_key>")
signer = EIP3009Signer(SdkConfig())
adapter = MyPaymentAdapter(wallet, signer)

intent = PaymentIntent(
    agent_id=agent.agent_id,
    bucket_id="primary",
    asset="USDC",
    network="eip155:84532",
    amount=500_000,
    destination="0x<recipient>",
    verifying_contract="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
)

result = adapter.execute(intent)
if result.success:
    print(f"Signed. Nonce: {result.nonce}")
else:
    print(f"Failed: {result.error}")
```

### Dry-run / simulation adapter

```python
from conway_sdk import ExecutionAdapter, ExecutionResult
from conway_sdk.models import PaymentIntent
from uuid import uuid4

class DryRunAdapter(ExecutionAdapter):
    """Returns a fake successful result without signing anything."""

    def execute(self, intent: PaymentIntent) -> ExecutionResult:
        fake_nonce = "0x" + "ab" * 32
        return ExecutionResult(
            success=True,
            intent_id=intent.intent_id,
            nonce=fake_nonce,
        )
```

---

## Redis Nonce Deduplication

In multi-instance deployments, two instances could sign with the same nonce
before either has settled on-chain. `RedisNonceCache` prevents this using
an atomic `SET key NX EX` operation — the first instance to call `record()`
wins; all others get `False`.

```python
# Requires: pip install "conway-sdk[redis]"
import redis
from conway_sdk import RedisNonceCache

client = redis.Redis.from_url("redis://localhost:6379/0")
cache = RedisNonceCache(client, ttl_seconds=3600)

# After signing, register the nonce before submitting
authorization = signer.sign(wallet, requirements)

is_fresh = cache.record(authorization.nonce)
if not is_fresh:
    raise RuntimeError("Duplicate nonce — another instance already used this nonce")

# Safe to submit the authorization to the server
```

### Checking without registering

```python
# Non-destructive check (does not mark the nonce as used)
already_used = cache.is_known(authorization.nonce)
```

### Ping / health check

```python
is_alive = cache.ping()  # True if Redis is reachable
```

### Connection failure handling

```python
# RedisNonceCache raises ConwayRedisError on connection failure.
# Use this to implement fail-safe behaviour:

from conway_sdk.exceptions import ConwayRedisError

try:
    cache.record(nonce)
except ConwayRedisError:
    # Redis is down — nonce deduplication is unavailable.
    # In a strict system: abort the payment.
    # In a lenient system: log and continue (on-chain deduplication still applies).
    raise
```

---

## CAIP-2 Network Utilities

The x402 protocol uses [CAIP-2](https://github.com/ChainAgnostic/CAIPs/blob/main/CAIPs/caip-2.md)
format to identify networks: `eip155:<chain_id>`.

```python
from conway_sdk import parse_caip2_chain_id
from conway_sdk.payment.caip2 import build_caip2

# Parse network string → chain ID integer
chain_id = parse_caip2_chain_id("eip155:84532")  # → 84532
chain_id = parse_caip2_chain_id("eip155:8453")   # → 8453  (Base Mainnet)
chain_id = parse_caip2_chain_id("eip155:1")      # → 1     (Ethereum Mainnet)

# Build CAIP-2 string from chain ID
network = build_caip2(84532)  # → "eip155:84532"
network = build_caip2(1)      # → "eip155:1"
```

### Common chain IDs

| Network | Chain ID | CAIP-2 |
|---|---|---|
| Ethereum Mainnet | `1` | `eip155:1` |
| Base Mainnet | `8453` | `eip155:8453` |
| Base Sepolia (testnet) | `84532` | `eip155:84532` |
| Polygon | `137` | `eip155:137` |
| Arbitrum One | `42161` | `eip155:42161` |

---

## Connecting with the ATR Runtime

The **Conway ATR** (Agent Treasury Runtime) is a private runtime built on top
of this SDK. It adds:

- **SpendBucket** — per-transaction and rolling-window rate limits with atomic reservations
- **Ledger** — append-only audit trail for every payment state transition
- **Treasury** — economic orchestrator (never raises; always returns `ExecutionResult`)
- **PostgreSQL + Redis** — distributed-safe persistence and nonce deduplication
- **REST API** — FastAPI endpoints for agent registration, payment execution, and health monitoring

The ATR uses `ExecutionAdapter` as its integration point. The SDK's
`X402ExecutionAdapter` (shipped with the ATR) bridges `PaymentIntent` → `EIP3009Signer`:

```
ATR Treasury
    │
    ├─ check SpendBucket limits
    ├─ write BUCKET_RESERVED to Ledger
    │
    └─ ExecutionAdapter.execute(intent)   ← SDK contract
           │
           └─ EIP3009Signer.sign(wallet, requirements)
                  │
                  └─ KMSWallet / LocalWallet
```

### Using the SDK with the ATR (programmatic)

If you're running the ATR runtime directly (not via its REST API), you can wire
the SDK components yourself:

```python
from conway_sdk import Agent, PaymentIntent, LocalWallet
from conway_sdk.wallet.kms import KMSWallet

# Development
wallet = LocalWallet("0x<hardhat_test_key>")

# Production — use KMSWallet so keys never touch memory
# wallet = KMSWallet(key_id="alias/conway-signing-key")

# The ATR's X402ExecutionAdapter wraps the wallet + signer for you.
# See the ATR repository for full Treasury setup.
```

### Using the SDK standalone (without the ATR)

You don't need the ATR to use the SDK. For a lightweight integration:

```python
from conway_sdk import LocalWallet, EIP3009Signer, Agent, PaymentIntent
from conway_sdk.config import SdkConfig
from conway_sdk.payment.models import PaymentRequirements

wallet = LocalWallet("0x<private_key>")
signer = EIP3009Signer(SdkConfig())

# Build your own lightweight adapter
def sign_payment(intent: PaymentIntent) -> dict:
    requirements = PaymentRequirements(
        amount=intent.amount,
        chain_id=84532,
        verifying_contract=intent.verifying_contract,
        pay_to=intent.destination,
    )
    auth = signer.sign(wallet, requirements)
    return {"nonce": auth.nonce, "headers": auth.to_payment_headers()}
```

---

## Building a Custom Wallet

Subclass `AbstractWallet` to integrate any signing backend — hardware security
modules, MPC signers, Ledger devices, or threshold signature schemes.

```python
from conway_sdk.wallet.base import AbstractWallet, ECDSASignature, EIP712Payload

class MyHSMWallet(AbstractWallet):
    """Example: wallet backed by an external HSM API."""

    def __init__(self, key_id: str, hsm_client):
        self._key_id = key_id
        self._hsm = hsm_client
        self._address = self._resolve_address()

    @property
    def address(self) -> str:
        return self._address

    def sign_typed_data(self, payload: EIP712Payload) -> ECDSASignature:
        """Synchronous signing — called by EIP3009Signer.sign()."""
        # Build the EIP-712 digest from payload
        from eth_account.structured_data.hashing import hash_domain, hash_message
        from eth_account._utils.structured_data.hashing import hash_of_encoded_struct
        from eth_utils import keccak

        # Compute the EIP-712 digest and send to HSM
        digest = self._compute_digest(payload)
        raw_sig = self._hsm.sign(self._key_id, digest)  # your HSM call
        return ECDSASignature(v=raw_sig.v, r=raw_sig.r, s=raw_sig.s)

    async def sign_typed_data_async(self, payload: EIP712Payload) -> ECDSASignature:
        """Async signing — called by EIP3009Signer.sign_async()."""
        import asyncio
        # For I/O-bound HSMs: use aiohttp or the HSM's async client
        # For CPU-bound operations: run_in_executor to avoid blocking the loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.sign_typed_data, payload)

    def _resolve_address(self) -> str:
        public_key = self._hsm.get_public_key(self._key_id)
        # ... derive checksummed EVM address from DER-encoded public key
        return derived_address

    def _compute_digest(self, payload: EIP712Payload) -> bytes:
        # Build EIP-712 hash — see eth_account for reference implementation
        ...
```

### Wallet interface contract

| Method | Required | Called by |
|---|---|---|
| `address: str` (property) | Yes | Everything that needs to know the sender |
| `sign_typed_data(payload)` | Yes | `EIP3009Signer.sign()` |
| `sign_typed_data_async(payload)` | Yes | `EIP3009Signer.sign_async()` |
| `sign_hash(message_hash)` | No | `KMSWallet` internal only |

---

## Module Reference

| Module | Key exports | Install extra |
|---|---|---|
| `conway_sdk` | `Agent`, `PaymentIntent`, `ExecutionAdapter`, `ExecutionResult`, `EIP3009Signer`, `LocalWallet`, `PaymentRequirements`, `PaymentAuthorization`, `RedisNonceCache`, `SdkConfig`, `parse_caip2_chain_id` | core |
| `conway_sdk.config` | `SdkConfig` | core |
| `conway_sdk.models` | `Agent`, `PaymentIntent` | core |
| `conway_sdk.execution_adapter` | `ExecutionAdapter`, `ExecutionResult` | core |
| `conway_sdk.payment.eip3009` | `EIP3009Signer` | core |
| `conway_sdk.payment.models` | `PaymentRequirements`, `PaymentAuthorization` | core |
| `conway_sdk.payment.caip2` | `parse_caip2_chain_id`, `build_caip2` | core |
| `conway_sdk.wallet.base` | `AbstractWallet`, `ECDSASignature`, `EIP712Payload`, `WalletProtocol` | core |
| `conway_sdk.wallet.local` | `LocalWallet` | core |
| `conway_sdk.wallet.redis_nonce_cache` | `RedisNonceCache` | `[redis]` |
| `conway_sdk.wallet.kms` | `KMSWallet`, `KMSWalletStub` | `[kms]` |
| `conway_sdk.exceptions` | `ConwayError`, `ConwaySigningError`, `ConwayRedisError`, … | core |

### `SdkConfig` fields

| Field | Default | Description |
|---|---|---|
| `payment_timeout_seconds` | `300` | Authorization window duration (sets `valid_before`) |
| `max_authorization_window_seconds` | `86400` | Reject server challenges requesting longer windows |

---

## Exception Hierarchy

```
ConwayError
├── ConwaySigningError          — EIP-712 signing failed
├── ConwayTypedDataError        — Malformed EIP-712 payload
├── ConwayRedisError            — Redis connection or operation failure
├── ConwayPaymentParseError     — Could not parse PAYMENT-REQUIRED header
├── ConwayNetworkMismatchError  — chain_id in challenge ≠ config chain_id
├── ConwayPolicyViolationError  — Payment amount exceeds configured limit
├── ConwayUntrustedRecipientError — pay_to not in trusted recipients list
├── ConwayIdempotencyError      — Nonce already used (replay attempt)
├── ConwayAuthError             — HTTP 401/403
├── ConwayNotFoundError         — HTTP 404
├── ConwayTimeoutError          — Network timeout
├── ConwayRetryExhaustedError   — Max retries reached
├── ConwayPaymentExpiredError   — Server: authorization expired
├── ConwayPaymentSignatureError — Server: signature rejected
├── ConwayPaymentRejectedError  — Server: payment rejected (other reason)
└── ConwayPaymentRetryError     — Network error after signing (nonce consumed)
```

```python
from conway_sdk.exceptions import (
    ConwayNetworkMismatchError,
    ConwayPolicyViolationError,
    ConwaySigningError,
)

try:
    auth = signer.sign(wallet, requirements)
except ConwayNetworkMismatchError:
    print("Chain ID in challenge does not match config")
except ConwayPolicyViolationError:
    print("Amount exceeds max_spend_atomic_units")
except ConwaySigningError as exc:
    print(f"Signing failed: {exc}")
```

---

## Security

### Wallet choice

| Environment | Wallet | Risk |
|---|---|---|
| Local dev / tests | `LocalWallet` or `KMSWalletStub` | Key in memory — acceptable for test keys |
| Staging / CI | `LocalWallet` with a dedicated test key | Rotate frequently |
| Production | `KMSWallet` | Key never leaves AWS KMS |

### Authorization window

The SDK computes `valid_before` as:

```
valid_before = now + payment_timeout_seconds - 5 seconds (safety buffer)
```

The 5-second buffer accounts for network transit time between signature
generation and facilitator receipt. Without it, an authorization generated
just before the window closes may arrive expired.

Set `max_authorization_window_seconds` to reject servers requesting unusually
long windows — a defence against servers attempting to obtain long-lived
authorizations for later misuse.

### Nonce lifecycle

- Every authorization carries a cryptographically random 32-byte nonce (`secrets.token_bytes(32)`)
- The USDC contract enforces single-use on-chain — a nonce cannot be replayed
- In multi-instance deployments, use `RedisNonceCache` to block replays before on-chain settlement
- `ConwayIdempotencyError` is raised if a nonce is reused within the same process

### Never log private keys

The SDK does not log key material, but ensure keys are not passed through
logging frameworks or exception traceback handlers.

### EIP-712 domain binding

The signing domain (`name`, `version`, `chainId`, `verifyingContract`) must
match the on-chain USDC contract exactly. A mismatch causes the facilitator
to reject the signature. The SDK constructs the domain from the `402` challenge
payload — never from hardcoded values.

---

## Links

- **PyPI**: [pypi.org/project/conway-sdk](https://pypi.org/project/conway-sdk/)
- **GitHub**: [github.com/dxpe147/conway-sdk](https://github.com/dxpe147/conway-sdk)
- **x402 Protocol**: [x402.org](https://x402.org)
- **EIP-3009**: [eips.ethereum.org/EIPS/eip-3009](https://eips.ethereum.org/EIPS/eip-3009)
- **EIP-712**: [eips.ethereum.org/EIPS/eip-712](https://eips.ethereum.org/EIPS/eip-712)

---

## License

MIT — see [LICENSE](LICENSE).
