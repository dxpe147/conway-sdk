"""
conway_sdk.wallet.kms
=======================
KMSWallet — AWS KMS-backed wallet for production Ethereum signing.

AWS KMS call flow
-----------------
1. ``get_public_key(KeyId)``   → DER-encoded SubjectPublicKeyInfo
2. ``sign(KeyId, message_hash, ECDSA_SHA_256)`` → DER-encoded signature
3. Decode DER → (r, s) → recoverable signature → Ethereum address check

Key requirements
----------------
- Key type: ``ECC_SECQ_P256K1``
- Signing algorithm: ``ECDSA_SHA_256``
- Key usage: ``SIGN_VERIFY``

Security model
--------------
- The private key material NEVER leaves AWS KMS.
- This wallet is a thin adapter that translates the AbstractWallet interface
  into KMS API calls.
- Boto3 credentials are loaded from the standard credential chain
  (environment variables, IAM role, etc.).

Dependencies
------------
boto3>=1.34  — install via ``pip install "conway-sdk[kms]"``
"""

from __future__ import annotations

from typing import Any

from conway_sdk.wallet.base import AbstractWallet

try:
    import boto3
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "boto3 is required for KMSWallet. "
        'Install it with: pip install "conway-sdk[kms]"'
    ) from _exc

try:
    import cryptography.hazmat.primitives.asymmetric.utils as _asn1_utils
    import cryptography.hazmat.primitives.serialization as _serialization
    import cryptography.hazmat.backends as _backends
    from eth_utils import keccak
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "eth-account and cryptography are required for KMSWallet. "
        "They are bundled with conway-sdk core dependencies."
    ) from _exc


class KMSWallet(AbstractWallet):
    """
    Production wallet backed by AWS KMS (ECC_SECQ_P256K1 / secp256k1).

    Parameters
    ----------
    key_id:
        AWS KMS key ARN or alias (e.g. ``"alias/my-signing-key"``).
    region_name:
        AWS region where the KMS key resides (e.g. ``"us-east-1"``).
    boto_session:
        Optional pre-configured ``boto3.Session``.  When ``None``, the
        default credential chain is used (env vars, IAM role, etc.).
    boto3_config:
        Optional ``botocore.config.Config`` to customise the KMS client.
        When ``None``, defaults to ``connect_timeout=5, read_timeout=10``
        to prevent signing threads from blocking indefinitely on a slow KMS.

    Security warning
    ----------------
    - NEVER log or print the ``key_id`` — it reveals your key hierarchy.
    - NEVER pass AWS credentials directly to this constructor.
      Use IAM roles or environment variables instead.

    Startup validation
    ------------------
    The constructor calls ``get_public_key()`` eagerly to derive and cache
    the Ethereum address.  This validates both KMS connectivity and IAM
    permissions (``kms:GetPublicKey``) at construction time.
    """

    def __init__(
        self,
        key_id: str,
        region_name: str = "us-east-1",
        boto_session: Any | None = None,
        boto3_config: Any | None = None,
    ) -> None:
        self._key_id = key_id
        session = boto_session or boto3.Session()

        if boto3_config is None:
            try:
                from botocore.config import Config as _BotocoreConfig
                boto3_config = _BotocoreConfig(
                    connect_timeout=5,
                    read_timeout=10,
                )
            except ImportError:  # pragma: no cover
                pass

        self._kms = session.client("kms", region_name=region_name, config=boto3_config)
        self._address: str = self._resolve_address()

    @property
    def address(self) -> str:
        """
        Ethereum address derived from the KMS public key.

        Resolved eagerly at construction and cached.  Key rotation requires
        a service restart to pick up the new address.
        """
        return self._address

    def _resolve_address(self) -> str:
        """Fetch the DER public key from KMS and derive the Ethereum address."""
        response = self._kms.get_public_key(KeyId=self._key_id)
        der_bytes: bytes = response["PublicKey"]

        pub_key = _serialization.load_der_public_key(
            der_bytes, backend=_backends.default_backend()
        )
        raw = pub_key.public_bytes(
            _serialization.Encoding.X962,
            _serialization.PublicFormat.UncompressedPoint,
        )
        pubkey_bytes = raw[1:]  # drop the 04 uncompressed-point prefix
        addr_bytes = keccak(pubkey_bytes)[-20:]
        from eth_utils import to_checksum_address
        return to_checksum_address(addr_bytes)

    def sign_typed_data(self, payload: Any) -> Any:
        """
        Not implemented in the base KMSWallet.

        KMSWallet signs raw 32-byte message hashes via ``sign_hash()``.
        To implement full EIP-712 signing, build the typed-data digest
        externally (e.g. with eth-account's ``encode_structured_data``)
        and pass the 32-byte keccak256 digest to ``sign_hash()``.
        """
        raise NotImplementedError(
            "KMSWallet does not implement sign_typed_data directly. "
            "Use sign_hash() with a pre-computed EIP-712 digest, or "
            "subclass KMSWallet to add full typed-data support."
        )

    async def sign_typed_data_async(self, payload: Any) -> Any:
        """Async variant — see sign_typed_data for limitations."""
        raise NotImplementedError(
            "KMSWallet does not implement sign_typed_data_async directly."
        )

    def sign_hash(self, message_hash: bytes) -> bytes:
        """
        Sign a 32-byte message hash using KMS and return a 65-byte
        Ethereum recoverable signature (r + s + v).

        Parameters
        ----------
        message_hash:
            32-byte Keccak-256 hash to sign.

        Returns
        -------
        bytes
            65-byte signature: r (32) + s (32) + v (1).

        Raises
        ------
        ValueError
            If KMS returns a signature that cannot be decoded.
        """
        response = self._kms.sign(
            KeyId=self._key_id,
            Message=message_hash,
            MessageType="DIGEST",
            SigningAlgorithm="ECDSA_SHA_256",
        )
        der_sig: bytes = response["Signature"]

        r, s = _asn1_utils.decode_dss_signature(der_sig)

        _N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        if s > _N // 2:
            s = _N - s

        sig_bytes_27 = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27])
        sig_bytes_28 = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([28])

        from eth_account import Account

        for sig_candidate in (sig_bytes_27, sig_bytes_28):
            recovered = Account._recover_hash(  # type: ignore[attr-defined]
                message_hash.hex(),
                signature=sig_candidate.hex(),
            )
            if recovered.lower() == self.address.lower():
                return sig_candidate

        raise ValueError(
            f"KMS signature recovery failed — could not match address {self.address!r} "
            "with either recovery bit.  Check that the KMS key is ECC_SECQ_P256K1."
        )


class KMSWalletStub(AbstractWallet):
    """
    Test stub for KMSWallet that delegates to a LocalWallet internally.

    Use this in unit tests when you want to exercise code that accepts
    a KMSWallet without making real AWS API calls.

    Parameters
    ----------
    private_key:
        Hex private key (with or without 0x prefix).

    Example
    -------
    ::

        wallet = KMSWalletStub(
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        )
    """

    def __init__(self, private_key: str) -> None:
        from conway_sdk.wallet.local import LocalWallet
        self._inner = LocalWallet(private_key)

    @property
    def address(self) -> str:
        return self._inner.address

    def sign_typed_data(self, payload: Any) -> Any:
        return self._inner.sign_typed_data(payload)

    async def sign_typed_data_async(self, payload: Any) -> Any:
        return await self._inner.sign_typed_data_async(payload)
