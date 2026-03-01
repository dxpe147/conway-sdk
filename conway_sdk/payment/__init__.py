"""
conway_sdk.payment
===================
Payment utilities for the Conway SDK.

Exports
-------
EIP3009Signer
    Orchestrates EIP-3009 transferWithAuthorization signing.
PaymentRequirements
    Parsed payment requirements from an HTTP 402 response.
PaymentAuthorization
    A fully signed EIP-3009 authorization ready for submission.
parse_caip2_chain_id
    Parse a CAIP-2 network identifier to an integer chain ID.
parse_caip2_asset
    Parse a CAIP-19 ERC-20 asset identifier.
build_caip2
    Build a CAIP-2 string from an integer chain ID.
CAIP2ParseError
    Raised when a CAIP-2/CAIP-19 string is malformed.
generate_nonce
    Generate a cryptographically random 32-byte nonce (0x-prefixed hex).
build_transfer_with_authorization_payload
    Build a raw EIP-712 payload for transferWithAuthorization.
"""

from conway_sdk.payment.caip2 import (
    CAIP2ParseError,
    EVM_NAMESPACE,
    build_caip2,
    parse_caip2_asset,
    parse_caip2_chain_id,
)
from conway_sdk.payment.eip3009 import (
    EIP3009Signer,
    PRIMARY_TYPE,
    TRANSFER_WITH_AUTHORIZATION_TYPES,
    build_transfer_with_authorization_payload,
    generate_nonce,
)
from conway_sdk.payment.models import PaymentAuthorization, PaymentRequirements

__all__ = [
    "EIP3009Signer",
    "PaymentRequirements",
    "PaymentAuthorization",
    "parse_caip2_chain_id",
    "parse_caip2_asset",
    "build_caip2",
    "CAIP2ParseError",
    "EVM_NAMESPACE",
    "generate_nonce",
    "build_transfer_with_authorization_payload",
    "PRIMARY_TYPE",
    "TRANSFER_WITH_AUTHORIZATION_TYPES",
]
