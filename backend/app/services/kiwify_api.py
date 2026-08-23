from __future__ import annotations

import hashlib
import logging
import time
from urllib.parse import urlsplit

import httpx


API_BASE = "https://public-api.kiwify.com/v1"
OAUTH_URL = f"{API_BASE}/oauth/token"
WEBHOOKS_URL = f"{API_BASE}/webhooks"
PRODUCTS_URL = f"{API_BASE}/products"
ACCOUNT_DETAILS_URL = f"{API_BASE}/account-details"
TOTAL_BUDGET_SECONDS = 15.0
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
    value = str(secret or "").strip()
    if not value:
        return "shortsflow"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _client() -> httpx.Client:
    # O EasyPanel atual não possui rota IPv6 funcional. Mantemos IPv4 e sem
    # retries automáticos para que a resposta nunca ultrapasse o proxy Next.js.
    return httpx.Client(
        timeout=httpx.Timeout(6.0, connect=4.0),
        transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=0),
        follow_redirects=True,
        trust_env=False,
    )


def _request_with_budget(
    client: httpx.Client,
    deadline: float,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise KiwifyApiError(
            "Kiwify • comunicação: a API não respondeu dentro do limite de 15 segundos."
        )
    request_timeout = max(1.0, min(6.0, remaining))
    connect_timeout = max(1.0, min(4.0, remaining))
    return client.request(
        method,
        url,
        timeout=httpx.Timeout(request_timeout, connect=connect_timeout),
        **kwargs,
    )


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
    """Valida a conta Kiwify e cria/atualiza o webhook com resposta rápida.

    O clique de conexão executa apenas OAuth -> conta -> listagem de webhooks ->
    criação/atualização. O mapeamento de produtos não bloqueia mais a resposta.
    """
    del base_checkout_code, upgrade_checkout_code
    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS

    try:
        with _client() as client:
            oauth = _request_with_budget(
                client,
                deadline,
                "POST",
                OAUTH_URL,
                data={
                    "client_id": client_id.strip(),
                    "client_secret": client_secret.strip(),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if not oauth.is_success:
                raise _upstream_error(
                    "autenticação OAuth",
                    oauth,
                    "A Kiwify recusou o Client ID/Client Secret.",
                )

            token_payload = oauth.json() if oauth.content else {}
            access_token = str(token_payload.get("access_token") or "").strip()
            if not access_token:
                raise KiwifyApiError(
                    "Kiwify • autenticação OAuth: a API não retornou access_token."
                )

            scope = {
                item.strip().lower()
                for item in str(token_payload.get("scope") or "")
                .replace(",", " ")
                .split()
                if item.strip()
            }
            if scope and "webhooks" not in scope:
                raise KiwifyApiError(
                    "Kiwify • permissões: a API Key não possui acesso a Webhooks. "
                    "Em Apps > API, habilite Webhooks e salve a chave novamente."
                )

            headers = {
                "Authorization": f"Bearer {access_token}",
                "x-kiwify-account-id": account_id.strip(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            account = _request_with_budget(
                client,
                deadline,
                "GET",
                ACCOUNT_DETAILS_URL,
                headers=headers,
            )
            if not account.is_success:
                raise _upstream_error(
                    "validação da conta",
                    account,
                    "A Kiwify recusou o Account ID. Use exatamente o account_id exibido em Apps > API.",
                )
            account_payload = account.json() if account.content else {}
            account_name = (
                str(account_payload.get("company_name") or "").strip()
                if isinstance(account_payload, dict)
                else ""
            )

            listing = _request_with_budget(
                client,
                deadline,
                "GET",
                WEBHOOKS_URL,
                headers=headers,
            )
            if not listing.is_success:
                raise _upstream_error(
                    "listagem de webhooks",
                    listing,
                    "Não foi possível consultar os webhooks. Confirme a permissão Webhooks da API Key.",
                )

            existing_id = ""
            listing_payload = listing.json() if listing.content else {}
            rows = listing_payload.get("data", []) if isinstance(listing_payload, dict) else []
            target_identity = _webhook_identity(webhook_url)
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    row_url = str(row.get("url") or "").strip()
                    row_name = str(row.get("name") or "").strip().lower()
                    if (
                        row_url == webhook_url
                        or _webhook_identity(row_url) == target_identity
                        or row_name in {"shortsflow saas", "shorts i.a", "shortsflow"}
                    ):
                        existing_id = str(row.get("id") or "").strip()
                        if existing_id:
                            break

            body = {
                "name": "ShortsFlow SaaS",
                "url": webhook_url,
                "products": products.strip() or "all",
                "triggers": DEFAULT_TRIGGERS,
                "token": _delivery_token(webhook_token),
            }

            if existing_id:
                result = _request_with_budget(
                    client,
                    deadline,
                    "PUT",
                    f"{WEBHOOKS_URL}/{existing_id}",
                    headers=headers,
                    json=body,
                )
                action = "updated"
                stage = "atualização do webhook"
            else:
                result = _request_with_budget(
                    client,
                    deadline,
                    "POST",
                    WEBHOOKS_URL,
                    headers=headers,
                    json=body,
                )
                action = "created"
                stage = "criação do webhook"

            if not result.is_success:
                raise _upstream_error(
                    stage,
                    result,
                    "A Kiwify recusou a configuração do webhook.",
                )

            payload = result.json() if result.content else {}
            webhook_id = str(payload.get("id") or existing_id).strip()
            if not webhook_id:
                raise KiwifyApiError(
                    "Kiwify • webhook: operação confirmada, mas a API não retornou o ID do webhook."
                )

            logger.info("Kiwify connected: action=%s webhook_id=%s", action, webhook_id)
            return {
                "ok": True,
                "action": action,
                "webhook_id": webhook_id,
                "webhook_url": webhook_url,
                "triggers": DEFAULT_TRIGGERS,
                "account_name": account_name,
                "base_product_id": "",
                "upgrade_product_id": "",
            }
    except KiwifyApiError:
        raise
    except httpx.TimeoutException as exc:
        raise KiwifyApiError(
            "Kiwify • comunicação: a API demorou além do limite permitido. Tente novamente em alguns segundos."
        ) from exc
    except httpx.RequestError as exc:
        raise KiwifyApiError(
            f"Kiwify • comunicação: não foi possível alcançar a API por IPv4: {exc}"
        ) from exc
