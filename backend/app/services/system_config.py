from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from ..models import SystemSetting


PUBLIC_PREFIX = "public."
LIMIT_KEY = "billing.base_plan_job_limit"

DEFAULT_PUBLIC_CONFIG = {
    "brand_name": "ShortsFlow AI",
    "marketing_badge": "Shorts com Inteligência Artificial",
    "marketing_headline": "Transforme vídeos do YouTube em Shorts prontos para publicar.",
    "marketing_description": (
        "A IA encontra os melhores momentos do vídeo, cria cortes verticais 9:16, gera legendas, "
        "títulos, descrições, copy e tags e deixa cada Short pronto para revisão e publicação."
    ),
    "benefits": [
        "Cortes selecionados automaticamente pela IA",
        "Formato vertical 9:16 com legendas",
        "Títulos, descrições, copy e tags gerados por IA",
        "Fluxo de revisão e publicação no YouTube",
    ],
    "login_title": "Entrar no ShortsFlow",
    "login_description": "Entre para criar, revisar e gerenciar seus Shorts com Inteligência Artificial.",
    "checkout_url": settings.kiwify_checkout_url,
    "upgrade_url": settings.kiwify_upgrade_url,
    "base_plan_job_limit": max(1, settings.base_plan_job_limit),
}


def _setting_map(db: Session) -> dict[str, str]:
    keys = [
        f"{PUBLIC_PREFIX}brand_name",
        f"{PUBLIC_PREFIX}marketing_badge",
        f"{PUBLIC_PREFIX}marketing_headline",
        f"{PUBLIC_PREFIX}marketing_description",
        f"{PUBLIC_PREFIX}benefit_1",
        f"{PUBLIC_PREFIX}benefit_2",
        f"{PUBLIC_PREFIX}benefit_3",
        f"{PUBLIC_PREFIX}benefit_4",
        f"{PUBLIC_PREFIX}login_title",
        f"{PUBLIC_PREFIX}login_description",
        f"{PUBLIC_PREFIX}checkout_url",
        f"{PUBLIC_PREFIX}upgrade_url",
        LIMIT_KEY,
    ]
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(keys)).all()
    return {row.key: row.value for row in rows}


def get_public_config(db: Session) -> dict:
    values = _setting_map(db)
    result = dict(DEFAULT_PUBLIC_CONFIG)

    for name in (
        "brand_name",
        "marketing_badge",
        "marketing_headline",
        "marketing_description",
        "login_title",
        "login_description",
        "checkout_url",
        "upgrade_url",
    ):
        value = values.get(f"{PUBLIC_PREFIX}{name}", "").strip()
        if value:
            result[name] = value

    benefits = []
    for index in range(1, 5):
        value = values.get(f"{PUBLIC_PREFIX}benefit_{index}", "").strip()
        benefits.append(value or DEFAULT_PUBLIC_CONFIG["benefits"][index - 1])
    result["benefits"] = benefits

    try:
        result["base_plan_job_limit"] = max(1, int(values.get(LIMIT_KEY, "") or settings.base_plan_job_limit))
    except (TypeError, ValueError):
        result["base_plan_job_limit"] = max(1, settings.base_plan_job_limit)
    return result


def get_public_config_safe(db: Session) -> dict:
    try:
        return get_public_config(db)
    except Exception:
        return dict(DEFAULT_PUBLIC_CONFIG)


def get_base_plan_job_limit(db: Session) -> int:
    return int(get_public_config_safe(db)["base_plan_job_limit"])


def _upsert(db: Session, key: str, value: str) -> None:
    row = db.get(SystemSetting, key)
    if row:
        row.value = value
        row.secret = False
    else:
        db.add(SystemSetting(key=key, value=value, secret=False))


def update_public_config(db: Session, payload: dict) -> dict:
    for name in (
        "brand_name",
        "marketing_badge",
        "marketing_headline",
        "marketing_description",
        "login_title",
        "login_description",
        "checkout_url",
        "upgrade_url",
    ):
        value = str(payload.get(name) or "").strip()
        if value:
            _upsert(db, f"{PUBLIC_PREFIX}{name}", value)

    benefits = payload.get("benefits") or []
    for index in range(1, 5):
        value = str(benefits[index - 1] if index - 1 < len(benefits) else "").strip()
        if value:
            _upsert(db, f"{PUBLIC_PREFIX}benefit_{index}", value)

    limit = max(1, int(payload.get("base_plan_job_limit") or settings.base_plan_job_limit))
    _upsert(db, LIMIT_KEY, str(limit))
    db.commit()
    return get_public_config(db)
