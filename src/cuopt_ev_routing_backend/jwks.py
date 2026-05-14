# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Per-issuer JWKS fetcher + in-process cache.

Pack BEs verify auth-service-minted tokens by:

1. reading the unverified ``iss`` claim
2. resolving the issuer's JWKS URL by appending ``/.well-known/jwks.json``
3. caching the public keys (keyed by kid) for ``auth_jwks_cache_ttl`` seconds

On a kid cache miss we refresh the JWKS once before failing — gives a graceful
window for upstream key rotation. Untrusted issuers are rejected before the
fetch so a forged token can't direct us at an attacker-controlled URL.

Network IO uses a hardened ``urllib.request`` opener (see ``_build_opener``):

* Only ``https://`` is accepted — http/file/ftp/data handlers are not
  registered, so a typo'd or attacker-influenced issuer URL can't pivot us
  onto the loopback metadata service or read local files.
* TLS verification is pinned via an explicit default ``ssl.SSLContext``; we
  don't rely on urllib's implicit context, which has historically been
  unverified in some embedded Python builds.
* Redirects are disabled. A 30x from an issuer's JWKS endpoint is treated as
  an error rather than silently followed to an unvalidated target.

A second, http-and-https opener (``_local_opener``, built by
``_build_local_opener``) is used ONLY for the operator-supplied in-cluster
override URL ``settings.auth_local_jwks_url``. http is allowed here BECAUSE
the URL is operator-supplied via Terraform (it's the cluster-internal
``http://auth-service:8080/...`` Service URL pinned in ``auth-locals.tf``),
not derived from a token claim — there is no attacker-influenced input. All
other SSRF protections (no file/ftp/data handlers, no redirects, same TLS
context for the https case) are preserved.

stdlib ``urllib.request`` is used deliberately: this is the only outbound HTTP
this module makes, so pulling in httpx for it isn't worth the dep.
"""

import json
import logging
import ssl
import threading
import time
import urllib.request
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm

from cuopt_ev_routing_backend.config import settings

_FETCH_TIMEOUT_SECONDS = 5

logger = logging.getLogger(__name__)


class JwksError(Exception):
    """Raised when JWKS resolution fails for a token."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse to follow 30x redirects on JWKS fetches.

    Following a redirect would mean re-validating the target against the
    trusted-issuer allowlist; the cheaper, equally-correct option is to
    require issuers to publish a stable JWKS URL with no redirect chain.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 — match stdlib signature
        raise URLError(f"redirect to {newurl!r} refused: JWKS endpoints must not redirect")


def _ssl_context() -> ssl.SSLContext:
    """Construct the TLS context the JWKS opener uses.

    Honors ``CUOPT_TLS_VERIFY=false`` to support dev clusters with self-signed
    certs (the same knob the upstream-service httpx clients use). Disabling
    verification is also gated upstream by ``main._validate_safety()`` which
    refuses to start with ``auth_require_auth=true`` outside debug mode, so
    this code path is only reachable in dev/debug deploys.
    """
    ctx = ssl.create_default_context()
    if not settings.tls_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        logger.warning("CUOPT_TLS_VERIFY=false; JWKS fetches skip TLS verification (dev only)")
    return ctx


def _build_opener() -> urllib.request.OpenerDirector:
    """Build an ``OpenerDirector`` that only speaks https with explicit TLS.

    Importantly the opener has NO ``HTTPHandler`` / ``FileHandler`` /
    ``FTPHandler`` / ``DataHandler`` — only ``HTTPSHandler``. urllib's
    ``build_opener`` would silently add all of those defaults, which is the
    root cause of "urlopen can read file:// and reach the metadata service"
    SSRF reports. We instead construct ``OpenerDirector`` directly and
    register only the handlers we want.
    """
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.HTTPSHandler(context=_ssl_context()))
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    opener.add_handler(_NoRedirectHandler())
    return opener


def _build_local_opener() -> urllib.request.OpenerDirector:
    """Build the opener used for the operator-supplied in-cluster override URL.

    Differs from ``_build_opener`` only by also registering ``HTTPHandler`` —
    the cluster-internal Service URL (``http://auth-service:8080/...``) is
    plain http inside the pod network. Allowing http is safe BECAUSE this
    opener is reached only when the fetch URL equals
    ``settings.auth_local_jwks_url`` — an operator-supplied Terraform value,
    not a token-derived one. file/ftp/data handlers remain unregistered and
    redirects remain refused.
    """
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.HTTPHandler())
    opener.add_handler(urllib.request.HTTPSHandler(context=_ssl_context()))
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    opener.add_handler(_NoRedirectHandler())
    return opener


