
# Conway SDK

![Status](https://img.shields.io/badge/status-stable-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

Conway SDK is a Python library for building payment-enabled agents using the
[x402](https://x402.org) protocol with EIP-3009 delegated USDC transfers.
It provides typed models, EVM wallet integrations, EIP-712 signing primitives,
and distributed nonce deduplication — without bundling runtime or persistence
logic.

---

## Installation

```bash
pip install conway-sdk
```

### Optional extras

```bash
# Redis nonce deduplication (multi-instance deployments)
pip install "conway-sdk[redis]"

# AWS KMS wallet (production signing)
pip install "conway-sdk[kms]"

# Development tools (pytest, ruff, mypy)
pip install "conway-sdk[dev]"
```

---

## Python version

Requires **Python 3.10 or later**.

---

## Core features

| Feature | Module |
|---------|--------|
| Typed agent and payment intent models | `conway_sdk.models` |
| EIP-3009 / EIP-712 signing | `conway_sdk.payment.eip3009` |
| Abstract wallet interface + local wallet | `conway_sdk.wallet` |
| AWS KMS wallet (optional) | `conway_sdk.wallet.kms` |
| Distributed Redis nonce cache (optional) | `conway_sdk.wallet.redis_nonce_cache` |
| CAIP-2 chain identifier utilities | `conway_sdk.payment.caip2` |
| Payment requirements / authorization models | `conway_sdk.payment.models` |
| Execution adapter interface | `conway_sdk.execution_adapter` |
| Structured exception hierarchy | `conway_sdk.exceptions` |

---

## Usage

### Signing a payment

```python
from conway_sdk import LocalWallet, EIP3009Signer
from conway_sdk.config import SdkConfig
from conway_sdk.payment.models import PaymentRequirements

# Load wallet from private key (use a secrets manager in production)
wallet = LocalWallet("0x<private_key_hex>")

# Configure the signer
config = SdkConfig(payment_timeout_seconds=300)
signer = EIP3009Signer(config)

# Build payment requirements (typically parsed from an HTTP 402 response)
requirements = PaymentRequirements(
    amount=1_000_000,          # 1 USDC (6 decimal places)
    chain_id=8453,             # Base Mainnet
    verifying_contract="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    pay_to="0x<recipient_address>",
)

# Sign synchronously
authorization = signer.sign(wallet, requirements)

# Attach the resulting headers to your retried HTTP request
headers = authorization.to_payment_headers()
```

### Parsing a 402 response header

```python
from conway_sdk.payment.models import PaymentRequirements

header = response.headers["PAYMENT-REQUIRED"]
requirements = PaymentRequirements.from_payment_required_header(header)
```

### Async signing

```python
authorization = await signer.sign_async(wallet, requirements)
```

### Redis nonce deduplication (multi-instance)

```python
import redis
from conway_sdk.wallet.redis_nonce_cache import RedisNonceCache

client = redis.Redis.from_url("redis://localhost:6379/0")
cache = RedisNonceCache(client)

is_fresh = cache.record(authorization.nonce)
if not is_fresh:
    raise RuntimeError("Duplicate nonce detected — refusing to submit.")
```

### CAIP-2 utilities

```python
from conway_sdk.payment.caip2 import parse_caip2_chain_id, build_caip2

chain_id = parse_caip2_chain_id("eip155:8453")  # → 8453
caip2    = build_caip2(8453)                     # → "eip155:8453"
```

### Implementing a custom wallet

```python
from conway_sdk.wallet.base import AbstractWallet, ECDSASignature, EIP712Payload

class MyHSMWallet(AbstractWallet):
    @property
    def address(self) -> str:
        return "0x<address>"

    def sign_typed_data(self, payload: EIP712Payload) -> ECDSASignature:
        # Call your HSM or external signer here
        ...

    async def sign_typed_data_async(self, payload: EIP712Payload) -> ECDSASignature:
        # Async variant for I/O-bound signers
        ...
```

---

## Security notes

- **LocalWallet** holds the private key in process memory as raw bytes. Use it
  only with short-lived keys loaded from a secrets manager. For production
  deployments handling real funds, use **KMSWallet** or a hardware security
  module.

- **Never log private keys.** The SDK does not log key material, but callers
  must ensure keys are not passed through logging frameworks.

- **Nonce uniqueness** is enforced per contract by the EIP-3009 standard. In
  multi-instance deployments, use `RedisNonceCache` to prevent concurrent
  instances from producing authorizations with conflicting nonces.

- **EIP-712 domain parameters** (name, version, chainId, verifyingContract)
  must match the on-chain contract exactly. A mismatch causes the server to
  reject the signature.

- **validBefore window**: the SDK enforces a configurable maximum
  (`SdkConfig.max_authorization_window_seconds`, default 24 hours). Servers
  requesting longer windows are refused — a defence against malicious servers
  attempting to obtain long-lived authorizations.

---

## Scope

This SDK provides signing primitives and typed models only.


License

MIT — see [LICENSE](LICENSE).
