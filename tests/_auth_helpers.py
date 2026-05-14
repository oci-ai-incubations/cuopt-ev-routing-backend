# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Shared test helpers for RS256 token generation + JWKS stubbing.

The cuopt-backend's auth dependency fetches the issuer's JWKS at
``{issuer}/.well-known/jwks.json`` via a hardened ``OpenerDirector``. Tests
generate an RSA keypair at import time, monkeypatch the module-level
``_opener.open`` to serve a stubbed JWKS, and sign tokens with the private
half. Network IO is fully stubbed.
"""

import io
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_ISSUER = "https://issuer.test/auth"
TEST_KID = "test-kid"


def _generate_keypair() -> tuple[rsa.RSAPrivateKey, str, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private, private_pem, public_pem


# Generated once at module import — RSA gen is slow.
TEST_PRIVATE_KEY, TEST_PRIVATE_PEM, TEST_PUBLIC_PEM = _generate_keypair()


def jwk_for_test_key(kid: str = TEST_KID) -> dict:
    """Return a JWK dict for the module-level test public key."""
    return json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(TEST_PRIVATE_KEY.public_key())) | {
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


def jwks_document(kid: str = TEST_KID) -> dict:
    """Return a JWKS document containing the test key."""
    return {"keys": [jwk_for_test_key(kid)]}


def make_token(
    *,
    role: str = "user",
    exp_offset: int = 600,
    issuer: str = TEST_ISSUER,
    kid: str = TEST_KID,
    private_pem: str = TEST_PRIVATE_PEM,
    audience: str | list[str] | None = "cuopt",
    sub: str = "42",
    principal_type: str | None = None,
    scope: str | None = None,
    scp: str | None = None,
    roles: list[str] | None = None,
) -> str:
    """Mint an RS256 user-style token signed by the test key.

    ``principal_type`` lets callers stamp the spec-002 claim explicitly;
    omitting it preserves the legacy pre-spec-002 shape so the BE's default-
    to-user behavior remains exercised.

    ``scope`` (when set) is stamped as the space-joined OAuth2 ``scope``
    claim — needed by scope-gated routes (spec 003). ``scp`` mints the
    Microsoft Entra delegated-permissions claim; ``roles`` mints the Entra
    app-roles claim (a list, not space-separated). Tests pick whichever
    shape they're pinning.

    ``audience`` defaults to ``"cuopt"`` to match the new always-on aud
    verification (RFC 9068). Pass ``None`` to omit the claim entirely (for
    negative-path tests). Pass a list to stamp multiple audiences.
    """
    now = datetime.now(UTC)
    payload: dict = {
        "sub": sub,
        "email": "u@example.com",
        "name": "Test User",
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset)).timestamp()),
        "iss": issuer,
    }
    if principal_type is not None:
        payload["principal_type"] = principal_type
    if scope is not None:
        payload["scope"] = scope
    if scp is not None:
        payload["scp"] = scp
    if roles is not None:
        payload["roles"] = roles
    if audience is not None:
        payload["aud"] = audience
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


def make_client_token(
    *,
    client_id: str = "cli_test",
    scope: str = "",
    exp_offset: int = 600,
    issuer: str = TEST_ISSUER,
    kid: str = TEST_KID,
    private_pem: str = TEST_PRIVATE_PEM,
    audience: str | list[str] | None = "cuopt",
) -> str:
    """Mint an RS256 client-style token (OAuth2 client_credentials shape).

    Mirrors the claim layout of ``auth-service.create_client_access_token``:
    ``sub=client:<id>``, ``principal_type=client``, ``client_id`` populated,
    ``scope`` space-joined. No ``email`` / ``name`` / ``role`` — those are
    user-only.
    """
    now = datetime.now(UTC)
    payload: dict = {
        "sub": f"client:{client_id}",
        "client_id": client_id,
        "scope": scope,
        "principal_type": "client",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset)).timestamp()),
        "iss": issuer,
    }
    if audience is not None:
        payload["aud"] = audience
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def install_jwks_stub(
    monkeypatch,
    document: dict | None = None,
    *,
    responder: Callable[[str], bytes] | None = None,
    counter: list[int] | None = None,
    discovery_counter: list[int] | None = None,
    issuer: str = TEST_ISSUER,
) -> None:
    """Stub the JWKS opener so no real network IO happens during tests.

    Replaces ``jwks._opener.open`` rather than ``urlopen`` because the
    production code goes through a custom hardened ``OpenerDirector``.

    The default responder serves an OIDC discovery doc at
    ``{issuer}/.well-known/openid-configuration`` (pointing at
    ``{issuer}/.well-known/jwks.json``) and a JWKS doc at that URL. Pass
    ``responder`` to override the URL→body mapping for multi-issuer or
    custom-path (e.g. IDCS-style) tests.

    ``counter`` increments on every fetch (discovery + jwks combined);
    ``discovery_counter`` increments only on discovery-doc fetches — useful
    for tests that need to assert the discovery cache is hot.
    """
    from cuopt_ev_routing_backend import jwks

    if responder is None:
        doc = document if document is not None else jwks_document()
        jwks_body = json.dumps(doc).encode()
        jwks_url = issuer.rstrip("/") + "/.well-known/jwks.json"
        discovery_url = issuer.rstrip("/") + "/.well-known/openid-configuration"
        discovery_body = json.dumps({"issuer": issuer, "jwks_uri": jwks_url}).encode()

        def responder(url: str) -> bytes:
            if url == discovery_url:
                return discovery_body
            if url == jwks_url:
                return jwks_body
            raise AssertionError(f"unexpected fetch to {url!r}")

    def _fake_open(url, timeout=None):  # noqa: ARG001 — signature must match OpenerDirector.open
        if counter is not None:
            counter[0] += 1
        if discovery_counter is not None and url.endswith("/.well-known/openid-configuration"):
            discovery_counter[0] += 1
        return _FakeResponse(responder(url))

    monkeypatch.setattr(jwks._opener, "open", _fake_open)
    jwks.reset_cache()
