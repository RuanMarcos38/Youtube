import asyncio
import importlib.util
import json
import struct
from pathlib import Path

import pytest

from app.services.residential_proxy import ResidentialRelay, allowed_destination, connection_status

client_path = Path(__file__).resolve().parents[2] / "scripts" / "residential_client.py"
spec = importlib.util.spec_from_file_location("residential_test_client", client_path)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


@pytest.mark.parametrize("host,port,allowed", [
    ("www.youtube.com", 443, True),
    ("rr1---sn-ab.googlevideo.com", 443, True),
    ("youtubei.googleapis.com", 443, True),
    ("www.youtube.com.evil.example", 443, False),
    ("evil-youtube.com", 443, False),
    ("127.0.0.1", 443, False),
    ("192.168.0.1", 443, False),
    ("www.youtube.com", 22, False),
    ("www.youtube.com", 80, False),
    ("other.googleapis.com", 443, False),
])
def test_both_ends_restrict_destinations(host, port, allowed):
    assert allowed_destination(host, port) is allowed
    assert client.allowed_destination(host, port) is allowed


def test_client_blocks_private_dns_before_connect(monkeypatch):
    async def run():
        async def dns(*_args, **_kwargs):
            return [(2, 1, 6, "", ("192.168.0.10", 443))]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
        with pytest.raises(ValueError, match="públicos"):
            await client.connect_public("www.youtube.com", 443)
    asyncio.run(run())


def test_pairing_expires_and_unpaired_websocket_is_rejected(tmp_path, monkeypatch):
    relay = ResidentialRelay(tmp_path, port=0)
    token = relay.issue_code()
    assert relay.authorized(token)
    assert not relay.authorized("incorrect")
    monkeypatch.setattr("app.services.residential_proxy.time.time", lambda: relay._expires + 1)
    assert not relay.authorized(token)
    class RejectedSocket:
        async def accept(self):
            pytest.fail("Invalid credentials must never accept a socket")
        async def close(self, code):
            assert code == 1008
    asyncio.run(relay.attach(RejectedSocket(), token))


def test_connect_tunnel_multiplexes_and_disconnect_closes_channels(tmp_path):
    async def run():
        relay = ResidentialRelay(tmp_path, port=0)
        await relay.start()
        token = relay.issue_code()
        class Socket:
            def __init__(self):
                self.incoming = asyncio.Queue()
                self.accepted = asyncio.Event()
            async def accept(self):
                self.accepted.set()
            async def close(self, code=1000):
                pass
            async def receive(self):
                return await self.incoming.get()
            async def send_json(self, message):
                if message["type"] == "open":
                    await self.incoming.put({"type": "websocket.receive", "text": json.dumps({"type": "opened", "id": message["id"]})})
            async def send_bytes(self, data):
                # Echo independent channels through the same authenticated relay.
                await self.incoming.put({"type": "websocket.receive", "bytes": data})
        socket = Socket()
        tunnel = asyncio.create_task(relay.attach(socket, token))
        await socket.accepted.wait()
        assert connection_status(tmp_path)["connected"]
        writers = []
        async def transfer(payload):
            reader, writer = await asyncio.open_connection("127.0.0.1", relay.port)
            writers.append(writer)
            writer.write(b"CONNECT www.youtube.com:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            assert b"200" in await reader.readuntil(b"\r\n\r\n")
            writer.write(payload)
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(len(payload)), 2) == payload
            return reader
        readers = await asyncio.gather(transfer(b"first-channel"), transfer(b"second-channel"))
        reader, denied = await asyncio.open_connection("127.0.0.1", relay.port)
        denied.write(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n")
        await denied.drain()
        assert b"403" in await reader.read()
        denied.close()
        await denied.wait_closed()
        await socket.incoming.put({"type": "websocket.disconnect"})
        await asyncio.wait_for(tunnel, 2)
        assert not connection_status(tmp_path)["connected"]
        assert await asyncio.gather(*(reader.read() for reader in readers)) == [b"", b""]
        for writer in writers:
            writer.close()
            await writer.wait_closed()
        await relay.stop()
    asyncio.run(run())


def test_admin_pairing_and_websocket_require_authorization():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.routers.residential_proxy import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as api:
        assert api.post("/api/admin/residential-proxy/pair").status_code == 401
        assert api.get("/api/admin/residential-proxy").status_code == 401
        with pytest.raises(WebSocketDisconnect) as error:
            with api.websocket_connect("/api/admin/residential-proxy/connect"):
                pass
        assert error.value.code == 1008


def test_downloader_never_falls_back_to_vps_when_residential_is_offline(tmp_path, monkeypatch):
    from app.services import downloader
    monkeypatch.setattr(downloader, "residential_status", lambda _: {"enabled": True, "connected": False})
    monkeypatch.setattr(downloader, "_download_with_options", lambda *_: pytest.fail("Offline mode must not contact YouTube"))
    with pytest.raises(downloader.DownloadError, match="offline"):
        downloader.download_video("https://www.youtube.com/watch?v=test", tmp_path)
    assert downloader.validate_download_session()["attempts"] == 0


def test_residential_public_download_does_not_retry_stale_account_cookies(tmp_path, monkeypatch):
    import base64
    from app.services import downloader
    cookies = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tPREF\tsynthetic\n"
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", base64.b64encode(cookies.encode()).decode())
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader, "cookie_override_file", lambda: None)
    monkeypatch.setattr(downloader, "residential_status", lambda _: {"enabled": True, "connected": True})
    monkeypatch.setattr(downloader, "YTDLP_CACHE_DIR", tmp_path / "cache")
    calls = []
    def download(_url, output, options):
        calls.append(options)
        if options.get("cookiefile"):
            raise RuntimeError("The provided YouTube account cookies are no longer valid")
        video = output / "source.mp4"
        video.write_bytes(b"synthetic-video")
        return video
    monkeypatch.setattr(downloader, "_download_with_options", download)
    assert downloader.download_video("https://www.youtube.com/watch?v=test", tmp_path).is_file()
    assert len(calls) == 1
    assert "cookiefile" not in calls[0]


