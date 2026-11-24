from fastapi import APIRouter, Depends, Form, HTTPException, status
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user
from api.models import Role, User
from api.security import (
    create_access_token, hash_password, verify_oidc_id_token, verify_password,
)
from api.utils.audit import record_audit
from api.validators.schemas import OIDCLoginInput, RegisterInput, TokenRead, UserRead

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=Role.BORROWER,
        student_or_staff_id=payload.student_or_staff_id,
    )
    db.add(user)
    db.flush()
    record_audit(db, user, "user.registered", "user", user.id)
    db.commit()
    db.refresh(user)
    return user


@router.post("/token", response_model=TokenRead)
def login(
    username: str = Form(description="Account email"),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == username.lower()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    record_audit(db, user, "auth.login", "user", user.id)
    db.commit()
    return TokenRead(
        access_token=create_access_token(user.id),
        refresh_token=create_access_token(user.id, token_type="refresh"),
    )


@router.post("/refresh", response_model=TokenRead)
def refresh_token(refresh_token: str = Form(), db: Session = Depends(get_db)):
    from api.security import decode_token

    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Wrong token type")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account is unavailable")
    return TokenRead(
        access_token=create_access_token(user.id),
        refresh_token=create_access_token(user.id, token_type="refresh"),
    )


@router.post("/oidc", response_model=TokenRead)
def oidc_login(payload: OIDCLoginInput, db: Session = Depends(get_db)):
    claims = verify_oidc_id_token(payload.id_token, payload.nonce)
    subject = claims["sub"]
    email = claims["email"].lower()
    user = db.scalar(select(User).where(User.oidc_subject == subject))
    if not user:
        user = db.scalar(select(User).where(User.email == email))
        if user and user.oidc_subject and user.oidc_subject != subject:
            raise HTTPException(status_code=409, detail="OIDC subject is already linked to another account")
        if not user:
            user = User(
                email=email,
                full_name=claims.get("name") or email,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                role=Role.BORROWER,
                oidc_subject=subject,
                is_active=True,
            )
            db.add(user)
        else:
            user.oidc_subject = subject
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    record_audit(db, user, "auth.oidc_login", "user", user.id)
    db.commit()
    return TokenRead(
        access_token=create_access_token(user.id),
        refresh_token=create_access_token(user.id, token_type="refresh"),
    )


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user

