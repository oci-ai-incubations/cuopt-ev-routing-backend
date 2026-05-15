# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Federation-readiness acceptance tests.

Pins the four federation fixes against the design notes in the auth-service
specs (001/002/003): default-on ``aud`` verification (RFC 9068 §4),
Microsoft Entra's ``scp`` / ``roles`` claim shapes, OIDC discovery-doc
resolution of the JWKS URI (for IDCS-style ``/admin/v1/SigningCert/jwk``
and similar federated issuers), and the per-issuer audience list.

These tests exercise the public surface only — no internal monkeypatching
beyond what the existing test suite already does. Each test is independent
and rebuilds its own JWKS / discovery stub.
"""

import json

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from cuopt_ev_routing_backend import jwks
from cuopt_ev_routing_backend.auth import (
    PrincipalType,
    _decode_token,
    _extract_scopes,
    _principal_from_payload,
)
from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.jwks import JwksError, get_signing_key, reset_cache

from ._auth_helpers import (
    TEST_ISSUER,
    TEST_KID,
    TEST_PRIVATE_PEM,
    _FakeResponse,
    _generate_keypair,
    install_jwks_stub,
    jwks_document,
    make_token,
)

# --- F1. Default-on audience verification --------------------------------------


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", TEST_ISSUER)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", "cuopt")
    install_jwks_stub(monkeypatch)


def test_default_audience_is_cuopt():
    """RFC 9068 §4: every verifier MUST check aud. The default lands as
    ``cuopt`` so a freshly-deployed pack BE rejects audience-less tokens."""
    assert settings.auth_token_audience == "cuopt"
    assert settings.auth_token_audience_list == ["cuopt"]


def test_token_with_matching_audience_accepted(auth_enabled):
    token = make_token(audience="cuopt")
    payload = _decode_token(token)
    assert payload["aud"] == "cuopt"


def test_token_with_wrong_audience_rejected(auth_enabled):
    token = make_token(audience="some-other-resource")
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401


def test_token_with_no_audience_rejected_when_aud_required(auth_enabled):
    """A token minted without ``aud`` is rejected — verify_aud is default-on
    regardless of whether the operator overrode the audience setting."""
    token = make_token(audience=None)
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401


# --- F4. Per-issuer audience support (comma-separated list) --------------------


def test_audience_list_accepts_multiple_audiences(monkeypatch):
    """Decision: F4 option (A) — auth_token_audience is a comma-separated
    list; PyJWT accepts a match against any element."""
    monkeypatch.setattr(
        settings,
        "auth_token_audience",
        "cuopt,https://cuopt.example.com/api/",
    )
    assert settings.auth_token_audience_list == ["cuopt", "https://cuopt.example.com/api/"]


def test_token_aud_matches_any_of_listed_audiences(auth_enabled, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_token_audience",
        "cuopt,https://cuopt.example.com/api/",
    )
    # auth-service-minted token: aud=cuopt.
    payload = _decode_token(make_token(audience="cuopt"))
    assert payload["aud"] == "cuopt"
    # IDCS-style token: aud=resource URL.
    payload = _decode_token(make_token(audience="https://cuopt.example.com/api/"))
    assert payload["aud"] == "https://cuopt.example.com/api/"


def test_token_aud_matches_no_listed_audience_rejected(auth_enabled, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_token_audience",
        "cuopt,https://cuopt.example.com/api/",
    )
    with pytest.raises(HTTPException) as exc:
        _decode_token(make_token(audience="https://attacker.example.com/api/"))
    assert exc.value.status_code == 401


def test_audience_list_strips_whitespace(monkeypatch):
    """Operators are forgiven for ``" cuopt , other "`` env values."""
    monkeypatch.setattr(settings, "auth_token_audience", " cuopt ,  other ")
    assert settings.auth_token_audience_list == ["cuopt", "other"]


def test_audience_list_drops_empty_entries(monkeypatch):
    """``"cuopt,,other"`` — the empty entry is dropped, not treated as a
    blank-string audience that nothing can match."""
    monkeypatch.setattr(settings, "auth_token_audience", "cuopt,,other")
    assert settings.auth_token_audience_list == ["cuopt", "other"]


# --- F2. scp / roles claim fallback --------------------------------------------


def test_extract_scopes_reads_scope_first():
    """Standard OAuth2 / RFC 9068 / auth-service / IDCS shape."""
    scopes = _extract_scopes({"scope": "cuopt.solve cuopt.view"})
    assert scopes == ["cuopt.solve", "cuopt.view"]


def test_extract_scopes_falls_back_to_scp_when_scope_absent():
    """Microsoft Entra delegated permissions are stamped as ``scp``."""
    scopes = _extract_scopes({"scp": "cuopt.solve cuopt.view"})
    assert scopes == ["cuopt.solve", "cuopt.view"]


def test_extract_scopes_falls_back_to_roles_when_scope_and_scp_absent():
    """Entra app permissions land in ``roles`` (a list, not space-joined)."""
    scopes = _extract_scopes({"roles": ["cuopt.solve", "cuopt.view"]})
    assert scopes == ["cuopt.solve", "cuopt.view"]


def test_extract_scopes_prefers_scope_over_scp_when_both_present():
    """No real token will carry both, but if it does we use the RFC-blessed
    one — defensive, future-proof."""
    scopes = _extract_scopes({"scope": "cuopt.solve", "scp": "cuopt.view"})
    assert scopes == ["cuopt.solve"]


def test_extract_scopes_prefers_scp_over_roles_when_both_present():
    """When scope is absent but scp present, we don't also merge roles —
    one source of truth per token."""
    scopes = _extract_scopes({"scp": "cuopt.solve", "roles": ["cuopt.view"]})
    assert scopes == ["cuopt.solve"]


def test_extract_scopes_missing_all_claims_yields_empty_list():
    """Forces scope-gated routes to 403 rather than silently allow."""
    assert _extract_scopes({"sub": "1"}) == []


def test_extract_scopes_empty_string_scope_yields_empty_list():
    assert _extract_scopes({"scope": ""}) == []


def test_extract_scopes_empty_string_scp_yields_empty_list():
    assert _extract_scopes({"scp": ""}) == []


def test_extract_scopes_empty_roles_list_yields_empty_list():
    assert _extract_scopes({"roles": []}) == []


def test_extract_scopes_roles_list_filters_empty_entries():
    """A poorly-shaped Entra roles claim with empty strings doesn't pollute
    the scope set."""
    assert _extract_scopes({"roles": ["cuopt.solve", "", None]}) == ["cuopt.solve"]


def test_principal_from_payload_entra_scp_token():
    """End-to-end: an Entra-style token resolves scopes via scp fallback."""
    payload = {
        "sub": "user-uuid",
        "principal_type": "user",
        "scp": "cuopt.solve cuopt.view",
    }
    principal = _principal_from_payload(payload)
    assert principal.scopes == ["cuopt.solve", "cuopt.view"]
    assert principal.principal_type is PrincipalType.user


def test_principal_from_payload_entra_roles_token():
    """End-to-end: an Entra app-permission token resolves scopes via roles."""
    payload = {
        "sub": "client-uuid",
        "principal_type": "client",
        "roles": ["cuopt.solve"],
    }
    principal = _principal_from_payload(payload)
    assert principal.scopes == ["cuopt.solve"]
    assert principal.principal_type is PrincipalType.client


# --- F3. OIDC discovery doc resolution -----------------------------------------


def test_oidc_discovery_happy_path_resolves_jwks_uri(auth_enabled, monkeypatch):
    """The discovery doc's ``jwks_uri`` is the URL we fetch the JWKS from —
    we don't hardcode ``/.well-known/jwks.json`` any more."""
    custom_jwks_url = TEST_ISSUER + "/non-standard/keys"
    discovery_url = TEST_ISSUER + "/.well-known/openid-configuration"
    discovery_body = json.dumps({"issuer": TEST_ISSUER, "jwks_uri": custom_jwks_url}).encode()
    jwks_body = json.dumps(jwks_document()).encode()

    fetched: list[str] = []

    def _responder(url: str) -> bytes:
        fetched.append(url)
        if url == discovery_url:
            return discovery_body
        if url == custom_jwks_url:
            return jwks_body
        raise AssertionError(f"unexpected fetch to {url!r}")

    install_jwks_stub(monkeypatch, responder=_responder)
    key = get_signing_key(TEST_ISSUER, TEST_KID)
    assert key is not None
    assert fetched == [discovery_url, custom_jwks_url]


