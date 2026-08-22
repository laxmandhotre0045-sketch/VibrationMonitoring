from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.integration import SEVERITY_ORDER


def _require_text(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("must not be blank")
    return cleaned


# ── API keys ────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(max_length=120)
    expires_at: Optional[datetime] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return _require_text(value)


class ApiKeyOut(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApiKeyCreated(ApiKeyOut):
    """Returned only by the create call — the one time the plaintext is visible."""

    key: str


# ── Webhooks ────────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    name: str = Field(max_length=120)
    url: str = Field(max_length=1000)
    min_severity: str = "warning"
    is_active: bool = True
    headers: Dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("url")
    @classmethod
    def _clean_url(cls, value: str) -> str:
        cleaned = _require_text(value)
        if not cleaned.lower().startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return cleaned

    @field_validator("min_severity")
    @classmethod
    def _clean_severity(cls, value: str) -> str:
        cleaned = (value or "").strip().lower()
        if cleaned not in SEVERITY_ORDER:
            raise ValueError(f"must be one of {', '.join(SEVERITY_ORDER)}")
        return cleaned


class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    url: Optional[str] = Field(default=None, max_length=1000)
    min_severity: Optional[str] = None
    is_active: Optional[bool] = None
    headers: Optional[Dict[str, str]] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: Optional[str]) -> Optional[str]:
        return _require_text(value) if value is not None else None

    @field_validator("url")
    @classmethod
    def _clean_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = _require_text(value)
        if not cleaned.lower().startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return cleaned

    @field_validator("min_severity")
    @classmethod
    def _clean_severity(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in SEVERITY_ORDER:
            raise ValueError(f"must be one of {', '.join(SEVERITY_ORDER)}")
        return cleaned


class WebhookOut(BaseModel):
    id: UUID
    name: str
    url: str
    min_severity: str
    is_active: bool
    headers: Dict[str, str] = {}
    last_status_code: Optional[int] = None
    last_triggered_at: Optional[datetime] = None
    consecutive_failures: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WebhookCreated(WebhookOut):
    """The signing secret is returned once, at creation, and never listed again."""

    secret: str


class WebhookDeliveryOut(BaseModel):
    id: UUID
    event: str
    status_code: Optional[int] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    succeeded: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WebhookTestResult(BaseModel):
    delivered: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class WebhookSecretOut(BaseModel):
    secret: str
