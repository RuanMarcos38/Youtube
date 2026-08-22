from __future__ import annotations

import httpx


API_BASE = "https://public-api.kiwify.com/v1"
OAUTH_URL = f"{API_BASE}/oauth/token"
WEBHOOKS_URL = f"{API_BASE}/webhooks"
PRODUCTS_URL = f"{API_BASE}/products"
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


def _resolve_checkout_products(
    client: httpx.Client,
    headers: dict,
    *,
    base_checkout_code: str,
    upgrade_checkout_code: str,
) -> dict[str, str]:
    """Best-effort mapping from Kiwify checkout-link IDs to product IDs."""
    wanted = {base_checkout_code.strip(), upgrade_checkout_code.strip()} - {""}
    found = {"base_product_id": "", "upgrade_product_id": ""}
    if not wanted:
        return found

    listing = client.get(PRODUCTS_URL, headers=headers, params={"page_size": "100", "page_number": "1"})
    if not listing.is_success:
        return found
    payload = listing.json()
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return found

    for row in rows:
        if not isinstance(row, dict):
            continue
        product_id = str(row.get("id") or "").strip()
        if not product_id:
            continue
        detail = client.get(f"{PRODUCTS_URL}/{product_id}", headers=headers)
        if not detail.is_success:
            continue
        data = detail.json()
        links = data.get("links", []) if isinstance(data, dict) else []
        if not isinstance(links, list):
            continue
        link_ids = {
            str(item.get("id") or "").strip()
            for item in links
            if isinstance(item, dict) and item.get("id")
        }
        if base_checkout_code and base_checkout_code in link_ids:
            found["base_product_id"] = product_id
        if upgrade_checkout_code and upgrade_checkout_code in link_ids:
            found["upgrade_product_id"] = product_id
        if all(found.values()):
            break
    return found


def register_webhook(
    *,
    client_id: str,
    client_secret: str,
    account_id: str,
    webhook_url: str,
    webhook_token: str,
    products: str = "all",
    base_checkout_code: str = "",
    upgrade_checkout_code: str = "",
) -> dict:
    """Create/update the ShortsFlow webhook without persisting Kiwify API credentials."""
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
            product_map = _resolve_checkout_products(
                client,
                headers,
                base_checkout_code=base_checkout_code,
                upgrade_checkout_code=upgrade_checkout_code,
            )
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
                **product_map,
            }
    except httpx.RequestError as exc:
        raise KiwifyApiError(f"Falha de comunicação com a API da Kiwify: {exc}") from exc
