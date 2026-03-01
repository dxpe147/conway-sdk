"""
conway_sdk.models
==================
Public SDK models: Agent and PaymentIntent.

Both classes depend only on the Python standard library — no external
imports are made at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Agent:
    """
    Immutable identity record for an agent.

    Attributes
    ----------
    agent_id:
        Unique identifier for this agent instance.
    treasury_id:
        The Treasury this agent is authorized to submit intents to.
    environment:
        ``"development"`` (testnet, zero-cost) or ``"production"`` (mainnet).
    metadata:
        Arbitrary key-value store for caller-defined context (name, owner, etc.).
        Not transmitted on-chain; used for observability and logging only.
    """

    agent_id: UUID
    treasury_id: UUID
    environment: str
    metadata: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def __post_init__(self) -> None:
        if self.environment not in ("development", "production"):
            raise ValueError(
                f"environment must be 'development' or 'production', "
                f"got {self.environment!r}"
            )

    @classmethod
    def create(
        cls,
        treasury_id: UUID,
        environment: str = "development",
        metadata: dict[str, Any] | None = None,
    ) -> "Agent":
        """
        Factory: create a new Agent with a fresh UUID.

        Parameters
        ----------
        treasury_id:
            UUID of the Treasury this agent submits intents to.
        environment:
            ``"development"`` or ``"production"``.
        metadata:
            Optional key-value context attached to this agent.
        """
        return cls(
            agent_id=uuid4(),
            treasury_id=treasury_id,
            environment=environment,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:
        return (
            f"Agent(agent_id={str(self.agent_id)[:8]}..., "
            f"treasury_id={str(self.treasury_id)[:8]}..., "
            f"environment={self.environment!r})"
        )


# ---------------------------------------------------------------------------
# PaymentIntent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentIntent:
    """
    An Agent's request to make a payment.

    Attributes
    ----------
    agent_id:
        UUID of the Agent submitting this intent.
    bucket_id:
        Identifier of the spend bucket to debit.
    asset:
        Token identifier (e.g. ``"USDC"``).
    network:
        CAIP-2 chain identifier (e.g. ``"eip155:84532"``).
    amount:
        Transfer amount in token atomic units (USDC: 1 USDC = 1_000_000).
    destination:
        EVM recipient address (0x-prefixed, 42 chars).
    verifying_contract:
        ERC-20 token contract address used as EIP-712 ``verifyingContract``.
    metadata:
        Caller-defined context — logged but not transmitted on-chain.
    intent_id:
        Auto-assigned UUID; primary correlation key across all ledger entries.
    """

    agent_id: UUID
    bucket_id: str
    asset: str
    network: str
    amount: int
    destination: str
    verifying_contract: str
    metadata: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    intent_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError(f"amount must be > 0, got {self.amount}")
        if not self.bucket_id:
            raise ValueError("bucket_id must be a non-empty string")
        if not self.network:
            raise ValueError(
                "network must be a non-empty CAIP-2 string (e.g. 'eip155:84532')"
            )
        _validate_evm_address("destination", self.destination)
        _validate_evm_address("verifying_contract", self.verifying_contract)

    def __repr__(self) -> str:
        return (
            f"PaymentIntent(intent_id={str(self.intent_id)[:8]}..., "
            f"agent_id={str(self.agent_id)[:8]}..., "
            f"bucket_id={self.bucket_id!r}, "
            f"asset={self.asset!r}, "
            f"network={self.network!r}, "
            f"amount={self.amount})"
        )


def _validate_evm_address(field_name: str, value: str) -> None:
    """Lightweight structural check — full checksum validation happens at signing."""
    if not isinstance(value, str) or not value.startswith("0x") or len(value) != 42:
        raise ValueError(
            f"{field_name} must be a 0x-prefixed 42-character EVM address, "
            f"got {value!r}"
        )
