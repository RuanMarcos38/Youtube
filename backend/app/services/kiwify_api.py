from __future__ import annotations

import httpx


OAUTH_URL = "https://public-api.kiwify.com/v1/oauth/token"
WEBHOOKS_URL = "https://public-api.kiwify.com/v1/webhooks"
DEFAULT_TRIGGERS = [
    "compra_aprovada",
    "compra_reembolsada",
    "chargeback",
    "subscription_canceled",
    "subscription_late",
    "subscription_renewed",
]


class KiwifyApiError(RuntimeError):
    pass


def _safe_error(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("message", "error_description", "error", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:300]
    except Exception:
        pass
    return fallback


def register_webhook(
    *,
    client_id: str,
    client_secret: str,
    account_id: str,
    webhook_url: str,
    webhook_token: str,
    products: str = "all",
) -> dict:
    """Create or update the ShortsFlow webhook without persisting Kiwify API credentials."""
    try:
        with httpx.Client(timeout=30.0) as client:
            oauth = client.post(
                OAUTH_URL,
                data={"client_id": client_id.strip(), "client_secret": client_secret.strip()},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if not oauth.is_success:
                raise KiwifyApiError(_safe_error(oauth, "A Kiwify recusou o Client ID/Client Secret."))
            token_payload = oauth.json()
            access_token = str(token_payload.get("access_token") or "").strip()
            if not access_token:
                raise KiwifyApiError("A Kiwify não retornou um access_token.")

            headers = {
                "Authorization": f"Bearer {access_token}",
                "x-kiwify-account-id": account_id.strip(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            body = {
                "name": "ShortsFlow SaaS",
                "url": webhook_url,
                "products": products.strip() or "all",
                "triggers": DEFAULT_TRIGGERS,
                "token": webhook_token,
            }

            existing_id = ""
            listing = client.get(WEBHOOKS_URL, headers=headers)
            if listing.is_success:
                listing_payload = listing.json()
                rows = listing_payload.get("data", []) if isinstance(listing_payload, dict) else []
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        if str(row.get("url") or "").strip() == webhook_url:
                            existing_id = str(row.get("id") or "").strip()
                            break

            if existing_id:
                result = client.put(f"{WEBHOOKS_URL}/{existing_id}", headers=headers, json=body)
                action = "updated"
            else:
                result = client.post(WEBHOOKS_URL, headers=headers, json=body)
                action = "created"

            if not result.is_success:
                raise KiwifyApiError(_safe_error(result, "A Kiwify recusou o cadastro do webhook."))

            payload = result.json() if result.content else {}
            return {
                "ok": True,
                "action": action,
                "webhook_id": str(payload.get("id") or existing_id),
                "webhook_url": webhook_url,
                "triggers": DEFAULT_TRIGGERS,
            }
    except httpx.RequestError as exc:
        raise KiwifyApiError(f"Falha de comunicação com a API da Kiwify: {exc}") from exc
