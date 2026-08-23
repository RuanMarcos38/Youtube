from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlsplit

import httpx


API_BASE = "https://public-api.kiwify.com/v1"
OAUTH_URL = f"{API_BASE}/oauth/token"
WEBHOOKS_URL = f"{API_BASE}/webhooks"
PRODUCTS_URL = f"{API_BASE}/products"
ACCOUNT_DETAILS_URL = f"{API_BASE}/account-details"
DEFAULT_TRIGGERS = [
    "compra_aprovada",
    "compra_reembolsada",
    "chargeback",
    "subscription_canceled",
    "subscription_late",
    "subscription_renewed",
]

logger = logging.getLogger(__name__)


class KiwifyApiError(RuntimeError):
    pass


def _safe_error(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("message", "error_description", "error", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:400]
    except Exception:
        pass
    text = str(response.text or "").strip()
    return text[:400] if text else fallback


def _upstream_error(stage: str, response: httpx.Response, fallback: str) -> KiwifyApiError:
    detail = _safe_error(response, fallback)
    message = f"Kiwify • {stage}: {detail} (HTTP {response.status_code})"
    logger.warning(message)
    return KiwifyApiError(message)


def _webhook_identity(url: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(str(url or "").strip())
        return (parsed.netloc.lower(), parsed.path.rstrip("/").lower())
    except Exception:
        return ("", "")


def _delivery_token(secret: str) -> str:
    """Token curto e estável para o campo `token` da Kiwify.

    O segredo interno completo continua somente na query string do endpoint do
    ShortsFlow. O token cadastrado na Kiwify não precisa expor esse segredo e
    fica no formato compacto usado pela documentação oficial.
    """
    value = str(secret or "").strip()
    if not value:
        return "shortsflow"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _client() -> httpx.Client:
    # A VPS do ShortsFlow não possui uma rota IPv6 funcional. Forçar IPv4
    # evita que uma tentativa IPv6 sem rota seja confundida com falha da API.
    transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=2)
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=12.0),
        transport=transport,
        follow_redirects=True,
        trust_env=False,
    )


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
        logger.info("Kiwify product mapping skipped: HTTP %s", listing.status_code)
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
    """Validate the Kiwify API account and create/update the ShortsFlow webhook."""
    try:
        with _client() as client:
            oauth = client.post(
                OAUTH_URL,
                data={"client_id": client_id.strip(), "client_secret": client_secret.strip()},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if not oauth.is_success:
                raise _upstream_error("autenticação OAuth", oauth, "A Kiwify recusou o Client ID/Client Secret.")
            token_payload = oauth.json()
            access_token = str(token_payload.get("access_token") or "").strip()
            if not access_token:
                raise KiwifyApiError("Kiwify • autenticação OAuth: a API não retornou access_token.")

            scope = {
                item.strip().lower()
                for item in str(token_payload.get("scope") or "").replace(",", " ").split()
                if item.strip()
            }
            if scope and "webhooks" not in scope:
                raise KiwifyApiError(
                    "Kiwify • permissões: a API Key atual não possui acesso a Webhooks. "
                    "Em Apps > API, habilite o endpoint Webhooks nesta chave e tente novamente."
                )

            headers = {
                "Authorization": f"Bearer {access_token}",
                "x-kiwify-account-id": account_id.strip(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            account = client.get(ACCOUNT_DETAILS_URL, headers=headers)
            if not account.is_success:
                raise _upstream_error(
                    "validação da conta",
                    account,
                    "A Kiwify recusou o Account ID. Copie o account_id exibido em Apps > API.",
                )
            account_payload = account.json() if account.content else {}
            account_name = str(account_payload.get("company_name") or "").strip() if isinstance(account_payload, dict) else ""

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
                "token": _delivery_token(webhook_token),
            }

            existing_id = ""
            listing = client.get(WEBHOOKS_URL, headers=headers)
            if not listing.is_success:
                raise _upstream_error(
                    "listagem de webhooks",
                    listing,
                    "Não foi possível consultar os webhooks existentes. Verifique a permissão Webhooks da API Key.",
                )
            listing_payload = listing.json()
            rows = listing_payload.get("data", []) if isinstance(listing_payload, dict) else []
            if isinstance(rows, list):
                target_identity = _webhook_identity(webhook_url)
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    row_url = str(row.get("url") or "").strip()
                    row_name = str(row.get("name") or "").strip().lower()
                    if row_url == webhook_url or _webhook_identity(row_url) == target_identity or row_name in {"shortsflow saas", "shorts i.a", "shortsflow"}:
                        existing_id = str(row.get("id") or "").strip()
                        if existing_id:
                            break

            if existing_id:
                result = client.put(f"{WEBHOOKS_URL}/{existing_id}", headers=headers, json=body)
                action = "updated"
                stage = "atualização do webhook"
            else:
                result = client.post(WEBHOOKS_URL, headers=headers, json=body)
                action = "created"
                stage = "criação do webhook"

            if not result.is_success:
                raise _upstream_error(stage, result, "A Kiwify recusou o cadastro do webhook.")

            payload = result.json() if result.content else {}
            webhook_id = str(payload.get("id") or existing_id).strip()
            if not webhook_id:
                raise KiwifyApiError("Kiwify • webhook: a API confirmou a operação, mas não retornou o ID do webhook.")

            return {
                "ok": True,
                "action": action,
                "webhook_id": webhook_id,
                "webhook_url": webhook_url,
                "triggers": DEFAULT_TRIGGERS,
                "account_name": account_name,
                **product_map,
            }
    except KiwifyApiError:
        raise
    except httpx.RequestError as exc:
        message = f"Kiwify • comunicação: não foi possível alcançar a API por IPv4: {exc}"
        logger.warning(message)
        raise KiwifyApiError(message) from exc