def test_offline_relay_does_not_accept_connect(tmp_path):
    async def run():
        relay = ResidentialRelay(tmp_path, port=0)
        await relay.start()
        relay.issue_code()
        reader, writer = await asyncio.open_connection("127.0.0.1", relay.port)
        writer.write(b"CONNECT www.youtube.com:443 HTTP/1.1\r\n\r\n")
        await writer.drain()
        assert b"503" in await reader.read()
        writer.close()
        await writer.wait_closed()
        await relay.stop()
    asyncio.run(run())

@pytest.mark.parametrize("source", ["override", "environment"])
def test_permanent_proxy_bypasses_offline_computer_without_mutating_pairing(tmp_path, monkeypatch, source):
    from app.services import downloader, runtime_download_auth as auth
    proxy = "http://proxy.example:8080"
    monkeypatch.setattr(auth, "proxy_override_url", lambda: proxy if source == "override" else "")
    monkeypatch.setattr(auth.settings, "ytdlp_proxy_url", proxy if source == "environment" else "")
    monkeypatch.setattr(auth, "residential_enabled", lambda _: True)
    monkeypatch.setattr(downloader, "residential_status", lambda _: {"enabled": True, "connected": False})
    monkeypatch.setattr(downloader, "YTDLP_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(downloader, "_strategy_variants", lambda: [("guest:test", {}, False, "none")])
    calls = []
    def download(_url, output, options):
        calls.append(options["proxy"])
        video = output / "source.mp4"
        video.write_bytes(b"synthetic-video")
        return video
    class Youtube:
        def __init__(self, options):
            calls.append(options["proxy"])
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def extract_info(self, *_args, **_kwargs):
            return {"id": "test", "title": "Synthetic"}
    monkeypatch.setattr(downloader, "_download_with_options", download)
    monkeypatch.setattr(downloader, "YoutubeDL", Youtube)
    assert auth.effective_proxy_url() == proxy
    assert downloader.download_video("https://www.youtube.com/watch?v=test", tmp_path).is_file()
    assert downloader.validate_download_session()["ok"] is True
    assert calls == [proxy, proxy]
    assert auth.residential_enabled(tmp_path) is True
    # Removing the explicit proxy restores the unchanged temporary route.
    monkeypatch.setattr(auth, "proxy_override_url", lambda: "")
    monkeypatch.setattr(auth.settings, "ytdlp_proxy_url", "")
    assert auth.effective_proxy_url() == "http://127.0.0.1:18888"
    assert downloader.validate_download_session()["attempts"] == 0
