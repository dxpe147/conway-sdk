"""
conway_sdk.wallet
==================
Wallet interfaces and implementations for the Conway SDK.

Exports
-------
AbstractWallet
    Abstract base class all wallet implementations must satisfy.
ECDSASignature
    ECDSA signature container (v, r, s, signature_hex).
WalletProtocol
    Structural protocol for duck-typed wallet acceptance.
LocalWallet
    In-process wallet backed by eth-account.  Development and testing only.
RedisNonceCache
    Distributed nonce deduplication cache backed by Redis.

Optional (requires extras)
--------------------------
KMSWallet
    AWS KMS-backed wallet (requires ``pip install "conway-sdk[kms]"``).
KMSWalletStub
    Test stub for KMSWallet (requires ``pip install "conway-sdk[kms]"``).
"""

from conway_sdk.wallet.base import AbstractWallet, ECDSASignature, EIP712Payload, WalletProtocol
from conway_sdk.wallet.local import LocalWallet
from conway_sdk.wallet.redis_nonce_cache import RedisNonceCache

__all__ = [
    "AbstractWallet",
    "ECDSASignature",
    "EIP712Payload",
    "WalletProtocol",
    "LocalWallet",
    "RedisNonceCache",
]
