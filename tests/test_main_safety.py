# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for the startup safety validator in main._validate_safety."""

import pytest

from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.main import _validate_safety


def test_validate_safety_passes_with_synthetic_admin_in_debug(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", False)
    monkeypatch.setattr(settings, "debug", True)
    _validate_safety()


def test_validate_safety_passes_with_auth_on_and_trusted_issuers_set(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", "https://issuer.test/auth")
    monkeypatch.setattr(settings, "debug", False)
    _validate_safety()


def test_validate_safety_refuses_auth_off_in_production(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", False)
    monkeypatch.setattr(settings, "debug", False)
    with pytest.raises(RuntimeError, match="CUOPT_AUTH_REQUIRE_AUTH=false"):
        _validate_safety()


def test_validate_safety_refuses_auth_on_with_empty_trusted_issuers(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", "")
    with pytest.raises(RuntimeError, match="CUOPT_AUTH_TRUSTED_ISSUERS to be set"):
        _validate_safety()


def test_validate_safety_refuses_auth_on_with_whitespace_only_trusted_issuers(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", "   ")
    with pytest.raises(RuntimeError, match="CUOPT_AUTH_TRUSTED_ISSUERS to be set"):
        _validate_safety()