def test_oidc_discovery_idcs_style_jwks_path(auth_enabled, monkeypatch):
    """Oracle IDCS publishes JWKS at ``/admin/v1/SigningCert/jwk`` — entirely
    different from the auth-service path. Discovery resolves the IDCS-style
    URL end-to-end."""
    idcs_jwks_url = TEST_ISSUER + "/admin/v1/SigningCert/jwk"
    discovery_url = TEST_ISSUER + "/.well-known/openid-configuration"
    discovery_body = json.dumps({"issuer": TEST_ISSUER, "jwks_uri": idcs_jwks_url}).encode()
    jwks_body = json.dumps(jwks_document()).encode()

    def _responder(url: str) -> bytes:
        if url == discovery_url:
            return discovery_body
        if url == idcs_jwks_url:
            return jwks_body
        raise AssertionError(f"unexpected fetch to {url!r}")

    install_jwks_stub(monkeypatch, responder=_responder)
    # End-to-end: an RS256 token signed by the test key validates against
    # the JWKS fetched from the IDCS-style path.
    payload = _decode_token(make_token())
    assert payload["sub"] == "42"


def test_oidc_discovery_404_raises_jwks_error(auth_enabled, monkeypatch):
    """A 404 (or any URLError) on the discovery endpoint surfaces as
    JwksError with the issuer in the message — operators need to know
    which discovery URL broke."""
    from urllib.error import HTTPError

    def _fake_open(url, timeout=None):  # noqa: ARG001
        raise HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(jwks._opener, "open", _fake_open)
    reset_cache()
    with pytest.raises(JwksError, match="OIDC discovery failed"):
        get_signing_key(TEST_ISSUER, TEST_KID)


