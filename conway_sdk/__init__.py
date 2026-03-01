"""
conway_sdk
===========
Conway SDK — dependency-light surface for building payment-enabled agents.

The SDK provides typed models, wallet integrations, and EIP-3009 signing
primitives.  It does not include runtime, persistence, or database logic.

Modules
-------
conway_sdk.models
    ``Agent`` and ``PaymentIntent`` — stdlib-only typed models.
conway_sdk.execution_adapter
    ``ExecutionAdapter`` ABC and ``ExecutionResult`` dataclass.
conway_sdk.config
    ``SdkConfig`` — payment timeout and window configuration.
conway_sdk.wallet
    ``AbstractWallet``, ``LocalWallet``, ``RedisNonceCache``.
    Optional: ``KMSWallet``, ``KMSWalletStub`` (requires ``conway-sdk[kms]``).
conway_sdk.payment
    ``EIP3009Signer``, ``PaymentRequirements``, ``PaymentAuthorization``,
    CAIP-2 utilities.
conway_sdk.exceptions
    Exception hierarchy rooted at ``ConwayError``.

Quick start
-----------
::

    from conway_sdk import Agent, PaymentIntent, LocalWallet, EIP3009Signer
    from conway_sdk.config import SdkConfig
    from conway_sdk.payment.models import PaymentRequirements
    from uuid import uuid4

    wallet = LocalWallet("0x<private_key>")
    signer = EIP3009Signer(SdkConfig())

    requirements = PaymentRequirements(
        amount=1_000_000,          # 1 USDC
        chain_id=84532,            # Base Sepolia
        verifying_contract="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        pay_to="0x<recipient>",
    )

    authorization = signer.sign(wallet, requirements)
    headers = authorization.to_payment_headers()
"""

from conway_sdk.config import SdkConfig
from conway_sdk.execution_adapter import ExecutionAdapter, ExecutionResult
from conway_sdk.models import Agent, PaymentIntent
from conway_sdk.payment import EIP3009Signer, parse_caip2_chain_id
from conway_sdk.payment.models import PaymentAuthorization, PaymentRequirements
from conway_sdk.wallet import AbstractWallet, LocalWallet, RedisNonceCache

__version__ = "1.0.0"

__all__ = [
    # Models
    "Agent",
    "PaymentIntent",
    # Execution adapter
    "ExecutionAdapter",
    "ExecutionResult",
    # Config
    "SdkConfig",
    # Payment
    "EIP3009Signer",
    "PaymentRequirements",
    "PaymentAuthorization",
    "parse_caip2_chain_id",
    # Wallet
    "AbstractWallet",
    "LocalWallet",
    "RedisNonceCache",
]
