from app.contifico import ContificoAPIError, ContificoTransportError
from app.odoo_migration.service import OdooMigrationService


class StubClient:
    def __init__(self):
        self.calls = []

    def list_products(self, *, page: int, page_size: int):
        self.calls.append((page, page_size))
        if len(self.calls) < 3:
            raise ContificoTransportError("transient network error")
        return [{"id": "P-1", "codigo": "SKU-1"}]


class StubClientApiError:
    def __init__(self):
        self.calls = []

    def list_products(self, *, page: int, page_size: int):
        self.calls.append((page, page_size))
        if len(self.calls) < 2:
            raise ContificoAPIError(503, "service unavailable")
        return [{"id": "P-2", "codigo": "SKU-2"}]


class StubClientNonRetriable:
    def list_products(self, *, page: int, page_size: int):
        raise ContificoAPIError(400, "bad request")


def test_fetch_products_page_retries_transport_errors_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.odoo_migration.service.time.sleep", lambda _s: None)
    client = StubClient()
    service = OdooMigrationService(client=client)

    rows, effective_size = service._fetch_products_page_with_fallback(page=1, page_size=200)

    assert rows == [{"id": "P-1", "codigo": "SKU-1"}]
    assert effective_size == 200
    assert client.calls == [(1, 200), (1, 200), (1, 200)]


def test_fetch_products_page_retries_server_errors_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.odoo_migration.service.time.sleep", lambda _s: None)
    client = StubClientApiError()
    service = OdooMigrationService(client=client)

    rows, effective_size = service._fetch_products_page_with_fallback(page=2, page_size=120)

    assert rows == [{"id": "P-2", "codigo": "SKU-2"}]
    assert effective_size == 120
    assert client.calls == [(2, 120), (2, 120)]


def test_fetch_products_page_raises_non_retriable_api_errors():
    service = OdooMigrationService(client=StubClientNonRetriable())

    try:
        service._fetch_products_page_with_fallback(page=1, page_size=200)
    except ContificoAPIError as exc:
        assert exc.status_code == 400
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ContificoAPIError")


def test_fetch_products_resumes_from_last_successful_page(tmp_path):
    class ResumeClient:
        def __init__(self):
            self.calls = []

        def list_products(self, *, page: int, page_size: int):
            self.calls.append((page, page_size))
            if page == 3:
                return []
            return [{"id": f"P-{page}", "codigo": f"SKU-{page}"}]

    output_root = tmp_path / "odoo_migration"
    output_root.mkdir(parents=True, exist_ok=True)
    state_path = output_root / "products_fetch_resume_state.json"
    items_path = output_root / "products_fetch_resume_items.jsonl"
    state_path.write_text('{"last_successful_page": 2, "page_size": 200, "max_pages": 5}', encoding="utf-8")
    items_path.write_text('{"id":"P-1","codigo":"SKU-1"}\n{"id":"P-2","codigo":"SKU-2"}\n', encoding="utf-8")

    client = ResumeClient()
    service = OdooMigrationService(client=client, output_root=output_root)

    items, pages, _, expected_min = service._fetch_products(page_size=200, max_pages=5, run_folder=output_root)

    assert client.calls[0] == (3, 200)
    assert items == [
        {"id": "P-1", "codigo": "SKU-1"},
        {"id": "P-2", "codigo": "SKU-2"},
    ]
    assert pages == 3
    assert expected_min is None
    assert not state_path.exists()
    assert not items_path.exists()


def test_fetch_products_page_does_not_change_page_size_on_retries(monkeypatch):
    monkeypatch.setattr("app.odoo_migration.service.time.sleep", lambda _s: None)

    class SameSizeOnlyClient:
        def __init__(self):
            self.calls = []

        def list_products(self, *, page: int, page_size: int):
            self.calls.append((page, page_size))
            raise ContificoTransportError("network down")

    client = SameSizeOnlyClient()
    service = OdooMigrationService(client=client)

    try:
        service._fetch_products_page_with_fallback(page=4, page_size=200)
    except ContificoTransportError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ContificoTransportError")

    assert client.calls == [(4, 200), (4, 200), (4, 200)]


def test_fetch_products_v2_does_not_stop_on_first_short_page(tmp_path):
    class V2Client:
        products_base_url = "https://api.contifico.com/sistema/api/v2"

        def __init__(self):
            self.calls = []

        def list_products(self, *, page: int, page_size: int):
            self.calls.append((page, page_size))
            if page == 1:
                return [{"id": "P-1"}] * 100
            if page == 2:
                return [{"id": "P-2"}] * 100
            return []

    service = OdooMigrationService(client=V2Client(), output_root=tmp_path / "odoo_migration")

    items, pages, hit_max, expected_min = service._fetch_products(page_size=200, max_pages=10, run_folder=tmp_path / "odoo_migration")

    assert len(items) == 200
    assert pages == 3
    assert hit_max is False
    assert expected_min is None


def test_fetch_products_uses_configured_page_delay_and_retry_backoff(monkeypatch, tmp_path):
    sleep_calls = []
    monkeypatch.setattr("app.odoo_migration.service.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("app.odoo_migration.service.random.uniform", lambda _a, _b: 0.0)

    class SlowClient:
        def __init__(self):
            self.calls = 0
            self.products_base_url = "https://api.contifico.com/sistema/api/v2"

        def list_products(self, *, page: int, page_size: int):
            self.calls += 1
            if self.calls == 1:
                raise ContificoTransportError("timeout")
            if page == 1:
                return [{"id": "P-1"}]
            return []

    service = OdooMigrationService(
        client=SlowClient(),
        output_root=tmp_path / "odoo_migration",
        page_delay_seconds=1.2,
        page_retry_attempts=4,
        page_retry_backoff_base_seconds=2.0,
        page_retry_jitter_seconds=0.5,
    )

    items, pages, _, expected_min = service._fetch_products(page_size=200, max_pages=3, run_folder=tmp_path / "odoo_migration")

    assert items == [{"id": "P-1"}]
    assert pages == 2
    assert expected_min is None
    assert 2.0 in sleep_calls  # retry backoff
    assert 1.2 in sleep_calls  # inter-page pacing


def test_fetch_products_tracks_expected_total_from_v2_count(tmp_path):
    class V2CountClient:
        products_base_url = "https://api.contifico.com/sistema/api/v2"

        def __init__(self):
            self.last_products_total_count = None

        def list_products(self, *, page: int, page_size: int):
            self.last_products_total_count = 24605
            if page <= 2:
                return [{"id": f"P-{page}-{i}"} for i in range(100)]
            return []

    service = OdooMigrationService(client=V2CountClient(), output_root=tmp_path / "odoo_migration")
    items, pages, hit_max, expected_min = service._fetch_products(page_size=200, max_pages=10, run_folder=tmp_path / "odoo_migration")

    assert len(items) == 200
    assert pages == 3
    assert hit_max is False
    assert expected_min == 24605


def test_fetch_products_page_out_of_range_is_treated_as_end_of_pagination():
    class OutOfRangeClient:
        def list_products(self, *, page: int, page_size: int):
            raise ContificoAPIError(
                400,
                'Error: {"code":"400","error":"Pagina fuera del rango"}',
                payload={"code": "400", "error": "Pagina fuera del rango"},
            )

    service = OdooMigrationService(client=OutOfRangeClient())
    rows, effective_size = service._fetch_products_page_with_fallback(page=999, page_size=200)

    assert rows == []
    assert effective_size == 200
