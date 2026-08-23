from __future__ import annotations

import logging

import httpx

from .kiwify_api import (
    ACCOUNT_DETAILS_URL,
    DEFAULT_TRIGGERS,
    OAUTH_URL,
    WEBHOOKS_URL,
    KiwifyApiError,
    _delivery_token,
    _safe_error,
    _webhook_identity,
)

logger = logging.getLogger(__name__)


def _client() -> httpx.Client:
    # O EasyPanel atual não possui rota IPv6 funcional. Forçar IPv4 evita
    # tentativas de conexão que podem ficar presas até o timeout do proxy.
    return httpx.Client(
        timeout=httpx.Timeout(18.0, connect=8.0),
        transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=1),
        follow_redirects=True,
        trust_env=False,
    )


def _raise_stage(stage: str, response: httpx.Response, fallback: str) -> None:
    detail = _safe_error(response, fallback)
    message = f"Kiwify • {stage}: {detail} (HTTP {response.status_code})"
    logger.warning(message)
    raise KiwifyApiError(message)


def register_webhook_fast(
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
    """Conecta a Kiwify sem bloquear a resposta com varredura de produtos.

    O fluxo síncrono fica limitado ao necessário para provar que a integração
    está operacional: OAuth -> conta -> webhooks -> create/update. O mapeamento
    de produtos não é requisito para receber pagamentos e já possui fallback
    no processamento do próprio webhook (checkout_link/nome do produto).
    """
    del base_checkout_code, upgrade_checkout_code

    try:
        with _client() as client:
            oauth = client.post(
                OAUTH_URL,
                data={
                    "client_id": client_id.strip(),
                    "client_secret": client_secret.strip(),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if not oauth.is_success:
                _raise_stage("autenticação OAuth", oauth, "Client ID ou Client Secret recusado.")

            token_payload = oauth.json() if oauth.content else {}
            access_token = str(token_payload.get("access_token") or "").strip()
            if not access_token:
                raise KiwifyApiError("Kiwify • autenticação OAuth: access_token não foi retornado.")

            scope = {
                item.strip().lower()
                for item in str(token_payload.get("scope") or "").replace(",", " ").split()
                if item.strip()
            }
            if scope and "webhooks" not in scope:
                raise KiwifyApiError(
                    "Kiwify • permissões: habilite Webhooks na API Key em Apps > API e salve novamente."
                )

            headers = {
                "Authorization": f"Bearer {access_token}",
                "x-kiwify-account-id": account_id.strip(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            account = client.get(ACCOUNT_DETAILS_URL, headers=headers)
            if not account.is_success:
                _raise_stage(
                    "validação da conta",
                    account,
                    "Account ID recusado. Use exatamente o account_id exibido em Apps > API.",
                )
            account_payload = account.json() if account.content else {}
            account_name = (
                str(account_payload.get("company_name") or "").strip()
                if isinstance(account_payload, dict)
                else ""
            )

            listing = client.get(WEBHOOKS_URL, headers=headers)
            if not listing.is_success:
                _raise_stage(
                    "listagem de webhooks",
                    listing,
                    "Não foi possível listar webhooks. Confirme a permissão Webhooks da API Key.",
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
                result = client.put(f"{WEBHOOKS_URL}/{existing_id}", headers=headers, json=body)
                action = "updated"
                stage = "atualização do webhook"
            else:
                result = client.post(WEBHOOKS_URL, headers=headers, json=body)
                action = "created"
                stage = "criação do webhook"

            if not result.is_success:
                _raise_stage(stage, result, "A Kiwify recusou a configuração do webhook.")

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
    except httpx.RequestError as exc:
        raise KiwifyApiError(f"Kiwify • comunicação: falha ao alcançar a API: {exc}") from exc
