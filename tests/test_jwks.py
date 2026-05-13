# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""JWKS caching, refresh, and multi-issuer behavior.

Pins spec 001's acceptance criteria for the cuopt BE: that a kid-miss
triggers exactly one refresh, that TTL governs cache lifetime, and that the
trusted-issuer allowlist is honored per token.
"""

import json
import ssl

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from cuopt_ev_routing_backend import jwks
from cuopt_ev_routing_backend.auth import _decode_token
from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.jwks import JwksError, get_signing_key

from ._auth_helpers import (
    TEST_ISSUER,
    TEST_KID,
    TEST_PRIVATE_PEM,
    _generate_keypair,
    install_jwks_stub,
    jwk_for_test_key,
    make_token,
)


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", TEST_ISSUER)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", None)


def test_jwks_cache_hit_within_ttl_does_not_refetch(auth_enabled, monkeypatch):
    """Two calls within TTL → exactly one fetch (T1, happy-path half)."""
    counter = [0]
    install_jwks_stub(monkeypatch, counter=counter)
    get_signing_key(TEST_ISSUER, TEST_KID)
    get_signing_key(TEST_ISSUER, TEST_KID)
    assert counter[0] == 1


def test_jwks_cache_refetches_after_ttl_expiry(auth_enabled, monkeypatch):
    """TTL=0 → every call refetches (T1, expiry half)."""
    counter = [0]
    install_jwks_stub(monkeypatch, counter=counter)
    get_signing_key(TEST_ISSUER, TEST_KID)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 0)
    get_signing_key(TEST_ISSUER, TEST_KID)
    assert counter[0] == 2


def test_jwks_kid_miss_triggers_exactly_one_refresh(auth_enabled, monkeypatch):
    """A request for an unknown kid forces one refresh, then raises (T2)."""
    counter = [0]
    install_jwks_stub(monkeypatch, counter=counter)
    # Prime cache with kid A.
    get_signing_key(TEST_ISSUER, TEST_KID)
    assert counter[0] == 1
    # Request kid B → one refresh, then failure (because the stub still
    # only serves kid A — pins the contract: refresh-once-then-fail).
    with pytest.raises(JwksError, match="not in JWKS"):
        get_signing_key(TEST_ISSUER, "kid-never-issued")
    assert counter[0] == 2


def test_jwks_multi_issuer_routes_per_url(monkeypatch):
    """Per-issuer JWKS routing: tokens from each trusted issuer validate;
    a third unknown issuer is rejected before any network IO (T3)."""
    issuer_a = "https://a.example.com/auth"
    issuer_b = "https://b.example.com/auth"
    issuer_c = "https://c.example.com/auth"

    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", f"{issuer_a},{issuer_b}")
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", None)

    # Different keypair per issuer so we know routing actually picks correctly.
    private_a, private_a_pem, _ = _generate_keypair()
    private_b, private_b_pem, _ = _generate_keypair()
    kid_a = "issuer-a-kid"
    kid_b = "issuer-b-kid"

    jwk_a = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(private_a.public_key())) | {
        "kid": kid_a,
        "alg": "RS256",
        "use": "sig",
    }
    jwk_b = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(private_b.public_key())) | {
        "kid": kid_b,
        "alg": "RS256",
        "use": "sig",
    }
    bodies = {
        issuer_a.rstrip("/") + "/.well-known/jwks.json": json.dumps({"keys": [jwk_a]}).encode(),
        issuer_b.rstrip("/") + "/.well-known/jwks.json": json.dumps({"keys": [jwk_b]}).encode(),
    }

    def _responder(url: str) -> bytes:
        if url not in bodies:
            raise AssertionError(f"unexpected JWKS fetch to {url!r}")
        return bodies[url]

    install_jwks_stub(monkeypatch, responder=_responder)

    # Token from issuer A → accepted.
    token_a = make_token(issuer=issuer_a, kid=kid_a, private_pem=private_a_pem)
    payload_a = _decode_token(token_a)
    assert payload_a["iss"] == issuer_a

    # Token from issuer B → accepted.
    token_b = make_token(issuer=issuer_b, kid=kid_b, private_pem=private_b_pem)
    payload_b = _decode_token(token_b)
    assert payload_b["iss"] == issuer_b

    # Token from issuer C (not in allowlist) → rejected before any fetch.
    token_c = make_token(issuer=issuer_c, kid="anything", private_pem=TEST_PRIVATE_PEM)
    with pytest.raises(HTTPException) as exc:
        _decode_token(token_c)
    assert exc.value.status_code == 401
    assert "untrusted issuer" in exc.value.detail


def test_non_https_issuer_rejected(monkeypatch):
    """Operator typo: http://issuer.example in trusted list must fail closed."""
    http_issuer = "http://issuer.test/auth"
    monkeypatch.setattr(settings, "auth_trusted_issuers", http_issuer)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)

    # No need to stub the opener — we should never get that far.
    with pytest.raises(JwksError, match="must use https"):
        get_signing_key(http_issuer, "any-kid")


def test_tls_verification_failure_raises_jwks_error(auth_enabled, monkeypatch):
    """An ssl.SSLError on the JWKS fetch surfaces as JwksError, not a 500."""

    def _fake_open(_url, timeout=None):  # noqa: ARG001
        raise ssl.SSLError("certificate verify failed: self signed certificate")

    monkeypatch.setattr(jwks._opener, "open", _fake_open)
    jwks.reset_cache()
    with pytest.raises(JwksError, match="TLS verification failed"):
        get_signing_key(TEST_ISSUER, TEST_KID)


def test_malformed_jwk_entry_is_dropped_not_propagated(auth_enabled, monkeypatch):
    """An unparseable JWK is logged + skipped; the valid entry still resolves."""
    good_jwk = jwk_for_test_key()
    # Missing required RSA field 'n' — RSAAlgorithm.from_jwk raises KeyError.
    bad_jwk = {"kty": "RSA", "kid": "broken", "alg": "RS256", "use": "sig", "e": "AQAB"}
    doc = {"keys": [bad_jwk, good_jwk]}
    install_jwks_stub(monkeypatch, document=doc)
    key = get_signing_key(TEST_ISSUER, TEST_KID)
    assert key is not None


def test_redirect_is_refused(auth_enabled, monkeypatch):
    """30x responses from the JWKS endpoint must not be followed silently."""
    from urllib.error import URLError

    def _fake_open(_url, timeout=None):  # noqa: ARG001
        # Simulate what _NoRedirectHandler would do if hit.
        raise URLError("redirect to 'https://attacker.example/jwks.json' refused")

    monkeypatch.setattr(jwks._opener, "open", _fake_open)
    jwks.reset_cache()
    with pytest.raises(JwksError, match="failed to fetch JWKS"):
        get_signing_key(TEST_ISSUER, TEST_KID)


def test_opener_has_no_file_handler():
    """The hardened opener must not register a FileHandler — file:// URLs
    have no legitimate use case here and are the canonical SSRF vector."""
    handlers = [type(h).__name__ for h in jwks._opener.handlers]
    assert "FileHandler" not in handlers
    assert "FTPHandler" not in handlers
    assert "HTTPHandler" not in handlers


def test_opener_has_https_handler():
    """Sanity: the opener must still speak https."""
    handlers = [type(h).__name__ for h in jwks._opener.handlers]
    assert "HTTPSHandler" in handlers
