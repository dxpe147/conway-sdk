"""
conway_sdk.exceptions
=====================
Exception hierarchy for the Conway SDK.

Design principles:
  - Every public exception inherits from ConwayError.
  - HTTP errors carry raw response metadata for inspection.
  - Payment exceptions carry structured context so handlers can branch on
    fields rather than parsing strings.
  - Signing exceptions carry EIP-712 context for auditability.
  - All exceptions are picklable (no unpicklable locals captured).
  - Exception names are unambiguous: "what went wrong" not "which layer".
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class ConwayError(Exception):
    """Base class for all Conway SDK errors."""

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, Any] = context or {}

    def __repr__(self) -> str:  # pragma: no cover
        ctx = f", context={self.context!r}" if self.context else ""
        return f"{type(self).__name__}({str(self)!r}{ctx})"


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


class ConwayConfigError(ConwayError):
    """Raised when SDK configuration is invalid or missing required fields."""


# ---------------------------------------------------------------------------
# HTTP / transport errors
# ---------------------------------------------------------------------------


class ConwayHTTPError(ConwayError):
    """
    Raised for non-2xx responses not handled by payment logic.

    Attributes
    ----------
    status_code : int
        HTTP status code returned by the server.
    response_body : bytes
        Raw response body bytes (truncated to 8 KB).
    headers : dict[str, str]
        Response headers as plain dict.
    request_id : str | None
        Value of X-Request-ID / X-Conway-Request-ID if present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: bytes = b"",
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.status_code = status_code
        self.response_body = response_body
        self.headers: dict[str, str] = headers or {}
        self.request_id = request_id

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"{type(self).__name__}(status_code={self.status_code}, "
            f"message={str(self)!r}, request_id={self.request_id!r})"
        )


class ConwayTimeoutError(ConwayHTTPError):
    """Raised when an HTTP request times out (connect or read)."""


class ConwayRateLimitError(ConwayHTTPError):
    """
    Raised on HTTP 429.

    Attributes
    ----------
    retry_after : float | None
        Seconds to wait before retrying, from Retry-After header.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, status_code=status_code, **kwargs)
        self.retry_after = retry_after


class ConwayServerError(ConwayHTTPError):
    """Raised on HTTP 5xx responses."""


class ConwayNotFoundError(ConwayHTTPError):
    """Raised on HTTP 404."""


class ConwayAuthError(ConwayHTTPError):
    """Raised on HTTP 401 / 403."""


# ---------------------------------------------------------------------------
# Payment errors (x402 flow)
# ---------------------------------------------------------------------------


class ConwayPaymentError(ConwayError):
    """Base for all payment-flow errors."""


class ConwayPolicyViolationError(ConwayPaymentError):
    """
    Raised when a payment amount exceeds the configured spend threshold.

    Attributes
    ----------
    amount : int
        The payment amount requested.
    limit : int
        The configured maximum.
    """

    def __init__(
        self,
        message: str,
        *,
        amount: int,
        limit: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.amount = amount
        self.limit = limit


class ConwayNetworkMismatchError(ConwayPaymentError):
    """
    Raised when the chain_id in a 402 challenge does not match the
    configured chain_id.

    Attributes
    ----------
    server_chain_id : int
        The chain_id supplied by the server in the 402 challenge.
    config_chain_id : int
        The chain_id in the SDK configuration.
    """

    def __init__(
        self,
        message: str,
        *,
        server_chain_id: int,
        config_chain_id: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.server_chain_id = server_chain_id
        self.config_chain_id = config_chain_id


class Conway402Error(ConwayPaymentError):
    """
    Raised when an HTTP 402 response cannot be automatically resolved.

    Attributes
    ----------
    payment_requirements : dict[str, Any]
        Parsed requirements from the 402, or {} if parsing failed.
    response_body : bytes
        Raw 402 response body.
    """

    def __init__(
        self,
        message: str,
        *,
        payment_requirements: dict[str, Any] | None = None,
        response_body: bytes = b"",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.payment_requirements: dict[str, Any] = payment_requirements or {}
        self.response_body = response_body


class ConwayPaymentParseError(ConwayPaymentError):
    """Raised when x402 payment requirements cannot be parsed."""


class ConwayPaymentRejectedError(ConwayPaymentError):
    """
    Raised when the server explicitly rejects a submitted payment.

    Attributes
    ----------
    rejection_reason : str | None
    nonce : str | None
    amount : int | None
    """

    def __init__(
        self,
        message: str,
        *,
        rejection_reason: str | None = None,
        nonce: str | None = None,
        amount: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.rejection_reason = rejection_reason
        self.nonce = nonce
        self.amount = amount


class ConwayPaymentExpiredError(ConwayPaymentError):
    """
    Raised when the server rejects a payment because the authorization expired.

    Attributes
    ----------
    valid_before : int | None
    nonce : str | None
    """

    def __init__(
        self,
        message: str,
        *,
        valid_before: int | None = None,
        nonce: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.valid_before = valid_before
        self.nonce = nonce


class ConwayPaymentRetryError(ConwayPaymentError):
    """
    Raised when the payment retry request fails with a non-402 error.

    CRITICAL: This error is AMBIGUOUS regarding payment status. The
    authorization was signed and sent. Do NOT resubmit without verifying
    the nonce state on-chain.

    Attributes
    ----------
    authorization_nonce : str | None
    underlying : Exception | None
    """

    def __init__(
        self,
        message: str,
        *,
        authorization_nonce: str | None = None,
        underlying: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.authorization_nonce = authorization_nonce
        self.underlying = underlying


class ConwayIdempotencyError(ConwayPaymentError):
    """Raised when the client-side nonce cache detects a nonce reuse."""


class ConwayUntrustedRecipientError(ConwayPaymentError):
    """
    Raised when the pay_to address is not in the trusted recipients allowlist.

    Attributes
    ----------
    pay_to : str
    trusted : list[str]
    """

    def __init__(
        self,
        message: str,
        *,
        pay_to: str,
        trusted: list[str],
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.pay_to = pay_to
        self.trusted = trusted


# ---------------------------------------------------------------------------
# Signing / wallet errors
# ---------------------------------------------------------------------------


class ConwaySigningError(ConwayError):
    """Base for wallet and cryptographic signing errors."""


class ConwayWalletNotConfiguredError(ConwaySigningError):
    """Raised when a wallet operation is attempted but no wallet is attached."""


class ConwayInvalidPrivateKeyError(ConwaySigningError):
    """Raised when a private key fails validation (wrong length, bad format)."""


class ConwayTypedDataError(ConwaySigningError):
    """
    Raised when EIP-712 typed data is malformed or cannot be constructed.

    Attributes
    ----------
    domain : dict[str, Any] | None
    primary_type : str | None
    """

    def __init__(
        self,
        message: str,
        *,
        domain: dict[str, Any] | None = None,
        primary_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.domain = domain
        self.primary_type = primary_type


# ---------------------------------------------------------------------------
# Retry / resilience errors
# ---------------------------------------------------------------------------


class ConwayRetryExhaustedError(ConwayError):
    """
    Raised when all retry attempts are exhausted.

    Attributes
    ----------
    attempts : int
    last_error : Exception | None
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.attempts = attempts
        self.last_error = last_error


# ---------------------------------------------------------------------------
# Response parsing errors
# ---------------------------------------------------------------------------


class ConwayInvalidResponseError(ConwayError):
    """
    Raised when a 2xx response body cannot be deserialized into the
    expected model.
    """
