from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import PaymentEvent, Tenant, TenantPlan, User
from .plans import PAID_PLAN_CODES, get_plan_definition


ASAAS_CHECKOUT_EVENTS = ["CHECKOUT_CREATED", "CHECKOUT_CANCELED", "CHECKOUT_EXPIRED", "CHECKOUT_PAID"]
ASAAS_SUBSCRIPTION_EVENTS = ["SUBSCRIPTION_CREATED", "SUBSCRIPTION_UPDATED", "SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"]
ASAAS_PAYMENT_EVENTS = [
    "PAYMENT_CREATED",
    "PAYMENT_CONFIRMED",
    "PAYMENT_RECEIVED",
    "PAYMENT_OVERDUE",
    "PAYMENT_REFUNDED",
    "PAYMENT_CHARGEBACK_REQUESTED",
]
ASAAS_WEBHOOK_EVENTS = ASAAS_CHECKOUT_EVENTS + ASAAS_SUBSCRIPTION_EVENTS + ASAAS_PAYMENT_EVENTS


def asaas_configured() -> bool:
    return bool(settings.asaas_api_key.strip())


def webhook_configured() -> bool:
    return bool(settings.asaas_webhook_auth_token.strip())


def _api_url(path: str) -> str:
    return f"{settings.asaas_base_url.rstrip('/')}/{path.lstrip('/')}"


def _api_headers() -> dict[str, str]:
    key = settings.asaas_api_key.strip()
    if not key:
        raise RuntimeError("Asaas ainda não foi habilitado no ambiente de produção.")
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "access_token": key,
        "User-Agent": "ShortsFlow/2.6",
    }


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        errors = body.get("errors") if isinstance(body, dict) else None
        if isinstance(errors, list):
            descriptions = [str(item.get("description") or "").strip() for item in errors if isinstance(item, dict)]
            descriptions = [item for item in descriptions if item]
            if descriptions:
                return " | ".join(descriptions[:3])
    except Exception:
        pass
    return f"Asaas respondeu HTTP {response.status_code}."