def test_oidc_discovery_missing_jwks_uri_raises(auth_enabled, monkeypatch):
    """A discovery doc without ``jwks_uri`` is malformed — fail closed."""
    discovery_url = TEST_ISSUER + "/.well-known/openid-configuration"
    body = json.dumps({"issuer": TEST_ISSUER}).encode()

    def _responder(url: str) -> bytes:
        if url == discovery_url:
            return body
        raise AssertionError(f"unexpected fetch to {url!r}")

    install_jwks_stub(monkeypatch, responder=_responder)
    with pytest.raises(JwksError, match="missing jwks_uri"):
        get_signing_key(TEST_ISSUER, TEST_KID)


def test_oidc_discovery_malformed_json_raises(auth_enabled, monkeypatch):
    discovery_url = TEST_ISSUER + "/.well-known/openid-configuration"

    def _responder(url: str) -> bytes:
        if url == discovery_url:
            return b"<html>not json</html>"
        raise AssertionError(f"unexpected fetch to {url!r}")

    install_jwks_stub(monkeypatch, responder=_responder)
    with pytest.raises(JwksError, match="invalid JSON"):
        get_signing_key(TEST_ISSUER, TEST_KID)


def test_oidc_discovery_non_https_jwks_uri_rejected(auth_enabled, monkeypatch):
    """A discovery doc that points at an ``http://`` JWKS URL is rejected
    — TLS verification is required on the public path. The local override is
    the only http-allowed seam, and it bypasses discovery entirely."""
    discovery_url = TEST_ISSUER + "/.well-known/openid-configuration"
    body = json.dumps(
        {"issuer": TEST_ISSUER, "jwks_uri": "http://attacker.example.com/jwks"}
    ).encode()

    def _responder(url: str) -> bytes:
        if url == discovery_url:
            return body
        raise AssertionError(f"unexpected fetch to {url!r}")

    install_jwks_stub(monkeypatch, responder=_responder)
    with pytest.raises(JwksError, match="must use https"):
        get_signing_key(TEST_ISSUER, TEST_KID)


def test_oidc_discovery_doc_cached_across_kid_refreshes(auth_enabled, monkeypatch):
    """The discovery doc cache is separate from the JWKS cache, so a kid-miss
    refresh on the JWKS doesn't re-fetch discovery — the JWKS URL doesn't
    change between rotations."""
    counter = [0]
    discovery_counter = [0]
    install_jwks_stub(monkeypatch, counter=counter, discovery_counter=discovery_counter)

    # Prime: 1 discovery + 1 JWKS.
    get_signing_key(TEST_ISSUER, TEST_KID)
    assert discovery_counter[0] == 1

    # Kid-miss: 1 more JWKS fetch, but discovery stays cached.
    with pytest.raises(JwksError):
        get_signing_key(TEST_ISSUER, "kid-never-issued")
    assert discovery_counter[0] == 1


