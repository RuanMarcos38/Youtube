from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Job, SourceVideo, TenantPlan, User, YouTubeConnection


# Valores e limites ficam centralizados para que frontend, checkout e backend
# usem exatamente a mesma regra. Planos legados continuam compatíveis e não são
# convertidos automaticamente, evitando alterar assinaturas existentes.
PLAN_CATALOG: dict[str, dict] = {
    "trial": {
        "code": "trial",
        "name": "Teste",
        "description": "Conheça o ShortsFlow antes de assinar.",
        "monthly_price_cents": 0,
        "yearly_price_cents": 0,
        "processing_minutes_limit": 30,
        "shorts_limit": 3,
        "channel_limit": 1,
        "user_limit": 1,
        "featured": False,
        "features": [
            "30 minutos de vídeo processado",
            "Até 3 Shorts",
            "1 canal do YouTube",
            "Cortes, transcrição e formato 9:16",
        ],
    },
    "creator": {
        "code": "creator",
        "name": "Creator",
        "description": "Para criadores que querem publicar com consistência.",
        "monthly_price_cents": 7990,
        "yearly_price_cents": 79900,
        "processing_minutes_limit": 180,
        "shorts_limit": 30,
        "channel_limit": 1,
        "user_limit": 1,
        "featured": False,
        "features": [
            "180 minutos processados por mês",
            "Até 30 Shorts por mês",
            "1 canal do YouTube",
            "Cortes automáticos com IA",
            "Transcrição, legendas e formato 9:16",
            "Títulos, descrições e publicação no YouTube",
        ],
    },
    "pro": {
        "code": "pro",
        "name": "Pro",
        "description": "Mais automação, canais e volume para operação profissional.",
        "monthly_price_cents": 14990,
        "yearly_price_cents": 149900,
        "processing_minutes_limit": 600,
        "shorts_limit": 120,
        "channel_limit": 3,
        "user_limit": 3,
        "featured": True,
        "features": [
            "600 minutos processados por mês",
            "Até 120 Shorts por mês",
            "Até 3 canais do YouTube",
            "Melhores momentos, títulos, descrições e hashtags com IA",
            "Histórico, analytics e publicação em lote",
            "Processamento prioritário",
        ],
    },
    "business": {
        "code": "business",
        "name": "Business",
        "description": "Para empresas e produtoras com equipe e vários canais.",
        "monthly_price_cents": 29990,
        "yearly_price_cents": 299900,
        "processing_minutes_limit": 1500,
        "shorts_limit": 350,
        "channel_limit": 7,
        "user_limit": 10,
        "featured": False,
        "features": [
            "1.500 minutos processados por mês",
            "Até 350 Shorts por mês",
            "Até 7 canais do YouTube",
            "Equipe com até 10 usuários",
            "Biblioteca de conteúdo, analytics e processamento em lote",
            "Suporte prioritário",
        ],
    },
    "agency": {
        "code": "agency",
        "name": "Agency",
        "description": "Operação de alto volume para agências e múltiplos clientes.",
        "monthly_price_cents": 59990,
        "yearly_price_cents": 599900,
        "processing_minutes_limit": 4000,
        "shorts_limit": 1000,
        "channel_limit": 20,
        "user_limit": 25,
        "featured": False,
        "features": [
            "4.000 minutos processados por mês",
            "Até 1.000 Shorts por mês",
            "Até 20 canais do YouTube",
            "Equipe com até 25 usuários",
            "Operação em lote, analytics e automações",
            "Estrutura preparada para múltiplos clientes",
        ],
    },
}

PAID_PLAN_CODES = ("creator", "pro", "business", "agency")


def get_plan_definition(plan_code: str) -> dict | None:
    return PLAN_CATALOG.get((plan_code or "").strip().lower())


def public_plans() -> list[dict]:
    return [dict(PLAN_CATALOG[code]) for code in ("trial", *PAID_PLAN_CODES)]


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def processing_seconds_used(db: Session, tenant_id: int) -> int:
    value = (
        db.query(func.coalesce(func.sum(SourceVideo.duration_seconds), 0))
        .join(Job, Job.source_video_id == SourceVideo.id)
        .filter(Job.tenant_id == tenant_id, Job.created_at >= _month_start())
        .scalar()
    )
    return int(value or 0)


def processing_minutes_used(db: Session, tenant_id: int) -> int:
    seconds = processing_seconds_used(db, tenant_id)
    return int(math.ceil(seconds / 60)) if seconds else 0