def _request(method: str, path: str, *, payload: dict | None = None) -> dict:
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, _api_url(path), headers=_api_headers(), json=payload)
    except httpx.RequestError as exc:
        raise RuntimeError("Não foi possível conectar ao Asaas agora.") from exc
    if response.status_code >= 400:
        raise RuntimeError(_error_message(response))
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError("O Asaas retornou uma resposta inválida.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("O Asaas retornou uma resposta inesperada.")
    return data


def external_reference(tenant_id: int, plan_code: str, billing_cycle: str) -> str:
    return f"shortsflow:{int(tenant_id)}:{plan_code}:{billing_cycle}"


def parse_external_reference(value: str | None) -> tuple[int, str, str] | None:
    parts = str(value or "").strip().split(":")
    if len(parts) != 4 or parts[0] != "shortsflow":
        return None
    try:
        tenant_id = int(parts[1])
    except (TypeError, ValueError):
        return None
    plan_code = parts[2].strip().lower()
    billing_cycle = parts[3].strip().lower()
    if plan_code not in PAID_PLAN_CODES or billing_cycle not in {"monthly", "yearly"}:
        return None
    return tenant_id, plan_code, billing_cycle


def create_checkout(db: Session, user: User, plan_code: str, billing_cycle: str) -> dict:
    plan_code = (plan_code or "").strip().lower()
    billing_cycle = (billing_cycle or "monthly").strip().lower()
    definition = get_plan_definition(plan_code)
    if plan_code not in PAID_PLAN_CODES or not definition:
        raise ValueError("Plano inválido para contratação.")
    if billing_cycle not in {"monthly", "yearly"}:
        raise ValueError("Periodicidade inválida.")

    price_cents = int(definition[f"{billing_cycle}_price_cents"])
    if price_cents <= 0:
        raise ValueError("Este plano não possui cobrança configurada.")

    reference = external_reference(user.tenant_id, plan_code, billing_cycle)
    frontend = settings.frontend_url.rstrip("/")
    now_br = datetime.now(ZoneInfo("America/Sao_Paulo"))
    first_due = now_br.strftime("%Y-%m-%d %H:%M:%S")
    cycle = "MONTHLY" if billing_cycle == "monthly" else "YEARLY"

    payload = {
        "billingTypes": ["CREDIT_CARD"],
        "chargeTypes": ["RECURRENT"],
        "minutesToExpire": max(10, min(1440, int(settings.asaas_checkout_expiration_minutes))),
        "externalReference": reference,
        "callback": {
            "successUrl": f"{frontend}/planos?checkout=success",
            "cancelUrl": f"{frontend}/planos?checkout=cancel",
            "expiredUrl": f"{frontend}/planos?checkout=expired",
        },
        "items": [
            {
                "externalReference": plan_code,
                "name": f"ShortsFlow {definition['name']}",
                "description": f"Assinatura {billing_cycle} do ShortsFlow {definition['name']}",
                "quantity": 1,
                "value": round(price_cents / 100, 2),
            }
        ],
        "customerData": {
            "name": user.display_name,
            "email": user.email,
        },
        "subscription": {
            "cycle": cycle,
            "nextDueDate": first_due,
        },
    }

    data = _request("POST", "/checkouts", payload=payload)
    checkout_id = str(data.get("id") or "").strip()
    if not checkout_id:
        raise RuntimeError("O Asaas não retornou o identificador do checkout.")
    checkout_url = str(data.get("link") or "").strip() or f"https://asaas.com/checkoutSession/show?id={checkout_id}"

    from .billing import ensure_plan

    tenant_plan = ensure_plan(db, user.tenant_id)
    tenant_plan.asaas_checkout_id = checkout_id
    tenant_plan.billing_provider = "asaas"
    tenant_plan.billing_cycle = billing_cycle
    # A criação do checkout não ativa a assinatura. O plano atual continua
    # intacto até o evento CHECKOUT_PAID chegar pelo webhook.
    db.commit()

    return {
        "checkout_id": checkout_id,
        "checkout_url": checkout_url,
        "plan_code": plan_code,
        "billing_cycle": billing_cycle,
        "amount_cents": price_cents,
    }


def register_webhook(webhook_url: str, email: str = "") -> dict:
    token = settings.asaas_webhook_auth_token.strip()
    if len(token) < 32 or " " in token:
        raise RuntimeError("O token de autenticação do webhook Asaas precisa ter ao menos 32 caracteres e não pode conter espaços.")
    payload = {
        "name": "ShortsFlow Billing",
        "url": webhook_url,
        "email": email.strip(),
        "enabled": True,
        "interrupted": False,
        "apiVersion": 3,
        "authToken": token,
        "sendType": "SEQUENTIALLY",
        "events": ASAAS_WEBHOOK_EVENTS,
    }
    return _request("POST", "/webhooks", payload=payload)


def _resource(payload: dict, name: str) -> dict:
    value = payload.get(name) or {}
    return value if isinstance(value, dict) else {}


def _resource_id(value) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "").strip()
    return str(value or "").strip()


def _external_from_payload(payload: dict) -> str:
    for name in ("checkout", "subscription", "payment"):
        resource = _resource(payload, name)
        value = resource.get("externalReference") or resource.get("external_reference")
        if value:
            return str(value).strip()
    return ""


def _find_plan(db: Session, payload: dict) -> tuple[TenantPlan | None, str | None, str | None]:
    parsed = parse_external_reference(_external_from_payload(payload))
    if parsed:
        tenant_id, plan_code, billing_cycle = parsed
        plan = db.query(TenantPlan).filter(TenantPlan.tenant_id == tenant_id).first()
        return plan, plan_code, billing_cycle

    checkout_id = _resource_id(_resource(payload, "checkout").get("id"))
    subscription_id = _resource_id(_resource(payload, "subscription").get("id"))
    payment_subscription_id = _resource_id(_resource(payload, "payment").get("subscription"))
    query = db.query(TenantPlan)
    if checkout_id:
        plan = query.filter(TenantPlan.asaas_checkout_id == checkout_id).first()
        if plan:
            return plan, None, None
    if subscription_id:
        plan = query.filter(TenantPlan.asaas_subscription_id == subscription_id).first()
        if plan:
            return plan, None, None
    if payment_subscription_id:
        plan = query.filter(TenantPlan.asaas_subscription_id == payment_subscription_id).first()
        if plan:
            return plan, None, None
    return None, None, None


