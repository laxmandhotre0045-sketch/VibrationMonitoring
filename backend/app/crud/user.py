from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.user import Role, User, UserRole, RefreshToken

SUPPORTED_ROLES = ["super_admin", "admin", "user"]
WRITE_ROLES = {"super_admin", "admin"}


def primary_role(role_names: List[str]) -> str:
    normalized = [name.lower() for name in role_names if isinstance(name, str)]
    if "super_admin" in normalized:
        return "super_admin"
    if "admin" in normalized or "plant_admin" in normalized or "engineer" in normalized:
        return "admin"
    return "user"


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.email == email.lower())
        .first()
    )


def get_user_by_id(db: Session, user_id: UUID) -> Optional[User]:
    return (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.id == user_id)
        .first()
    )


def get_role_by_name(db: Session, name: str) -> Optional[Role]:
    return db.query(Role).filter(Role.name == name).first()


def list_roles(db: Session) -> List[Role]:
    return db.query(Role).order_by(Role.name).all()


def create_user(
    db: Session,
    email: str,
    password_hash: str,
    full_name: str,
    role_names: List[str],
    must_change_password: bool = False,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=password_hash,
        full_name=full_name,
        role=primary_role(role_names),
        must_change_password=must_change_password,
    )
    db.add(user)
    db.flush()

    for role_name in role_names:
        role = get_role_by_name(db, role_name)
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return get_user_by_id(db, user.id)


def update_last_login(db: Session, user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()


def create_refresh_token_record(
    db: Session,
    user_id: UUID,
    token_hash: str,
    expires_at: datetime,
) -> RefreshToken:
    record = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_refresh_token_by_hash(db: Session, token_hash: str) -> Optional[RefreshToken]:
    return (
        db.query(RefreshToken)
        .options(joinedload(RefreshToken.user).joinedload(User.roles))
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )


def revoke_refresh_token(db: Session, token: RefreshToken) -> None:
    token.revoked_at = datetime.now(timezone.utc)
    db.commit()


def revoke_all_user_refresh_tokens(db: Session, user_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": now})
    db.commit()


def super_admin_exists(db: Session) -> bool:
    super_role = get_role_by_name(db, "super_admin")
    if not super_role:
        return False
    return (
        db.query(UserRole)
        .filter(UserRole.role_id == super_role.id)
        .first()
        is not None
    )


# ── Admin user management ───────────────────────────────────────────────────
# users.role is the column every authorisation check reads; the user_roles join
# table is the older representation and is kept in sync so both agree.

def list_users(
    db: Session,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[User]:
    query = db.query(User).options(joinedload(User.roles))
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            func.lower(User.email).like(pattern) | func.lower(User.full_name).like(pattern)
        )
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))
    return query.order_by(User.full_name.asc()).all()


def set_user_roles(db: Session, user: User, role_names: List[str]) -> None:
    """Replace the join-table rows and the denormalised role column together."""
    db.query(UserRole).filter(UserRole.user_id == user.id).delete(synchronize_session=False)
    for role_name in role_names:
        role = get_role_by_name(db, role_name)
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))
    user.role = primary_role(role_names)


def update_user(db: Session, user: User, data: dict) -> User:
    new_role = data.pop("role", None)
    for field, value in data.items():
        setattr(user, field, value)
    if new_role and new_role != user.role:
        set_user_roles(db, user, [new_role])
    db.commit()
    db.refresh(user)
    return get_user_by_id(db, user.id)


def set_user_password(db: Session, user: User, password_hash: str, must_change: bool) -> User:
    user.password_hash = password_hash
    user.must_change_password = must_change
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def count_active_super_admins(db: Session, excluding: Optional[UUID] = None) -> int:
    query = db.query(User).filter(User.role == "super_admin", User.is_active.is_(True))
    if excluding is not None:
        query = query.filter(User.id != excluding)
    return query.count()


def role_user_counts(db: Session) -> dict:
    rows = db.query(User.role, func.count(User.id)).group_by(User.role).all()
    return {role: count for role, count in rows}