def shorts_used(db: Session, tenant_id: int) -> int:
    value = (
        db.query(func.coalesce(func.sum(Job.requested_clips), 0))
        .filter(Job.tenant_id == tenant_id, Job.created_at >= _month_start())
        .scalar()
    )
    return int(value or 0)


def channels_used(db: Session, tenant_id: int) -> int:
    return (
        db.query(YouTubeConnection)
        .join(User, User.id == YouTubeConnection.user_id)
        .filter(
            User.tenant_id == tenant_id,
            User.active.is_(True),
            YouTubeConnection.token_json.is_not(None),
            YouTubeConnection.token_json != "",
        )
        .count()
    )


def users_used(db: Session, tenant_id: int) -> int:
    return db.query(User).filter(User.tenant_id == tenant_id, User.active.is_(True)).count()


def quota_payload(db: Session, plan: TenantPlan) -> dict:
    definition = get_plan_definition(plan.plan_code)
    if not definition:
        # Kiwify/planos legados preservam a regra já existente. Novas cotas só
        # são impostas a planos do catálogo atual.
        return {
            "plan_name": plan.plan_code.title(),
            "billing_cycle": getattr(plan, "billing_cycle", "monthly") or "monthly",
            "processing_minutes_limit": None,
            "processing_minutes_used": 0,
            "processing_minutes_remaining": None,
            "shorts_limit": None,
            "shorts_used": 0,
            "shorts_remaining": None,
            "channel_limit": None,
            "channels_used": channels_used(db, plan.tenant_id),
            "channels_remaining": None,
            "user_limit": None,
            "users_used": users_used(db, plan.tenant_id),
            "users_remaining": None,
        }

    minutes_used = processing_minutes_used(db, plan.tenant_id)
    clips_used = shorts_used(db, plan.tenant_id)
    connected = channels_used(db, plan.tenant_id)
    seats = users_used(db, plan.tenant_id)

    def remaining(limit: int, used: int) -> int:
        return max(0, int(limit) - int(used))

    return {
        "plan_name": definition["name"],
        "billing_cycle": getattr(plan, "billing_cycle", "monthly") or "monthly",
        "processing_minutes_limit": definition["processing_minutes_limit"],
        "processing_minutes_used": minutes_used,
        "processing_minutes_remaining": remaining(definition["processing_minutes_limit"], minutes_used),
        "shorts_limit": definition["shorts_limit"],
        "shorts_used": clips_used,
        "shorts_remaining": remaining(definition["shorts_limit"], clips_used),
        "channel_limit": definition["channel_limit"],
        "channels_used": connected,
        "channels_remaining": remaining(definition["channel_limit"], connected),
        "user_limit": definition["user_limit"],
        "users_used": seats,
        "users_remaining": remaining(definition["user_limit"], seats),
    }


def can_create_job(db: Session, plan: TenantPlan, duration_seconds: int, requested_clips: int) -> tuple[bool, str]:
    definition = get_plan_definition(plan.plan_code)
    if not definition:
        return True, ""

    duration_seconds = max(0, int(duration_seconds or 0))
    requested_clips = max(1, int(requested_clips or 1))
    current_seconds = processing_seconds_used(db, plan.tenant_id)
    projected_minutes = int(math.ceil((current_seconds + duration_seconds) / 60)) if current_seconds + duration_seconds else 0
    current_shorts = shorts_used(db, plan.tenant_id)

    if projected_minutes > definition["processing_minutes_limit"]:
        return False, (
            f"Seu plano {definition['name']} permite {definition['processing_minutes_limit']} minutos processados por mês. "
            "Faça upgrade para continuar."
        )
    if current_shorts + requested_clips > definition["shorts_limit"]:
        return False, (
            f"Seu plano {definition['name']} permite até {definition['shorts_limit']} Shorts por mês. "
            "Faça upgrade para continuar."
        )
    return True, ""


def can_add_user(db: Session, plan: TenantPlan) -> tuple[bool, str]:
    definition = get_plan_definition(plan.plan_code)
    if not definition:
        return True, ""
    if users_used(db, plan.tenant_id) >= definition["user_limit"]:
        return False, f"Seu plano {definition['name']} permite até {definition['user_limit']} usuário(s). Faça upgrade para adicionar mais perfis."
    return True, ""


def can_connect_channel(db: Session, plan: TenantPlan) -> tuple[bool, str]:
    definition = get_plan_definition(plan.plan_code)
    if not definition:
        return True, ""
    if channels_used(db, plan.tenant_id) >= definition["channel_limit"]:
        return False, f"Seu plano {definition['name']} permite até {definition['channel_limit']} canal(is) do YouTube. Faça upgrade para conectar outro canal."
    return True, ""
