import json

import httpx

from app.config import settings
from app.services.vidiq_mcp import _extract_mcp_payload, vidiq_configured


def test_vidiq_is_disabled_without_runtime_secret(monkeypatch):
    monkeypatch.setattr(settings, "vidiq_mcp_api_key", "")
    assert vidiq_configured() is False


def test_vidiq_is_enabled_with_runtime_secret(monkeypatch):
    monkeypatch.setattr(settings, "vidiq_mcp_api_key", "test-only-secret")
    assert vidiq_configured() is True


def test_mcp_json_response_is_parsed():
    request = httpx.Request("POST", "https://mcp.vidiq.com/mcp")
    response = httpx.Response(
        200,
        request=request,
        headers={"content-type": "application/json"},
        content=json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}).encode(),
    )
    parsed = _extract_mcp_payload(response)
    assert parsed["result"]["ok"] is True


def test_mcp_sse_response_is_parsed():
    request = httpx.Request("POST", "https://mcp.vidiq.com/mcp")
    response = httpx.Response(
        200,
        request=request,
        headers={"content-type": "text/event-stream"},
        content=b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"score":77}}\n\n',
    )
    parsed = _extract_mcp_payload(response)
    assert parsed["result"]["score"] == 77
