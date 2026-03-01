"""
conway_sdk.config
==================
SDK configuration for payment signing.

SdkConfig holds the timing parameters used by EIP3009Signer when
constructing authorization windows.  All values have safe defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SdkConfig:
    """
    Configuration for the Conway SDK payment signer.

    Parameters
    ----------
    payment_timeout_seconds:
        Duration in seconds for which a signed EIP-3009 authorization is
        considered valid.  The signer sets ``validBefore = now +
        payment_timeout_seconds - 5`` (5-second safety buffer).
        Default: 600 (10 minutes).
    max_authorization_window_seconds:
        Maximum server-supplied ``validBefore`` window the signer will
        accept.  If a 402 server proposes a window longer than this value,
        the signer refuses — a defence against malicious servers trying to
        obtain long-lived authorizations.
        Default: 86400 (24 hours).

    Example
    -------
    ::

        from conway_sdk.config import SdkConfig
        config = SdkConfig(payment_timeout_seconds=300)
    """

    payment_timeout_seconds: int = field(default=600)
    max_authorization_window_seconds: int = field(default=86_400)

    def __post_init__(self) -> None:
        if self.payment_timeout_seconds <= 0:
            raise ValueError(
                f"payment_timeout_seconds must be positive, "
                f"got {self.payment_timeout_seconds}"
            )
        if self.max_authorization_window_seconds <= 0:
            raise ValueError(
                f"max_authorization_window_seconds must be positive, "
                f"got {self.max_authorization_window_seconds}"
            )
