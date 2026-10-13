"""Authenticated outbound relay; the HTTP CONNECT listener stays on loopback."""
import asyncio
import hashlib
import json
import re
import secrets
import struct
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

PROXY_PORT = 18888
MAX_CHANNELS = 16
MAX_CHUNK = 32768
PAIR_SECONDS = 6 * 60 * 60
_DOMAINS = ("youtube.com", "googlevideo.com", "ytimg.com", "ggpht.com")
_EXACT_HOSTS = {"youtubei.googleapis.com", "jnn-pa.googleapis.com", "www.google.com", "accounts.google.com"}


def allowed_destination(host: str, port: int) -> bool:
    host = host.lower().rstrip(".")
    if port != 443 or len(host) > 253:
        return False
    if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part) for part in host.split(".")):
        return False
    return host in _EXACT_HOSTS or any(host == domain or host.endswith("." + domain) for domain in _DOMAINS)


def _private_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        temp.chmod(0o600)
        json.dump(payload, handle)
    temp.replace(path)


def enabled(data_path: Path) -> bool:
    return (data_path / "residential_proxy_enabled").is_file()


def connection_status(data_path: Path) -> dict:
    active = False
    try:
        state = json.loads((data_path / "residential_proxy_status.json").read_text())
        active = bool(state.get("connected")) and 0 <= time.time() - float(state.get("checked_at", 0)) < 35
    except (OSError, ValueError, TypeError):
        pass
    return {"enabled": enabled(data_path), "connected": active}


@dataclass
class Channel:
    writer: asyncio.StreamWriter
    opened: asyncio.Future


class ResidentialRelay:
    def __init__(self, data_path: Path, port: int = PROXY_PORT):
        self.data_path = data_path
        self.port = port
        self.server = None
        self.websocket = None
        self.channels: dict[int, Channel] = {}
        self._send_lock = asyncio.Lock()
        self._attach_lock = asyncio.Lock()
        self._code_hash = ""
        self._expires = 0.0
        self._sequence = 0

    def issue_code(self) -> str:
        if self.websocket is not None:
            raise ValueError("A conexão residencial já está ativa. Desconecte antes de gerar outro código.")
        token = secrets.token_urlsafe(32)
        self._code_hash = hashlib.sha256(token.encode()).hexdigest()
        self._expires = time.time() + PAIR_SECONDS
        flag = self.data_path / "residential_proxy_enabled"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch(mode=0o600, exist_ok=True)
        return token

    def authorized(self, token: str) -> bool:
        digest = hashlib.sha256(token.encode()).hexdigest()
        return bool(self._code_hash) and time.time() < self._expires and secrets.compare_digest(digest, self._code_hash)

    def _status(self, connected: bool) -> None:
        _private_json(self.data_path / "residential_proxy_status.json", {"connected": connected, "checked_at": time.time()})

    async def start(self) -> None:
        self._status(False)
        self.server = await asyncio.start_server(self._connect, "127.0.0.1", self.port, limit=8192)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.websocket is not None:
            with suppress(Exception):
                await self.websocket.close(code=1001)
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        self._status(False)

    async def disable(self) -> None:
        self._code_hash = ""
        self._expires = 0
        (self.data_path / "residential_proxy_enabled").unlink(missing_ok=True)
        await self.stop()
        await self.start()

    async def _send(self, message) -> None:
        async with self._send_lock:
            if self.websocket is None:
                raise ConnectionError("Conexão residencial desconectada.")
            if isinstance(message, bytes):
                await self.websocket.send_bytes(message)
            else:
                await self.websocket.send_json(message)

    async def _heartbeat(self) -> None:
        while self.websocket is not None:
            if time.time() >= self._expires:
                await self.websocket.close(code=1008)
                return
            self._status(True)
            await asyncio.sleep(10)

    async def attach(self, websocket, token: str) -> None:
        async with self._attach_lock:
            if not self.authorized(token) or self.websocket is not None:
                await websocket.close(code=1008)
                return
            await websocket.accept()
            self.websocket = websocket
        self._status(True)
        heartbeat = asyncio.create_task(self._heartbeat())
        try:
            while True:
                message = await asyncio.wait_for(websocket.receive(), 45)
                if message["type"] == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if data is not None:
                    if not 4 < len(data) <= MAX_CHUNK + 4:
                        break
                    ident = struct.unpack("!I", data[:4])[0]
                    channel = self.channels.get(ident)
                    if channel and channel.opened.done() and not channel.opened.cancelled() and channel.opened.result():
                        channel.writer.write(data[4:])
                        await channel.writer.drain()
                elif message.get("text") is not None:
                    if len(message["text"]) > 1024:
                        break
                    control = json.loads(message["text"])
                    if not isinstance(control, dict):
                        break
                    kind = control.get("type")
                    if kind == "heartbeat":
                        continue
                    channel = self.channels.get(control.get("id"))
                    if channel:
                        if kind in {"opened", "error"} and not channel.opened.done():
                            channel.opened.set_result(kind == "opened")
                        elif kind == "close":
                            channel.writer.close()
        except (TimeoutError, ConnectionError, ValueError, RuntimeError):
            pass
        finally:
            with suppress(Exception):
                await websocket.close()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            self.websocket = None
            self._status(False)
            for channel in list(self.channels.values()):
                if not channel.opened.done():
                    channel.opened.set_result(False)
                channel.writer.close()

    async def _connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        ident = None
        established = False
        try:
            headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            if len(headers) > 8192:
                raise ValueError("Cabeçalho grande demais.")
            method, target, protocol = headers.split(b"\r\n", 1)[0].decode("ascii").split()
            host, raw_port = target.rsplit(":", 1)
            port = int(raw_port)
            if method != "CONNECT" or protocol not in {"HTTP/1.0", "HTTP/1.1"} or not allowed_destination(host, port):
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            if self.websocket is None or len(self.channels) >= MAX_CHANNELS:
                writer.write(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            self._sequence = (self._sequence + 1) % (2**32)
            ident = self._sequence
            channel = Channel(writer, asyncio.get_running_loop().create_future())
            self.channels[ident] = channel
            await self._send({"type": "open", "id": ident, "host": host, "port": port})
            if not await asyncio.wait_for(channel.opened, 20):
                raise ConnectionError("O destino não pôde ser conectado.")
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            established = True
            while data := await reader.read(MAX_CHUNK):
                await self._send(struct.pack("!I", ident) + data)
        except (OSError, ValueError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            if not established:
                with suppress(Exception):
                    writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                    await writer.drain()
        finally:
            if ident is not None:
                self.channels.pop(ident, None)
                with suppress(Exception):
                    await self._send({"type": "close", "id": ident})
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


from ..config import settings

relay = ResidentialRelay(settings.data_path)
