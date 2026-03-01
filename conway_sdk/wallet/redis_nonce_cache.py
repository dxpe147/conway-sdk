"""
conway_sdk.wallet.redis_nonce_cache
=====================================
RedisNonceCache — distributed nonce deduplication using Redis SET NX EX.

In a multi-instance deployment, a signed EIP-3009 authorization carries a
nonce that must be used at most once within its ``valid_before`` window.
If two instances sign the same intent concurrently (e.g. due to a retry
race), both might produce valid-looking authorizations with the same or
overlapping nonces.

RedisNonceCache prevents this by recording every nonce immediately after
signing, using ``SET key value NX EX ttl``:

  - ``NX`` (SET if Not eXists): atomic "first writer wins" guarantee
  - ``EX ttl``: automatic expiry when the nonce's ``valid_before`` passes

Protocol
--------
1. After signing, call ``cache.record(nonce, ttl)``.
2. If the call returns ``False``, the nonce was already recorded by another
   instance — treat as a duplicate and surface an error.
3. If the call returns ``True``, the nonce is fresh and was recorded.

Key format: ``conway:nonce:{nonce}``  (nonce is the 0x-prefixed hex string)

Dependencies
------------
redis>=5.0  — install via ``pip install "conway-sdk[redis]"``

In tests use ``fakeredis.FakeRedis()`` as a drop-in replacement.
"""

from __future__ import annotations

from typing import Any

try:
    import redis as _redis_module  # noqa: F401
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "redis is required for RedisNonceCache. "
        'Install it with: pip install "conway-sdk[redis]"'
    ) from _exc

_DEFAULT_TTL_SECONDS = 3600
_KEY_PREFIX = "conway:nonce:"


class RedisNonceCache:
    """
    Distributed nonce deduplication cache backed by Redis.

    Parameters
    ----------
    client:
        A ``redis.Redis`` (or compatible) client.  Pass a
        ``fakeredis.FakeRedis()`` instance in tests.
    default_ttl:
        Default TTL in seconds applied when ``record()`` is called without
        an explicit ttl.  Defaults to 3600 (1 hour).
    key_prefix:
        Redis key prefix.  Defaults to ``"conway:nonce:"``.

    Examples
    --------
    Production::

        import redis
        client = redis.Redis.from_url("redis://localhost:6379/0")
        cache = RedisNonceCache(client)

    Tests::

        import fakeredis
        cache = RedisNonceCache(fakeredis.FakeRedis())
    """

    def __init__(
        self,
        client: Any,
        *,
        default_ttl: int = _DEFAULT_TTL_SECONDS,
        key_prefix: str = _KEY_PREFIX,
    ) -> None:
        self._client = client
        self._default_ttl = default_ttl
        self._key_prefix = key_prefix

    def record(self, nonce: str, ttl: int | None = None) -> bool:
        """
        Record a nonce with SET NX EX (first-writer-wins semantics).

        Parameters
        ----------
        nonce:
            The 0x-prefixed hex nonce string from the EIP-3009 signature.
        ttl:
            TTL in seconds.  Defaults to ``default_ttl``.

        Returns
        -------
        True
            Nonce was not previously recorded; it is now registered.
        False
            Nonce was already present — this is a duplicate.
        """
        key = self._key_prefix + nonce
        effective_ttl = ttl if ttl is not None else self._default_ttl
        result = self._client.set(key, "1", nx=True, ex=effective_ttl)
        return result is True or result == 1

    def is_known(self, nonce: str) -> bool:
        """
        Check whether a nonce has been recorded without recording it.

        Use ``record()`` for the authoritative first-write check; use
        ``is_known()`` only for informational/diagnostic queries.
        """
        key = self._key_prefix + nonce
        return bool(self._client.exists(key))

    def evict(self, nonce: str) -> bool:
        """
        Explicitly remove a nonce from the cache.

        Intended for test cleanup and administrative use only.  In
        production, nonces expire automatically via TTL.

        Returns True if the key was deleted, False if it was not present.
        """
        key = self._key_prefix + nonce
        result = self._client.delete(key)
        return bool(result)

    def ping(self) -> bool:
        """Return True if Redis is reachable; False otherwise."""
        try:
            self._client.ping()
            return True
        except Exception:
            return False
