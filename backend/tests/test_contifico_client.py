import logging
import json
import os
import sys
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, status

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import schemas
from app import contifico as contifico_module
from app.contifico import (
    ContificoAPIError,
    ContificoClient,
    ContificoConfigurationError,
    ContificoTransportError,
)
from app.temp_contifico import (
    build_invoice_page,
    build_product_page,
    build_warehouse_list,
    fetch_invoice_by_document_number,
)


def test_client_requires_key_and_token() -> None:
    with pytest.raises(ContificoConfigurationError):
        ContificoClient("", "token")

    with pytest.raises(ContificoConfigurationError):
        ContificoClient("key", "")


def test_contifico_logger_emits_to_console() -> None:
    stream_handlers = [
        handler
        for handler in contifico_module.logger.handlers
        if isinstance(handler, logging.StreamHandler)
    ]
    assert stream_handlers, "contifico logger should stream to console"
    for handler in stream_handlers:
        assert handler.level in (logging.NOTSET, logging.INFO)
    assert contifico_module.logger.level == logging.INFO
    assert not contifico_module.logger.propagate


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


def test_list_invoices_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        assert request.url.path.endswith("/registro/documento/")
        return httpx.Response(200, json=[{"id": "inv-1", "numero": "001-001-0000001"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoices = list(
        client.list_invoices(
            page=3,
            page_size=25,
            customer_document="0912345678",
            document_number="001-001-0000001",
        )
    )

    assert len(invoices) == 1
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["result_page"] == "3"
    assert params["result_size"] == "25"
    assert params["tipo_registro"] == "CLI"
    assert params["tipo"] == "FAC"
    assert params["persona_identificacion"] == "0912345678"
    assert params["documento"] == "001-001-0000001"


def test_list_invoices_recovers_from_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, str]] = []
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ContificoClient, "_sleep", staticmethod(fake_sleep))

    attempts_by_size: dict[int, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requests.append(params)
        size = int(params["result_size"])
        attempts_by_size[size] = attempts_by_size.get(size, 0) + 1
        if size == 25:
            return httpx.Response(HTTPStatus.BAD_GATEWAY, json={"mensaje": "Bad"})
        assert size == 10, f"Unexpected fallback size: {size}"
        return httpx.Response(200, json=[{"id": "inv-1", "numero": "001-001-0000001"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoices = list(client.list_invoices(page_size=25))

    assert invoices == [{"id": "inv-1", "numero": "001-001-0000001"}]
    assert [params["result_size"] for params in requests] == ["25", "25", "25", "10"]
    assert attempts_by_size[25] == ContificoClient.INVOICE_LOOKUP_SERVER_RETRIES + 1
    assert attempts_by_size[10] == 1
    assert sleeps == [
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE,
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE * 2,
    ]


def test_list_invoices_raises_last_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ContificoClient, "_sleep", staticmethod(fake_sleep))

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(HTTPStatus.BAD_GATEWAY, json={"mensaje": "Bad"})

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    with pytest.raises(ContificoAPIError) as exc_info:
        list(client.list_invoices(page_size=5))

    assert exc_info.value.status_code == HTTPStatus.BAD_GATEWAY
    assert sleeps == [
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE,
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE * 2,
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE,
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE * 2,
    ]


def test_list_invoices_requires_list_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"detalle": "unexpected"})

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    with pytest.raises(ContificoAPIError) as exc_info:
        list(client.list_invoices())

    assert "facturas" in exc_info.value.detail


def test_list_invoices_by_customer_document_validates_input() -> None:
    client = ContificoClient("key", "token")

    with pytest.raises(ValueError):
        list(client.list_invoices_by_customer_document(""))


def test_find_invoice_by_document_number_returns_matching_invoice() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000001/"):
            return httpx.Response(200, json={"id": 1, "numero": "001-001-0000001"})
        raise AssertionError("Unexpected request")

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000001")

    assert invoice == {"id": 1, "numero": "001-001-0000001"}


def test_find_invoice_by_document_number_strips_prefix_and_spaces() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/registro/documento/001-001-0000001/"):
            return httpx.Response(200, json={"id": 7, "numero_documento": "FAC0010010000001"})
        raise AssertionError("Unexpected request")

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("  FAC  001-001-0000001  ")

    assert invoice == {"id": 7, "numero_documento": "FAC0010010000001"}
    assert seen == ["/registro/documento/001-001-0000001/"]


def test_find_invoice_by_document_number_retries_with_original_value() -> None:
    captured: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000001/"):
            captured.append(("direct", {}))
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No"})
        params = dict(request.url.params)
        captured.append(("paged", params))
        if params.get("documento") == "FAC 001-001-0000001":
            return httpx.Response(
                200,
                json=[
                    {"id": 5, "numero": "FAC 001-001-0000001"},
                ],
            )
        raise AssertionError("Unexpected parameters")

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("FAC 001-001-0000001")

    assert invoice == {"id": 5, "numero": "FAC 001-001-0000001"}
    assert captured[0][0] == "direct"
    assert captured[1][1]["documento"] == "FAC 001-001-0000001"
    assert captured[1][1]["numero"] == "001-001-0000001"


def test_find_invoice_by_document_number_direct_server_error_falls_back() -> None:
    requests: list[dict[str, str] | dict[str, bool]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000009/"):
            requests.append({"direct": True})
            return httpx.Response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                json={"mensaje": "Busy"},
            )
        params = dict(request.url.params)
        requests.append(params)
        assert params.get("result_page") == "1"
        return httpx.Response(200, json=[{"id": 9, "numero": "001-001-0000009"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000009")

    assert invoice == {"id": 9, "numero": "001-001-0000009"}
    assert requests[0] == {"direct": True}
    assert requests[1]["result_page"] == "1"


def test_find_invoice_by_document_number_direct_transport_error_falls_back() -> None:
    requests: list[dict[str, str] | dict[str, bool]] = []
    direct_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000011/"):
            nonlocal direct_attempts
            direct_attempts += 1
            raise httpx.ConnectError("boom", request=request)
        params = dict(request.url.params)
        requests.append(params)
        assert params.get("result_page") == "1"
        return httpx.Response(200, json=[{"id": 11, "numero": "001-001-0000011"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000011")

    assert invoice == {"id": 11, "numero": "001-001-0000011"}
    assert direct_attempts == 1
    assert requests[0]["result_page"] == "1"


def test_find_invoice_by_document_number_fetches_multiple_pages() -> None:
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000005/"):
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No"})
        params = dict(request.url.params)
        page = int(params.get("result_page", 1))
        pages.append(page)
        if page == 1:
            invoices = [
                {"id": idx, "numero": f"001-001-0001{idx:03d}"}
                for idx in range(200)
            ]
            return httpx.Response(200, json=invoices)
        if page == 2:
            return httpx.Response(
                200,
                json=[
                    {"id": 2, "numero": "FAC 001-001-0000005"},
                ],
            )
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("FAC 001-001-0000005")

    assert invoice == {"id": 2, "numero": "FAC 001-001-0000005"}
    assert pages == [1, 2]


def test_find_invoice_by_document_number_falls_back_to_smaller_page_size(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, str]] = []
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ContificoClient, "_sleep", staticmethod(fake_sleep))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000001/"):
            requests.append({"direct": True})
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No"})
        params = dict(request.url.params)
        requests.append(params)
        if params.get("result_size") == str(ContificoClient.INVOICE_LOOKUP_PAGE_SIZE):
            return httpx.Response(status.HTTP_504_GATEWAY_TIMEOUT, json={"mensaje": "Timeout"})
        assert params.get("result_size") == str(ContificoClient.INVOICE_LOOKUP_FALLBACK_PAGE_SIZES[0])
        return httpx.Response(200, json=[{"id": 3, "numero": "001-001-0000001"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000001")

    assert invoice == {"id": 3, "numero": "001-001-0000001"}
    default_size = str(ContificoClient.INVOICE_LOOKUP_PAGE_SIZE)
    fallback_size = str(ContificoClient.INVOICE_LOOKUP_FALLBACK_PAGE_SIZES[0])
    assert [params.get("result_size") for params in requests] == [
        None,
        default_size,
        default_size,
        default_size,
        fallback_size,
    ]
    assert sleeps == [
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE,
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE * 2,
    ]


def test_find_invoice_by_document_number_retries_before_returning(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, str]] = []
    sleeps: list[float] = []
    fallback_calls = 0

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ContificoClient, "_sleep", staticmethod(fake_sleep))

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fallback_calls
        if request.url.path.endswith("/registro/documento/001-001-0000001/"):
            requests.append({"direct": True})
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "Timeout"})
        params = dict(request.url.params)
        requests.append(params)
        fallback_calls += 1
        if fallback_calls < 3:
            return httpx.Response(status.HTTP_504_GATEWAY_TIMEOUT, json={"mensaje": "Timeout"})
        return httpx.Response(200, json=[{"id": 11, "numero": "001-001-0000001"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000001")

    assert invoice == {"id": 11, "numero": "001-001-0000001"}
    default_size = str(ContificoClient.INVOICE_LOOKUP_PAGE_SIZE)
    assert [params.get("result_size") for params in requests] == [
        None,
        default_size,
        default_size,
        default_size,
    ]
    assert sleeps == [
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE,
        ContificoClient.INVOICE_LOOKUP_RETRY_BACKOFF_BASE * 2,
    ]


def test_find_invoice_by_document_number_tries_compact_candidate_after_failures() -> None:
    requests: list[dict[str, str] | str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000022/"):
            requests.append("direct")
            return httpx.Response(status.HTTP_504_GATEWAY_TIMEOUT, json={"mensaje": "Timeout"})

        params = dict(request.url.params)
        requests.append(params)
        if params.get("documento") == "001-001-0000022":
            return httpx.Response(status.HTTP_504_GATEWAY_TIMEOUT, json={"mensaje": "Timeout"})

        assert params.get("documento") == "0010010000022"
        return httpx.Response(200, json=[{"id": 22, "numero": "001-001-0000022"}])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000022")

    assert invoice == {"id": 22, "numero": "001-001-0000022"}
    assert requests[0] == "direct"
    fallback_requests = [
        params for params in requests[1:] if isinstance(params, dict)
    ]
    assert fallback_requests
    assert any(params.get("documento") == "001-001-0000022" for params in fallback_requests)
    assert fallback_requests[-1].get("documento") == "0010010000022"


def test_find_invoice_by_document_number_retries_after_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, str] | str] = []
    sleep_calls: list[float] = []
    cooldowns = 0

    def fake_sleep(seconds: float) -> None:
        nonlocal cooldowns
        sleep_calls.append(seconds)
        if seconds >= ContificoClient.INVOICE_LOOKUP_SERVER_COOLDOWN_BASE:
            cooldowns += 1

    monkeypatch.setattr(ContificoClient, "_sleep", staticmethod(fake_sleep))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000033/"):
            requests.append("direct")
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No"})

        params = dict(request.url.params)
        requests.append(params)

        if cooldowns == 0:
            return httpx.Response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                json={"mensaje": "Timeout"},
            )

        return httpx.Response(
            200,
            json=[{"id": 33, "numero": "001-001-0000033"}],
        )

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000033")

    assert invoice == {"id": 33, "numero": "001-001-0000033"}
    assert requests[0] == "direct"
    assert cooldowns == 1
    assert any(
        call >= ContificoClient.INVOICE_LOOKUP_SERVER_COOLDOWN_BASE
        for call in sleep_calls
    )
    fallback_requests = [params for params in requests[1:] if isinstance(params, dict)]
    assert fallback_requests
    assert len(fallback_requests) > 1
    assert any(
        params.get("documento") == "0010010000033" for params in fallback_requests
    )
    assert fallback_requests[-1].get("documento") == "001-001-0000033"


def test_find_invoice_by_document_number_downloads_catalog_after_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, dict[str, str]]] = []
    catalog_requests: list[dict[str, str]] = []
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ContificoClient, "_sleep", staticmethod(fake_sleep))

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.url.path.endswith("/registro/documento/001-001-0000044/"):
            requests.append(("direct", {}))
            return httpx.Response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                json={"mensaje": "Timeout"},
            )
        if request.url.path.endswith("/registro/documento/"):
            if params.get("documento") in {"001-001-0000044", "0010010000044"}:
                requests.append(("search", params))
                return httpx.Response(
                    status.HTTP_504_GATEWAY_TIMEOUT,
                    json={"mensaje": "Timeout"},
                )
            if "documento" not in params:
                catalog_requests.append(params)
                assert params.get("result_page") == "1"
                return httpx.Response(
                    200,
                    json=[
                        {"id": 44, "numero": "001-001-0000044"},
                        {"id": 45, "numero": "001-001-0000045"},
                    ],
                )
        raise AssertionError("Unexpected request")

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    client.INVOICE_LOOKUP_PAGE_SIZE = 1
    client.INVOICE_LOOKUP_FALLBACK_PAGE_SIZES = ()
    client.INVOICE_LOOKUP_MAX_PAGES = 1
    client.INVOICE_LOOKUP_SERVER_RETRIES = 0
    client.INVOICE_LOOKUP_SERVER_FAILURE_ATTEMPTS = 0
    client.INVOICE_LOOKUP_CATALOG_PAGE_SIZE = 2
    client.INVOICE_LOOKUP_CATALOG_MAX_PAGES = 1
    client.INVOICE_LOOKUP_CATALOG_SERVER_RETRIES = 0

    invoice = client.find_invoice_by_document_number("001-001-0000044")

    assert invoice == {"id": 44, "numero": "001-001-0000044"}
    assert requests
    assert requests[0][0] == "direct"
    assert any(kind == "search" for kind, _ in requests)
    assert catalog_requests == [{"result_page": "1", "result_size": "2", "tipo_registro": "CLI", "tipo": "FAC"}]
    assert client._invoice_catalog_complete is True
    assert "001-001-0000044" in client._invoice_cache
    assert sleeps == []


def test_find_invoice_by_document_number_reuses_catalog_without_http() -> None:
    catalog_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal catalog_calls
        params = dict(request.url.params)
        if request.url.path.endswith("/registro/documento/001-001-0000045/"):
            return httpx.Response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                json={"mensaje": "Timeout"},
            )
        if "documento" not in params:
            catalog_calls += 1
            return httpx.Response(
                200,
                json=[{"id": 45, "numero": "001-001-0000045"}],
            )
        return httpx.Response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            json={"mensaje": "Timeout"},
        )

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    client.INVOICE_LOOKUP_PAGE_SIZE = 1
    client.INVOICE_LOOKUP_FALLBACK_PAGE_SIZES = ()
    client.INVOICE_LOOKUP_MAX_PAGES = 1
    client.INVOICE_LOOKUP_SERVER_RETRIES = 0
    client.INVOICE_LOOKUP_SERVER_FAILURE_ATTEMPTS = 0
    client.INVOICE_LOOKUP_CATALOG_PAGE_SIZE = 1
    client.INVOICE_LOOKUP_CATALOG_MAX_PAGES = 1
    client.INVOICE_LOOKUP_CATALOG_SERVER_RETRIES = 0

    invoice = client.find_invoice_by_document_number("001-001-0000045")
    assert invoice == {"id": 45, "numero": "001-001-0000045"}
    assert catalog_calls == 1

    def failing_handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP should not be called when catalog is cached")

    client._transport = httpx.MockTransport(failing_handler)

    cached_invoice = client.find_invoice_by_document_number("001-001-0000045")
    assert cached_invoice == {"id": 45, "numero": "001-001-0000045"}

