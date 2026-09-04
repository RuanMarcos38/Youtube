from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import create_session, delete_session, get_current_user, hash_password, normalize_email, require_owner, verify_password
from ..config import settings
from ..database import get_db
from ..models import PaymentEvent, ProvisionedCredential, Tenant, TenantPlan, User, YouTubeConnection
from ..schemas import ActivationRequest, LoginRequest, RegisterRequest, TeamUserCreate, TeamUserOut, UserOut
from ..services.billing import ensure_plan, plan_payload
from ..services.plans import can_add_user
from ..services.system_config import get_public_config_safe

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_payload(user: User, db: Session) -> dict:
    plan = plan_payload(db, user.tenant_id)
    public_config = get_public_config_safe(db)
    return {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "active": user.active,
        "billing_status": plan["billing_status"],
        "checkout_url": public_config["checkout_url"],
        "upgrade_url": public_config["upgrade_url"],
        "plan_code": plan["plan_code"],
        "plan_name": plan["plan_name"],
        "billing_provider": plan["billing_provider"],
        "billing_cycle": plan["billing_cycle"],
        "monthly_job_limit": plan["monthly_job_limit"],
        "unlimited": plan["unlimited"],
        "jobs_used": plan["jobs_used"],
        "jobs_remaining": plan["jobs_remaining"],
        "processing_minutes_limit": plan["processing_minutes_limit"],
        "processing_minutes_used": plan["processing_minutes_used"],
        "processing_minutes_remaining": plan["processing_minutes_remaining"],
        "shorts_limit": plan["shorts_limit"],
        "shorts_used": plan["shorts_used"],
        "shorts_remaining": plan["shorts_remaining"],
        "channel_limit": plan["channel_limit"],
        "channels_used": plan["channels_used"],
        "channels_remaining": plan["channels_remaining"],
        "user_limit": plan["user_limit"],
        "users_used": plan["users_used"],
        "users_remaining": plan["users_remaining"],
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max(3600, settings.auth_session_hours * 3600),
        httponly=True,
        secure=settings.environment.strip().lower() == "production",
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email))
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Este e-mail já possui uma conta.")

    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tenant = Tenant(name=(payload.company_name or payload.name).strip(), billing_status="trial")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=password_hash,
        display_name=payload.name.strip(),
        role="owner",
        active=True,
    )
    db.add(user)
    db.flush()
    # O teste gratuito é um plano real, com limites explícitos. Isso evita
    # qualquer alteração nos usuários legados que já possuem TenantPlan.
    db.add(
        TenantPlan(
            tenant_id=tenant.id,
            plan_code="trial",
            billing_status="trial",
            billing_provider="shortsflow",
            billing_cycle="monthly",
            monthly_job_limit=999999,
            unlimited=False,
            subscription_value_cents=0,
        )
    )
    db.commit()
    db.refresh(user)
    db.refresh(tenant)
    user.tenant = tenant

    token, _ = create_session(db, user)
    _set_session_cookie(response, token)
    return _user_payload(user, db)


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email))
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos.")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Este usuário está desativado.")

    token, _ = create_session(db, user)
    _set_session_cookie(response, token)
    db.refresh(user, attribute_names=["tenant"])
    return _user_payload(user, db)


@router.post("/activate", response_model=UserOut)
def activate_paid_access(payload: ActivationRequest, response: Response, db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email))
    order_code = payload.order_code.strip()
    event = (
        db.query(PaymentEvent)
        .filter(
            PaymentEvent.customer_email == email,
            PaymentEvent.order_status == "paid",
            or_(PaymentEvent.order_id == order_code, PaymentEvent.order_ref == order_code),
        )
        .order_by(PaymentEvent.id.desc())
        .first()
    )
    if not event:
        raise HTTPException(
            status_code=404,
            detail="Pagamento aprovado não localizado. Confira o mesmo e-mail da compra e o código do pedido.",
        )

    credential = (
        db.query(ProvisionedCredential)
        .filter(
            ProvisionedCredential.order_id == event.order_id,
            ProvisionedCredential.delivered.is_(False),
        )
        .first()
    )
    if not credential:
        raise HTTPException(
            status_code=409,
            detail="Este pedido já foi ativado. Entre com sua senha existente ou solicite suporte ao administrador.",
        )

    user = db.get(User, credential.user_id)
    if not user or user.email != email:
        raise HTTPException(status_code=404, detail="Conta do comprador não localizada.")

    try:
        user.password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user.active = True

    tenant = db.get(Tenant, user.tenant_id)
    if tenant:
        tenant.billing_status = "active"
    plan = ensure_plan(db, user.tenant_id)
    plan.billing_status = "active"

    credential.delivered = True
    credential.temporary_password = ""
    db.commit()

    token, _ = create_session(db, user)
    _set_session_cookie(response, token)
    db.refresh(user, attribute_names=["tenant"])
    return _user_payload(user, db)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.auth_cookie_name)
    delete_session(db, token)
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_payload(user, db)


@router.get("/team", response_model=list[TeamUserOut])
def list_team(owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.tenant_id == owner.tenant_id).order_by(User.id.asc()).all()
    connections = {
        row.user_id: row
        for row in db.query(YouTubeConnection).filter(YouTubeConnection.user_id.in_([u.id for u in users])).all()
    } if users else {}
    return [
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "active": user.active,
            "youtube_connected": bool(connections.get(user.id) and connections[user.id].token_json),
            "youtube_channel_title": connections[user.id].channel_title if user.id in connections else None,
        }
        for user in users
    ]


@router.post("/team", response_model=TeamUserOut, status_code=status.HTTP_201_CREATED)
def create_team_user(payload: TeamUserCreate, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email))
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Este e-mail já possui uma conta.")

    if owner.role != "superadmin":
        plan = ensure_plan(db, owner.tenant_id)
        allowed, reason = can_add_user(db, plan)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = User(
        tenant_id=owner.tenant_id,
        email=email,
        password_hash=password_hash,
        display_name=payload.name.strip(),
        role=payload.role,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "active": user.active,
        "youtube_connected": False,
        "youtube_channel_title": None,
    }
