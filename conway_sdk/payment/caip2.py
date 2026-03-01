"""
conway_sdk.payment.caip2
==========================
CAIP-2 chain identifier parsing utilities.

CAIP-2 format (Chain Agnostic Improvement Proposal):
    <namespace>:<reference>

Examples for EVM chains:
    eip155:1      → Ethereum Mainnet
    eip155:8453   → Base Mainnet
    eip155:84532  → Base Sepolia (default for development)

Asset identifiers (CAIP-19):
    eip155:84532/erc20:0x036CbD53842c5426634e7929541eC2318f3dCF7e

Reference: https://github.com/ChainAgnostic/CAIPs/blob/main/CAIPs/caip-2.md
"""

from __future__ import annotations

__all__ = [
    "parse_caip2_chain_id",
    "parse_caip2_asset",
    "build_caip2",
    "CAIP2ParseError",
    "EVM_NAMESPACE",
]

EVM_NAMESPACE = "eip155"


class CAIP2ParseError(ValueError):
    """Raised when a CAIP-2 string is malformed or uses an unsupported namespace."""


def parse_caip2_chain_id(caip2: str) -> int:
    """
    Parse an EVM CAIP-2 string and return the integer chain ID.

    Parameters
    ----------
    caip2 : str
        CAIP-2 network identifier, e.g. ``"eip155:84532"``.

    Returns
    -------
    int
        The integer chain ID (e.g. ``84532``).

    Raises
    ------
    CAIP2ParseError
        If the string is malformed, namespace is not ``eip155``, or
        the chain reference is not a valid positive integer.

    Examples
    --------
    >>> parse_caip2_chain_id("eip155:84532")
    84532
    >>> parse_caip2_chain_id("eip155:1")
    1
    """
    if not isinstance(caip2, str) or ":" not in caip2:
        raise CAIP2ParseError(
            f"Invalid CAIP-2 format {caip2!r}: expected '<namespace>:<reference>', "
            f"e.g. 'eip155:84532'."
        )

    namespace, _, chain_ref = caip2.partition(":")

    if namespace != EVM_NAMESPACE:
        raise CAIP2ParseError(
            f"Unsupported CAIP-2 namespace {namespace!r}. "
            f"Only '{EVM_NAMESPACE}' (EVM) is currently supported."
        )

    if not chain_ref:
        raise CAIP2ParseError(
            f"CAIP-2 chain reference is empty in {caip2!r}."
        )

    try:
        chain_id = int(chain_ref)
    except ValueError as exc:
        raise CAIP2ParseError(
            f"CAIP-2 chain reference {chain_ref!r} is not a valid integer in {caip2!r}."
        ) from exc

    if chain_id <= 0:
        raise CAIP2ParseError(
            f"CAIP-2 chain ID must be a positive integer, got {chain_id} in {caip2!r}."
        )

    return chain_id


def parse_caip2_asset(caip19: str) -> tuple[int, str]:
    """
    Parse a CAIP-19 ERC-20 asset identifier.

    Format: ``eip155:<chain_id>/erc20:<contract_address>``

    Parameters
    ----------
    caip19 : str
        CAIP-19 asset identifier, e.g.
        ``"eip155:84532/erc20:0x036CbD53842c5426634e7929541eC2318f3dCF7e"``.

    Returns
    -------
    tuple[int, str]
        ``(chain_id, contract_address)``

    Raises
    ------
    CAIP2ParseError
        If the format is invalid.

    Examples
    --------
    >>> chain_id, contract = parse_caip2_asset(
    ...     "eip155:84532/erc20:0x036CbD53842c5426634e7929541eC2318f3dCF7e"
    ... )
    >>> chain_id
    84532
    """
    if "/" not in caip19:
        raise CAIP2ParseError(
            f"Invalid CAIP-19 format {caip19!r}: expected "
            f"'eip155:<chain_id>/erc20:<address>'."
        )

    network_part, asset_part = caip19.split("/", 1)
    chain_id = parse_caip2_chain_id(network_part)

    if not asset_part.startswith("erc20:"):
        raise CAIP2ParseError(
            f"Unsupported asset type in {caip19!r}: expected 'erc20:<address>'."
        )

    contract = asset_part[len("erc20:"):]
    if not contract.startswith("0x") or len(contract) != 42:  # noqa: PLR2004
        raise CAIP2ParseError(
            f"Contract address {contract!r} in {caip19!r} is not a valid "
            "0x-prefixed 20-byte EVM address."
        )

    return chain_id, contract


def build_caip2(chain_id: int) -> str:
    """
    Build a CAIP-2 string from an integer chain ID.

    Parameters
    ----------
    chain_id : int
        EVM chain ID (e.g. ``84532``).

    Returns
    -------
    str
        CAIP-2 string (e.g. ``"eip155:84532"``).

    Examples
    --------
    >>> build_caip2(84532)
    'eip155:84532'
    """
    if chain_id <= 0:
        raise CAIP2ParseError(f"chain_id must be positive, got {chain_id}.")
    return f"{EVM_NAMESPACE}:{chain_id}"
