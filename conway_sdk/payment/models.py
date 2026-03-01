"""
conway_sdk.payment.models
===========================
Pydantic v2 models for the x402 payment flow.

Conway x402 Protocol
---------------------
Conway uses the ``PAYMENT-REQUIRED`` HTTP header (or a JSON body fallback)
to communicate payment requirements on HTTP 402 responses.

Header format::

    PAYMENT-REQUIRED: <base64-encoded JSON>

Decoded JSON (Conway canonical)::

    {
        "amount":             1000000,
        "currency":           "USDC",
        "chain_id":           8453,
        "verifying_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "pay_to":             "0x<payment recipient>",
        "valid_before":       1735689600
    }

After signing, the proof is sent as::

    PAYMENT-SIGNATURE: <base64-encoded JSON of full authorization>
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Payment requirements (from 402 response)
# ---------------------------------------------------------------------------


class PaymentRequirements(BaseModel):
    """
    Parsed payment requirements from an HTTP 402 response.

    Field names match Conway's canonical PAYMENT-REQUIRED JSON schema.
    """

    amount: int = Field(..., ge=1, description="Payment amount in token base units.")
    currency: str = Field(default="USDC", description="Payment currency identifier.")
    chain_id: int = Field(..., description="EVM chain ID.")
    network: str | None = Field(
        default=None,
        description="CAIP-2 network identifier (e.g. 'eip155:84532'). Optional.",
    )
    verifying_contract: str = Field(
        ...,
        description="ERC-20 contract address (EIP-712 verifyingContract).",
        pattern=r"^0x[0-9a-fA-F]{40}$",
    )
    pay_to: str = Field(
        ...,
        description="Payment recipient (EVM address).",
        pattern=r"^0x[0-9a-fA-F]{40}$",
    )
    valid_before: int | None = Field(
        default=None,
        description="Unix timestamp: authorization expires after this time.",
    )
    nonce: str | None = Field(
        default=None,
        description="Server-provided bytes32 nonce (0x-prefixed hex, 66 chars).",
    )
    eip712_domain_name: str = Field(default="USD Coin")
    eip712_domain_version: str = Field(default="2")
    description: str | None = None
    resource_idempotency_key: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("verifying_contract", "pay_to", mode="before")
    @classmethod
    def checksum_address(cls, v: str) -> str:
        from eth_utils import to_checksum_address
        try:
            return to_checksum_address(v)
        except Exception as exc:
            raise ValueError(f"Invalid EVM address {v!r}: {exc}") from exc

    @field_validator("nonce")
    @classmethod
    def validate_nonce_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.startswith("0x") or len(v) != 66:  # noqa: PLR2004
            raise ValueError(
                f"nonce must be 0x-prefixed 64-char hex (bytes32), "
                f"got length {len(v)}: {v!r}"
            )
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        supported = {"USDC"}
        if v.upper() not in supported:
            raise ValueError(f"Unsupported currency {v!r}. Supported: {supported}")
        return v.upper()

    @classmethod
    def from_payment_required_header(cls, header_value: str) -> "PaymentRequirements":
        """
        Parse from the ``PAYMENT-REQUIRED`` HTTP header value.

        The header value is standard base64-encoded JSON.  Both padded and
        unpadded base64 are accepted; both standard (+/) and URL-safe (-_)
        alphabets are tried.

        Raises
        ------
        ValueError
            If the header is not valid base64 or the decoded JSON does not
            match the schema.
        """
        try:
            stripped = header_value.strip()
            padded = stripped + "=" * (-len(stripped) % 4)
            try:
                raw = base64.b64decode(padded)
            except Exception:
                raw = base64.urlsafe_b64decode(padded)
            body: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError(
                f"PAYMENT-REQUIRED header is not valid base64-encoded JSON: {exc}. "
                f"Header preview: {header_value[:80]!r}"
            ) from exc

        logger.debug(
            "Parsed PAYMENT-REQUIRED header: amount=%s chain_id=%s pay_to=%s",
            body.get("amount"),
            body.get("chain_id") or body.get("chainId"),
            body.get("pay_to") or body.get("payTo"),
        )
        return cls._from_dict(body)

    @classmethod
    def from_response_body(cls, body: dict[str, Any]) -> "PaymentRequirements":
        """
        Parse from a 402 JSON response body.

        Accepts Conway canonical (snake_case) and camelCase variants.
        """
        return cls._from_dict(body)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "PaymentRequirements":
        """Internal normalizer — maps field name variants to canonical names."""
        _known = {
            "amount", "currency",
            "chain_id", "chainId",
            "network", "x402Network",
            "verifying_contract", "verifyingContract", "token_contract",
            "pay_to", "payTo", "recipient",
            "valid_before", "validBefore",
            "nonce",
            "eip712_domain_name", "eip712DomainName",
            "eip712_domain_version", "eip712DomainVersion",
            "description", "resource_idempotency_key", "idempotencyKey",
        }
        network_str = data.get("network") or data.get("x402Network")
        raw_chain_id = data.get("chain_id") or data.get("chainId")
        if raw_chain_id is None and network_str is not None:
            from conway_sdk.payment.caip2 import parse_caip2_chain_id  # noqa: PLC0415
            try:
                raw_chain_id = parse_caip2_chain_id(network_str)
            except Exception:
                pass
        normalized: dict[str, Any] = {
            "amount": data.get("amount"),
            "currency": data.get("currency", "USDC"),
            "chain_id": raw_chain_id,
            "network": network_str,
            "verifying_contract": (
                data.get("verifying_contract")
                or data.get("verifyingContract")
                or data.get("token_contract")
            ),
            "pay_to": (
                data.get("pay_to")
                or data.get("payTo")
                or data.get("recipient")
            ),
            "valid_before": data.get("valid_before") or data.get("validBefore"),
            "nonce": data.get("nonce"),
            "eip712_domain_name": (
                data.get("eip712_domain_name")
                or data.get("eip712DomainName", "USD Coin")
            ),
            "eip712_domain_version": (
                data.get("eip712_domain_version")
                or data.get("eip712DomainVersion", "2")
            ),
            "description": data.get("description"),
            "resource_idempotency_key": (
                data.get("resource_idempotency_key") or data.get("idempotencyKey")
            ),
            "extra": {k: v for k, v in data.items() if k not in _known},
        }
        return cls.model_validate(normalized)


# ---------------------------------------------------------------------------
# Signed payment authorization
# ---------------------------------------------------------------------------


class PaymentAuthorization(BaseModel):
    """
    A fully signed EIP-3009 ``transferWithAuthorization`` ready for submission.

    Attributes
    ----------
    from_address : str
        Checksummed EVM address of the payer (wallet address).
    pay_to : str
        Checksummed EVM address of the payment recipient.
    amount : int
        Transfer amount in token base units (USDC: 1 USDC = 1_000_000).
    valid_after : int
        Unix timestamp: authorization is not valid before this time.
    valid_before : int
        Unix timestamp: authorization expires after this time.
    nonce : str
        0x-prefixed bytes32 hex nonce.
    chain_id : int
        EVM chain ID.
    verifying_contract : str
        ERC-20 token contract address used as EIP-712 verifyingContract.
    signature : str
        0x-prefixed 65-byte ECDSA signature: r[32] ++ s[32] ++ v[1].
    signed_at : int
        Unix timestamp when the authorization was constructed.
    currency : str
        Token identifier (currently always "USDC").
    """

    from_address: str
    pay_to: str
    amount: int = Field(..., ge=1)
    valid_after: int = Field(..., ge=0)
    valid_before: int
    nonce: str
    chain_id: int
    verifying_contract: str
    signature: str
    signed_at: int = Field(default_factory=lambda: int(time.time()))
    currency: str = "USDC"

    @model_validator(mode="after")
    def validate_timing(self) -> "PaymentAuthorization":
        if self.valid_before <= self.valid_after:
            raise ValueError(
                f"valid_before ({self.valid_before}) must be > "
                f"valid_after ({self.valid_after})."
            )
        return self

    @model_validator(mode="after")
    def validate_not_already_expired(self) -> "PaymentAuthorization":
        """Refuse to construct an already-expired authorization."""
        now = int(time.time())
        if self.valid_before <= now:
            raise ValueError(
                f"valid_before ({self.valid_before}) is already in the past "
                f"(now={now}).  This authorization would be immediately rejected."
            )
        return self

    def to_payment_signature_header(self) -> str:
        """
        Encode the full authorization as a base64 JSON string for the
        ``PAYMENT-SIGNATURE`` HTTP header.

        Integers are encoded as decimal strings to avoid JSON number precision
        loss.  Encoding is compact JSON → standard base64 (no URL-safe).
        """
        payload: dict[str, Any] = {
            "from":              self.from_address,
            "to":                self.pay_to,
            "value":             str(self.amount),
            "validAfter":        str(self.valid_after),
            "validBefore":       str(self.valid_before),
            "nonce":             self.nonce,
            "chainId":           self.chain_id,
            "verifyingContract": self.verifying_contract,
            "signature":         self.signature,
            "currency":          self.currency,
        }
        return base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")

    def to_payment_headers(self) -> dict[str, str]:
        """
        Build the HTTP headers to attach to the retried request.

        Primary header:
            ``PAYMENT-SIGNATURE`` — base64 JSON.

        Supplementary headers (for logging / server-side routing):
            ``X-Payment-From``, ``X-Payment-To``, etc.
        """
        return {
            "PAYMENT-SIGNATURE":          self.to_payment_signature_header(),
            "X-Payment-From":             self.from_address,
            "X-Payment-To":               self.pay_to,
            "X-Payment-Chain-Id":         str(self.chain_id),
            "X-Payment-Amount":           str(self.amount),
            "X-Payment-Currency":         self.currency,
            "X-Payment-Valid-Before":     str(self.valid_before),
            "X-Payment-Nonce":            self.nonce,
        }

    def to_dict(self) -> dict[str, Any]:
        """Plain dict for logging or JSON body submission."""
        return {
            "from":              self.from_address,
            "to":                self.pay_to,
            "value":             str(self.amount),
            "validAfter":        str(self.valid_after),
            "validBefore":       str(self.valid_before),
            "nonce":             self.nonce,
            "chainId":           self.chain_id,
            "verifyingContract": self.verifying_contract,
            "currency":          self.currency,
        }
