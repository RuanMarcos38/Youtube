"""ShortsFlow application package bootstrap.

Keep runtime credentials untouched while ensuring official Asaas API URLs match
new-format keys. This prevents a Sandbox key from being sent to Production (or
vice-versa), which Asaas rejects with an authentication/environment error.
Custom Asaas endpoints and legacy keys keep the explicitly configured URL.
"""

from .config import settings as _settings


_ASAAS_PRODUCTION_URL = "https://api.asaas.com/v3"
_ASAAS_SANDBOX_URL = "https://api-sandbox.asaas.com/v3"

_key = _settings.asaas_api_key.strip()
_base = _settings.asaas_base_url.rstrip("/")

if _base in {_ASAAS_PRODUCTION_URL, _ASAAS_SANDBOX_URL}:
    if _key.startswith("$aact_hmlg_"):
        _settings.asaas_base_url = _ASAAS_SANDBOX_URL
    elif _key.startswith("$aact_prod_"):
        _settings.asaas_base_url = _ASAAS_PRODUCTION_URL
