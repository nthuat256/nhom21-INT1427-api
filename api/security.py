from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from api.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, token_type: str = "access", expires: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    lifetime = expires or (
        timedelta(days=settings.refresh_token_days)
        if token_type == "refresh"
        else timedelta(minutes=settings.access_token_minutes)
    )
    return jwt.encode(
        {"sub": subject, "type": token_type, "iat": now, "exp": now + lifetime},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
