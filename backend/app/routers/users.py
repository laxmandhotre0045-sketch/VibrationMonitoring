"""Admin user management.

Guard rails enforced here rather than in CRUD, because they all depend on who is
making the call:
  * nobody can demote, deactivate or delete themselves — that is how an estate
    ends up with no administrator;
  * only a super_admin may create, modify or delete another super_admin, so an
    admin cannot escalate itself or anyone else;
  * the last active super_admin cannot be removed or downgraded.
Any change that narrows a user's access also revokes their refresh tokens, so it
takes effect immediately instead of at the end of the current token's life.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import user as crud
from app.database import get_db
from app.dependencies.auth import is_super_admin, require_admin
from app.models.user import User
from app.schemas.user import PasswordReset, RoleOut, UserCreate, UserOut, UserUpdate
from app.services.auth_service import hash_password

router = APIRouter(
    prefix="/api/v1",
    tags=["Users"],
    dependencies=[Depends(require_admin)],
)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        roles=[role.name for role in user.roles],
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def _forbid_self(actor: User, target_id: UUID, action: str) -> None:
    if actor.id == target_id:
        raise HTTPException(status_code=400, detail=f"You cannot {action} your own account")


def _require_super_admin_for(actor: User, target_role: str, action: str) -> None:
    if target_role == "super_admin" and not is_super_admin(actor):
        raise HTTPException(
            status_code=403,
            detail=f"Only a super admin can {action} a super admin account",
        )


def _protect_last_super_admin(db: Session, target: User) -> None:
    """Defence in depth: currently unreachable, and deliberately kept.

    Touching a super admin already requires the caller to be an active super
    admin, and role/deactivation changes already require target != actor, so the
    actor themselves is always a second active super admin by the time we get
    here. This stays so that loosening either of those rules cannot silently
    leave the estate with no administrator.
    """
    if target.role == "super_admin" and crud.count_active_super_admins(db, excluding=target.id) == 0:
        raise HTTPException(
            status_code=409,
            detail="This is the last active super admin. Promote another user first.",
        )


# ── Users ───────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserOut])
def list_users(
    search: Optional[str] = Query(None, description="Match against email or full name"),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    return [_user_out(u) for u in crud.list_users(db, search=search, role=role, is_active=is_active)]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(status_code=409, detail=f"A user with email '{data.email}' already exists")
    _require_super_admin_for(actor, data.role, "create")

    user = crud.create_user(
        db,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role_names=[data.role],
        must_change_password=data.must_change_password,
    )
    if not data.is_active:
        user = crud.update_user(db, user, {"is_active": False})
    return _user_out(user)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: UUID,
    data: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes = data.model_dump(exclude_unset=True)
    new_role = changes.get("role")
    deactivating = changes.get("is_active") is False

    # Editing a super admin at all, or promoting anyone to super admin, is
    # reserved to super admins.
    _require_super_admin_for(actor, user.role, "modify")
    if new_role:
        _require_super_admin_for(actor, new_role, "promote to")

    if new_role and new_role != user.role:
        _forbid_self(actor, user_id, "change the role of")
        _protect_last_super_admin(db, user)
    if deactivating:
        _forbid_self(actor, user_id, "deactivate")
        _protect_last_super_admin(db, user)

    user = crud.update_user(db, user, changes)

    # A demotion or a deactivation must not survive on an already-issued token.
    if new_role or deactivating:
        crud.revoke_all_user_refresh_tokens(db, user.id)
    return _user_out(user)


@router.post("/users/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: UUID,
    data: PasswordReset,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_super_admin_for(actor, user.role, "reset the password of")

    user = crud.set_user_password(
        db, user, hash_password(data.new_password), data.must_change_password
    )
    # Force every existing session to re-authenticate with the new credential.
    crud.revoke_all_user_refresh_tokens(db, user.id)
    return _user_out(crud.get_user_by_id(db, user.id))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _forbid_self(actor, user_id, "delete")
    _require_super_admin_for(actor, user.role, "delete")
    _protect_last_super_admin(db, user)
    crud.delete_user(db, user)


# ── Roles ───────────────────────────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db)):
    """The roles the platform actually authorises against, with usage counts."""
    counts = crud.role_user_counts(db)
    described = {role.name: role.description for role in crud.list_roles(db)}
    return [
        RoleOut(name=name, description=described.get(name), user_count=counts.get(name, 0))
        for name in crud.SUPPORTED_ROLES
    ]
