from datetime import datetime, timedelta, timezone
import json
from urllib.request import urlopen

import bcrypt
from jose import JWTError, jwt
from fastapi import HTTPException

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


def _oidc_jwks() -> dict:
    if not settings.oidc_jwks_url:
        raise HTTPException(status_code=503, detail="OIDC provider is not configured")
    try:
        with urlopen(settings.oidc_jwks_url, timeout=5) as response:
            return json.loads(response.read())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Unable to retrieve OIDC signing keys") from exc


def verify_oidc_id_token(token: str, nonce: str) -> dict:
    if not settings.oidc_issuer or not settings.oidc_client_id or not settings.oidc_jwks_url:
        raise HTTPException(status_code=503, detail="OIDC provider is not configured")
    try:
        header = jwt.get_unverified_header(token)
        key = next(
            item for item in _oidc_jwks()["keys"]
            if item.get("kid") == header.get("kid")
        )
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.oidc_client_id,
            issuer=settings.oidc_issuer,
        )
    except (JWTError, StopIteration, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid OIDC ID token") from exc
    if claims.get("nonce") != nonce or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="OIDC nonce or subject validation failed")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="OIDC account must have a verified email")
    return claims
