import httpx

from app.contifico import ContificoClient


class _FakeResponse:
    status_code = 200
    content = b"[]"
    text = "[]"
    headers = {}

    def json(self):
        return []


class _FakeHttpClient:
    calls = 0

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, *_args, **_kwargs):
        self.__class__.calls += 1
        if self.__class__.calls < 3:
            raise httpx.ReadTimeout("timeout")
        return _FakeResponse()


def test_request_uses_longer_backoff_for_timeouts(monkeypatch):
    sleep_calls = []

    monkeypatch.setattr("app.contifico.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("app.contifico.httpx.Client", _FakeHttpClient)

    client = ContificoClient("key123", "token-xyz", base_url="https://api.example.com")

    data = client.list_products(page=1, page_size=5)

    assert data == []
    assert sleep_calls == [
        ContificoClient.REQUEST_TIMEOUT_RETRY_BACKOFF_BASE,
        ContificoClient.REQUEST_TIMEOUT_RETRY_BACKOFF_BASE * 2,
    ]
