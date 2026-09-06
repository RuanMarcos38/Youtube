"""ShortsFlow application package bootstrap.

Keep runtime credentials untouched while ensuring official Asaas API URLs match
new-format keys. This prevents a Sandbox key from being sent to Production (or
vice-versa), which Asaas rejects with an authentication/environment error.
Custom Asaas endpoints and legacy keys keep the explicitly configured URL.
"""

from .config import settings as _settings


_ASAAS_PRODUCTION_URL = "https://api.asaas.com/v3"
_ASAAS_SANDBOX_URL = "https://api-sandbox.asaas.com/v3"


def align_asaas_environment(runtime_settings) -> str:
    """Align only official Asaas endpoints to a recognized modern key prefix.

    Returns a safe environment label for diagnostics. The credential value is
    never changed or logged. Legacy keys remain on the explicitly configured
    endpoint because their prefix cannot safely identify an environment.
    """
    key = str(getattr(runtime_settings, "asaas_api_key", "") or "").strip()
    base = str(getattr(runtime_settings, "asaas_base_url", "") or "").rstrip("/")
    if base not in {_ASAAS_PRODUCTION_URL, _ASAAS_SANDBOX_URL}:
        return "custom"
    if key.startswith("$aact_hmlg_"):
        runtime_settings.asaas_base_url = _ASAAS_SANDBOX_URL
        return "sandbox"
    if key.startswith("$aact_prod_"):
        runtime_settings.asaas_base_url = _ASAAS_PRODUCTION_URL
        return "production"
    return "sandbox" if base == _ASAAS_SANDBOX_URL else "production"


align_asaas_environment(_settings)
