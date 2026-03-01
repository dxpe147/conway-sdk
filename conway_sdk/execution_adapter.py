"""
conway_sdk.execution_adapter
==============================
ExecutionAdapter ABC and ExecutionResult.

This module depends only on the Python standard library.
Type annotations use ``from __future__ import annotations`` so they are
strings at runtime (no circular-import risk).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from conway_sdk.models import PaymentIntent


@dataclass
class ExecutionResult:
    """
    Result of a single adapter execution attempt.

    Attributes
    ----------
    success:
        ``True`` if signing completed without error.
    intent_id:
        The ``PaymentIntent.intent_id`` this result corresponds to.
    nonce:
        EIP-3009 nonce from the signed authorization.
        ``None`` on failure.
    authorization:
        Full ``PaymentAuthorization`` object on success; ``None`` on failure.
    error:
        Exception caught during execution; ``None`` on success.
    """

    success: bool
    intent_id: UUID
    nonce: str | None = None
    authorization: Any | None = None
    error: Exception | None = None


class ExecutionAdapter(ABC):
    """
    Abstract execution adapter — convert a PaymentIntent into a signed result.

    Implementors must provide ``execute(intent)`` which attempts to create
    a signed payment authorization for the given ``PaymentIntent``.

    Contract
    --------
    - ``execute()`` MUST NOT raise.  All errors are returned as
      ``ExecutionResult(success=False, error=exc)``.
    - Results are not cached across calls.  Each ``execute()`` is independent.
    """

    @abstractmethod
    def execute(self, payment_intent: "PaymentIntent") -> ExecutionResult:
        """
        Execute the payment described by the intent.

        Parameters
        ----------
        payment_intent:
            The validated ``PaymentIntent`` to execute.

        Returns
        -------
        ExecutionResult
            Always returned; never raises.
        """
        ...
