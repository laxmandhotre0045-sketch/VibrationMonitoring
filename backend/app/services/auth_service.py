import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import user as user_crud
from app.models.user import RefreshToken, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TOKEN_TYPE_ACCESS = "access"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: UUID, roles: list[str] | None = None) -> tuple[str, int]:
    expires_minutes = settings.jwt_access_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": TOKEN_TYPE_ACCESS,
        "roles": roles or [],
    }
    token = jwt.encode(payload, settings.effective_jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.effective_jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise JWTError("Invalid token type")
    return payload


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(db: Session, user_id: UUID) -> str:
    plain_token = secrets.token_urlsafe(48)
    token_hash = _hash_refresh_token(plain_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)
    user_crud.create_refresh_token_record(db, user_id, token_hash, expires_at)
    return plain_token


def validate_refresh_token(db: Session, plain_token: str) -> RefreshToken:
    token_hash = _hash_refresh_token(plain_token)
    record = user_crud.get_refresh_token_by_hash(db, token_hash)
    if not record:
        raise ValueError("Invalid refresh token")
    if record.revoked_at is not None:
        raise ValueError("Refresh token revoked")
    now = datetime.now(timezone.utc)
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise ValueError("Refresh token expired")
    if not record.user.is_active:
        raise ValueError("User inactive")
    return record


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = user_crud.get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def user_to_me_dict(user: User) -> dict[str, Any]:
    if user.role:
        roles = [user.role]
    else:
        roles = [r.name for r in user.roles] or ["user"]
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "roles": roles,
        "plants": [],
        "last_login_at": user.last_login_at,
    }
