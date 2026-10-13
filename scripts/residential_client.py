"""Keep this client running to route ShortsFlow's YouTube HTTPS traffic locally."""
import argparse
import asyncio
import getpass
import ipaddress
import json
import re
import socket
import struct
from contextlib import suppress
from urllib.parse import urlsplit

MAX_CHUNK = 32768
MAX_CHANNELS = 16
DOMAINS = ("youtube.com", "googlevideo.com", "ytimg.com", "ggpht.com")
EXACT_HOSTS = {"youtubei.googleapis.com", "jnn-pa.googleapis.com", "www.google.com", "accounts.google.com"}


def allowed_destination(host: str, port: int) -> bool:
    host = host.lower().rstrip(".")
    return (
        port == 443 and len(host) <= 253
        and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part) for part in host.split("."))
        and (host in EXACT_HOSTS or any(host == domain or host.endswith("." + domain) for domain in DOMAINS))
    )


def public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        return address.is_global and not address.is_multicast and not address.is_reserved
    except ValueError:
        return False


async def connect_public(host: str, port: int):
    if not allowed_destination(host, port):
        raise ValueError("Destino não permitido.")
    addresses = await asyncio.wait_for(
        asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), 10
    )
    if not addresses or any(not public_address(item[4][0]) for item in addresses):
        raise ValueError("O destino não resolve exclusivamente para endereços públicos.")
    addresses.sort(key=lambda item: item[0] != socket.AF_INET)
    for family, _, _, _, address in addresses:
        try:
            # Use the validated numeric address. Do not resolve the name twice.
            return await asyncio.wait_for(asyncio.open_connection(address[0], port, family=family), 12)
        except (OSError, TimeoutError):
            continue
    raise ConnectionError("O YouTube não pôde ser conectado pela rede local.")


class ClientRelay:
    def __init__(self, websocket):
        self.websocket = websocket
        self.channels = {}
        self.tasks = {}
        self.send_lock = asyncio.Lock()

    async def send(self, message):
        async with self.send_lock:
            await self.websocket.send(message if isinstance(message, bytes) else json.dumps(message))

    async def open_channel(self, ident, host, port):
        writer = None
        try:
            reader, writer = await connect_public(host, port)
            self.channels[ident] = writer
            await self.send({"type": "opened", "id": ident})
            while data := await reader.read(MAX_CHUNK):
                await self.send(struct.pack("!I", ident) + data)
        except (OSError, ValueError, TimeoutError):
            with suppress(Exception):
                await self.send({"type": "error", "id": ident})
        finally:
            self.channels.pop(ident, None)
            if writer:
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
            with suppress(Exception):
                await self.send({"type": "close", "id": ident})

    async def heartbeat(self):
        while True:
            await self.send({"type": "heartbeat"})
            await asyncio.sleep(15)

    async def run(self):
        heartbeat = asyncio.create_task(self.heartbeat())
        try:
            async for message in self.websocket:
                if isinstance(message, bytes):
                    if not 4 < len(message) <= MAX_CHUNK + 4:
                        raise ValueError("Quadro de dados inválido.")
                    ident = struct.unpack("!I", message[:4])[0]
                    writer = self.channels.get(ident)
                    if writer:
                        writer.write(message[4:])
                        await writer.drain()
                else:
                    if len(message) > 1024:
                        raise ValueError("Mensagem de controle inválida.")
                    control = json.loads(message)
                    ident = control.get("id")
                    kind = control.get("type")
                    if not isinstance(ident, int) or not 0 <= ident < 2**32:
                        raise ValueError("Canal inválido.")
                    if kind == "open":
                        # Only bounded concurrent channels, even for an authenticated server.
                        self.tasks = {key: task for key, task in self.tasks.items() if not task.done()}
                        host, port = control.get("host"), control.get("port")
                        if (ident in self.tasks or len(self.tasks) >= MAX_CHANNELS
                                or not isinstance(host, str) or not isinstance(port, int)
                                or not allowed_destination(host, port)):
                            await self.send({"type": "error", "id": ident})
                            continue
                        self.tasks[ident] = asyncio.create_task(self.open_channel(ident, host, port))
                    elif kind == "close":
                        task = self.tasks.get(ident)
                        if task:
                            task.cancel()
        finally:
            heartbeat.cancel()
            for task in self.tasks.values():
                task.cancel()
            await asyncio.gather(heartbeat, *self.tasks.values(), return_exceptions=True)


async def run_connection(url: str, code: str):
    from websockets.asyncio.client import connect
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use o endereço HTTPS da sua instalação do ShortsFlow.")
    endpoint = "wss://" + parsed.netloc + "/api/admin/residential-proxy/connect"
    # Authentication stays in a header, never in URLs, logs or files.
    async with connect(endpoint, additional_headers={"Authorization": "Bearer " + code},
                       max_size=MAX_CHUNK + 4, open_timeout=20, close_timeout=5) as websocket:
        print("Conexão residencial ativa. Mantenha esta janela aberta. Ctrl+C desconecta.", flush=True)
        await ClientRelay(websocket).run()


def main():
    parser = argparse.ArgumentParser(description="Conexão residencial privada do ShortsFlow")
    parser.add_argument("--url", default="https://shorts.r2rmarketingdigital.com.br")
    args = parser.parse_args()
    print("Este cliente abre apenas conexões HTTPS para os destinos permitidos do YouTube.")
    code = getpass.getpass("Cole o código temporário gerado no painel (entrada oculta): ").strip()
    if not code:
        raise SystemExit("Informe o código temporário.")
    try:
        asyncio.run(run_connection(args.url, code))
    except KeyboardInterrupt:
        print("Conexão encerrada.")
    except Exception as exc:
        # Do not render exceptions containing request headers or credentials.
        print("A conexão não foi estabelecida ou foi encerrada (" + type(exc).__name__ + ").")
        print("Confira o código, o acesso ao servidor e o estado no painel.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
