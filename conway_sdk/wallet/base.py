"""
conway_sdk.wallet.base
========================
Abstract wallet interface.

AbstractWallet is an ABC so that:
  - Subclasses receive isinstance checks automatically.
  - Integration points can assert isinstance(wallet, AbstractWallet) for
    a clear error rather than a cryptic AttributeError.

WalletProtocol is also provided for callers who want structural
(duck-type) compatibility without subclassing.
"""

from __future__ import annotations

import abc
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

#: Full EIP-712 structured data payload.
#: See: https://eips.ethereum.org/EIPS/eip-712
EIP712Payload = dict[str, Any]


class ECDSASignature:
    """
    ECDSA signature broken into v / r / s components.

    Attributes
    ----------
    v : int
        Recovery parameter (27 or 28).
    r : bytes
        32-byte R component.
    s : bytes
        32-byte S component.
    signature_hex : str
        Full 65-byte signature as 0x-prefixed hex (r ++ s ++ v).
    """

    __slots__ = ("v", "r", "s", "signature_hex")

    def __init__(self, *, v: int, r: bytes, s: bytes) -> None:
        if len(r) != 32:  # noqa: PLR2004
            raise ValueError(f"r must be 32 bytes, got {len(r)}")
        if len(s) != 32:  # noqa: PLR2004
            raise ValueError(f"s must be 32 bytes, got {len(s)}")
        if v not in (27, 28):
            raise ValueError(f"v must be 27 or 28, got {v}")
        self.v = v
        self.r = r
        self.s = s
        raw = r + s + bytes([v])
        self.signature_hex = "0x" + raw.hex()

    @classmethod
    def from_eth_account_sig(cls, sig: Any) -> "ECDSASignature":
        """
        Construct from eth_account's sign_typed_data return value
        which has .v, .r, .s as ints.
        """
        r_bytes = sig.r.to_bytes(32, "big")
        s_bytes = sig.s.to_bytes(32, "big")
        return cls(v=sig.v, r=r_bytes, s=s_bytes)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ECDSASignature(v={self.v}, "
            f"r=0x{self.r.hex()[:8]}..., "
            f"s=0x{self.s.hex()[:8]}...)"
        )


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class AbstractWallet(abc.ABC):
    """
    Abstract wallet base class.

    All wallet implementations must provide:
      - A checksummed EVM address (``address`` property).
      - Synchronous EIP-712 signing (``sign_typed_data``).
      - Asynchronous EIP-712 signing (``sign_typed_data_async``).

    For hardware wallets or KMS signers, the async variant is essential
    because signing may involve network I/O (HSM API calls, etc.).
    """

    @property
    @abc.abstractmethod
    def address(self) -> str:
        """
        Checksummed EVM address (EIP-55) of this wallet.

        Example: ``"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"``
        """
        ...

    @abc.abstractmethod
    def sign_typed_data(self, payload: EIP712Payload) -> ECDSASignature:
        """
        Sign an EIP-712 typed data payload synchronously.

        Parameters
        ----------
        payload:
            Full EIP-712 structured data dict::

                {
                    "types": {"EIP712Domain": [...], "<PrimaryType>": [...]},
                    "primaryType": "<PrimaryType>",
                    "domain": {...},
                    "message": {...},
                }

        Returns
        -------
        ECDSASignature
            ECDSA signature components.

        Raises
        ------
        ConwayTypedDataError
            If the payload is malformed.
        ConwaySigningError
            If signing fails for any other reason.
        """
        ...

    @abc.abstractmethod
    async def sign_typed_data_async(self, payload: EIP712Payload) -> ECDSASignature:
        """
        Sign an EIP-712 typed data payload asynchronously.

        For CPU-bound wallets (LocalWallet), this runs signing in an executor
        to avoid blocking the event loop.  For I/O-bound wallets (HSM), this
        awaits the signer API.
        """
        ...

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(address={self.address!r})"


# ---------------------------------------------------------------------------
# Structural protocol (duck-typing without inheritance)
# ---------------------------------------------------------------------------


@runtime_checkable
class WalletProtocol(Protocol):
    """
    Structural protocol matching AbstractWallet's public interface.

    Use this for type annotations if you want to accept any wallet-shaped
    object without requiring inheritance from AbstractWallet.
    """

    @property
    def address(self) -> str: ...

    def sign_typed_data(self, payload: EIP712Payload) -> ECDSASignature: ...

    async def sign_typed_data_async(self, payload: EIP712Payload) -> ECDSASignature: ...
