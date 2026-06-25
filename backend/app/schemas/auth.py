from datetime import datetime
from typing import List
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserMeResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    is_active: bool
    must_change_password: bool
    roles: List[str]
    plants: List[str] = Field(default_factory=list)
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}
