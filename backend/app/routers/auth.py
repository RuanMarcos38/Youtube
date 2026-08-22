from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..auth import create_session, delete_session, get_current_user, hash_password, normalize_email, require_owner, verify_password
from ..config import settings
from ..database import get_db
from ..models import Tenant, User, YouTubeConnection
from ..schemas import LoginRequest, RegisterRequest, TeamUserCreate, TeamUserOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "active": user.active,
        "billing_status": user.tenant.billing_status if user.tenant else "pending",
        "checkout_url": settings.kiwify_checkout_url,
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

    tenant = Tenant(name=(payload.company_name or payload.name).strip(), billing_status="pending")
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
    db.commit()
    db.refresh(user)
    db.refresh(tenant)
    user.tenant = tenant

    token, _ = create_session(db, user)
    _set_session_cookie(response, token)
    return _user_payload(user)


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
    return _user_payload(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.auth_cookie_name)
    delete_session(db, token)
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_payload(user)


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
