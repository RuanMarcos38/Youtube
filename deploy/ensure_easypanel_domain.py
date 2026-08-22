import json
import os
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = os.getenv("EASYPANEL_URL", "https://ke4n49.easypanel.host").rstrip("/")
API_KEY = os.getenv("EASYPANEL_API_KEY", "").strip()
PROJECT = os.getenv("EASYPANEL_PROJECT", "r2rmarketingdigital")
SERVICE = os.getenv("EASYPANEL_SERVICE", "shortsia")
HOST = os.getenv("EASYPANEL_DOMAIN", "shorts.r2rmarketingdigital.com.br")
PORT = int(os.getenv("EASYPANEL_DOMAIN_PORT", "3000"))


def request_json(method: str, path: str, payload: dict | None = None):
    if not API_KEY:
        raise RuntimeError("EASYPANEL_API_KEY is not configured")

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        f"{BASE_URL}/api/{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8").strip()
            return None if not raw else json.loads(raw)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"EasyPanel API {method} {path} failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"EasyPanel API {method} {path} failed: {exc.reason}") from exc


def collect_domain_objects(value):
    found = []
    if isinstance(value, dict):
        if isinstance(value.get("host"), str) and "id" in value:
            found.append(value)
        for child in value.values():
            found.extend(collect_domain_objects(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(collect_domain_objects(child))
    return found


def main() -> int:
    query = urlencode({"projectName": PROJECT, "serviceName": SERVICE})
    current = request_json("GET", f"listDomains?{query}")
    domains = collect_domain_objects(current)
    matches = [item for item in domains if item.get("host") == HOST]

    if matches:
        domain = matches[0]
        domain_id = str(domain.get("id"))
        destination = domain.get("serviceDestination") or domain.get("destination") or {}
        destination_project = destination.get("projectName")
        destination_service = destination.get("serviceName")
        destination_port = destination.get("port")

        if destination_project not in (None, PROJECT) or destination_service not in (None, SERVICE):
            raise RuntimeError(
                f"Domain {HOST} already exists but targets another service; refusing to change it automatically."
            )
        if destination_port not in (None, PORT):
            raise RuntimeError(
                f"Domain {HOST} exists with target port {destination_port}, expected {PORT}; refusing destructive overwrite."
            )

        request_json("POST", "setPrimaryDomain", {"id": domain_id})
        print(f"Domain already present and set as primary: https://{HOST} -> {PROJECT}/{SERVICE}:{PORT}")
        return 0

    domain_id = str(uuid.uuid4())
    payload = {
        "certificateResolver": "",
        "host": HOST,
        "https": True,
        "id": domain_id,
        "middlewares": [],
        "path": "/",
        "wildcard": False,
        "destinationType": "service",
        "serviceDestination": {
            "port": PORT,
            "projectName": PROJECT,
            "protocol": "http",
            "serviceName": SERVICE,
        },
    }
    request_json("POST", "createDomain", payload)
    request_json("POST", "setPrimaryDomain", {"id": domain_id})
    print(f"Domain created and set as primary: https://{HOST} -> {PROJECT}/{SERVICE}:{PORT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