_opener = _build_opener()
_local_opener = _build_local_opener()


class _IssuerCache:
    """Thread-safe per-issuer JWK cache keyed by kid."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # issuer -> (fetched_at_epoch, {kid: RSAPublicKey})
        self._entries: dict[str, tuple[float, dict[str, RSAPublicKey]]] = {}

    def reset(self) -> None:
        """Clear all cached JWKS — exposed for tests."""
        with self._lock:
            self._entries.clear()

    def get_key(self, issuer: str, kid: str) -> RSAPublicKey:
        """Return the public key for (issuer, kid).

        Refreshes the cache if the entry is missing, the TTL has expired, or
        the kid isn't present (single retry on kid miss handles rotation).

        The cache lock is held across the network fetch on purpose: it
        serializes concurrent first-time requests for the same issuer so we
        issue exactly one outbound JWKS HTTP call instead of N. Trades a
        small amount of latency for fetch-deduplication ("thundering herd"
        protection on cold caches and TTL expiry).
        """
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(issuer)
            ttl = settings.auth_jwks_cache_ttl
            if cached is not None and now - cached[0] <= ttl and kid in cached[1]:
                return cached[1][kid]

            keys = self._fetch_keys(issuer)
            self._entries[issuer] = (time.monotonic(), keys)
            if kid in keys:
                return keys[kid]
            raise JwksError(f"kid {kid!r} not in JWKS for issuer {issuer!r}")

    def _fetch_keys(self, issuer: str) -> dict[str, RSAPublicKey]:
        # In-cluster override: when this BE is co-located with auth-service,
        # the public ingress hop is wasted (and trips self-signed-cert TLS in
        # dev). The token's `iss` claim still carries the public issuer URL —
        # token-verification contract unchanged — only the FETCH URL changes.
        local_issuer = settings.auth_local_issuer_url
        local_url = settings.auth_local_jwks_url
        if local_issuer and local_url and issuer == local_issuer:
            url = local_url
            opener = _local_opener
        else:
            url = issuer.rstrip("/") + "/.well-known/jwks.json"
            opener = _opener
        try:
            with opener.open(url, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
                body = resp.read()
        except ssl.SSLError as exc:
            raise JwksError(f"TLS verification failed for JWKS at {url}: {exc}") from exc
        except (URLError, TimeoutError) as exc:
            raise JwksError(f"failed to fetch JWKS from {url}: {exc}") from exc

        try:
            doc = json.loads(body)
        except json.JSONDecodeError as exc:
            raise JwksError(f"JWKS at {url} is not valid JSON: {exc}") from exc

        keys: dict[str, RSAPublicKey] = {}
        for entry in doc.get("keys", []):
            kid = entry.get("kid")
            if not kid:
                continue
            try:
                key: Any = RSAAlgorithm.from_jwk(entry)
            except (jwt.InvalidKeyError, ValueError, KeyError):
                logger.warning("dropping malformed JWK entry", extra={"issuer": issuer})
                continue
            if isinstance(key, RSAPublicKey):
                keys[kid] = key
        return keys


_cache = _IssuerCache()


def trusted_issuers() -> set[str]:
    """Return the configured set of trusted issuers (one per comma)."""
    return {iss.strip() for iss in settings.auth_trusted_issuers.split(",") if iss.strip()}


def get_signing_key(issuer: str, kid: str) -> RSAPublicKey:
    """Resolve the public RSA key for (issuer, kid).

    Rejects unknown issuers before any network IO so a forged ``iss`` can't
    direct us at an attacker URL. Also enforces ``https://`` at the boundary
    — operators who put an ``http://`` or other scheme in the trusted list
    get a synchronous failure rather than a silent TLS bypass.
    """
    if issuer not in trusted_issuers():
        raise JwksError(f"untrusted issuer {issuer!r}")
    if urlsplit(issuer).scheme != "https":
        raise JwksError(f"issuer {issuer!r} must use https:// (got non-https scheme)")
    return _cache.get_key(issuer, kid)


def reset_cache() -> None:
    """Clear the JWKS cache — for tests only."""
    _cache.reset()