def test_find_invoice_lookup_uses_persistent_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "invoices.json"
    cache_path.write_text(
        json.dumps({"001-001-0000007": {"id": 7, "numero": "001-001-0000007"}}),
        encoding="utf-8",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP should not be called when the invoice exists in the cache")

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
        invoice_cache_path=cache_path,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000007")
    assert invoice == {"id": 7, "numero": "001-001-0000007"}


def test_find_invoice_lookup_persists_results(tmp_path: Path) -> None:
    cache_path = tmp_path / "persist.json"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000008/"):
            return httpx.Response(200, json={"id": 8, "numero": "001-001-0000008"})
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
        invoice_cache_path=cache_path,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000008")
    assert invoice == {"id": 8, "numero": "001-001-0000008"}

    persisted = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "001-001-0000008" in persisted
    assert persisted["001-001-0000008"]["numero"] == "001-001-0000008"


def test_find_invoice_by_document_number_emits_progress_events() -> None:
    events: list[tuple[str, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/registro/documento/001-001-0000099/")
        return httpx.Response(200, json={"id": 99, "numero": "001-001-0000099"})

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number(
        "001-001-0000099",
        progress_callback=lambda stage, payload: events.append(
            (stage, int(payload.get("progress", 0)))
        ),
    )

    assert invoice == {"id": 99, "numero": "001-001-0000099"}
    assert events[0][0] == "start"
    assert events[-1][0] == "direct_lookup_success"
    assert events[-1][1] == 100
    progress_values = [progress for _, progress in events]
    assert progress_values == sorted(progress_values)


def test_find_invoice_by_document_number_handles_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000002/"):
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No"})
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000002")

    assert invoice is None


def test_find_invoice_by_document_number_returns_none_when_no_match() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000005/"):
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No"})
        return httpx.Response(
            200,
            json=[
                {"id": 1, "numero": "001-001-0000003"},
                {"id": 2, "numero": "001-001-0000004"},
            ],
        )

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000005")

    assert invoice is None


def test_find_invoice_by_document_number_handles_404_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/registro/documento/001-001-0000005/"):
            return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No existe"})
        return httpx.Response(status.HTTP_404_NOT_FOUND, json={"mensaje": "No existe"})

    transport = httpx.MockTransport(handler)
    client = ContificoClient(
        "key123",
        "token-xyz",
        base_url="https://api.example.com",
        transport=transport,
    )

    invoice = client.find_invoice_by_document_number("001-001-0000005")

    assert invoice is None


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


def test_build_invoice_page_success() -> None:
    class StubClient:
        def list_invoices_by_customer_document(self, document_id: str, *, page: int, page_size: int):
            assert document_id == "0912345678"
            assert page == 2
            assert page_size == 10
            return [
                {"id": 1, "numero": "001-001-0000001", "cliente": "María"},
                {"id": 2, "numero": "001-001-0000002", "cliente": "Juan"},
            ]

    result = build_invoice_page(StubClient(), page=2, page_size=10, document_id="0912345678")

    assert result.page == 2
    assert result.page_size == 10
    assert len(result.items) == 2
    assert result.items[0].numero == "001-001-0000001"


def test_build_invoice_page_handles_errors() -> None:
    class StubClient:
        def list_invoices_by_customer_document(self, document_id: str, *, page: int, page_size: int):
            raise ContificoTransportError("timeout")

    with pytest.raises(HTTPException) as exc_info:
        build_invoice_page(StubClient(), page=1, page_size=25, document_id="0912345678")

    assert exc_info.value.status_code == 503
    assert "timeout" in exc_info.value.detail


def test_build_invoice_page_raises_http_exception_on_not_found() -> None:
    class StubClient:
        def list_invoices_by_customer_document(self, document_id: str, *, page: int, page_size: int):
            raise ContificoAPIError(status.HTTP_404_NOT_FOUND, "Sin resultados")

    with pytest.raises(HTTPException) as exc_info:
        build_invoice_page(StubClient(), page=1, page_size=25, document_id="0912345678")

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Sin resultados" in exc_info.value.detail


def test_fetch_invoice_by_document_number_success() -> None:
    class StubClient:
        def find_invoice_by_document_number(self, document_number: str):
            assert document_number == "001-001-0000003"
            return {"id": 3, "numero": "001-001-0000003", "cliente": "Lucía"}

    result = fetch_invoice_by_document_number(StubClient(), document_number="001-001-0000003")

    assert result.numero == "001-001-0000003"
    assert result.cliente == "Lucía"


def test_fetch_invoice_by_document_number_not_found() -> None:
    class StubClient:
        def find_invoice_by_document_number(self, document_number: str):
            assert document_number == "001-001-0000004"
            return None

    with pytest.raises(HTTPException) as exc_info:
        fetch_invoice_by_document_number(StubClient(), document_number="001-001-0000004")

    assert exc_info.value.status_code == 404
    assert "No se encontró" in exc_info.value.detail


def test_fetch_invoice_by_document_number_handles_api_404() -> None:
    class StubClient:
        def find_invoice_by_document_number(self, document_number: str):
            assert document_number == "001-001-0000005"
            raise ContificoAPIError(status.HTTP_404_NOT_FOUND, "Sin resultados")

    with pytest.raises(HTTPException) as exc_info:
        fetch_invoice_by_document_number(StubClient(), document_number="001-001-0000005")

    assert exc_info.value.status_code == 404
    assert "No se encontró" in exc_info.value.detail


def test_contifico_invoice_from_api_supports_uppercase_keys() -> None:
    payload = {
        "NUMERO": "FAC 001-005-000012109",
        "CLIENTE": "María Demo",
        "DOCUMENTO": "0912345678",
        "FECHA_EMISION": "2023-11-01",
        "ESTADO": "AUT",
        "TOTAL": "123.45",
    }

    invoice = schemas.ContificoInvoice.from_api(payload)

    assert invoice.numero == "FAC 001-005-000012109"
    assert invoice.cliente == "María Demo"
    assert invoice.identificacion == "0912345678"
    assert invoice.fecha_emision == "2023-11-01"
    assert invoice.estado == "AUT"
    assert invoice.total == pytest.approx(123.45)


def test_contifico_invoice_from_api_uses_documento_when_numero_missing() -> None:
    payload = {
        "documento": "001-002-0000007",
        "cliente": "Comercial SA",
    }

    invoice = schemas.ContificoInvoice.from_api(payload)

    assert invoice.numero == "001-002-0000007"


def test_contifico_invoice_from_api_falls_back_to_persona_nombre() -> None:
    payload = {
        "persona_nombre": "Juan Ejemplo",
        "persona_identificacion": "0999999999",
    }

    invoice = schemas.ContificoInvoice.from_api(payload)

    assert invoice.cliente == "Juan Ejemplo"
    assert invoice.identificacion == "0999999999"


def test_contifico_invoice_from_api_handles_nested_persona_object() -> None:
    payload = {
        "persona": {
            "nombre": "Ana",
            "apellidos": "Díaz",
        },
    }

    invoice = schemas.ContificoInvoice.from_api(payload)

    assert invoice.cliente == "Ana Díaz"
