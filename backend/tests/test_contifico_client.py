import os
import sys
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contifico import (
    ContificoAPIError,
    ContificoClient,
    ContificoConfigurationError,
)


def test_client_requires_key_and_token() -> None:
    with pytest.raises(ContificoConfigurationError):
        ContificoClient("", "token")

    with pytest.raises(ContificoConfigurationError):
        ContificoClient("key", "")


def test_list_products_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        captured["api_token"] = request.headers.get("X-Api-Token")
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[{"id": 1, "codigo": "SKU-1"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "pos-token-abc",
        base_url="https://api.example.com/v1",
        transport=transport,
    )

    products = list(client.list_products(page=2, page_size=50))

    assert products == [{"id": 1, "codigo": "SKU-1"}]
    assert captured["authorization"] == "key123"
    assert captured["api_token"] == "pos-token-abc"
    assert client.api_token == "pos-token-abc"
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["result_page"] == "2"
    assert params["result_size"] == "50"
    assert str(captured["url"]).startswith("https://api.example.com/v1/producto/")


def test_list_products_error_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"mensaje": "No autorizado"})

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    with pytest.raises(ContificoAPIError) as exc_info:
        list(client.list_products())

    assert exc_info.value.status_code == 401
    assert "No autorizado" in exc_info.value.detail


def test_list_warehouses_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/bodega/")
        assert request.headers.get("Authorization") == "key123"
        assert request.headers.get("X-Api-Token") == "token-xyz"
        return httpx.Response(200, json=[{"id": 10, "codigo": "BOD"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    warehouses = list(client.list_warehouses())

    assert warehouses == [{"id": 10, "codigo": "BOD"}]
