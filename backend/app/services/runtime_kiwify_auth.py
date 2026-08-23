from __future__ import annotations

import json
import os
from pathlib import Path

from ..config import settings


CREDENTIALS_FILE = settings.data_path / "kiwify_api_credentials.json"


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def load_credentials() -> dict[str, str]:
    if not CREDENTIALS_FILE.is_file():
        return {"client_id": "", "client_secret": "", "account_id": ""}
    try:
        payload = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"client_id": "", "client_secret": "", "account_id": ""}
    if not isinstance(payload, dict):
        return {"client_id": "", "client_secret": "", "account_id": ""}
    return {
        "client_id": _clean(payload.get("client_id")),
        "client_secret": _clean(payload.get("client_secret")),
        "account_id": _clean(payload.get("account_id")),
    }


def save_credentials(*, client_id: str, client_secret: str, account_id: str) -> None:
    client_id = _clean(client_id)
    client_secret = _clean(client_secret)
    account_id = _clean(account_id)
    if len(client_id) < 5:
        raise ValueError("Client ID da Kiwify inválido.")
    if len(client_secret) < 8:
        raise ValueError("Client Secret da Kiwify inválido.")
    if len(account_id) < 3 or "@" in account_id:
        raise ValueError("Account ID da Kiwify inválido. Use o account_id exibido em Apps > API, não um e-mail.")

    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CREDENTIALS_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "account_id": account_id,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    tmp.replace(CREDENTIALS_FILE)
    os.chmod(CREDENTIALS_FILE, 0o600)


def resolve_credentials(*, client_id: str = "", client_secret: str = "", account_id: str = "") -> dict[str, str]:
    current = load_credentials()
    return {
        "client_id": _clean(client_id) or current["client_id"],
        "client_secret": _clean(client_secret) or current["client_secret"],
        "account_id": _clean(account_id) or current["account_id"],
    }


def status_payload() -> dict:
    current = load_credentials()
    return {
        "client_id": current["client_id"],
        "account_id": current["account_id"],
        "client_secret_configured": bool(current["client_secret"]),
        "credentials_configured": bool(current["client_id"] and current["client_secret"] and current["account_id"]),
    }
