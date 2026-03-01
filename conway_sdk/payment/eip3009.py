"""
conway_sdk.payment.eip3009
============================
EIP-3009 transferWithAuthorization typed-data builder and signer.

EIP-712 digest:
    keccak256("\\x19\\x01" || domainSeparator || hashStruct)

    domainSeparator = keccak256(encode(EIP712Domain {
        name:              "USD Coin",
        version:           "2",
        chainId:           <chain_id>,
        verifyingContract: <usdc_contract>,
    }))

    hashStruct = keccak256(encode(TransferWithAuthorization {
        from, to, value, validAfter, validBefore, nonce
    }))

Timing:
    validAfter  = 0           (immediately usable)
    validBefore = now + config.payment_timeout_seconds - 5s (safety buffer)

Security:
    - Server-provided validBefore is capped at max_authorization_window_seconds.
    - Nonce: 32-byte CSPRNG (secrets.token_bytes).
    - Nonce field sent as bytes32 (Python bytes) to eth-account.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from conway_sdk.config import SdkConfig
from conway_sdk.exceptions import ConwayTypedDataError
from conway_sdk.payment.models import PaymentAuthorization, PaymentRequirements
from conway_sdk.wallet.base import AbstractWallet, EIP712Payload

logger = logging.getLogger(__name__)

#: Seconds subtracted from validBefore to account for network transit time.
_SAFETY_BUFFER_SECONDS: int = 5

# ---------------------------------------------------------------------------
# EIP-712 type definitions — MUST match USDC v2 on-chain struct exactly
# ---------------------------------------------------------------------------

EIP712_DOMAIN_TYPES: list[dict[str, str]] = [
    {"name": "name",              "type": "string"},
    {"name": "version",           "type": "string"},
    {"name": "chainId",           "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]

TRANSFER_WITH_AUTHORIZATION_TYPES: list[dict[str, str]] = [
    {"name": "from",        "type": "address"},
    {"name": "to",          "type": "address"},
    {"name": "value",       "type": "uint256"},
    {"name": "validAfter",  "type": "uint256"},
    {"name": "validBefore", "type": "uint256"},
    {"name": "nonce",       "type": "bytes32"},
]

PRIMARY_TYPE = "TransferWithAuthorization"


# ---------------------------------------------------------------------------
# Nonce generation
# ---------------------------------------------------------------------------


def generate_nonce() -> str:
    """
    Generate a cryptographically random 32-byte nonce as 0x-prefixed hex.

    Uses ``secrets.token_bytes`` (OS CSPRNG).  Returns a 66-character string.
    """
    return "0x" + secrets.token_bytes(32).hex()


# ---------------------------------------------------------------------------
# EIP-712 payload builder
# ---------------------------------------------------------------------------


def build_transfer_with_authorization_payload(
    *,
    from_address: str,
    to_address: str,
    value: int,
    valid_after: int,
    valid_before: int,
    nonce: str,
    chain_id: int,
    verifying_contract: str,
    domain_name: str,
    domain_version: str,
) -> EIP712Payload:
    """
    Construct the EIP-712 structured data payload for transferWithAuthorization.

    The ``nonce`` field is converted from hex string to Python bytes because
    eth-account requires bytes32 fields as bytes objects, not hex strings.
    """
    if not isinstance(nonce, str) or not nonce.startswith("0x") or len(nonce) != 66:  # noqa: PLR2004
        raise ConwayTypedDataError(
            f"nonce must be 0x-prefixed 64-char hex (bytes32), got: {nonce!r}",
            primary_type=PRIMARY_TYPE,
        )
    nonce_bytes = bytes.fromhex(nonce[2:])

    return {
        "types": {
            "EIP712Domain": EIP712_DOMAIN_TYPES,
            PRIMARY_TYPE: TRANSFER_WITH_AUTHORIZATION_TYPES,
        },
        "primaryType": PRIMARY_TYPE,
        "domain": {
            "name":              domain_name,
            "version":           domain_version,
            "chainId":           chain_id,
            "verifyingContract": verifying_contract,
        },
        "message": {
            "from":        from_address,
            "to":          to_address,
            "value":       value,
            "validAfter":  valid_after,
            "validBefore": valid_before,
            "nonce":       nonce_bytes,
        },
    }


# ---------------------------------------------------------------------------
# EIP3009Signer
# ---------------------------------------------------------------------------


class EIP3009Signer:
    """
    Orchestrates EIP-3009 transferWithAuthorization signing.

    Steps:
      1. Compute ``validAfter = 0``, ``validBefore = now + timeout - 5s``.
      2. Enforce ``max_authorization_window_seconds`` (security guard against
         malicious servers requesting excessively long authorization windows).
      3. Resolve nonce: ``override`` > ``requirements.nonce`` > CSPRNG.
      4. Build EIP-712 payload.
      5. Sign via wallet.
      6. Return ``PaymentAuthorization``.

    Parameters
    ----------
    config:
        ``SdkConfig`` controlling timeout and window bounds.
        Defaults to ``SdkConfig()`` (600s timeout, 24h max window).

    Example
    -------
    ::

        from conway_sdk.config import SdkConfig
        from conway_sdk.payment.eip3009 import EIP3009Signer
        from conway_sdk.payment.models import PaymentRequirements
        from conway_sdk.wallet.local import LocalWallet

        config = SdkConfig(payment_timeout_seconds=300)
        signer = EIP3009Signer(config)
        wallet = LocalWallet("0x...")

        requirements = PaymentRequirements(
            amount=1_000_000,
            chain_id=84532,
            verifying_contract="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            pay_to="0xRecipientAddress...",
        )
        authorization = signer.sign(wallet, requirements)
    """

    def __init__(self, config: SdkConfig | None = None) -> None:
        self._config = config or SdkConfig()

    def sign(
        self,
        wallet: AbstractWallet,
        requirements: PaymentRequirements,
        *,
        nonce: str | None = None,
    ) -> PaymentAuthorization:
        """
        Sign synchronously.

        Parameters
        ----------
        wallet:
            Wallet to sign with.
        requirements:
            Payment requirements parsed from the 402 response.
        nonce:
            Optional nonce override (bypasses CSPRNG and server nonce).

        Returns
        -------
        PaymentAuthorization
        """
        payload, meta = self._build_payload(wallet, requirements, nonce)
        sig = wallet.sign_typed_data(payload)
        return self._assemble(sig, meta, requirements, wallet.address)

    async def sign_async(
        self,
        wallet: AbstractWallet,
        requirements: PaymentRequirements,
        *,
        nonce: str | None = None,
    ) -> PaymentAuthorization:
        """
        Sign asynchronously.

        Awaits ``wallet.sign_typed_data_async`` — suitable for I/O-bound
        wallets (HSM, KMS) or when you want to avoid blocking an event loop.
        """
        payload, meta = self._build_payload(wallet, requirements, nonce)
        sig = await wallet.sign_typed_data_async(payload)
        return self._assemble(sig, meta, requirements, wallet.address)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        wallet: AbstractWallet,
        requirements: PaymentRequirements,
        override_nonce: str | None,
    ) -> tuple[EIP712Payload, dict[str, Any]]:
        now = int(time.time())
        valid_after: int = 0

        if requirements.valid_before is not None:
            server_window = requirements.valid_before - now
            max_window = self._config.max_authorization_window_seconds
            if server_window > max_window:
                raise ConwayTypedDataError(
                    f"Server validBefore ({requirements.valid_before}) is "
                    f"{server_window}s from now, exceeding "
                    f"max_authorization_window_seconds={max_window}. "
                    "Refusing to sign — possible malicious server.",
                    primary_type=PRIMARY_TYPE,
                    domain={
                        "chainId":           requirements.chain_id,
                        "verifyingContract": requirements.verifying_contract,
                    },
                )
            valid_before = requirements.valid_before
        else:
            valid_before = (
                now + self._config.payment_timeout_seconds - _SAFETY_BUFFER_SECONDS
            )

        if valid_before <= now:
            raise ConwayTypedDataError(
                f"valid_before ({valid_before}) is in the past (now={now}).",
                primary_type=PRIMARY_TYPE,
            )

        effective_nonce = override_nonce or requirements.nonce or generate_nonce()

        payload = build_transfer_with_authorization_payload(
            from_address=wallet.address,
            to_address=requirements.pay_to,
            value=requirements.amount,
            valid_after=valid_after,
            valid_before=valid_before,
            nonce=effective_nonce,
            chain_id=requirements.chain_id,
            verifying_contract=requirements.verifying_contract,
            domain_name=requirements.eip712_domain_name,
            domain_version=requirements.eip712_domain_version,
        )

        logger.debug(
            "EIP3009 payload: chain=%d contract=%s amount=%d "
            "valid_before=%d nonce=%s...",
            requirements.chain_id,
            requirements.verifying_contract,
            requirements.amount,
            valid_before,
            effective_nonce[:12],
        )

        meta: dict[str, Any] = {
            "nonce":        effective_nonce,
            "valid_after":  valid_after,
            "valid_before": valid_before,
        }
        return payload, meta

    @staticmethod
    def _assemble(
        sig: Any,
        meta: dict[str, Any],
        requirements: PaymentRequirements,
        signer_address: str,
    ) -> PaymentAuthorization:
        return PaymentAuthorization(
            from_address=signer_address,
            pay_to=requirements.pay_to,
            amount=requirements.amount,
            valid_after=meta["valid_after"],
            valid_before=meta["valid_before"],
            nonce=meta["nonce"],
            chain_id=requirements.chain_id,
            verifying_contract=requirements.verifying_contract,
            signature=sig.signature_hex,
            currency=requirements.currency,
        )