def _amount_cents(payload: dict) -> int:
    for name in ("payment", "subscription", "checkout"):
        resource = _resource(payload, name)
        value = resource.get("value")
        if value is None and name == "checkout":
            items = resource.get("items") or []
            if isinstance(items, list):
                total = 0.0
                for item in items:
                    if isinstance(item, dict):
                        total += float(item.get("value") or 0) * int(item.get("quantity") or 1)
                value = total
        if value is not None:
            try:
                return int(round(float(value) * 100))
            except (TypeError, ValueError):
                pass
    return 0


def apply_asaas_webhook(db: Session, payload: dict) -> dict:
    event_id = str(payload.get("id") or "").strip()
    event_type = str(payload.get("event") or "").strip().upper()
    if not event_id or not event_type:
        raise ValueError("Webhook Asaas sem id ou event.")

    existing = (
        db.query(PaymentEvent)
        .filter(PaymentEvent.order_id == event_id, PaymentEvent.event_type == event_type.lower())
        .first()
    )
    if existing:
        return {"ok": True, "duplicate": True, "event_id": event_id}

    plan, requested_plan_code, requested_cycle = _find_plan(db, payload)
    checkout = _resource(payload, "checkout")
    subscription = _resource(payload, "subscription")
    payment = _resource(payload, "payment")
    tenant_id = plan.tenant_id if plan else None

    if plan:
        plan.billing_provider = "asaas"
        checkout_id = _resource_id(checkout.get("id"))
        subscription_id = _resource_id(subscription.get("id")) or _resource_id(payment.get("subscription"))
        customer_id = _resource_id(checkout.get("customer")) or _resource_id(subscription.get("customer")) or _resource_id(payment.get("customer"))
        payment_id = _resource_id(payment.get("id"))
        if checkout_id:
            plan.asaas_checkout_id = checkout_id
        if subscription_id:
            plan.asaas_subscription_id = subscription_id
        if customer_id:
            plan.asaas_customer_id = customer_id
        if payment_id:
            plan.asaas_payment_id = payment_id

        if event_type == "CHECKOUT_PAID":
            if requested_plan_code:
                definition = get_plan_definition(requested_plan_code)
                plan.plan_code = requested_plan_code
                plan.billing_cycle = requested_cycle or "monthly"
                plan.monthly_job_limit = 999999
                plan.unlimited = False
                if definition:
                    plan.subscription_value_cents = int(definition[f"{plan.billing_cycle}_price_cents"])
            plan.billing_status = "active"
            plan.current_period_start = datetime.now(timezone.utc)
            tenant = db.get(Tenant, plan.tenant_id)
            if tenant:
                tenant.billing_status = "active"

        elif event_type in {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}:
            plan.billing_status = "active"
            plan.current_period_start = datetime.now(timezone.utc)
            tenant = db.get(Tenant, plan.tenant_id)
            if tenant:
                tenant.billing_status = "active"

        elif event_type == "PAYMENT_OVERDUE":
            plan.billing_status = "past_due"
            tenant = db.get(Tenant, plan.tenant_id)
            if tenant:
                tenant.billing_status = "past_due"

        elif event_type in {"PAYMENT_REFUNDED", "PAYMENT_CHARGEBACK_REQUESTED", "SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"}:
            plan.billing_status = "inactive"
            tenant = db.get(Tenant, plan.tenant_id)
            if tenant:
                tenant.billing_status = "inactive"

    user = None
    if tenant_id:
        user = db.query(User).filter(User.tenant_id == tenant_id, User.role.in_(["owner", "superadmin"])).order_by(User.id.asc()).first()

    event = PaymentEvent(
        tenant_id=tenant_id,
        order_id=event_id,
        order_ref=_external_from_payload(payload) or None,
        event_type=event_type.lower(),
        order_status=("paid" if event_type in {"CHECKOUT_PAID", "PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"} else event_type.lower()),
        payment_method=str(payment.get("billingType") or checkout.get("billingType") or "").lower() or None,
        customer_name=user.display_name if user else "",
        customer_email=user.email if user else "",
        product_id=requested_plan_code or (plan.plan_code if plan else ""),
        product_name=f"ShortsFlow {(requested_plan_code or (plan.plan_code if plan else '')).title()}".strip(),
        amount_cents=_amount_cents(payload),
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(event)
    db.commit()

    return {
        "ok": True,
        "duplicate": False,
        "event_id": event_id,
        "event": event_type,
        "tenant_id": tenant_id,
        "billing_status": plan.billing_status if plan else None,
    }
