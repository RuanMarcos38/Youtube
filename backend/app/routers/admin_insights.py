from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_superadmin
from ..database import get_db
from ..models import Clip, SystemSetting, Tenant, TenantPlan, User, YouTubeConnection
from ..services.daily_admin_audit import audit_status, run_daily_audit_if_due
from ..services.plans import PAID_PLAN_CODES, get_plan_definition
from ..services.youtube_metrics import get_live_channel_metrics


router = APIRouter(tags=["admin-insights"])
PRESENCE_PREFIX = "presence.user."
ONLINE_WINDOW = timedelta(seconds=90)
ACTIVE_BILLING = {"active", "paid"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def monthly_equivalent_cents(plan: TenantPlan) -> int:
    value = int(plan.subscription_value_cents or 0)
    definition = get_plan_definition(plan.plan_code)
    if value <= 0 and definition:
        price_key = "yearly_price_cents" if (plan.billing_cycle or "monthly") == "yearly" else "monthly_price_cents"
        value = int(definition.get(price_key) or 0)
    if (plan.billing_cycle or "monthly").strip().lower() == "yearly":
        return int(round(value / 12))
    return value


def _presence_rows(db: Session) -> dict[int, datetime]:
    rows = db.query(SystemSetting).filter(SystemSetting.key.like(f"{PRESENCE_PREFIX}%")).all()
    result: dict[int, datetime] = {}
    for row in rows:
        try:
            user_id = int(row.key[len(PRESENCE_PREFIX):])
            payload = json.loads(row.value or "{}")
            seen = _parse_datetime(str(payload.get("last_seen") or "")) if isinstance(payload, dict) else None
            if seen:
                result[user_id] = seen
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def _plan_name(code: str) -> str:
    definition = get_plan_definition(code)
    return str(definition.get("name")) if definition else (code or "Sem plano").title()


@router.post("/presence/heartbeat")
def presence_heartbeat(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = f"{PRESENCE_PREFIX}{user.id}"
    now = _utcnow()
    value = json.dumps(
        {"user_id": user.id, "tenant_id": user.tenant_id, "last_seen": now.isoformat()},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    row = db.get(SystemSetting, key)
    if row:
        row.value = value
        row.secret = False
    else:
        db.add(SystemSetting(key=key, value=value, secret=False))
    db.commit()
    return {"ok": True, "last_seen": now}


@router.get("/admin/insights")
def admin_insights(_: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.role != "superadmin").order_by(User.created_at.desc()).all()
    tenants = {row.id: row for row in db.query(Tenant).all()}
    plans = db.query(TenantPlan).all()
    plan_by_tenant = {row.tenant_id: row for row in plans}
    presence = _presence_rows(db)
    online_cutoff = _utcnow() - ONLINE_WINDOW

    plan_groups: dict[str, dict] = defaultdict(lambda: {"users": 0, "tenants": set(), "mrr_cents": 0})
    online_users = []
    trial_users = 0
    for user in users:
        plan = plan_by_tenant.get(user.tenant_id)
        code = (plan.plan_code if plan else "unknown").strip().lower()
        group = plan_groups[code]
        group["users"] += 1
        group["tenants"].add(user.tenant_id)
        if code == "trial":
            trial_users += 1
        seen = presence.get(user.id)
        if seen and seen >= online_cutoff:
            online_users.append(
                {
                    "user_id": user.id,
                    "display_name": user.display_name,
                    "email": user.email,
                    "workspace": tenants.get(user.tenant_id).name if tenants.get(user.tenant_id) else "",
                    "plan_code": code,
                    "plan_name": _plan_name(code),
                    "last_seen": seen,
                }
            )

    paying_plans = [
        plan for plan in plans
        if plan.plan_code in PAID_PLAN_CODES and (plan.billing_status or "").strip().lower() in ACTIVE_BILLING
    ]
    mrr_cents = 0
    for plan in paying_plans:
        monthly = monthly_equivalent_cents(plan)
        mrr_cents += monthly
        plan_groups[plan.plan_code]["mrr_cents"] += monthly

    plan_distribution = [
        {
            "plan_code": code,
            "plan_name": _plan_name(code),
            "users": values["users"],
            "tenants": len(values["tenants"]),
            "mrr_cents": int(values["mrr_cents"]),
        }
        for code, values in plan_groups.items()
    ]
    plan_distribution.sort(key=lambda item: (item["plan_code"] == "trial", -item["mrr_cents"], item["plan_name"]))

    connections = (
        db.query(YouTubeConnection)
        .join(User, User.id == YouTubeConnection.user_id)
        .filter(User.role != "superadmin", YouTubeConnection.token_json.is_not(None), YouTubeConnection.token_json != "")
        .order_by(YouTubeConnection.updated_at.desc())
        .all()
    )
    connected_user_ids = [item.user_id for item in connections]
    published_counts = {}
    if connected_user_ids:
        published_counts = {
            int(user_id): int(count)
            for user_id, count in (
                db.query(Clip.user_id, func.count(Clip.id))
                .filter(Clip.user_id.in_(connected_user_ids), Clip.youtube_video_id.is_not(None), Clip.youtube_video_id != "")
                .group_by(Clip.user_id)
                .all()
            )
        }
    user_map = {row.id: row for row in users}
    channels = []
    for connection in connections:
        user = user_map.get(connection.user_id)
        if not user:
            continue
        plan = plan_by_tenant.get(user.tenant_id)
        channels.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "workspace": tenants.get(user.tenant_id).name if tenants.get(user.tenant_id) else "",
                "plan_code": plan.plan_code if plan else "unknown",
                "channel_id": connection.channel_id,
                "channel_title": connection.channel_title,
                "published_shorts": published_counts.get(user.id, 0),
                "updated_at": connection.updated_at,
                "official_revenue_cents": None,
                "revenue_status": "A receita oficial do canal não é exposta pela integração atual; nenhum valor estimado é inventado.",
            }
        )

    return {
        "refreshed_at": _utcnow(),
        "total_users": len(users),
        "online_users": len(online_users),
        "paying_customers": len(paying_plans),
        "trial_users": trial_users,
        "mrr_cents": int(mrr_cents),
        "arr_cents": int(mrr_cents * 12),
        "connected_channels": len(channels),
        "plan_distribution": plan_distribution,
        "online": sorted(online_users, key=lambda item: item["last_seen"], reverse=True),
        "channels": channels,
        "audit": audit_status(db),
    }


@router.get("/admin/insights/channels/{user_id}")
def admin_channel_metrics(user_id: int, _: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.role == "superadmin":
        raise HTTPException(status_code=404, detail="Canal de usuário não encontrado.")
    connection = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user.id).first()
    if not connection or not connection.token_json:
        raise HTTPException(status_code=404, detail="Este usuário não possui canal do YouTube conectado.")
    try:
        live = get_live_channel_metrics(db, user.id, max_results=8)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"Não foi possível atualizar as métricas deste canal agora: {exc}") from exc
    return {
        **live,
        "official_revenue_cents": None,
        "revenue_status": "Receita oficial indisponível pela API/autorização atual. O ShortsFlow mostra somente dados confirmados e não calcula faturamento fictício.",
    }


@router.get("/admin/insights/audit")
def admin_audit_status(_: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    return audit_status(db)


@router.post("/admin/insights/audit/run")
def admin_force_daily_audit(_: User = Depends(require_superadmin)):
    return run_daily_audit_if_due(force=True)
