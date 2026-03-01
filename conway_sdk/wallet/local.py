"""
conway_sdk.wallet.local
=========================
LocalWallet — in-process wallet backed by eth-account.

Security considerations
-----------------------
- The private key is stored as a Python ``bytes`` object in memory.
  It is NOT encrypted at rest. This wallet is appropriate for:
    * Server-side automation with short-lived keys loaded from a secrets manager.
    * Integration tests with throwaway keys.
  It is NOT appropriate for:
    * Mobile / browser wallets.
    * Any environment where process memory can be dumped by an attacker.

- The key is loaded at construction time and validated (length + format).
  Fail-fast is safer than fail-at-signing-time.

- sign_typed_data_async runs the synchronous signer in
  asyncio.get_event_loop().run_in_executor(None, ...) to avoid blocking
  the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount

from conway_sdk.exceptions import ConwayInvalidPrivateKeyError, ConwayTypedDataError
from conway_sdk.wallet.base import AbstractWallet, ECDSASignature, EIP712Payload

logger = logging.getLogger(__name__)


class LocalWallet(AbstractWallet):
    """
    In-process wallet using eth-account for EIP-712 signing.

    Parameters
    ----------
    private_key:
        Raw private key as hex string (0x-prefixed or bare 64 hex chars)
        or as raw 32 bytes.

    Example
    -------
    ::

        wallet = LocalWallet(
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        )
        print(wallet.address)
        # '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'
    """

    Account.enable_unaudited_hdwallet_features()  # noqa: S106

    def __init__(self, private_key: str | bytes) -> None:
        self._account: LocalAccount = self._load_account(private_key)
        logger.debug("LocalWallet initialized for address %s", self._account.address)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_account(private_key: str | bytes) -> LocalAccount:
        """Validate and load a private key into an eth-account LocalAccount."""
        try:
            if isinstance(private_key, bytes):
                if len(private_key) != 32:  # noqa: PLR2004
                    raise ConwayInvalidPrivateKeyError(
                        f"Private key bytes must be exactly 32 bytes, "
                        f"got {len(private_key)}."
                    )
                key_hex = "0x" + private_key.hex()
            else:
                key_hex = private_key.strip()
                if not key_hex.startswith("0x"):
                    key_hex = "0x" + key_hex
                if len(key_hex) != 66:  # 0x + 64 hex chars  # noqa: PLR2004
                    raise ConwayInvalidPrivateKeyError(
                        f"Private key hex must be 64 characters (plus 0x prefix), "
                        f"got {len(key_hex) - 2} characters."
                    )
            return Account.from_key(key_hex)
        except ConwayInvalidPrivateKeyError:
            raise
        except Exception as exc:
            raise ConwayInvalidPrivateKeyError(
                f"Failed to load private key: {exc}"
            ) from exc

    @staticmethod
    def _build_signable_data(payload: EIP712Payload) -> dict[str, Any]:
        """
        Validate the payload shape and return it in the form eth-account expects.

        Required keys: ``types``, ``primaryType``, ``domain``, ``message``.
        ``types`` must include ``"EIP712Domain"``.
        """
        required_keys = {"types", "primaryType", "domain", "message"}
        missing = required_keys - payload.keys()
        if missing:
            raise ConwayTypedDataError(
                f"EIP-712 payload missing required keys: {missing}",
                primary_type=payload.get("primaryType"),
                domain=payload.get("domain"),
            )
        if "EIP712Domain" not in payload["types"]:
            raise ConwayTypedDataError(
                "EIP-712 payload.types must include 'EIP712Domain' key.",
                primary_type=payload.get("primaryType"),
                domain=payload.get("domain"),
            )
        return payload

    # ------------------------------------------------------------------
    # AbstractWallet implementation
    # ------------------------------------------------------------------

    @property
    def address(self) -> str:
        return self._account.address  # already checksummed by eth-account

    def sign_typed_data(self, payload: EIP712Payload) -> ECDSASignature:
        """
        Sign EIP-712 typed data synchronously.

        eth-account computes:
          1. domainSeparator = keccak256(encode(EIP712Domain))
          2. hashStruct = keccak256(encode(primaryType, message))
          3. digest = keccak256("\\x19\\x01" + domainSeparator + hashStruct)
          4. ECDSA sign(digest, private_key)
        """
        data = self._build_signable_data(payload)
        try:
            signed = self._account.sign_typed_data(
                domain_data=data["domain"],
                message_types={
                    k: v for k, v in data["types"].items() if k != "EIP712Domain"
                },
                message_data=data["message"],
            )
        except ConwayTypedDataError:
            raise
        except Exception as exc:
            raise ConwayTypedDataError(
                f"EIP-712 signing failed: {exc}",
                primary_type=payload.get("primaryType"),
                domain=payload.get("domain"),
            ) from exc

        sig = ECDSASignature.from_eth_account_sig(signed)
        logger.debug(
            "Signed typed data: primaryType=%s address=%s sig=%s",
            payload.get("primaryType"),
            self.address,
            sig.signature_hex[:12] + "...",
        )
        return sig

    async def sign_typed_data_async(self, payload: EIP712Payload) -> ECDSASignature:
        """
        Sign EIP-712 typed data asynchronously.

        Runs the synchronous signer in the default executor (ThreadPoolExecutor)
        to avoid blocking the event loop during CPU-bound cryptographic work.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self.sign_typed_data, payload))

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_mnemonic(cls, mnemonic: str, account_index: int = 0) -> "LocalWallet":
        """
        Derive a LocalWallet from a BIP-39 mnemonic.

        Parameters
        ----------
        mnemonic:
            12 or 24 word BIP-39 mnemonic phrase.
        account_index:
            BIP-44 account index (default 0 → m/44'/60'/0'/0/0).

        Warning
        -------
        Mnemonic phrases are extremely sensitive. Ensure they are loaded
        from a secrets manager and never logged or stored as plaintext.
        """
        try:
            acct, _ = Account.from_mnemonic(
                mnemonic,
                account_path=f"m/44'/60'/0'/0/{account_index}",
            )
        except Exception as exc:
            raise ConwayInvalidPrivateKeyError(
                f"Failed to derive account from mnemonic: {exc}"
            ) from exc
        return cls(acct.key)
