from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import settings


class VidiqMcpError(RuntimeError):
    pass


def vidiq_configured() -> bool:
    return bool((settings.vidiq_mcp_api_key or "").strip())


def _extract_mcp_payload(response: httpx.Response) -> dict[str, Any]:
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        data = response.json()
        return data if isinstance(data, dict) else {"result": data}

    payloads: list[dict[str, Any]] = []
    for raw_line in response.text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
    if payloads:
        return payloads[-1]
    raise VidiqMcpError("Resposta inválida do servidor MCP do vidIQ.")


async def _post_mcp(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
    protocol_version: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    headers = {
        "Authorization": f"Bearer {settings.vidiq_mcp_api_key.strip()}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if protocol_version:
        headers["MCP-Protocol-Version"] = protocol_version

    response = await client.post(settings.vidiq_mcp_url, json=payload, headers=headers)
    if response.status_code >= 400:
        detail = response.text[:1000].strip()
        raise VidiqMcpError(f"vidIQ MCP HTTP {response.status_code}: {detail}")
    return _extract_mcp_payload(response), response.headers.get("Mcp-Session-Id") or session_id


async def call_vidiq_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not vidiq_configured():
        raise VidiqMcpError(
            "VIDIQ_MCP_API_KEY não está configurada no ambiente do ShortsFlow."
        )

    timeout = max(10.0, float(settings.vidiq_mcp_timeout_seconds or 45.0))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        init, session_id = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "ShortsFlow AI", "version": "1.0"},
                },
            },
        )
        if init.get("error"):
            raise VidiqMcpError(str(init["error"]))
        protocol_version = str((init.get("result") or {}).get("protocolVersion") or "2025-06-18")

        # Standard MCP initialized notification.
        try:
            await _post_mcp(
                client,
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                session_id=session_id,
                protocol_version=protocol_version,
            )
        except VidiqMcpError:
            # Some stateless MCP implementations do not return a payload for
            # notifications. The tool call below remains authoritative.
            pass

        result, _ = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            },
            session_id=session_id,
            protocol_version=protocol_version,
        )

    if result.get("error"):
        raise VidiqMcpError(str(result["error"]))

    tool_result = result.get("result")
    if not isinstance(tool_result, dict):
        return {"value": tool_result}

    if isinstance(tool_result.get("structuredContent"), dict):
        return tool_result["structuredContent"]

    content = tool_result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text":
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
                return {"value": parsed}
            except json.JSONDecodeError:
                return {"text": text}

    return tool_result
