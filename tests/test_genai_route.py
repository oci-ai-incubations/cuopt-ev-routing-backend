# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for /api/models, /api/genai/chat, /api/genai/health and the format helpers."""

import httpx
import pytest

from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.services import genai as genai_service

LLAMA = "http://llamastack.example.com"


@pytest.fixture(autouse=True)
def llama_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "llamastack_endpoint", LLAMA)
    monkeypatch.setattr(settings, "llamastack_model", "test-model")


def test_transform_includes_model_default():
    out = genai_service.transform_to_llamastack_format(
        {"messages": [{"role": "USER", "content": [{"type": "TEXT", "text": "hi"}]}]}
    )
    assert out["model"] == "test-model"
    assert out["instructions"] == "You are a helpful assistant"
    assert out["input"] == [{"role": "user", "content": "hi"}]
    assert out["stream"] is False


def test_transform_extracts_system_message():
    out = genai_service.transform_to_llamastack_format(
        {
            "messages": [
                {"role": "SYSTEM", "content": "be terse"},
                {"role": "USER", "content": "hi"},
            ],
            "model": "override-model",
        }
    )
    assert out["instructions"] == "be terse"
    assert out["model"] == "override-model"
    assert out["input"] == [{"role": "user", "content": "hi"}]


def test_extract_response_text_output_text():
    assert genai_service.extract_response_text({"output_text": "hello"}) == "hello"


def test_extract_response_text_output_items():
    data = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "part1 "},
                    {"type": "text", "text": "part2"},
                ],
            }
        ]
    }
    assert genai_service.extract_response_text(data) == "part1 part2"


def test_extract_response_text_choices_fallback():
    data = {"choices": [{"message": {"content": "fallback"}}]}
    assert genai_service.extract_response_text(data) == "fallback"


def test_extract_response_text_empty():
    assert genai_service.extract_response_text({}) == ""


def test_models_filters_to_llm_only(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{LLAMA}/v1/models",
        method="GET",
        json={
            "data": [
                {"id": "a", "custom_metadata": {"model_type": "llm"}},
                {"id": "b", "custom_metadata": {"model_type": "embedding"}},
                {"id": "c", "custom_metadata": {"model_type": "llm"}},
            ]
        },
        status_code=200,
    )
    resp = client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert {m["id"] for m in data["data"]} == {"a", "c"}


def test_models_upstream_error(client, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"), url=f"{LLAMA}/v1/models", method="GET")
    resp = client.get("/api/models")
    assert resp.status_code == 503


def test_models_upstream_non_200(client, httpx_mock):
    httpx_mock.add_response(url=f"{LLAMA}/v1/models", method="GET", status_code=502, text="bad")
    resp = client.get("/api/models")
    assert resp.status_code == 502


def test_chat_returns_frontend_envelope(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{LLAMA}/v1/responses",
        method="POST",
        json={"output_text": "answer", "usage": {"input_tokens": 5, "output_tokens": 3}},
        status_code=200,
    )
    payload = {
        "chatRequest": {"messages": [{"role": "USER", "content": [{"type": "TEXT", "text": "hi"}]}]}
    }
    resp = client.post("/api/genai/chat", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["chatResponse"]["text"] == "answer"
    assert body["usageMetadata"] == {"inputTokenCount": 5, "outputTokenCount": 3}


def test_chat_upstream_error(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{LLAMA}/v1/responses", method="POST", status_code=502, text="bad gateway"
    )
    payload = {"chatRequest": {"messages": []}}
    resp = client.post("/api/genai/chat", json=payload)
    assert resp.status_code == 502
    assert resp.json()["error"] == "LlamaStack error"


def test_chat_connection_error(client, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"), url=f"{LLAMA}/v1/responses", method="POST")
    resp = client.post("/api/genai/chat", json={"chatRequest": {"messages": []}})
    assert resp.status_code == 500


def test_genai_health_connected(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{LLAMA}/v1/models", method="GET", json={"data": []}, status_code=200
    )
    resp = client.get("/api/genai/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"


def test_genai_health_unavailable(client, httpx_mock):
    httpx_mock.add_response(url=f"{LLAMA}/v1/models", method="GET", status_code=503, text="x")
    resp = client.get("/api/genai/health")
    assert resp.status_code == 503


def test_genai_health_disconnected(client, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"), url=f"{LLAMA}/v1/models", method="GET")
    resp = client.get("/api/genai/health")
    assert resp.status_code == 503
