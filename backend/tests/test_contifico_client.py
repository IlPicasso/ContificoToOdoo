import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contifico import (
    ContificoAPIError,
    ContificoClient,
    ContificoConfigurationError,
    ContificoTransportError,
)
from app.temp_contifico import build_product_page, build_warehouse_list


def test_client_requires_key_and_token() -> None:
    with pytest.raises(ContificoConfigurationError):
        ContificoClient("", "token")

    with pytest.raises(ContificoConfigurationError):
        ContificoClient("key", "")


def test_list_products_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
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


def test_build_product_page_success() -> None:
    class StubClient:
        def list_products(self, *, page: int, page_size: int):
            assert page == 2
            assert page_size == 5
            return [
                {"id": 1, "nombre": "Camisa"},
                {"id": 2, "nombre": "Pantalón"},
            ]

    result = build_product_page(StubClient(), page=2, page_size=5)

    assert result.page == 2
    assert result.page_size == 5
    assert len(result.items) == 2
    assert result.items[0].nombre == "Camisa"


def test_build_product_page_raises_http_exception() -> None:
    class StubClient:
        def list_products(self, *, page: int, page_size: int):
            raise ContificoTransportError("Network error")

    with pytest.raises(HTTPException) as exc_info:
        build_product_page(StubClient(), page=1, page_size=25)

    assert exc_info.value.status_code == 503
    assert "Network error" in exc_info.value.detail


def test_build_warehouse_list_success() -> None:
    class StubClient:
        def list_warehouses(self):
            return [{"id": 1, "nombre": "Matriz"}]

    result = build_warehouse_list(StubClient())

    assert len(result) == 1
    assert result[0].nombre == "Matriz"


def test_build_warehouse_list_propagates_http_error() -> None:
    class StubClient:
        def list_warehouses(self):
            raise ContificoAPIError(400, "Bad request")

    with pytest.raises(HTTPException) as exc_info:
        build_warehouse_list(StubClient())

    assert exc_info.value.status_code == 400
    assert "Bad request" in exc_info.value.detail
