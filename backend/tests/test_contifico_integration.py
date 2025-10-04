import json
import os
import sys
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations import (  # noqa: E402
    ContificoClient,
    ContificoPermanentError,
    ContificoTransientError,
)


def build_contifico_client(handler, *, company_id: str | None = "EMP-001", **kwargs):
    client = ContificoClient(
        base_url="https://api.example.com/sistema/api/v1",
        api_key="key-123",
        api_token="token-abc",
        max_retries=0,
        rate_limit_per_minute=100,
        sleep_func=lambda _seconds: None,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        company_id=company_id,
        **kwargs,
    )
    return client


def test_create_invoice_builds_expected_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("authorization")
        captured["accept"] = request.headers.get("accept")
        captured["content-type"] = request.headers.get("content-type")
        captured["api-token"] = request.headers.get("api-token")
        captured["json"] = json.loads(request.content.decode())
        captured["params"] = dict(request.url.params)
        return httpx.Response(201, json={"id": "INV-1"})

    client = build_contifico_client(handler)
    response = client.create_invoice({"total": 100})

    assert response == {"id": "INV-1"}
    assert captured["path"] == "/sistema/api/v1/documento/"
    assert captured["authorization"] == "key-123"
    assert captured["accept"] == "application/json"
    assert captured["content-type"] == "application/json; charset=UTF-8"
    assert captured["api-token"] == "token-abc"
    assert captured["json"] == {"total": 100}
    assert captured["params"] == {}


def test_update_invoice_sends_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"status": "ok"})

    client = build_contifico_client(handler)
    response = client.update_invoice("INV-2", {"total": 200})

    assert response == {"status": "ok"}
    assert captured["path"] == "/sistema/api/v1/documento/"
    assert captured["json"] == {"id": "INV-2", "total": 200}
    assert captured["params"] == {}


def test_get_invoice_fetches_specific_document():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"id": "INV-25"})

    client = build_contifico_client(handler)
    response = client.get_invoice("INV-25")

    assert response == {"id": "INV-25"}
    assert captured["path"] == "/sistema/api/v1/documento/INV-25/"
    assert captured["params"] == {"empresa": "EMP-001", "empresa_id": "EMP-001"}


def test_get_invoice_by_numero_includes_company_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"id": "001-001-000123456"})

    client = build_contifico_client(handler)
    response = client.get_invoice("001-001-000123456", customer_document="0991234567")

    assert response == {"id": "001-001-000123456"}
    assert captured["path"].endswith("/documento/")
    assert captured["params"]["numero"] == "001-001-000123456"
    assert captured["params"]["establecimiento"] == "001"
    assert captured["params"]["pto_emision"] == "001"
    assert captured["params"]["secuencial"] == "000123456"
    assert captured["params"]["empresa"] == "EMP-001"


def test_get_invoice_falls_back_to_persona_lookup():
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/sistema/api/v1/documento/":
            return httpx.Response(504, text="timeout")
        if request.url.path.endswith("/registro/documento/"):
            payload = {
                "results": [
                    {
                        "numero": "001-005-000012717",
                        "documento": "abc123",
                    }
                ]
            }
            return httpx.Response(200, json=payload)
        if request.url.path.endswith("/documento/abc123/"):
            return httpx.Response(200, json={"id": "abc123", "numero": "001-005-000012717"})
        raise AssertionError(f"Unexpected path: {request.url.path}")

    client = build_contifico_client(handler)
    response = client.get_invoice(
        "001-005-000012717",
        customer_document="0999999999",
    )

    assert response == {"id": "abc123", "numero": "001-005-000012717"}
    assert requested_paths == [
        "/sistema/api/v1/documento/",
        "/sistema/api/v1/registro/documento/",
        "/sistema/api/v1/documento/abc123/",
    ]


def test_get_customer_by_document_sets_query_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    client = build_contifico_client(handler)
    client.get_customer_by_document("0909090909")

    assert (
        captured["url"]
        == "https://api.example.com/sistema/api/v1/persona/?identificacion=0909090909&empresa=EMP-001"
    )
    assert captured["params"]["identificacion"] == "0909090909"
    assert captured["params"]["empresa"] == "EMP-001"


def test_omits_company_params_when_not_configured():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    client = build_contifico_client(handler, company_id=None)
    client.get_customer_by_document("0101010101")

    assert captured["params"] == {"identificacion": "0101010101"}


def test_raises_transient_on_rate_limit():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "too many"})

    client = build_contifico_client(handler)

    with pytest.raises(ContificoTransientError):
        client.get_customer_by_document("0909090909")


def test_raises_permanent_on_client_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad request"})

    client = build_contifico_client(handler)

    with pytest.raises(ContificoPermanentError):
        client.create_invoice({})


def test_does_not_retry_permanent_error(monkeypatch):
    call_count = {"value": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["value"] += 1
        return httpx.Response(401, json={"detail": "unauthorized"})

    client = ContificoClient(
        base_url="https://api.example.com",
        api_key="key-123",
        api_token="token-abc",
        max_retries=3,
        retry_backoff_seconds=0,
        rate_limit_per_minute=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_func=lambda _seconds: None,
    )

    with pytest.raises(ContificoPermanentError):
        client.create_invoice({})

    assert call_count["value"] == 1


def test_retries_and_then_raises_transient_on_request_error(monkeypatch):
    call_count = {"value": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["value"] += 1
        raise httpx.ConnectError("boom", request=_request)

    transport = httpx.MockTransport(handler)
    mock_httpx_client = httpx.Client(transport=transport)

    client = ContificoClient(
        base_url="https://api.example.com",
        api_key="key-123",
        api_token="token-abc",
        max_retries=1,
        retry_backoff_seconds=0,
        rate_limit_per_minute=100,
        client=mock_httpx_client,
        sleep_func=lambda _seconds: None,
    )

    with pytest.raises(ContificoTransientError):
        client.get_customer_by_document("0909090909")

    assert call_count["value"] == 2
