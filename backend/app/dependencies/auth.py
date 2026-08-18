from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.crud import user as user_crud
from app.database import get_db
from app.models.user import User
from app.services.auth_service import decode_access_token

WRITE_ROLES = {"super_admin", "admin"}
ADMIN_ROLES = {"super_admin", "admin"}


def _user_role(user: User) -> str:
    if getattr(user, "role", None):
        return user.role
    normalized = [role.name.lower() for role in user.roles if isinstance(role.name, str)]
    if "super_admin" in normalized:
        return "super_admin"
    if "admin" in normalized or "plant_admin" in normalized or "engineer" in normalized:
        return "admin"
    return "user"


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = user_crud.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_write_access(current_user: User = Depends(get_current_user)) -> User:
    if _user_role(current_user) not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Admin or super_admin. Same set as write access today, but kept separate so
    user administration can tighten independently of ordinary data writes."""
    if _user_role(current_user) not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


def is_super_admin(user: User) -> bool:
    return _user_role(user) == "super_admin"
