"""Admin-facing user management payloads.

Distinct from schemas/auth.py, which covers the self-service login flow. Nothing
here ever emits password_hash — UserOut is the only shape returned to callers.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.crud.user import SUPPORTED_ROLES

MIN_PASSWORD_LENGTH = 8


def _validate_role(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned not in SUPPORTED_ROLES:
        raise ValueError(f"must be one of {', '.join(SUPPORTED_ROLES)}")
    return cleaned


def _validate_full_name(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("must not be blank")
    return cleaned


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(max_length=150)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    role: str = "user"
    is_active: bool = True
    # A user created by an admin is given a temporary password by default, so the
    # admin never has to know the credential the user ends up with.
    must_change_password: bool = True

    @field_validator("full_name")
    @classmethod
    def _clean_full_name(cls, value: str) -> str:
        return _validate_full_name(value)

    @field_validator("role")
    @classmethod
    def _clean_role(cls, value: str) -> str:
        return _validate_role(value)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=150)
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("full_name")
    @classmethod
    def _clean_full_name(cls, value: Optional[str]) -> Optional[str]:
        return _validate_full_name(value) if value is not None else None

    @field_validator("role")
    @classmethod
    def _clean_role(cls, value: Optional[str]) -> Optional[str]:
        return _validate_role(value) if value is not None else None


class PasswordReset(BaseModel):
    """Admin-initiated reset. The user is forced to change it at next login."""

    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    must_change_password: bool = True


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: str
    roles: List[str] = []
    is_active: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleOut(BaseModel):
    name: str
    description: Optional[str] = None
    user_count: int = 0
