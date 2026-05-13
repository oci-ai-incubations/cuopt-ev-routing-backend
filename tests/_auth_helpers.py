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
    audience: str | None = None,
    sub: str = "42",
) -> str:
    """Mint an RS256 token signed by the test key (or a caller-supplied one)."""
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
) -> None:
    """Stub the JWKS opener so no real network IO happens during tests.

    Replaces ``jwks._opener.open`` rather than ``urlopen`` because the
    production code goes through a custom hardened ``OpenerDirector``.

    Pass ``document`` for the single-issuer happy path, or ``responder`` for
    per-URL responses (e.g. multi-issuer tests). Optionally pass ``counter``
    (a single-element list) to count fetches across the test.
    """
    from cuopt_ev_routing_backend import jwks

    if responder is None:
        doc = document if document is not None else jwks_document()
        default_body = json.dumps(doc).encode()

        def responder(_url: str) -> bytes:
            return default_body

    def _fake_open(url, timeout=None):  # noqa: ARG001 — signature must match OpenerDirector.open
        if counter is not None:
            counter[0] += 1
        return _FakeResponse(responder(url))

    monkeypatch.setattr(jwks._opener, "open", _fake_open)
    jwks.reset_cache()
