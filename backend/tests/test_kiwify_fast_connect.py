from app.services import kiwify_fast


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"1" if payload is not None else b""
        self.text = ""

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/oauth/token"):
            return FakeResponse({"access_token": "token", "scope": "webhooks products"})
        if url.endswith("/webhooks"):
            return FakeResponse({"id": "webhook-123"})
        raise AssertionError(url)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/account-details"):
            return FakeResponse({"company_name": "Empresa Teste"})
        if url.endswith("/webhooks"):
            return FakeResponse({"data": []})
        raise AssertionError(url)

    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return FakeResponse({"id": "webhook-123"})


def test_fast_connect_does_not_scan_products(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(kiwify_fast, "_client", lambda: fake)

    result = kiwify_fast.register_webhook_fast(
        client_id="client-id",
        client_secret="client-secret",
        account_id="account-id",
        webhook_url="https://shorts.example/api/billing/kiwify-webhook?token=secret",
        webhook_token="secret",
        products="all",
        base_checkout_code="base",
        upgrade_checkout_code="upgrade",
    )

    assert result["ok"] is True
    assert result["webhook_id"] == "webhook-123"
    assert all("/products" not in url for _, url, _ in fake.calls)
    create_call = next(call for call in fake.calls if call[0] == "POST" and call[1].endswith("/webhooks"))
    body = create_call[2]["json"]
    assert body["products"] == "all"
    assert len(body["token"]) == 16