def test_oidc_discovery_local_override_bypasses_discovery(monkeypatch):
    """When the operator pins ``auth_local_jwks_url``, discovery is skipped —
    the operator already knows the URL."""
    public_issuer = "https://public.example.com/auth"
    local_url = "http://auth-service:8080/auth/.well-known/jwks.json"
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", public_issuer)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", "cuopt")
    monkeypatch.setattr(settings, "auth_local_issuer_url", public_issuer)
    monkeypatch.setattr(settings, "auth_local_jwks_url", local_url)

    body = json.dumps(jwks_document()).encode()
    fetched: list[str] = []

    def _fake_local(url, timeout=None):  # noqa: ARG001
        fetched.append(url)
        return _FakeResponse(body)

    def _fake_public(url, timeout=None):  # noqa: ARG001
        raise AssertionError(f"public opener (incl. discovery) must not be hit; got {url!r}")

    monkeypatch.setattr(jwks._local_opener, "open", _fake_local)
    monkeypatch.setattr(jwks._opener, "open", _fake_public)
    reset_cache()

    get_signing_key(public_issuer, TEST_KID)
    # Only the local JWKS URL was fetched — no discovery roundtrip.
    assert fetched == [local_url]


def test_oidc_discovery_per_issuer_jwks_uris(monkeypatch):
    """Multi-issuer: each trusted issuer's discovery doc resolves its own
    jwks_uri. Pins that the per-issuer cache is keyed correctly."""
    issuer_a = "https://a.example.com/auth"
    issuer_b = "https://b.example.com/auth"
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", f"{issuer_a},{issuer_b}")
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", "cuopt")

    private_a, private_a_pem, _ = _generate_keypair()
    private_b, private_b_pem, _ = _generate_keypair()
    kid_a = "kid-a"
    kid_b = "kid-b"

    # A uses a "standard" path; B uses an IDCS-style path. Both work.
    jwks_a_url = issuer_a + "/.well-known/jwks.json"
    jwks_b_url = issuer_b + "/admin/v1/SigningCert/jwk"

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
        f"{issuer_a}/.well-known/openid-configuration": json.dumps(
            {"issuer": issuer_a, "jwks_uri": jwks_a_url}
        ).encode(),
        f"{issuer_b}/.well-known/openid-configuration": json.dumps(
            {"issuer": issuer_b, "jwks_uri": jwks_b_url}
        ).encode(),
        jwks_a_url: json.dumps({"keys": [jwk_a]}).encode(),
        jwks_b_url: json.dumps({"keys": [jwk_b]}).encode(),
    }

    def _responder(url: str) -> bytes:
        if url not in bodies:
            raise AssertionError(f"unexpected fetch to {url!r}")
        return bodies[url]

    install_jwks_stub(monkeypatch, responder=_responder)
    # Token from each issuer validates against its own JWKS.
    _decode_token(make_token(issuer=issuer_a, kid=kid_a, private_pem=private_a_pem))
    _decode_token(make_token(issuer=issuer_b, kid=kid_b, private_pem=private_b_pem))

    # An issuer-a token signed with B's key fails — pins that the per-issuer
    # caches are not cross-contaminated.
    with pytest.raises(HTTPException) as exc:
        _decode_token(make_token(issuer=issuer_a, kid=kid_b, private_pem=private_b_pem))
    assert exc.value.status_code == 401


# --- Untrusted issuers don't reach discovery -----------------------------------


def test_untrusted_issuer_rejected_before_discovery(monkeypatch):
    """A token whose ``iss`` isn't in the allowlist must fail before any
    network IO — discovery wouldn't reach an attacker URL."""
    monkeypatch.setattr(settings, "auth_trusted_issuers", TEST_ISSUER)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)

    def _no_io(url, timeout=None):  # noqa: ARG001
        raise AssertionError(f"discovery must not run for untrusted issuer; got {url!r}")

    monkeypatch.setattr(jwks._opener, "open", _no_io)
    reset_cache()
    with pytest.raises(JwksError, match="untrusted issuer"):
        get_signing_key("https://attacker.example.com/auth", TEST_KID)


# --- Sanity: tokens minted by make_token's defaults still pass through ---------


def test_default_token_with_default_audience_passes_through(auth_enabled):
    """Sanity: the test helper's defaults align with the production
    auth_token_audience default — protects against accidental drift."""
    token = make_token()
    payload = _decode_token(token)
    assert payload["aud"] == "cuopt"
    assert payload["sub"] == "42"
    assert TEST_PRIVATE_PEM  # imported for clarity
